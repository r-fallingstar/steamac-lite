/* SPDX-License-Identifier: Apache-2.0
 * Standalone Source Reader decode/timeline probe; no renderer, audio endpoint,
 * game process, or game files. Build/limits: docs/vrchat-video-investigation.md.
 */
#define COBJMACROS
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define __USE_MINGW_ANSI_STDIO 1
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <propvarutil.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <limits.h>
#include <errno.h>

#define MAX_STREAMS 64
#define MAX_TYPES 32
#define MAX_ATTRIBUTES 64
#define SHUTDOWN_MS 3000
#define FLUSH_MS 1000
#define VIDEO 1
#define AUDIO 2

typedef struct Options {
    const WCHAR *input;
    DWORD max_ms, max_samples, max_reads, read_ms, audio_rate, expect_video_frames;
    int async, streams, pace_audio, timeline_order;
} Options;

typedef struct Result {
    HRESULT hr;
    DWORD stream, flags;
    LONGLONG timestamp;
    IMFSample *sample;
} Result;

/* No reader/context pointer: the callback may outlive the worker's reader ref.
 * One outstanding read, one owning result slot, and no reader calls in callbacks.
 * ready is manual-reset; all result/error state and resets share the same lock.
 */
typedef struct Callback {
    IMFSourceReaderCallback iface;
    LONG refs;
    CRITICAL_SECTION lock;
    HANDLE ready, flushed;
    BOOL closing, has_result;
    HRESULT error;
    Result result;
    ULONG reads, events, flushes, discarded;
} Callback;

typedef struct Stream {
    DWORD index;
    int kind, enabled, eos;
    UINT32 rate;
    ULONGLONG samples, bytes, frames, durations, missing_duration, backwards;
    LONGLONG duration_sum, first, last, previous_end, min_time, max_end;
    BOOL have_time, have_end;
    double pcm_seconds;
} Stream;

typedef struct Run {
    Options opt;
    HANDLE stop;
    ULONGLONG start;
} Run;

static void hrlog(const char *stage, HRESULT hr) {
    printf("MF_HR stage=%s hr=0x%08lx\n", stage, (unsigned long)hr);
}

static ULONG STDMETHODCALLTYPE cb_addref(IMFSourceReaderCallback *iface) {
    return (ULONG)InterlockedIncrement(&((Callback *)iface)->refs);
}

static ULONG STDMETHODCALLTYPE cb_release(IMFSourceReaderCallback *iface) {
    Callback *cb = (Callback *)iface;
    LONG refs = InterlockedDecrement(&cb->refs);
    if (!refs) {
        if (cb->result.sample) IMFSample_Release(cb->result.sample);
        CloseHandle(cb->ready);
        CloseHandle(cb->flushed);
        DeleteCriticalSection(&cb->lock);
        HeapFree(GetProcessHeap(), 0, cb);
    }
    return (ULONG)refs;
}

