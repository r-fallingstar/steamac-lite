#define COBJMACROS
#include <windows.h>
#include <dshow.h>
#include <dvdmedia.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

/* qedit.h is absent from many MinGW SDKs. Keep the Sample Grabber ABI local. */
static const CLSID grabber_clsid =
    {0xc1f400a0, 0x3f08, 0x11d3, {0x9f, 0x0b, 0x00, 0x60, 0x08, 0x03, 0x9e, 0x37}};
static const CLSID null_renderer_clsid =
    {0xc1f400a4, 0x3f08, 0x11d3, {0x9f, 0x0b, 0x00, 0x60, 0x08, 0x03, 0x9e, 0x37}};
static const IID grabber_iid =
    {0x6b652fff, 0x11fe, 0x4fce, {0x92, 0xad, 0x02, 0x66, 0xb5, 0xd7, 0xc7, 0x8f}};
static const IID callback_iid =
    {0x0579154a, 0x2b53, 0x4994, {0xb0, 0xd0, 0xe7, 0x73, 0x14, 0x8e, 0xff, 0x85}};

typedef struct GrabberCallback GrabberCallback;
typedef struct GrabberCallbackVtbl {
    HRESULT (STDMETHODCALLTYPE *QueryInterface)(GrabberCallback *, REFIID, void **);
    ULONG (STDMETHODCALLTYPE *AddRef)(GrabberCallback *);
    ULONG (STDMETHODCALLTYPE *Release)(GrabberCallback *);
    HRESULT (STDMETHODCALLTYPE *SampleCB)(GrabberCallback *, double, IMediaSample *);
    HRESULT (STDMETHODCALLTYPE *BufferCB)(GrabberCallback *, double, BYTE *, LONG);
} GrabberCallbackVtbl;
struct GrabberCallback { const GrabberCallbackVtbl *lpVtbl; };

typedef struct SampleGrabber SampleGrabber;
typedef struct SampleGrabberVtbl {
    HRESULT (STDMETHODCALLTYPE *QueryInterface)(SampleGrabber *, REFIID, void **);
    ULONG (STDMETHODCALLTYPE *AddRef)(SampleGrabber *);
    ULONG (STDMETHODCALLTYPE *Release)(SampleGrabber *);
    HRESULT (STDMETHODCALLTYPE *SetOneShot)(SampleGrabber *, BOOL);
    HRESULT (STDMETHODCALLTYPE *SetMediaType)(SampleGrabber *, const AM_MEDIA_TYPE *);
    HRESULT (STDMETHODCALLTYPE *GetConnectedMediaType)(SampleGrabber *, AM_MEDIA_TYPE *);
    HRESULT (STDMETHODCALLTYPE *SetBufferSamples)(SampleGrabber *, BOOL);
    HRESULT (STDMETHODCALLTYPE *GetCurrentBuffer)(SampleGrabber *, LONG *, LONG *);
    HRESULT (STDMETHODCALLTYPE *GetCurrentSample)(SampleGrabber *, IMediaSample **);
    HRESULT (STDMETHODCALLTYPE *SetCallback)(SampleGrabber *, GrabberCallback *, LONG);
} SampleGrabberVtbl;
struct SampleGrabber { const SampleGrabberVtbl *lpVtbl; };

#define REQUIRED_FRAMES 8
#define FRAME_TIMEOUT_MS 8000

typedef struct FrameCallback {
    GrabberCallback iface;
    LONG references;
    CRITICAL_SECTION lock;
    HANDLE ready;
    ULONG callbacks, frames, nonzero_frames, errors;
    ULONGLONG bytes;
    LONG last_length, expected_length;
    HRESULT first_error;
} FrameCallback;

static void report_hr(const char *stage, HRESULT hr) {
    char message[512] = "";
    DWORD size = FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
                               NULL, (DWORD)hr, 0, message, sizeof message, NULL);
    while (size && (message[size - 1] == '\r' || message[size - 1] == '\n'))
        message[--size] = '\0';
    printf("DS_CAMERA_FAIL %s hr=0x%08lx%s%s\n", stage, (unsigned long)hr,
           size ? " message=" : "", message);
}

static ULONG STDMETHODCALLTYPE callback_addref(GrabberCallback *iface) {
    return (ULONG)InterlockedIncrement(&((FrameCallback *)iface)->references);
}

static ULONG STDMETHODCALLTYPE callback_release(GrabberCallback *iface) {
    FrameCallback *cb = (FrameCallback *)iface;
    LONG refs = InterlockedDecrement(&cb->references);
    if (!refs) {
        CloseHandle(cb->ready);
        DeleteCriticalSection(&cb->lock);
        HeapFree(GetProcessHeap(), 0, cb);
    }
    return (ULONG)refs;
}

