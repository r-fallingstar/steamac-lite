#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#define W 640
#define H 480
#define BYTES (W*H*3/2)
#define HEADER 32
static uint32_t u32(const unsigned char *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint64_t millis(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static int xio(int fd,unsigned long req,void *p){int r;do{r=ioctl(fd,req,p);}while(r<0&&errno==EINTR);return r;}
static void fail(const char *what){perror(what);exit(1);}
static void blank(unsigned char *p){memset(p,16,W*H);memset(p+W*H,128,W*H/2);}
static uint64_t hash(const unsigned char *p,size_t n){uint64_t h=14695981039346656037ULL;for(size_t i=0;i<n;i++){h^=p[i];h*=1099511628211ULL;}return h;}
static int probe(const char *device,int expect_black){
 int fd=open(device,O_RDWR|O_NONBLOCK);if(fd<0)fail("probe open");
 struct v4l2_capability cap={0};if(xio(fd,VIDIOC_QUERYCAP,&cap)<0)fail("querycap");
 if(!(cap.device_caps&V4L2_CAP_VIDEO_CAPTURE)){fprintf(stderr,"not a capture device\n");return 1;}
 struct v4l2_format fmt={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};if(xio(fd,VIDIOC_G_FMT,&fmt)<0)fail("get format");
 if(fmt.fmt.pix.width!=W||fmt.fmt.pix.height!=H||fmt.fmt.pix.pixelformat!=V4L2_PIX_FMT_NV12){fprintf(stderr,"unexpected capture format\n");return 1;}
 struct v4l2_requestbuffers req={.count=4,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};if(xio(fd,VIDIOC_REQBUFS,&req)<0)fail("request buffers");
 void *buffers[32];size_t sizes[32];if(req.count>32||!req.count)return 1;
 for(unsigned i=0;i<req.count;i++){
  struct v4l2_buffer b={.index=i,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};if(xio(fd,VIDIOC_QUERYBUF,&b)<0)fail("query buffer");
  sizes[i]=b.length;buffers[i]=mmap(NULL,b.length,PROT_READ|PROT_WRITE,MAP_SHARED,fd,b.m.offset);if(buffers[i]==MAP_FAILED)fail("mmap");if(xio(fd,VIDIOC_QBUF,&b)<0)fail("queue buffer");
 }
 enum v4l2_buf_type type=V4L2_BUF_TYPE_VIDEO_CAPTURE;if(xio(fd,VIDIOC_STREAMON,&type)<0)fail("stream on");
 uint64_t hashes[16]={0};int frames=0,distinct=0,black=0;uint64_t deadline=millis()+12000;
 while(frames<16&&millis()<deadline){
  struct pollfd p={fd,POLLIN,0};if(poll(&p,1,500)<=0)continue;
  struct v4l2_buffer b={.type=type,.memory=V4L2_MEMORY_MMAP};if(xio(fd,VIDIOC_DQBUF,&b)<0){if(errno==EAGAIN)continue;fail("dequeue");}
  if(b.index>=req.count||b.bytesused!=BYTES){fprintf(stderr,"invalid frame length\n");return 1;}
  unsigned char *image=buffers[b.index];int dark=1;for(int j=0;j<BYTES;j++)if(image[j]!=(j<W*H?16:128)){dark=0;break;}black+=dark;
  hashes[frames]=hash(buffers[b.index],b.bytesused);int seen=0;for(int i=0;i<frames;i++)if(hashes[i]==hashes[frames])seen=1;if(!seen)distinct++;frames++;
  if(xio(fd,VIDIOC_QBUF,&b)<0)fail("requeue");
 }
 xio(fd,VIDIOC_STREAMOFF,&type);for(unsigned i=0;i<req.count;i++)munmap(buffers[i],sizes[i]);close(fd);
 printf("CAMERA_PROBE {\"frames\":%d,\"distinct\":%d,\"width\":%d,\"height\":%d,\"format\":\"NV12\",\"mmap\":true}\n",frames,distinct,W,H);
 return frames==16&&(expect_black?black>=12:distinct>=3)?0:1;
}
int main(int argc,char **argv){
 if(argc==3&&(!strcmp(argv[1],"--probe")||!strcmp(argv[1],"--probe-black")))return probe(argv[2],!strcmp(argv[1],"--probe-black"));
 const char *port=argc>1?argv[1]:"/dev/virtio-ports/fx.camera";const char *device=argc>2?argv[2]:"/dev/video20";
 int input=open(port,O_RDWR|O_NONBLOCK);if(input<0)fail("camera port");int output=open(device,O_WRONLY|O_NONBLOCK);if(output<0)fail("video output");
 struct v4l2_format fmt={.type=V4L2_BUF_TYPE_VIDEO_OUTPUT};fmt.fmt.pix.width=W;fmt.fmt.pix.height=H;fmt.fmt.pix.pixelformat=V4L2_PIX_FMT_NV12;fmt.fmt.pix.field=V4L2_FIELD_NONE;fmt.fmt.pix.bytesperline=W;fmt.fmt.pix.sizeimage=BYTES;fmt.fmt.pix.colorspace=V4L2_COLORSPACE_REC709;
 if(xio(output,VIDIOC_S_FMT,&fmt)<0||fmt.fmt.pix.sizeimage!=BYTES)fail("set NV12");
 struct v4l2_streamparm parm={.type=V4L2_BUF_TYPE_VIDEO_OUTPUT};parm.parm.output.timeperframe.numerator=1;parm.parm.output.timeperframe.denominator=15;if(xio(output,VIDIOC_S_PARM,&parm)<0)fail("set fps");
 struct v4l2_control c={.id=V4L2_CID_USER_BASE|0xf000,.value=1};if(xio(output,VIDIOC_S_CTRL,&c)<0)fail("keep format");
 unsigned char *frame=malloc(BYTES),*rx=malloc(BYTES*3);if(!frame||!rx)fail("allocate");blank(frame);
 size_t used=0;uint64_t received=0,last=0,next=0;dprintf(input,"READY /dev/video20 NV12 640x480 15fps\n");fprintf(stderr,"camera-agent: ready (black until enabled)\n");
 for(;;){
  struct pollfd p={input,POLLIN,0};poll(&p,1,15);
  if(p.revents&POLLIN){
   ssize_t n=read(input,rx+used,BYTES*3-used);if(n<0&&errno!=EAGAIN&&errno!=EINTR)fail("read frames");if(n>0)used+=(size_t)n;
   while(used>=HEADER){
    if(memcmp(rx,"FXCM",4)||rx[4]!=1||rx[5]!=0){memmove(rx,rx+1,--used);continue;}
    uint32_t length=u32(rx+20);unsigned kind=rx[6]|(unsigned)rx[7]<<8;
    if(length>BYTES){memmove(rx,rx+1,--used);continue;}
    if(used<HEADER+length)break;
    if(kind==1&&length==BYTES&&u32(rx+8)==W&&u32(rx+12)==H&&u32(rx+16)==V4L2_PIX_FMT_NV12){memcpy(frame,rx+HEADER,BYTES);last=millis();received++;if(received==1||received%60==0)dprintf(input,"FRAMES %llu\n",(unsigned long long)received);}
    else if(kind==2){blank(frame);last=0;dprintf(input,"STOPPED\n");}
    used-=HEADER+length;memmove(rx,rx+HEADER+length,used);
   }
  }
  uint64_t now=millis();if(last&&now-last>1000){blank(frame);last=0;dprintf(input,"STALE black\n");}
  if(now>=next){ssize_t n=write(output,frame,BYTES);if(n<0&&errno!=EAGAIN&&errno!=EINTR)fail("write video");if(n>0&&n!=BYTES){fprintf(stderr,"short video write\n");return 1;}next=now+66;}
 }
}
