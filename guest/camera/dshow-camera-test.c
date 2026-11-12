#define COBJMACROS
#include <windows.h>
#include <dshow.h>
#include <stdio.h>

/* Enumerate and bind DirectShow video devices without opening a game or saving frames. */
int main(void) {
    HRESULT hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (FAILED(hr)) return 1;
    ICreateDevEnum *devices = NULL;
    IEnumMoniker *items = NULL;
    hr = CoCreateInstance(&CLSID_SystemDeviceEnum, NULL, CLSCTX_INPROC_SERVER,
                         &IID_ICreateDevEnum, (void **)&devices);
    if (FAILED(hr)) { printf("DS_CAMERA_FAIL create 0x%08lx\n", (unsigned long)hr); return 1; }
    hr = ICreateDevEnum_CreateClassEnumerator(devices, &CLSID_VideoInputDeviceCategory, &items, 0);
    unsigned count = 0, bound = 0;
    if (hr == S_OK) {
        IMoniker *item = NULL;
        while (IEnumMoniker_Next(items, 1, &item, NULL) == S_OK) {
            count++;
            IPropertyBag *bag = NULL;
            if (SUCCEEDED(IMoniker_BindToStorage(item, NULL, NULL, &IID_IPropertyBag, (void **)&bag))) {
                VARIANT name; VariantInit(&name);
                if (SUCCEEDED(IPropertyBag_Read(bag, L"FriendlyName", &name, NULL)) && V_VT(&name) == VT_BSTR) {
                    char text[1024];
                    if (WideCharToMultiByte(CP_UTF8, 0, V_BSTR(&name), -1, text, sizeof text, NULL, NULL))
                        printf("DS_CAMERA_NAME %s\n", text);
                }
                VariantClear(&name); IPropertyBag_Release(bag);
            }
            IBaseFilter *filter = NULL;
            hr = IMoniker_BindToObject(item, NULL, NULL, &IID_IBaseFilter, (void **)&filter);
            printf("DS_CAMERA_BIND 0x%08lx\n", (unsigned long)hr);
            if (SUCCEEDED(hr)) { bound++; IBaseFilter_Release(filter); }
            IMoniker_Release(item);
        }
        IEnumMoniker_Release(items);
    } else if (FAILED(hr)) printf("DS_CAMERA_FAIL enumerate 0x%08lx\n", (unsigned long)hr);
    printf("DS_CAMERA_DEVICES %u BOUND %u\n", count, bound);
    ICreateDevEnum_Release(devices); CoUninitialize();
    if (count && bound == count) { puts("DS_CAMERA_ENUM_PASS"); return 0; }
    return 1;
}