static HRESULT STDMETHODCALLTYPE callback_query(GrabberCallback *iface, REFIID iid,
                                                 void **object) {
    if (!object) return E_POINTER;
    *object = NULL;
    if (!IsEqualIID(iid, &IID_IUnknown) && !IsEqualIID(iid, &callback_iid))
        return E_NOINTERFACE;
    *object = iface;
    callback_addref(iface);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE callback_sample(GrabberCallback *iface, double time,
                                                  IMediaSample *sample) {
    FrameCallback *cb = (FrameCallback *)iface;
    BYTE *data = NULL;
    LONG length = 0;
    BOOL nonzero = FALSE;
    HRESULT hr = E_POINTER;
    (void)time;
    if (sample) {
        length = IMediaSample_GetActualDataLength(sample);
        hr = IMediaSample_GetPointer(sample, &data);
        if (SUCCEEDED(hr) && (!data || length <= 0 || length > IMediaSample_GetSize(sample)))
            hr = E_UNEXPECTED;
        if (SUCCEEDED(hr) && cb->expected_length && length != cb->expected_length)
            hr = E_UNEXPECTED;
        if (SUCCEEDED(hr)) {
            LONG i;
            for (i = 0; i < length; ++i) {
                if (data[i]) { nonzero = TRUE; break; }
            }
        }
    }
    EnterCriticalSection(&cb->lock);
    ++cb->callbacks;
    cb->last_length = length;
    if (SUCCEEDED(hr)) {
        ++cb->frames;
        cb->bytes += (ULONGLONG)length;
        if (nonzero) ++cb->nonzero_frames;
        if (cb->frames >= REQUIRED_FRAMES) SetEvent(cb->ready);
    } else {
        if (!cb->errors) cb->first_error = hr;
        ++cb->errors;
    }
    LeaveCriticalSection(&cb->lock);
    /* Keep streaming so one bad sample cannot hide subsequent diagnostics. */
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE callback_buffer(GrabberCallback *iface, double time,
                                                  BYTE *data, LONG length) {
    (void)iface; (void)time; (void)data; (void)length;
    return E_NOTIMPL;
}

static const GrabberCallbackVtbl callback_vtbl = {
    callback_query, callback_addref, callback_release, callback_sample, callback_buffer
};

static FrameCallback *create_callback(void) {
    FrameCallback *cb = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof *cb);
    if (!cb) { report_hr("allocate-callback", E_OUTOFMEMORY); return NULL; }
    cb->iface.lpVtbl = &callback_vtbl;
    cb->references = 1;
    InitializeCriticalSection(&cb->lock);
    cb->ready = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!cb->ready) {
        report_hr("create-frame-event", HRESULT_FROM_WIN32(GetLastError()));
        DeleteCriticalSection(&cb->lock);
        HeapFree(GetProcessHeap(), 0, cb);
        return NULL;
    }
    return cb;
}

static void free_media_type(AM_MEDIA_TYPE *type) {
    if (type->pbFormat) CoTaskMemFree(type->pbFormat);
    if (type->pUnk) IUnknown_Release(type->pUnk);
    memset(type, 0, sizeof *type);
}

static void print_guid(const GUID *id) {
    printf("{%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x}",
           (unsigned long)id->Data1, id->Data2, id->Data3,
           id->Data4[0], id->Data4[1], id->Data4[2], id->Data4[3],
           id->Data4[4], id->Data4[5], id->Data4[6], id->Data4[7]);
}

static const char *subtype_name(const GUID *subtype) {
    if (!subtype) return "any";
    if (IsEqualGUID(subtype, &MEDIASUBTYPE_RGB24)) return "RGB24";
    if (IsEqualGUID(subtype, &MEDIASUBTYPE_RGB32)) return "RGB32";
    if (IsEqualGUID(subtype, &MEDIASUBTYPE_ARGB32)) return "ARGB32";
    return "other";
}

static void print_media_type(const AM_MEDIA_TYPE *type) {
    const BITMAPINFOHEADER *bitmap = NULL;
    REFERENCE_TIME interval = 0;
    if (type->pbFormat && IsEqualGUID(&type->formattype, &FORMAT_VideoInfo) &&
        type->cbFormat >= sizeof(VIDEOINFOHEADER)) {
        const VIDEOINFOHEADER *video = (const VIDEOINFOHEADER *)type->pbFormat;
        bitmap = &video->bmiHeader;
        interval = video->AvgTimePerFrame;
    } else if (type->pbFormat && IsEqualGUID(&type->formattype, &FORMAT_VideoInfo2) &&
               type->cbFormat >= sizeof(VIDEOINFOHEADER2)) {
        const VIDEOINFOHEADER2 *video = (const VIDEOINFOHEADER2 *)type->pbFormat;
        bitmap = &video->bmiHeader;
        interval = video->AvgTimePerFrame;
    }
    printf("DS_CAMERA_FORMAT subtype=");
    print_guid(&type->subtype);
    if (IsEqualGUID(&type->subtype, &MEDIASUBTYPE_RGB24)) printf(" (RGB24/BGR-bytes)");
    if (IsEqualGUID(&type->subtype, &MEDIASUBTYPE_RGB32)) printf(" (RGB32)");
    if (IsEqualGUID(&type->subtype, &MEDIASUBTYPE_ARGB32)) printf(" (ARGB32)");
    if (bitmap) {
        printf(" width=%ld height=%ld bits=%u image_bytes=%lu AvgTimePerFrame=%lld fps=%.3f",
               (long)bitmap->biWidth, (long)bitmap->biHeight, (unsigned)bitmap->biBitCount,
               (unsigned long)bitmap->biSizeImage, (long long)interval,
               interval > 0 ? 10000000.0 / (double)interval : 0.0);
    } else {
        printf(" dimensions=unknown format=");
        print_guid(&type->formattype);
    }
    printf(" sample_bytes=%lu format_bytes=%lu format_null=%u subtype_name=%s\n",
           (unsigned long)type->lSampleSize, (unsigned long)type->cbFormat,
           type->pbFormat == NULL, subtype_name(&type->subtype));
}

