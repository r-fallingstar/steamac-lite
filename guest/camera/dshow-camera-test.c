#define COBJMACROS
#include <windows.h>
#include <dshow.h>
#include <dvdmedia.h>
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
    LONG last_length;
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
    if (bitmap) {
        printf(" width=%ld height=%ld bits=%u image_bytes=%lu fps=%.3f",
               (long)bitmap->biWidth, (long)bitmap->biHeight, (unsigned)bitmap->biBitCount,
               (unsigned long)bitmap->biSizeImage,
               interval > 0 ? 10000000.0 / (double)interval : 0.0);
    } else {
        printf(" dimensions=unknown format=");
        print_guid(&type->formattype);
        printf(" format_bytes=%lu", (unsigned long)type->cbFormat);
    }
    printf(" sample_bytes=%lu\n", (unsigned long)type->lSampleSize);
}

/* Each device gets a fresh graph and at most eight seconds of sample waiting. */
static int capture_frames(IBaseFilter *source) {
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
    DWORD started;
    memset(&type, 0, sizeof type);

#define CHECK_HR(label, expression) do { \
    stage = (label); hr = (expression); if (FAILED(hr)) goto failure; \
} while (0)
    CHECK_HR("create-graph", CoCreateInstance(&CLSID_FilterGraph, NULL, CLSCTX_INPROC_SERVER,
                                               &IID_IGraphBuilder, (void **)&graph));
    CHECK_HR("create-capture-builder", CoCreateInstance(&CLSID_CaptureGraphBuilder2, NULL,
             CLSCTX_INPROC_SERVER, &IID_ICaptureGraphBuilder2, (void **)&builder));
    CHECK_HR("set-filter-graph", ICaptureGraphBuilder2_SetFiltergraph(builder, graph));
    CHECK_HR("add-camera", IGraphBuilder_AddFilter(graph, source, L"Camera"));
    CHECK_HR("create-sample-grabber", CoCreateInstance(&grabber_clsid, NULL,
             CLSCTX_INPROC_SERVER, &IID_IBaseFilter, (void **)&grabber_filter));
    CHECK_HR("query-sample-grabber", IBaseFilter_QueryInterface(grabber_filter,
                                                               &grabber_iid, (void **)&grabber));
    CHECK_HR("add-sample-grabber", IGraphBuilder_AddFilter(graph, grabber_filter, L"Sample Grabber"));
    type.majortype = MEDIATYPE_Video;
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
    CHECK_HR("render-capture-stream", ICaptureGraphBuilder2_RenderStream(builder,
             &PIN_CATEGORY_CAPTURE, &MEDIATYPE_Video, (IUnknown *)source, grabber_filter, renderer));
    memset(&type, 0, sizeof type);
    CHECK_HR("get-connected-media-type", grabber->lpVtbl->GetConnectedMediaType(grabber, &type));
    print_media_type(&type);
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
               "sample_errors=%lu last_sample_bytes=%ld\n", (unsigned long)cb->callbacks,
               (unsigned long)cb->frames, (unsigned long long)cb->bytes,
               (unsigned long)cb->nonzero_frames, (unsigned long)cb->errors, (long)cb->last_length);
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
int main(void) {
    ICreateDevEnum *devices = NULL;
    IEnumMoniker *items = NULL;
    IMoniker *item = NULL;
    unsigned count = 0, bound = 0, captured = 0;
    int enum_ok = 0;
    HRESULT hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (FAILED(hr)) { report_hr("initialize-com", hr); return 1; }
    setvbuf(stdout, NULL, _IONBF, 0);
    hr = CoCreateInstance(&CLSID_SystemDeviceEnum, NULL, CLSCTX_INPROC_SERVER,
                         &IID_ICreateDevEnum, (void **)&devices);
    if (FAILED(hr)) { report_hr("create-device-enumerator", hr); goto cleanup; }
    hr = ICreateDevEnum_CreateClassEnumerator(devices, &CLSID_VideoInputDeviceCategory, &items, 0);
    if (hr == S_FALSE) { puts("DS_CAMERA_NO_DEVICES"); goto cleanup; }
    if (FAILED(hr)) { report_hr("enumerate-devices", hr); goto cleanup; }
    while ((hr = IEnumMoniker_Next(items, 1, &item, NULL)) == S_OK) {
        IPropertyBag *bag = NULL;
        IBaseFilter *filter = NULL;
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
            if (capture_frames(filter)) ++captured;
            IBaseFilter_Release(filter);
        } else report_hr("bind-camera", hr);
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