static HRESULT STDMETHODCALLTYPE cb_query(IMFSourceReaderCallback *iface,
                                           REFIID iid, void **out) {
    if (!out) return E_POINTER;
    *out = NULL;
    if (!IsEqualIID(iid, &IID_IUnknown) &&
        !IsEqualIID(iid, &IID_IMFSourceReaderCallback)) return E_NOINTERFACE;
    *out = iface;
    cb_addref(iface);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE cb_read(IMFSourceReaderCallback *iface, HRESULT hr,
        DWORD stream, DWORD flags, LONGLONG timestamp, IMFSample *sample) {
    Callback *cb = (Callback *)iface;
    EnterCriticalSection(&cb->lock);
    ++cb->reads;
    if (cb->closing) ++cb->discarded;
    else if (cb->has_result) {
        cb->error = E_UNEXPECTED; /* Never overwrite/leak an unconsumed sample. */
        SetEvent(cb->ready);
    } else {
        cb->result.hr = hr;
        /* The remaining callback arguments are undefined on failure. */
        cb->result.stream = SUCCEEDED(hr) ? stream : MF_SOURCE_READER_INVALID_STREAM_INDEX;
        cb->result.flags = SUCCEEDED(hr) ? flags : 0;
        cb->result.timestamp = SUCCEEDED(hr) ? timestamp : 0;
        cb->result.sample = SUCCEEDED(hr) ? sample : NULL;
        if (cb->result.sample) IMFSample_AddRef(cb->result.sample);
        cb->has_result = TRUE;
        SetEvent(cb->ready);
    }
    LeaveCriticalSection(&cb->lock);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE cb_flush(IMFSourceReaderCallback *iface, DWORD stream) {
    Callback *cb = (Callback *)iface;
    (void)stream; /* Exactly one Flush(ALL_STREAMS) is issued during shutdown. */
    EnterCriticalSection(&cb->lock);
    ++cb->flushes;
    SetEvent(cb->flushed);
    LeaveCriticalSection(&cb->lock);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE cb_event(IMFSourceReaderCallback *iface,
                                          DWORD stream, IMFMediaEvent *event) {
    Callback *cb = (Callback *)iface;
    MediaEventType type = MEUnknown;
    HRESULT status = S_OK;
    HRESULT type_hr = event ? IMFMediaEvent_GetType(event, &type) : E_POINTER;
    HRESULT status_hr = event ? IMFMediaEvent_GetStatus(event, &status) : E_POINTER;
    printf("MF_EVENT stream=%lu type=%u type_hr=0x%08lx status_hr=0x%08lx status=0x%08lx\n",
           (unsigned long)stream, (unsigned)type, (unsigned long)type_hr,
           (unsigned long)status_hr, (unsigned long)status);
    EnterCriticalSection(&cb->lock);
    ++cb->events;
    if (!cb->closing && (FAILED(type_hr) || FAILED(status_hr) || FAILED(status))) {
        cb->error = FAILED(type_hr) ? type_hr : FAILED(status_hr) ? status_hr : status;
        SetEvent(cb->ready);
    }
    LeaveCriticalSection(&cb->lock);
    return S_OK;
}

static const IMFSourceReaderCallbackVtbl callback_vtbl = {
    cb_query, cb_addref, cb_release, cb_read, cb_flush, cb_event
};

static Callback *callback_create(void) {
    Callback *cb = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof *cb);
    if (!cb) return NULL;
    /* MinGW versions differ in const qualification of the C interface vtable. */
    cb->iface.lpVtbl = (IMFSourceReaderCallbackVtbl *)&callback_vtbl;
    cb->refs = 1;
    InitializeCriticalSection(&cb->lock);
    cb->ready = CreateEventW(NULL, TRUE, FALSE, NULL);
    cb->flushed = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!cb->ready || !cb->flushed) {
        hrlog("callback-events", HRESULT_FROM_WIN32(GetLastError()));
        cb_release(&cb->iface);
        return NULL;
    }
    return cb;
}

static void guid_text(const GUID *id, char *text) {
    snprintf(text, 40, "{%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x}",
             (unsigned long)id->Data1, (unsigned)id->Data2, (unsigned)id->Data3,
             id->Data4[0], id->Data4[1], id->Data4[2], id->Data4[3],
             id->Data4[4], id->Data4[5], id->Data4[6], id->Data4[7]);
}

static const char *key_name(const GUID *key) {
#define KEY(k) if (IsEqualGUID(key, &k)) return #k
    KEY(MF_MT_MAJOR_TYPE); KEY(MF_MT_SUBTYPE); KEY(MF_MT_FRAME_SIZE);
    KEY(MF_MT_FRAME_RATE); KEY(MF_MT_DEFAULT_STRIDE); KEY(MF_MT_INTERLACE_MODE);
    KEY(MF_MT_PIXEL_ASPECT_RATIO); KEY(MF_MT_AVG_BITRATE);
    KEY(MF_MT_AUDIO_NUM_CHANNELS); KEY(MF_MT_AUDIO_SAMPLES_PER_SECOND);
    KEY(MF_MT_AUDIO_BITS_PER_SAMPLE); KEY(MF_MT_AUDIO_BLOCK_ALIGNMENT);
    KEY(MF_MT_AUDIO_AVG_BYTES_PER_SECOND); KEY(MF_MT_AUDIO_CHANNEL_MASK);
#undef KEY
    return "other";
}

/* Dump actual attributes, including HRESULTs and GUIDs, rather than silently
 * turning absent attributes into zero. Packed size/ratio UINT64s are split too.
 */
static void dump_type(const char *stage, DWORD stream, DWORD index, IMFMediaType *type) {
    UINT32 count = 0, i;
    HRESULT hr = IMFMediaType_GetCount(type, &count);
    printf("MF_TYPE stage=%s stream=%lu index=%lu count=%u hr=0x%08lx\n",
           stage, (unsigned long)stream, (unsigned long)index, (unsigned)count,
           (unsigned long)hr);
    if (FAILED(hr)) return;
    for (i = 0; i < count && i < MAX_ATTRIBUTES; ++i) {
        GUID key = GUID_NULL;
        PROPVARIANT value;
        char id[40];
        PropVariantInit(&value);
        hr = IMFMediaType_GetItemByIndex(type, i, &key, &value);
        guid_text(&key, id);
        printf("MF_ATTR stage=%s stream=%lu key=%s name=%s hr=0x%08lx vt=%u",
               stage, (unsigned long)stream, id, key_name(&key), (unsigned long)hr,
               (unsigned)value.vt);
        if (SUCCEEDED(hr)) {
            if (value.vt == VT_UI4) printf(" value=%lu", (unsigned long)value.ulVal);
            else if (value.vt == VT_UI8)
                printf(" value=%llu hi=%u lo=%u", (unsigned long long)value.uhVal.QuadPart,
                       (unsigned)(value.uhVal.QuadPart >> 32), (unsigned)value.uhVal.QuadPart);
            else if (value.vt == VT_R8) printf(" value=%.9g", value.dblVal);
            else if (value.vt == VT_CLSID && value.puuid) {
                guid_text(value.puuid, id);
                printf(" value=%s", id);
            } else if (value.vt == (VT_VECTOR | VT_UI1))
                printf(" blob_bytes=%lu", (unsigned long)value.caub.cElems);
            else printf(" value=not-rendered");
        }
        putchar('\n');
        PropVariantClear(&value);
    }
    if (count > MAX_ATTRIBUTES) puts("MF_LIMIT attribute-dump-truncated");
}

static BOOL stopping(Run *run) {
    return WaitForSingleObject(run->stop, 0) == WAIT_OBJECT_0 ||
           GetTickCount64() - run->start >= run->opt.max_ms;
}

static const char *kind_name(int kind) { return kind == VIDEO ? "video" : "audio"; }

static HRESULT current_type(IMFSourceReader *reader, Stream *s, const char *stage) {
    IMFMediaType *type = NULL;
    GUID major = GUID_NULL, sub = GUID_NULL;
    UINT32 rate = 0, channels = 0, bits = 0, align = 0;
    HRESULT hr = IMFSourceReader_GetCurrentMediaType(reader, s->index, &type);
    hrlog(stage, hr);
    if (FAILED(hr)) return hr;
    if (!type) return E_UNEXPECTED;
    dump_type(stage, s->index, 0, type);
    hr = IMFMediaType_GetGUID(type, &MF_MT_MAJOR_TYPE, &major);
    if (SUCCEEDED(hr)) hr = IMFMediaType_GetGUID(type, &MF_MT_SUBTYPE, &sub);
    if (SUCCEEDED(hr) && s->kind == VIDEO &&
        (!IsEqualGUID(&major, &MFMediaType_Video) || !IsEqualGUID(&sub, &MFVideoFormat_RGB32)))
        hr = MF_E_INVALIDMEDIATYPE;
    if (SUCCEEDED(hr) && s->kind == AUDIO) {
        if (!IsEqualGUID(&major, &MFMediaType_Audio) || !IsEqualGUID(&sub, &MFAudioFormat_Float))
            hr = MF_E_INVALIDMEDIATYPE;
        if (SUCCEEDED(hr)) hr = IMFMediaType_GetUINT32(type, &MF_MT_AUDIO_SAMPLES_PER_SECOND, &rate);
        if (SUCCEEDED(hr)) hr = IMFMediaType_GetUINT32(type, &MF_MT_AUDIO_NUM_CHANNELS, &channels);
        if (SUCCEEDED(hr)) hr = IMFMediaType_GetUINT32(type, &MF_MT_AUDIO_BITS_PER_SAMPLE, &bits);
        if (SUCCEEDED(hr)) hr = IMFMediaType_GetUINT32(type, &MF_MT_AUDIO_BLOCK_ALIGNMENT, &align);
        if (SUCCEEDED(hr) && (rate != s->rate || channels != 2 || bits != 32 || align != 8))
            hr = MF_E_INVALIDMEDIATYPE;
    }
    IMFMediaType_Release(type);
    hrlog("verify-output-type", hr);
    return hr;
}

static HRESULT select_type(IMFSourceReader *reader, Stream *s, UINT32 rate) {
    IMFMediaType *type = NULL;
    HRESULT hr = MFCreateMediaType(&type);
    if (FAILED(hr)) return hr;
#define SET(call) do { hr = (call); if (FAILED(hr)) goto done; } while (0)
    SET(IMFMediaType_SetGUID(type, &MF_MT_MAJOR_TYPE,
                            s->kind == VIDEO ? &MFMediaType_Video : &MFMediaType_Audio));
    SET(IMFMediaType_SetGUID(type, &MF_MT_SUBTYPE,
                            s->kind == VIDEO ? &MFVideoFormat_RGB32 : &MFAudioFormat_Float));
    if (s->kind == AUDIO) {
        SET(IMFMediaType_SetUINT32(type, &MF_MT_AUDIO_SAMPLES_PER_SECOND, rate));
        SET(IMFMediaType_SetUINT32(type, &MF_MT_AUDIO_NUM_CHANNELS, 2));
        SET(IMFMediaType_SetUINT32(type, &MF_MT_AUDIO_BITS_PER_SAMPLE, 32));
        SET(IMFMediaType_SetUINT32(type, &MF_MT_AUDIO_BLOCK_ALIGNMENT, 8));
        SET(IMFMediaType_SetUINT32(type, &MF_MT_AUDIO_AVG_BYTES_PER_SECOND, rate * 8));
    }
    dump_type("requested", s->index, 0, type);
    hr = IMFSourceReader_SetCurrentMediaType(reader, s->index, NULL, type);
done:
#undef SET
    printf("MF_SELECT kind=%s stream=%lu requested_rate=%u hr=0x%08lx\n",
           kind_name(s->kind), (unsigned long)s->index, (unsigned)rate, (unsigned long)hr);
    IMFMediaType_Release(type);
    if (FAILED(hr)) return hr;
    s->rate = rate;
    hr = current_type(reader, s, "selected");
    if (SUCCEEDED(hr)) hr = IMFSourceReader_SetStreamSelection(reader, s->index, TRUE);
    hrlog("enable-stream", hr);
    if (SUCCEEDED(hr)) s->enabled = 1;
    return hr;
}

static HRESULT read_one(Run *run, IMFSourceReader *reader, Callback *cb,
                         DWORD stream, Result *result) {
    HRESULT hr;
    memset(result, 0, sizeof *result);
    result->stream = MF_SOURCE_READER_INVALID_STREAM_INDEX;
    if (!cb) {
        hr = IMFSourceReader_ReadSample(reader, stream, 0, &result->stream,
                                       &result->flags, &result->timestamp, &result->sample);
        result->hr = hr;
        return hr;
    }
    hr = IMFSourceReader_ReadSample(reader, stream, 0, NULL, NULL, NULL, NULL);
    hrlog("ReadSample-request", hr);
    if (FAILED(hr)) return hr;
    {
        HANDLE handles[2] = {run->stop, cb->ready};
        ULONGLONG elapsed = GetTickCount64() - run->start;
        DWORD remaining = elapsed >= run->opt.max_ms ? 0 : run->opt.max_ms - (DWORD)elapsed;
        DWORD wait = WaitForMultipleObjects(2, handles, FALSE,
                          remaining < run->opt.read_ms ? remaining : run->opt.read_ms);
        if (wait == WAIT_OBJECT_0) return HRESULT_FROM_WIN32(ERROR_CANCELLED);
        if (wait == WAIT_TIMEOUT) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
        if (wait != WAIT_OBJECT_0 + 1) return HRESULT_FROM_WIN32(GetLastError());
    }
    EnterCriticalSection(&cb->lock);
    hr = cb->error;
    if (cb->has_result) {
        *result = cb->result; /* Transfer the callback's owning sample ref. */
        memset(&cb->result, 0, sizeof cb->result);
        cb->has_result = FALSE;
        if (SUCCEEDED(hr)) hr = result->hr;
    } else if (SUCCEEDED(hr)) hr = E_UNEXPECTED;
    ResetEvent(cb->ready);
    LeaveCriticalSection(&cb->lock);
    return hr;
}

static HRESULT record_sample(Stream *s, const Result *r, ULONGLONG elapsed) {
    DWORD bytes = 0;
    LONGLONG duration = 0, sample_time = 0, end;
    HRESULT length_hr = IMFSample_GetTotalLength(r->sample, &bytes);
    HRESULT duration_hr = IMFSample_GetSampleDuration(r->sample, &duration);
    HRESULT time_hr = IMFSample_GetSampleTime(r->sample, &sample_time);
    printf("MF_SAMPLE stream=%lu kind=%s timestamp_100ns=%lld sample_time_100ns=%lld "
           "time_hr=0x%08lx duration_100ns=%lld duration_hr=0x%08lx bytes=%lu "
           "length_hr=0x%08lx flags=0x%08lx wall_ms=%llu",
           (unsigned long)s->index, kind_name(s->kind), (long long)r->timestamp,
           (long long)sample_time, (unsigned long)time_hr, (long long)duration,
           (unsigned long)duration_hr, (unsigned long)bytes, (unsigned long)length_hr,
           (unsigned long)r->flags, (unsigned long long)elapsed);
    if (s->have_end) printf(" gap_from_previous_end_ms=%.4f",
                           ((double)r->timestamp - (double)s->previous_end) / 10000.0);
    putchar('\n');
    /* Observations only: never resize/set lengths, coalesce buffers, or change
     * sample accounting/read scheduling because a diagnostic fails. FNV-1a-64
     * covers valid bytes, never allocation capacity or padding beyond them. */
    {
        DWORD count = 0, index;
        HRESULT count_hr = IMFSample_GetBufferCount(r->sample, &count);
        printf("MF_BUFFER_COUNT kind=%s stream=%lu count=%lu hr=0x%08lx error=%s\n",
               kind_name(s->kind), (unsigned long)s->index, (unsigned long)count,
               (unsigned long)count_hr, FAILED(count_hr) ? "GetBufferCount" :
               count > 64 ? "count-exceeds-limit-truncated" : "none");
        for (index = 0; SUCCEEDED(count_hr) && index < count && index < 64; ++index) {
            IMFMediaBuffer *buffer = NULL;
            BYTE *data = NULL;
            DWORD current = 0, maximum = 0, lock_current = 0, lock_max = 0, offset;
            ULONGLONG hash = 14695981039346656037ULL;
            BOOL hash_valid = FALSE, inconsistent = FALSE;
            HRESULT get_hr = IMFSample_GetBufferByIndex(r->sample, index, &buffer);
            HRESULT current_hr = E_PENDING, max_hr = E_PENDING;
            HRESULT lock_hr = E_PENDING, unlock_hr = E_PENDING;
            if (SUCCEEDED(get_hr) && buffer) {
                current_hr = IMFMediaBuffer_GetCurrentLength(buffer, &current);
                max_hr = IMFMediaBuffer_GetMaxLength(buffer, &maximum);
                lock_hr = IMFMediaBuffer_Lock(buffer, &data, &lock_max, &lock_current);
                if (SUCCEEDED(lock_hr)) {
                    inconsistent = lock_current > lock_max || (lock_current && !data);
                    if (SUCCEEDED(current_hr) && SUCCEEDED(max_hr)) {
                        inconsistent = inconsistent || current > maximum ||
                            current != lock_current || maximum != lock_max;
                        if (!inconsistent) {
                            for (offset = 0; offset < lock_current; ++offset) {
                                hash ^= data[offset];
                                hash *= 1099511628211ULL;
                            }
                            hash_valid = TRUE;
                        }
                    }
                    /* Unlock every successful Lock, including inconsistent or
                     * empty results; the borrowed pointer is never retained. */
                    unlock_hr = IMFMediaBuffer_Unlock(buffer);
                } else if (SUCCEEDED(current_hr) && SUCCEEDED(max_hr))
                    inconsistent = current > maximum;
            }
            printf("MF_BUFFER kind=%s stream=%lu index=%lu current=%lu max=%lu "
                   "lock_current=%lu lock_max=%lu hash_fnv1a64=%016llx hash_valid=%d "
                   "get_hr=0x%08lx current_hr=0x%08lx max_hr=0x%08lx "
                   "lock_hr=0x%08lx unlock_hr=0x%08lx inconsistent=%d error=%s\n",
                   kind_name(s->kind), (unsigned long)s->index, (unsigned long)index,
                   (unsigned long)current, (unsigned long)maximum,
                   (unsigned long)lock_current, (unsigned long)lock_max,
                   (unsigned long long)hash, hash_valid, (unsigned long)get_hr,
                   (unsigned long)current_hr, (unsigned long)max_hr,
                   (unsigned long)lock_hr, (unsigned long)unlock_hr, inconsistent,
                   FAILED(get_hr) ? "GetBufferByIndex" : !buffer ? "null-buffer" :
                   FAILED(current_hr) ? "GetCurrentLength" : FAILED(max_hr) ? "GetMaxLength" :
                   FAILED(lock_hr) ? "Lock" : FAILED(unlock_hr) ? "Unlock" :
                   inconsistent ? "inconsistent-lengths-or-null-data" : "none");
            if (buffer) IMFMediaBuffer_Release(buffer);
        }
    }
    if (FAILED(length_hr)) return length_hr;
    if (!bytes) return S_OK;
    ++s->samples;
    s->bytes += bytes;
    end = r->timestamp;
    if (SUCCEEDED(duration_hr) && duration >= 0 && end <= LLONG_MAX - duration &&
        s->duration_sum <= LLONG_MAX - duration) {
        end += duration;
        s->duration_sum += duration;
        ++s->durations;
        s->previous_end = end;
        s->have_end = TRUE;
    } else {
        ++s->missing_duration;
        s->have_end = FALSE;
    }
    if (!s->have_time) {
        s->first = s->min_time = r->timestamp;
        s->max_end = end;
        s->have_time = TRUE;
    } else if (r->timestamp < s->last) ++s->backwards;
    s->last = r->timestamp;
    if (r->timestamp < s->min_time) s->min_time = r->timestamp;
    if (end > s->max_end) s->max_end = end;
    if (s->kind == AUDIO) {
        /* Float stereo: each audio frame contains two 32-bit values. This is
         * decoded payload duration, independent of sample/request count. */
        if (bytes % 8) return MF_E_INVALIDMEDIATYPE;
        s->frames += bytes / 8;
        s->pcm_seconds += (double)(bytes / 8) / s->rate;
    }
    return S_OK;
}

static void summary(Stream *s) {
    printf("MF_SUM stream=%lu kind=%s enabled=%d eos=%d samples=%llu bytes=%llu "
           "duration_sum_100ns=%lld durations=%llu missing_duration=%llu "
           "has_time=%d first_100ns=%lld last_100ns=%lld min_100ns=%lld max_end_100ns=%lld "
           "timeline_span_seconds=%.6f backwards=%llu audio_frames=%llu pcm_seconds=%.6f\n",
           (unsigned long)s->index, kind_name(s->kind), s->enabled, s->eos,
           (unsigned long long)s->samples, (unsigned long long)s->bytes,
           (long long)s->duration_sum, (unsigned long long)s->durations,
           (unsigned long long)s->missing_duration, s->have_time,
           (long long)s->first, (long long)s->last, (long long)s->min_time,
           (long long)s->max_end, s->have_time ? ((double)s->max_end - s->min_time) / 1e7 : 0.0,
           (unsigned long long)s->backwards, (unsigned long long)s->frames, s->pcm_seconds);
}

static DWORD WINAPI worker(void *arg) {
    Run *run = arg;
    Options *opt = &run->opt;
    IMFSourceReader *reader = NULL;
    IMFMediaSource *source = NULL;
    IMFAttributes *attrs = NULL;
    Callback *cb = NULL;
    Stream streams[2] = {{0}, {0}};
    DWORD i, j, reads = 0, total = 0, next = 0;
    HRESULT hr;
    BOOL com = FALSE, mf = FALSE, failed = FALSE;
    ULONGLONG pace_start = 0;
    const char *reason = "setup-error";
    streams[0].kind = VIDEO;
    streams[1].kind = AUDIO;
    streams[0].index = streams[1].index = MF_SOURCE_READER_INVALID_STREAM_INDEX;
    hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    hrlog("CoInitializeEx-MTA", hr);
    if (FAILED(hr)) { failed = TRUE; goto cleanup; }
    com = TRUE;
    hr = MFStartup(MF_VERSION, MFSTARTUP_FULL);
    hrlog("MFStartup", hr);
    if (FAILED(hr)) { failed = TRUE; goto cleanup; }
    mf = TRUE;
    hr = MFCreateAttributes(&attrs, 3);
    hrlog("MFCreateAttributes", hr);
    if (FAILED(hr)) { failed = TRUE; goto cleanup; }
    hr = IMFAttributes_SetUINT32(attrs, &MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING, TRUE);
    hrlog("enable-basic-video-processing", hr);
    if (FAILED(hr)) { failed = TRUE; goto cleanup; }
    if (opt->async) {
        cb = callback_create();
        if (!cb) { failed = TRUE; goto cleanup; }
        hr = IMFAttributes_SetUnknown(attrs, &MF_SOURCE_READER_ASYNC_CALLBACK, (IUnknown *)&cb->iface);
        hrlog("set-async-callback", hr);
        if (FAILED(hr)) { failed = TRUE; goto cleanup; }
    }
    puts("MF_OPEN begin");
    hr = MFCreateSourceReaderFromURL(opt->input, attrs, &reader);
    hrlog("MFCreateSourceReaderFromURL", hr);
    if (FAILED(hr) || !reader) { failed = TRUE; goto cleanup; }
    hr = IMFSourceReader_GetServiceForStream(reader, MF_SOURCE_READER_MEDIASOURCE,
                &GUID_NULL, &IID_IMFMediaSource, (void **)&source);
    hrlog("get-source-for-explicit-shutdown-optional", hr);
    {
        PROPVARIANT duration;
        PropVariantInit(&duration);
        hr = IMFSourceReader_GetPresentationAttribute(reader, MF_SOURCE_READER_MEDIASOURCE,
                                                       &MF_PD_DURATION, &duration);
        printf("MF_SOURCE_DURATION hr=0x%08lx vt=%u duration_100ns=%llu\n",
               (unsigned long)hr, (unsigned)duration.vt,
               SUCCEEDED(hr) && duration.vt == VT_UI8 ? (unsigned long long)duration.uhVal.QuadPart : 0);
        PropVariantClear(&duration);
    }
    hr = IMFSourceReader_SetStreamSelection(reader, MF_SOURCE_READER_ALL_STREAMS, FALSE);
    hrlog("deselect-all", hr);
    if (FAILED(hr)) { failed = TRUE; goto cleanup; }
    for (i = 0; i < MAX_STREAMS && !stopping(run); ++i) {
        for (j = 0; j < MAX_TYPES && !stopping(run); ++j) {
            IMFMediaType *type = NULL;
            GUID major = GUID_NULL;
            hr = IMFSourceReader_GetNativeMediaType(reader, i, j, &type);
            printf("MF_NATIVE stream=%lu index=%lu hr=0x%08lx\n",
                   (unsigned long)i, (unsigned long)j, (unsigned long)hr);
            if (FAILED(hr)) {
                if (hr != MF_E_NO_MORE_TYPES && hr != MF_E_INVALIDSTREAMNUMBER) failed = TRUE;
                break;
            }
            if (!type) { failed = TRUE; hr = E_UNEXPECTED; break; }
            dump_type("native", i, j, type);
            hr = IMFMediaType_GetGUID(type, &MF_MT_MAJOR_TYPE, &major);
            hrlog("native-major-type", hr);
            if (SUCCEEDED(hr) && j == 0) {
                int slot = IsEqualGUID(&major, &MFMediaType_Video) ? 0 :
                           IsEqualGUID(&major, &MFMediaType_Audio) ? 1 : -1;
                if (slot >= 0 && streams[slot].index == MF_SOURCE_READER_INVALID_STREAM_INDEX)
                    streams[slot].index = i;
            }
            IMFMediaType_Release(type);
        }
        if (j == MAX_TYPES) puts("MF_LIMIT native-types-truncated");
        if (hr == MF_E_INVALIDSTREAMNUMBER) break;
    }
    if (i == MAX_STREAMS) { puts("MF_LIMIT stream-discovery-truncated"); failed = TRUE; }
    for (i = 0; i < 2 && !stopping(run); ++i) {
        Stream *s = &streams[i];
        if (!(opt->streams & s->kind)) continue;
        if (s->index == MF_SOURCE_READER_INVALID_STREAM_INDEX) {
            printf("MF_CAP kind=%s available=0\n", kind_name(s->kind));
            failed = TRUE;
            continue;
        }
        UINT32 rate = s->kind == AUDIO ? (opt->audio_rate ? opt->audio_rate : 48000) : 0;
        hr = select_type(reader, s, rate);
        if (FAILED(hr) && s->kind == AUDIO && !opt->audio_rate && !stopping(run))
            hr = select_type(reader, s, 44100);
        printf("MF_CAP kind=%s available=1 output_supported=%d hr=0x%08lx\n",
               kind_name(s->kind), s->enabled, (unsigned long)hr);
        if (FAILED(hr)) failed = TRUE;
    }
    reason = "eos-or-no-enabled-streams";
    while (!stopping(run) && total < opt->max_samples && reads < opt->max_reads) {
        Result result;
        Stream *s = NULL;
        if (opt->timeline_order && streams[0].enabled && streams[1].enabled &&
            !streams[0].eos && !streams[1].eos) {
            /* A client-controlled read order, never a playback-speed override.
             * Request the stream whose delivered timeline is behind. */
            next = !streams[0].have_end ? 0 : !streams[1].have_end ? 1 :
                   streams[0].previous_end <= streams[1].previous_end ? 0 : 1;
        }
        for (i = 0; i < 2; ++i) {
            DWORD slot = (next + i) % 2;
            if (streams[slot].enabled && !streams[slot].eos) {
                s = &streams[slot]; next = (slot + 1) % 2; break;
            }
        }
        if (!s) break;
        if (opt->pace_audio && pace_start) {
            double due = s->pcm_seconds * 1000.0;
            while (!stopping(run)) {
                double left = due - (double)(GetTickCount64() - pace_start);
                if (left <= 0) break;
                WaitForSingleObject(run->stop, left > 50.0 ? 50 : (DWORD)left + 1);
            }
            if (stopping(run)) break;
        }
        printf("MF_REQUEST number=%lu stream=%lu wall_ms=%llu\n", (unsigned long)++reads,
               (unsigned long)s->index, (unsigned long long)(GetTickCount64() - run->start));
        hr = read_one(run, reader, cb, s->index, &result);
        printf("MF_READ stream=%lu hr=0x%08lx flags=0x%08lx sample=%d\n",
               (unsigned long)result.stream, (unsigned long)hr,
               (unsigned long)result.flags, result.sample != NULL);
        if (FAILED(hr)) {
            if (result.sample) IMFSample_Release(result.sample);
            if (!stopping(run)) { failed = TRUE; reason = "read-error-or-timeout"; }
            break;
        }
        if (result.stream != s->index) {
            hrlog("unexpected-stream-index", E_UNEXPECTED);
            failed = TRUE;
        } else {
            if (result.flags & (MF_SOURCE_READERF_NATIVEMEDIATYPECHANGED |
                                MF_SOURCE_READERF_CURRENTMEDIATYPECHANGED)) {
                IMFMediaType *native = NULL;
                hr = IMFSourceReader_GetNativeMediaType(reader, s->index, 0, &native);
                hrlog("native-after-change", hr);
                if (SUCCEEDED(hr) && native) dump_type("native-changed", s->index, 0, native);
                if (native) IMFMediaType_Release(native);
                hr = current_type(reader, s, "current-changed");
                if (FAILED(hr)) { failed = TRUE; s->enabled = 0; }
            }
            if (result.sample && s->enabled) {
                ULONGLONG before = s->samples;
                hr = record_sample(s, &result, GetTickCount64() - run->start);
                if (s->samples != before) {
                    ++total;
                    if (opt->pace_audio && !pace_start) pace_start = GetTickCount64();
                }
                if (FAILED(hr)) { hrlog("sample-payload", hr); failed = TRUE; s->enabled = 0; }
            }
            if (result.flags & MF_SOURCE_READERF_ENDOFSTREAM) s->eos = 1;
            if (result.flags & MF_SOURCE_READERF_ERROR) { failed = TRUE; s->enabled = 0; }
            if (result.flags & MF_SOURCE_READERF_NEWSTREAM) puts("MF_LIMIT new-stream-not-selected");
        }
        if (result.sample) IMFSample_Release(result.sample);
        /* Unexpected streams or a changed/invalid output must not be decoded
         * under stale assumptions; stop before requesting another sample. */
        if (result.stream != s->index || !s->enabled) { reason = "stream-or-format-error"; break; }
    }
    if (stopping(run)) reason = "max-time";
    else if (total >= opt->max_samples) reason = "max-samples";
    else if (reads >= opt->max_reads) { reason = "max-reads"; failed = TRUE; }
cleanup:
    /* Snapshot completed reads before potentially blocking teardown. A forced
     * exit may have these sums but never claims MF_DONE/shutdown_complete=1. */
    for (i = 0; i < 2; ++i) {
        summary(&streams[i]);
        if ((opt->streams & streams[i].kind) && !streams[i].samples) failed = TRUE;
    }
    if (opt->expect_video_frames) {
        BOOL matched = streams[0].eos && streams[0].samples == opt->expect_video_frames;
        printf("MF_EXPECT video_frames=%lu actual=%llu eos=%d matched=%d\n",
               (unsigned long)opt->expect_video_frames,
               (unsigned long long)streams[0].samples, streams[0].eos, matched);
        if (!matched) { failed = TRUE; reason = "incomplete-video-fixture"; }
    }
    printf("MF_DECODE_END reason=%s reads=%lu samples=%lu failed=%d wall_ms=%llu\n",
           reason, (unsigned long)reads, (unsigned long)total, failed,
           (unsigned long long)(GetTickCount64() - run->start));
    if (cb) {
        EnterCriticalSection(&cb->lock);
        cb->closing = TRUE;
        ResetEvent(cb->flushed);
        LeaveCriticalSection(&cb->lock);
    }
    if (reader) {
        puts("MF_SHUTDOWN stage=Flush-begin");
        hr = IMFSourceReader_Flush(reader, MF_SOURCE_READER_ALL_STREAMS);
        hrlog("Flush-all", hr);
        if (FAILED(hr)) failed = TRUE;
        else if (cb) {
            DWORD wait = WaitForSingleObject(cb->flushed, FLUSH_MS);
            printf("MF_FLUSH_WAIT result=0x%08lx\n", (unsigned long)wait);
            if (wait != WAIT_OBJECT_0) failed = TRUE;
        }
    }
    if (source) {
        hr = IMFMediaSource_Shutdown(source);
        hrlog("source-Shutdown", hr);
        if (FAILED(hr)) failed = TRUE;
    }
    if (reader) { puts("MF_SHUTDOWN stage=reader-Release"); IMFSourceReader_Release(reader); }
    if (source) IMFMediaSource_Release(source);
    if (attrs) IMFAttributes_Release(attrs);
    if (mf) {
        puts("MF_SHUTDOWN stage=MFShutdown-begin");
        hr = MFShutdown();
        hrlog("MFShutdown", hr);
        if (FAILED(hr)) failed = TRUE;
    }
    if (cb) {
        EnterCriticalSection(&cb->lock);
        printf("MF_CALLBACK reads=%lu events=%lu flushes=%lu discarded=%lu error=0x%08lx\n",
               (unsigned long)cb->reads, (unsigned long)cb->events,
               (unsigned long)cb->flushes, (unsigned long)cb->discarded, (unsigned long)cb->error);
        if (FAILED(cb->error)) failed = TRUE;
        LeaveCriticalSection(&cb->lock);
        cb_release(&cb->iface);
    }
    if (com) CoUninitialize();
    printf("MF_DONE shutdown_complete=1 result=%s exit=%d wall_ms=%llu\n",
           failed ? "failure" : "decoded-within-bounds", failed ? 1 : 0,
           (unsigned long long)(GetTickCount64() - run->start));
    return failed ? 1 : 0;
}

static int number(const WCHAR *text, DWORD maximum, DWORD *value) {
    WCHAR *end;
    unsigned long parsed;
    if (!*text || *text < L'0' || *text > L'9') return 0;
    errno = 0;
    parsed = wcstoul(text, &end, 10);
    if (errno || *end || !parsed || parsed > maximum) return 0;
    *value = (DWORD)parsed;
    return 1;
}

static void usage(void) {
    puts("Usage: mf-video-probe.exe [--sync|--async] [--streams=both|video|audio]\n"
         "  [--max-samples=N] [--max-ms=N] [--max-reads=N] [--read-timeout-ms=N]\n"
         "  [--audio-rate=44100|48000] [--pace-audio] [--timeline-order]\n"
         "  [--expect-video-frames=N] [--] PATH_OR_HTTP_URL\n"
         "Defaults: sync, both, 600 nonempty samples total, 15000 ms including setup,\n"
         "10000 reads, 3000 ms async read wait, audio 48000 then 44100.\n"
         "--pace-audio requires --streams=audio; requests follow decoded PCM duration\n"
         "against elapsed time, without a renderer/speaker. max-ms <= 300000,\n"
         "max-samples/max-reads <= 1000000; all limits must be positive.\n"
         "--timeline-order reads the stream with the earlier delivered end time.\n"
         "--expect-video-frames requires video EOS and exactly N nonempty samples;\n"
         "use a known-frame-count fixture. Exit 0 alone is not full playback proof.\n"
         "Shutdown has at most 3000 ms additional grace; hard self-exit is 124.\n"
         "Exit 0: requested streams decoded; 1: failure/unsupported; 2: usage.\n"
         "Only local paths and public/loopback HTTP(S) URLs; no credentials,\n"
         "playlists, DRM, Unity/AVPro, GPU rendering, or audio-device test.");
}

int wmain(int argc, WCHAR **argv) {
    Run run;
    HANDLE thread;
    DWORD wait, code = 1;
    unsigned scheme;
    int i, positional = 0;
    memset(&run, 0, sizeof run);
    run.opt.max_ms = 15000;
    run.opt.max_samples = 600;
    run.opt.max_reads = 10000;
    run.opt.read_ms = 3000;
    run.opt.streams = VIDEO | AUDIO;
    setvbuf(stdout, NULL, _IONBF, 0);
    for (i = 1; i < argc; ++i) {
        const WCHAR *a = argv[i];
        if (!positional && !wcscmp(a, L"--help")) { usage(); return 0; }
        if (!positional && !wcscmp(a, L"--")) { positional = 1; continue; }
        if (!positional && !wcscmp(a, L"--async")) run.opt.async = 1;
        else if (!positional && !wcscmp(a, L"--sync")) run.opt.async = 0;
        else if (!positional && !wcscmp(a, L"--streams=both")) run.opt.streams = VIDEO | AUDIO;
        else if (!positional && !wcscmp(a, L"--streams=video")) run.opt.streams = VIDEO;
        else if (!positional && !wcscmp(a, L"--streams=audio")) run.opt.streams = AUDIO;
        else if (!positional && !wcscmp(a, L"--pace-audio")) run.opt.pace_audio = 1;
        else if (!positional && !wcscmp(a, L"--timeline-order")) run.opt.timeline_order = 1;
        else if (!positional && !wcsncmp(a, L"--expect-video-frames=", 22)) {
            if (!number(a + 22, 1000000, &run.opt.expect_video_frames)) goto bad;
        }
        else if (!positional && !wcsncmp(a, L"--max-samples=", 14)) {
            if (!number(a + 14, 1000000, &run.opt.max_samples)) goto bad;
        } else if (!positional && !wcsncmp(a, L"--max-ms=", 9)) {
            if (!number(a + 9, 300000, &run.opt.max_ms)) goto bad;
        } else if (!positional && !wcsncmp(a, L"--max-reads=", 12)) {
            if (!number(a + 12, 1000000, &run.opt.max_reads)) goto bad;
        } else if (!positional && !wcsncmp(a, L"--read-timeout-ms=", 18)) {
            if (!number(a + 18, 300000, &run.opt.read_ms)) goto bad;
        } else if (!positional && !wcsncmp(a, L"--audio-rate=", 13)) {
            if (!number(a + 13, 48000, &run.opt.audio_rate) ||
                (run.opt.audio_rate != 44100 && run.opt.audio_rate != 48000)) goto bad;
        } else {
            if ((!positional && a[0] == L'-') || run.opt.input) goto bad;
            run.opt.input = a;
        }
    }
    if (!run.opt.input || (run.opt.pace_audio && run.opt.streams != AUDIO)) goto bad;
    if (run.opt.expect_video_frames && !(run.opt.streams & VIDEO)) goto bad;
    scheme = !_wcsnicmp(run.opt.input, L"http://", 7) ? 7 :
             !_wcsnicmp(run.opt.input, L"https://", 8) ? 8 : 0;
    if (wcsstr(run.opt.input, L"://") && !scheme) goto bad;
    if (scheme) {
        const WCHAR *host = run.opt.input + scheme;
        const WCHAR *end = wcspbrk(host, L"/?#");
        const WCHAR *at = wcschr(host, L'@');
        if (!*host || *host == L'/' || *host == L'?' || *host == L'#' ||
            (at && (!end || at < end))) goto bad;
    }
    puts("MF_PROBE version=1 pipeline=SourceReader render=none audio_endpoint=none");
    printf("MF_SCHEDULER order=%s\n", run.opt.timeline_order ? "delivered-timeline" : "round-robin");
    printf("MF_OPTIONS mode=%s streams=%d max_samples=%lu max_ms=%lu max_reads=%lu "
           "async_read_timeout_ms=%lu audio_rate=%lu pace_audio=%d shutdown_grace_ms=%u\n",
           run.opt.async ? "async" : "sync", run.opt.streams, (unsigned long)run.opt.max_samples,
           (unsigned long)run.opt.max_ms, (unsigned long)run.opt.max_reads,
           (unsigned long)run.opt.read_ms, (unsigned long)run.opt.audio_rate,
           run.opt.pace_audio, SHUTDOWN_MS);
    run.stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!run.stop) { hrlog("stop-event", HRESULT_FROM_WIN32(GetLastError())); return 1; }
    run.start = GetTickCount64();
    thread = CreateThread(NULL, 0, worker, &run, 0, NULL);
    if (!thread) {
        hrlog("worker-thread", HRESULT_FROM_WIN32(GetLastError()));
        CloseHandle(run.stop);
        return 1;
    }
    /* No COM/MF calls on the supervising thread. In particular, a blocked sync
     * read/open/release cannot prevent the hard deadline. Never TerminateThread:
     * it can strand COM locks and make process shutdown itself hang. */
    wait = WaitForSingleObject(thread, run.opt.max_ms);
    if (wait == WAIT_TIMEOUT) {
        SetEvent(run.stop);
        wait = WaitForSingleObject(thread, SHUTDOWN_MS);
    }
    if (wait != WAIT_OBJECT_0) {
        static const char message[] = "MF_HARD_TIMEOUT shutdown_complete=0 sums=partial-or-unavailable exit=124\r\n";
        DWORD written;
        /* Bypass the CRT stdout lock if a hung worker owns it. Keep stderr
         * drained too; an external timeout is still needed for a wedged Wine. */
        WriteFile(GetStdHandle(STD_ERROR_HANDLE), message, sizeof message - 1, &written, NULL);
        TerminateProcess(GetCurrentProcess(), 124);
        return 124;
    }
    if (!GetExitCodeThread(thread, &code)) code = 1;
    CloseHandle(thread);
    CloseHandle(run.stop);
    return (int)code;
bad:
    usage();
    return 2;
}