/* Only forced formats add size assertions; the default capture stays unchanged. */
static HRESULT forced_sample_length(const AM_MEDIA_TYPE *type, const GUID *subtype,
                                     LONG *length) {
    const BITMAPINFOHEADER *bitmap = NULL;
    ULONGLONG height, minimum, dib_bytes, expected;
    unsigned bits;
    if (!subtype) return S_OK;
    if (!IsEqualGUID(&type->majortype, &MEDIATYPE_Video) ||
        !IsEqualGUID(&type->subtype, subtype)) return VFW_E_TYPE_NOT_ACCEPTED;
    if (type->pbFormat && IsEqualGUID(&type->formattype, &FORMAT_VideoInfo) &&
        type->cbFormat >= sizeof(VIDEOINFOHEADER))
        bitmap = &((const VIDEOINFOHEADER *)type->pbFormat)->bmiHeader;
    else if (type->pbFormat && IsEqualGUID(&type->formattype, &FORMAT_VideoInfo2) &&
             type->cbFormat >= sizeof(VIDEOINFOHEADER2))
        bitmap = &((const VIDEOINFOHEADER2 *)type->pbFormat)->bmiHeader;
    bits = IsEqualGUID(subtype, &MEDIASUBTYPE_RGB24) ? 24 : 32;
    if (!bitmap || bitmap->biWidth <= 0 || !bitmap->biHeight || bitmap->biBitCount != bits)
        return E_UNEXPECTED;
    height = bitmap->biHeight < 0 ? (ULONGLONG)-(LONGLONG)bitmap->biHeight :
                                  (ULONGLONG)bitmap->biHeight;
    minimum = (ULONGLONG)bitmap->biWidth * height * (bits / 8);
    dib_bytes = (((ULONGLONG)bitmap->biWidth * bits + 31) / 32) * 4 * height;
    expected = type->lSampleSize ? type->lSampleSize :
               bitmap->biSizeImage ? bitmap->biSizeImage : dib_bytes;
    printf("DS_CAMERA_BUFFER minimum_bytes=%llu dib_bytes=%llu expected_sample_bytes=%llu "
           "length_source=%s\n", (unsigned long long)minimum, (unsigned long long)dib_bytes,
           (unsigned long long)expected, type->lSampleSize ? "lSampleSize" :
           bitmap->biSizeImage ? "biSizeImage" : "DIB-stride");
    if (expected < minimum || expected < dib_bytes || expected > 0x7fffffffULL)
        return E_UNEXPECTED;
    *length = (LONG)expected;
    return S_OK;
}

/* These records are observations, not capture failures. Append method outputs
 * even on failure so untouched sentinels and success-with-NULL are visible. */
static void diagnostic_hr(const char *method, HRESULT hr) {
    const char *status = hr == S_OK ? "S_OK" : hr == S_FALSE ? "S_FALSE" :
        hr == E_NOTIMPL ? "E_NOTIMPL" : hr == E_NOINTERFACE ? "E_NOINTERFACE" :
        FAILED(hr) ? "FAILED" : "SUCCEEDED";
    printf("DS_CAMERA_DIAG method=%s hr=0x%08lx status=%s", method, (unsigned long)hr, status);
}

static void delete_media_type(AM_MEDIA_TYPE *type) {
    if (type) { free_media_type(type); CoTaskMemFree(type); }
}

static REFERENCE_TIME *media_interval(AM_MEDIA_TYPE *type, SIZE *dimensions) {
    BITMAPINFOHEADER *bitmap;
    REFERENCE_TIME *interval;
    if (!type->pbFormat) return NULL;
    if (IsEqualGUID(&type->formattype, &FORMAT_VideoInfo) &&
        type->cbFormat >= sizeof(VIDEOINFOHEADER)) {
        VIDEOINFOHEADER *video = (VIDEOINFOHEADER *)type->pbFormat;
        bitmap = &video->bmiHeader;
        interval = &video->AvgTimePerFrame;
    } else if (IsEqualGUID(&type->formattype, &FORMAT_VideoInfo2) &&
               type->cbFormat >= sizeof(VIDEOINFOHEADER2)) {
        VIDEOINFOHEADER2 *video = (VIDEOINFOHEADER2 *)type->pbFormat;
        bitmap = &video->bmiHeader;
        interval = &video->AvgTimePerFrame;
    } else return NULL;
    dimensions->cx = bitmap->biWidth;
    /* A top-down DIB still has positive image dimensions for rate queries. */
    if (bitmap->biHeight == (LONG)(-2147483647L - 1)) return NULL;
    dimensions->cy = bitmap->biHeight < 0 ? -bitmap->biHeight : bitmap->biHeight;
    return interval;
}

