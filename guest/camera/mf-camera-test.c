#define COBJMACROS
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <stdio.h>
static int failed(const char *stage,HRESULT hr){printf("MF_CAMERA_FAIL %s 0x%08lx\n",stage,(unsigned long)hr);return 1;}
int main(void){
 HRESULT hr=CoInitializeEx(NULL,COINIT_MULTITHREADED);if(FAILED(hr))return failed("COM",hr);
 hr=MFStartup(MF_VERSION,MFSTARTUP_FULL);if(FAILED(hr))return failed("startup",hr);
 IMFAttributes *attributes=NULL;IMFActivate **devices=NULL;UINT32 count=0;
 hr=MFCreateAttributes(&attributes,1);if(FAILED(hr))return failed("attributes",hr);
 IMFAttributes_SetGUID(attributes,&MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,&MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
 hr=MFEnumDeviceSources(attributes,&devices,&count);printf("MF_CAMERA_DEVICES %u\n",count);if(FAILED(hr)||!count)return failed("enumerate",hr);
 IMFMediaSource *source=NULL;hr=IMFActivate_ActivateObject(devices[0],&IID_IMFMediaSource,(void**)&source);if(FAILED(hr))return failed("activate",hr);
 IMFSourceReader *reader=NULL;hr=MFCreateSourceReaderFromMediaSource(source,NULL,&reader);if(FAILED(hr))return failed("reader",hr);
 IMFMediaType *type=NULL;hr=IMFSourceReader_GetNativeMediaType(reader,MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&type);if(FAILED(hr))return failed("native type",hr);
 hr=IMFSourceReader_SetCurrentMediaType(reader,MF_SOURCE_READER_FIRST_VIDEO_STREAM,NULL,type);if(FAILED(hr))return failed("select type",hr);
 unsigned frames=0;for(int i=0;i<64&&frames<8;i++){
  DWORD index=0,flags=0;LONGLONG stamp=0;IMFSample *sample=NULL;
  hr=IMFSourceReader_ReadSample(reader,MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&index,&flags,&stamp,&sample);if(FAILED(hr))return failed("sample",hr);
  if(sample){IMFMediaBuffer *buffer=NULL;hr=IMFSample_ConvertToContiguousBuffer(sample,&buffer);if(FAILED(hr))return failed("buffer",hr);DWORD size=0;IMFMediaBuffer_GetCurrentLength(buffer,&size);if(size)frames++;IMFMediaBuffer_Release(buffer);IMFSample_Release(sample);}
 }
 printf("MF_CAMERA_FRAMES %u\n",frames);IMFMediaType_Release(type);IMFSourceReader_Release(reader);IMFMediaSource_Shutdown(source);IMFMediaSource_Release(source);
 for(UINT32 i=0;i<count;i++)IMFActivate_Release(devices[i]);CoTaskMemFree(devices);IMFAttributes_Release(attributes);MFShutdown();CoUninitialize();
 if(frames==8){puts("MF_CAMERA_PASS");return 0;}return 1;
}