static void diagnose_frame_rates(IAMVideoControl *control, IPin *pin, int index,
                                 AM_MEDIA_TYPE *type) {
    SIZE dimensions = {0, 0};
    LONGLONG *intervals = NULL, maximum = -1;
    LONG count = -1, i;
    HRESULT hr;
    if (!media_interval(type, &dimensions) || dimensions.cx <= 0 || dimensions.cy <= 0) {
        printf("DS_CAMERA_DIAG_RATE index=%d skipped=invalid-video-header-or-dimensions\n", index);
        return;
    }
    hr = IAMVideoControl_GetFrameRateList(control, pin, index, dimensions, &count, &intervals);
    diagnostic_hr("IAMVideoControl.GetFrameRateList", hr);
    printf(" index=%d width=%ld height=%ld count=%ld list_null=%u outputs_valid=%u\n",
           index, (long)dimensions.cx, (long)dimensions.cy, (long)count, intervals == NULL, hr == S_OK);
    if (hr == S_OK && intervals && count > 0) {
        for (i = 0; i < count; ++i)
            printf("DS_CAMERA_DIAG_RATE index=%d entry=%ld interval_100ns=%lld fps=%.6f\n",
                   index, (long)i, (long long)intervals[i],
                   intervals[i] > 0 ? 10000000.0 / (double)intervals[i] : 0.0);
    }
    CoTaskMemFree(intervals);
    hr = IAMVideoControl_GetMaxAvailableFrameRate(control, pin, index, dimensions, &maximum);
    diagnostic_hr("IAMVideoControl.GetMaxAvailableFrameRate", hr);
    printf(" index=%d width=%ld height=%ld interval_100ns=%lld fps=%.6f outputs_valid=%u\n",
           index, (long)dimensions.cx, (long)dimensions.cy, (long long)maximum,
           hr == S_OK && maximum > 0 ? 10000000.0 / (double)maximum : 0.0, hr == S_OK);
}

static void test_frame_rate(IAMStreamConfig *config, const AM_MEDIA_TYPE *original, unsigned fps) {
    AM_MEDIA_TYPE clone, *actual = NULL;
    SIZE dimensions = {0, 0};
    REFERENCE_TIME *interval;
    HRESULT hr;
    memset(&clone, 0, sizeof clone);
    if (!original || !original->pbFormat || !original->cbFormat) {
        puts("DS_CAMERA_DIAG_SET_FORMAT skipped=no-default-format");
        return;
    }
    clone = *original;
    clone.pbFormat = CoTaskMemAlloc(original->cbFormat);
    if (!clone.pbFormat) {
        diagnostic_hr("clone-default-format", E_OUTOFMEMORY); puts("");
        return;
    }
    memcpy(clone.pbFormat, original->pbFormat, original->cbFormat);
    if (clone.pUnk) IUnknown_AddRef(clone.pUnk);
    interval = media_interval(&clone, &dimensions);
    if (!interval) {
        puts("DS_CAMERA_DIAG_SET_FORMAT skipped=unsupported-default-format");
        free_media_type(&clone);
        return;
    }
    *interval = (10000000LL + fps / 2) / fps;
    printf("DS_CAMERA_DIAG_SET_FORMAT requested_fps=%u requested_interval_100ns=%lld base=GetFormat-clone\n",
           fps, (long long)*interval);
    print_media_type(&clone);
    hr = IAMStreamConfig_SetFormat(config, &clone);
    diagnostic_hr("IAMStreamConfig.SetFormat", hr); puts("");
    /* Read back even on failure: S_OK alone does not prove the interval stuck. */
    hr = IAMStreamConfig_GetFormat(config, &actual);
    diagnostic_hr("IAMStreamConfig.GetFormat-after-SetFormat", hr);
    printf(" media_type_null=%u\n", actual == NULL);
    if (hr == S_OK && actual) {
        print_media_type(actual);
        delete_media_type(actual);
    }
    free_media_type(&clone);
}

/* Query the source and its capture pin before a graph exists. A Unity-like
 * capability probe can fail even when Sample Grabber receives valid frames. */
static void diagnose_camera(IBaseFilter *source, ICaptureGraphBuilder2 *builder, unsigned fps) {
    IPin *pin = NULL;
    IAMVideoControl *control = NULL, *pin_control = NULL;
    IAMStreamConfig *config = NULL;
    AM_MEDIA_TYPE *original = NULL;
    BYTE *caps_buffer = NULL;
    int count = -1, size = -1, index;
    LONG flags = -1;
    HRESULT hr;
    puts("DS_CAMERA_DIAG_BEGIN phase=before-graph intervals_unit=100ns");
    hr = IBaseFilter_QueryInterface(source, &IID_IAMVideoControl, (void **)&control);
    diagnostic_hr("filter.QueryInterface(IAMVideoControl)", hr);
    printf(" interface_null=%u\n", control == NULL);
    hr = ICaptureGraphBuilder2_FindPin(builder, (IUnknown *)source, PINDIR_OUTPUT,
                                      &PIN_CATEGORY_CAPTURE, &MEDIATYPE_Video, TRUE, 0, &pin);
    diagnostic_hr("FindPin(capture-video-output)", hr);
    printf(" pin_null=%u\n", pin == NULL);
    if (hr != S_OK || !pin) goto cleanup;
    hr = IPin_QueryInterface(pin, &IID_IAMVideoControl, (void **)&pin_control);
    diagnostic_hr("capture-pin.QueryInterface(IAMVideoControl)", hr);
    printf(" interface_null=%u\n", pin_control == NULL);
    /* IAMVideoControl normally lives on the filter, not its IPin. */
    if (!control && hr == S_OK && pin_control) {
        control = pin_control;
        IAMVideoControl_AddRef(control);
        puts("DS_CAMERA_DIAG_VIDEO_CONTROL owner=capture-pin");
    } else if (control) puts("DS_CAMERA_DIAG_VIDEO_CONTROL owner=filter");
    if (control) {
        hr = IAMVideoControl_GetCaps(control, pin, &flags);
        diagnostic_hr("IAMVideoControl.GetCaps", hr);
        printf(" flags_raw=0x%08lx outputs_valid=%u\n", (unsigned long)flags, hr == S_OK);
    } else puts("DS_CAMERA_DIAG_VIDEO_CONTROL methods_skipped=interface-unavailable");
    hr = IPin_QueryInterface(pin, &IID_IAMStreamConfig, (void **)&config);
    diagnostic_hr("capture-pin.QueryInterface(IAMStreamConfig)", hr);
    printf(" interface_null=%u\n", config == NULL);
    if (hr != S_OK || !config) goto cleanup;
    hr = IAMStreamConfig_GetFormat(config, &original);
    diagnostic_hr("IAMStreamConfig.GetFormat-default", hr);
    printf(" media_type_null=%u\n", original == NULL);
    if (hr == S_OK && original) print_media_type(original);
    /* Some Wine failure paths free *ppmt without clearing it. Do not take
     * ownership of, dereference, or free an output from a failed GetFormat. */
    else original = NULL;
    hr = IAMStreamConfig_GetNumberOfCapabilities(config, &count, &size);
    diagnostic_hr("IAMStreamConfig.GetNumberOfCapabilities", hr);
    printf(" count=%d caps_bytes=%d expected_video_caps_bytes=%u outputs_valid=%u\n",
           count, size, (unsigned)sizeof(VIDEO_STREAM_CONFIG_CAPS), hr == S_OK);
    if (hr != S_OK) goto set_format;
    /* Reject corrupt allocation/count metadata, without suppressing capture. */
    if (count < 0 || count > 4096 || size <= 0 || size > 1024 * 1024) {
        puts("DS_CAMERA_DIAG_STREAM_CAPS skipped=invalid-count-or-size");
        goto set_format;
    }
    caps_buffer = CoTaskMemAlloc((SIZE_T)size);
    if (!caps_buffer) {
        diagnostic_hr("allocate-stream-caps", E_OUTOFMEMORY); puts("");
        goto set_format;
    }
    for (index = 0; index < count; ++index) {
        AM_MEDIA_TYPE *type = NULL;
        memset(caps_buffer, 0, (size_t)size);
        hr = IAMStreamConfig_GetStreamCaps(config, index, &type, caps_buffer);
        diagnostic_hr("IAMStreamConfig.GetStreamCaps", hr);
        printf(" index=%d media_type_null=%u\n", index, type == NULL);
        if (hr == S_OK) {
            if ((size_t)size >= sizeof(VIDEO_STREAM_CONFIG_CAPS)) {
                VIDEO_STREAM_CONFIG_CAPS caps;
                memcpy(&caps, caps_buffer, sizeof caps);
                printf("DS_CAMERA_DIAG_STREAM_CAPS index=%d guid=", index);
                print_guid(&caps.guid);
                printf(" MinFrameInterval=%lld MaxFrameInterval=%lld min_fps=%.6f max_fps=%.6f\n",
                       (long long)caps.MinFrameInterval, (long long)caps.MaxFrameInterval,
                       caps.MaxFrameInterval > 0 ? 10000000.0 / (double)caps.MaxFrameInterval : 0.0,
                       caps.MinFrameInterval > 0 ? 10000000.0 / (double)caps.MinFrameInterval : 0.0);
            } else printf("DS_CAMERA_DIAG_STREAM_CAPS index=%d metadata=short-buffer\n", index);
            if (type) {
                print_media_type(type);
                if (control) diagnose_frame_rates(control, pin, index, type);
            }
        }
        delete_media_type(type);
    }
set_format:
    if (fps) test_frame_rate(config, original, fps);
    else puts("DS_CAMERA_DIAG_SET_FORMAT skipped=no-fps-option");
cleanup:
    CoTaskMemFree(caps_buffer);
    delete_media_type(original);
    if (config) IAMStreamConfig_Release(config);
    if (pin_control) IAMVideoControl_Release(pin_control);
    if (control) IAMVideoControl_Release(control);
    if (pin) IPin_Release(pin);
    puts("DS_CAMERA_DIAG_END");
}

/* Each device gets a fresh graph and at most eight seconds of sample waiting. */
static int capture_frames(IBaseFilter *source, unsigned fps, const GUID *subtype, BOOL preview) {
    IGraphBuilder *graph = NULL;
    ICaptureGraphBuilder2 *builder = NULL;
    IBaseFilter *grabber_filter = NULL, *renderer = NULL;
    SampleGrabber *grabber = NULL;
    IMediaControl *control = NULL;
    IMediaEvent *events = NULL;
    FrameCallback *cb = NULL;
    AM_MEDIA_TYPE type;
    HRESULT hr;
    const char *stage = "create-graph";
    int passed = 0, run_attempted = 0;
    BOOL callback_set = FALSE;
    const GUID *category = preview ? &PIN_CATEGORY_PREVIEW : &PIN_CATEGORY_CAPTURE;
    DWORD started;
    memset(&type, 0, sizeof type);

#define CHECK_HR(label, expression) do { \
    stage = (label); hr = (expression); \
    printf("DS_CAMERA_STAGE stage=%s hr=0x%08lx requested_subtype=%s category=%s\n", \
           stage, (unsigned long)hr, subtype_name(subtype), preview ? "preview" : "capture"); \
    if (FAILED(hr)) goto failure; \
} while (0)
    CHECK_HR("create-capture-builder", CoCreateInstance(&CLSID_CaptureGraphBuilder2, NULL,
             CLSCTX_INPROC_SERVER, &IID_ICaptureGraphBuilder2, (void **)&builder));
    diagnose_camera(source, builder, fps);
    CHECK_HR("create-graph", CoCreateInstance(&CLSID_FilterGraph, NULL, CLSCTX_INPROC_SERVER,
                                               &IID_IGraphBuilder, (void **)&graph));
    CHECK_HR("set-filter-graph", ICaptureGraphBuilder2_SetFiltergraph(builder, graph));
    CHECK_HR("add-camera", IGraphBuilder_AddFilter(graph, source, L"Camera"));
    CHECK_HR("create-sample-grabber", CoCreateInstance(&grabber_clsid, NULL,
             CLSCTX_INPROC_SERVER, &IID_IBaseFilter, (void **)&grabber_filter));
    CHECK_HR("query-sample-grabber", IBaseFilter_QueryInterface(grabber_filter,
                                                               &grabber_iid, (void **)&grabber));
    CHECK_HR("add-sample-grabber", IGraphBuilder_AddFilter(graph, grabber_filter, L"Sample Grabber"));
    type.majortype = MEDIATYPE_Video;
    if (subtype) type.subtype = *subtype;
    CHECK_HR("set-video-media-type", grabber->lpVtbl->SetMediaType(grabber, &type));
    CHECK_HR("disable-one-shot", grabber->lpVtbl->SetOneShot(grabber, FALSE));
    CHECK_HR("disable-sample-copy", grabber->lpVtbl->SetBufferSamples(grabber, FALSE));
    CHECK_HR("create-null-renderer", CoCreateInstance(&null_renderer_clsid, NULL,
             CLSCTX_INPROC_SERVER, &IID_IBaseFilter, (void **)&renderer));
    CHECK_HR("add-null-renderer", IGraphBuilder_AddFilter(graph, renderer, L"Null Renderer"));
    cb = create_callback();
    if (!cb) goto cleanup;
    CHECK_HR("set-sample-callback", grabber->lpVtbl->SetCallback(grabber, &cb->iface, 0));
    callback_set = TRUE;
    CHECK_HR(preview ? "render-preview-stream" : "render-capture-stream",
             ICaptureGraphBuilder2_RenderStream(builder,
             category, &MEDIATYPE_Video, (IUnknown *)source, grabber_filter, renderer));
    memset(&type, 0, sizeof type);
    CHECK_HR("get-connected-media-type", grabber->lpVtbl->GetConnectedMediaType(grabber, &type));
    printf("DS_CAMERA_NEGOTIATED requested_subtype=%s actual_subtype=%s category=%s\n",
           subtype_name(subtype), subtype_name(&type.subtype), preview ? "preview" : "capture");
    print_media_type(&type);
    CHECK_HR("verify-forced-format", forced_sample_length(&type, subtype, &cb->expected_length));
    free_media_type(&type);
    CHECK_HR("query-media-control", IGraphBuilder_QueryInterface(graph, &IID_IMediaControl,
                                                                 (void **)&control));
    CHECK_HR("query-media-events", IGraphBuilder_QueryInterface(graph, &IID_IMediaEvent,
                                                                (void **)&events));
    started = GetTickCount();
    run_attempted = 1;
    CHECK_HR("run-graph", IMediaControl_Run(control));
    printf("DS_CAMERA_RUN hr=0x%08lx timeout_ms=%u required_frames=%u\n",
           (unsigned long)hr, FRAME_TIMEOUT_MS, REQUIRED_FRAMES);
    for (;;) {
        DWORD elapsed = GetTickCount() - started;
        DWORD wait_ms = elapsed < FRAME_TIMEOUT_MS ? FRAME_TIMEOUT_MS - elapsed : 0;
        DWORD result;
        long event;
        LONG_PTR param1, param2;
        if (wait_ms > 100) wait_ms = 100;
        result = WaitForSingleObject(cb->ready, wait_ms);
        if (result == WAIT_FAILED) {
            hr = HRESULT_FROM_WIN32(GetLastError()); stage = "wait-frames"; goto failure;
        }
        /* Also catch driver/graph errors, including an abort after the eighth sample. */
        while ((hr = IMediaEvent_GetEvent(events, &event, &param1, &param2, 0)) == S_OK) {
            HRESULT event_hr = (HRESULT)param1;
            printf("DS_CAMERA_EVENT code=0x%lx param1=0x%llx param2=0x%llx\n",
                   (unsigned long)event, (unsigned long long)param1, (unsigned long long)param2);
            CHECK_HR("free-event-params", IMediaEvent_FreeEventParams(events, event, param1, param2));
            if (event == EC_ERRORABORT || event == EC_STREAM_ERROR_STOPPED ||
                event == EC_STREAM_ERROR_STILLPLAYING) {
                hr = FAILED(event_hr) ? event_hr : E_FAIL;
                stage = "stream-error-event"; goto failure;
            }
            if (event == EC_COMPLETE || event == EC_USERABORT) {
                hr = E_ABORT; stage = "stream-ended-early"; goto failure;
            }
        }
        /* E_ABORT means that the event queue is currently empty. */
        if (FAILED(hr) && hr != E_ABORT) { stage = "read-graph-event"; goto failure; }
        if (result == WAIT_OBJECT_0) { passed = 1; break; }
        if (GetTickCount() - started >= FRAME_TIMEOUT_MS) {
            hr = HRESULT_FROM_WIN32(WAIT_TIMEOUT); stage = "frame-timeout"; goto failure;
        }
    }
    goto cleanup;

failure:
    report_hr(stage, hr);
cleanup:
    if (control && run_attempted) {
        hr = IMediaControl_Stop(control);
        if (FAILED(hr)) { report_hr("stop-graph", hr); passed = 0; }
    }
    if (callback_set) {
        hr = grabber->lpVtbl->SetCallback(grabber, NULL, 0);
        if (FAILED(hr)) { report_hr("detach-callback", hr); passed = 0; }
    }
    free_media_type(&type);
    if (events) IMediaEvent_Release(events);
    if (control) IMediaControl_Release(control);
    if (builder) ICaptureGraphBuilder2_Release(builder);
    if (grabber) grabber->lpVtbl->Release(grabber);
    if (grabber_filter) IBaseFilter_Release(grabber_filter);
    if (renderer) IBaseFilter_Release(renderer);
    if (graph) IGraphBuilder_Release(graph);
    if (cb) {
        EnterCriticalSection(&cb->lock);
        printf("DS_CAMERA_FRAMES callbacks=%lu frames=%lu bytes=%llu nonzero_frames=%lu "
               "sample_errors=%lu last_sample_bytes=%ld expected_sample_bytes=%ld\n", (unsigned long)cb->callbacks,
               (unsigned long)cb->frames, (unsigned long long)cb->bytes,
               (unsigned long)cb->nonzero_frames, (unsigned long)cb->errors, (long)cb->last_length,
               (long)cb->expected_length);
        if (cb->errors) report_hr("sample-buffer", cb->first_error);
        if (cb->frames < REQUIRED_FRAMES || cb->errors) passed = 0;
        LeaveCriticalSection(&cb->lock);
        callback_release(&cb->iface);
    }
    puts(passed ? "DS_CAMERA_CAPTURE_PASS" : "DS_CAMERA_CAPTURE_FAIL");
    return passed;
#undef CHECK_HR
}

/* No game attachment, window, or saved frames: camera -> grabber -> null renderer. */
int main(int argc, char **argv) {
    ICreateDevEnum *devices = NULL;
    IEnumMoniker *items = NULL;
    IMoniker *item = NULL;
    unsigned count = 0, bound = 0, captured = 0, fps = 0;
    const GUID *subtype = NULL;
    BOOL hold_second_filter = FALSE, preview = FALSE;
    int enum_ok = 0, arg;
    HRESULT hr;
    setvbuf(stdout, NULL, _IONBF, 0);
    for (arg = 1; arg < argc; ++arg) {
        char *end = NULL;
        unsigned long value;
        if (!strcmp(argv[arg], "--help")) {
            puts("Usage: dshow-camera-test.exe [--fps=INTEGER] [--subtype=rgb24|rgb32|argb32]\n"
                 "                             [--hold-second-filter] [--preview]\n"
                 "Default: read-only capability diagnostics, then capture pin with any video subtype.\n"
                 "--fps=15: clone GetFormat, request 15 fps with SetFormat, read back, then capture.\n"
                 "--subtype: request this Sample Grabber subtype; verify negotiated type and sample sizes.\n"
                 "--hold-second-filter: bind the same moniker again and hold it during first-filter capture.\n"
                 "--preview: RenderStream with PIN_CATEGORY_PREVIEW (default: PIN_CATEGORY_CAPTURE).");
            return 0;
        }
        if (!strncmp(argv[arg], "--subtype=", 10) && !subtype) {
            const char *name = argv[arg] + 10;
            if (!strcmp(name, "rgb24")) subtype = &MEDIASUBTYPE_RGB24;
            else if (!strcmp(name, "rgb32")) subtype = &MEDIASUBTYPE_RGB32;
            else if (!strcmp(name, "argb32")) subtype = &MEDIASUBTYPE_ARGB32;
            else {
                fprintf(stderr, "Invalid subtype: %s (expected rgb24, rgb32, or argb32)\n", name);
                return 2;
            }
            continue;
        }
        if (!strcmp(argv[arg], "--hold-second-filter") && !hold_second_filter) {
            hold_second_filter = TRUE;
            continue;
        }
        if (!strcmp(argv[arg], "--preview") && !preview) {
            preview = TRUE;
            continue;
        }
        if (strncmp(argv[arg], "--fps=", 6) || fps || argv[arg][6] < '0' || argv[arg][6] > '9') {
            fprintf(stderr, "Invalid option: %s (use --help)\n", argv[arg]);
            return 2;
        }
        value = strtoul(argv[arg] + 6, &end, 10);
        if (*end || !value || value > 1000) {
            fprintf(stderr, "Invalid fps: %s (expected integer 1..1000)\n", argv[arg] + 6);
            return 2;
        }
        fps = (unsigned)value;
    }
    printf("DS_CAMERA_REQUEST subtype=%s category=%s hold_second_filter=%u fps=%u\n",
           subtype_name(subtype), preview ? "preview" : "capture", hold_second_filter, fps);
    hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (FAILED(hr)) { report_hr("initialize-com", hr); return 1; }
    hr = CoCreateInstance(&CLSID_SystemDeviceEnum, NULL, CLSCTX_INPROC_SERVER,
                         &IID_ICreateDevEnum, (void **)&devices);
    if (FAILED(hr)) { report_hr("create-device-enumerator", hr); goto cleanup; }
    hr = ICreateDevEnum_CreateClassEnumerator(devices, &CLSID_VideoInputDeviceCategory, &items, 0);
    if (hr == S_FALSE) { puts("DS_CAMERA_NO_DEVICES"); goto cleanup; }
    if (FAILED(hr)) { report_hr("enumerate-devices", hr); goto cleanup; }
    while ((hr = IEnumMoniker_Next(items, 1, &item, NULL)) == S_OK) {
        IPropertyBag *bag = NULL;
        IBaseFilter *filter = NULL, *second_filter = NULL;
        VARIANT name;
        ++count;
        printf("DS_CAMERA_DEVICE index=%u\n", count);
        VariantInit(&name);
        hr = IMoniker_BindToStorage(item, NULL, NULL, &IID_IPropertyBag, (void **)&bag);
        if (SUCCEEDED(hr)) {
            hr = IPropertyBag_Read(bag, L"FriendlyName", &name, NULL);
            if (SUCCEEDED(hr) && V_VT(&name) == VT_BSTR) {
                char text[1024];
                if (WideCharToMultiByte(CP_UTF8, 0, V_BSTR(&name), -1, text, sizeof text, NULL, NULL))
                    printf("DS_CAMERA_NAME %s\n", text);
            }
            IPropertyBag_Release(bag);
        }
        VariantClear(&name);
        hr = IMoniker_BindToObject(item, NULL, NULL, &IID_IBaseFilter, (void **)&filter);
        printf("DS_CAMERA_BIND 0x%08lx\n", (unsigned long)hr);
        if (SUCCEEDED(hr)) {
            ++bound;
            if (hold_second_filter) {
                hr = IMoniker_BindToObject(item, NULL, NULL, &IID_IBaseFilter, (void **)&second_filter);
                printf("DS_CAMERA_SECOND_BIND hr=0x%08lx filter_null=%u held_during_capture=%u "
                       "same_filter_pointer=%u\n", (unsigned long)hr, second_filter == NULL,
                       SUCCEEDED(hr) && second_filter != NULL, second_filter == filter);
                /* A failed second open is an observation; still test the first capture. */
            }
            if (capture_frames(filter, fps, subtype, preview)) ++captured;
            IBaseFilter_Release(filter);
        } else report_hr("bind-camera", hr);
        if (second_filter) IBaseFilter_Release(second_filter);
        IMoniker_Release(item);
        item = NULL;
    }
    if (FAILED(hr)) report_hr("next-device", hr);
    else enum_ok = 1;
cleanup:
    if (item) IMoniker_Release(item);
    if (items) IEnumMoniker_Release(items);
    if (devices) ICreateDevEnum_Release(devices);
    CoUninitialize();
    printf("DS_CAMERA_DEVICES %u BOUND %u CAPTURED %u\n", count, bound, captured);
    if (enum_ok && count && bound == count) puts("DS_CAMERA_ENUM_PASS");
    if (enum_ok && count && captured == count) { puts("DS_CAMERA_PASS"); return 0; }
    puts("DS_CAMERA_FAIL frame-retrieval");
    return 1;
}
