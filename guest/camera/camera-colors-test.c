#include "camera-colors.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

int main(void) {
    /* Four 2x2 tiles: black, white, red and blue. Chroma rows and byte order matter. */
    uint8_t input[24] = {16,16,235,235,16,16,235,235,81,81,41,41,81,81,41,41,
                         128,128,128,128,90,240,240,110};
    uint8_t before[sizeof input], output[50];
    memcpy(before,input,sizeof input); memset(output,0xa5,sizeof output);
    camera_nv12_to_bgr24(input,output+1,4,4);
    const int expected[4][3] = {{0,0,0},{255,255,255},{0,0,255},{255,0,0}};
    for (unsigned row=0;row<4;row++) for(unsigned col=0;col<4;col++) {
        unsigned tile=(row/2)*2+col/2;
        for(unsigned channel=0;channel<3;channel++)
            if(abs((int)output[1+(row*4+col)*3+channel]-expected[tile][channel])>1) {
                fprintf(stderr,"color mismatch at %u,%u channel %u\n",col,row,channel); return 1;
            }
    }
    if (output[0]!=0xa5 || output[49]!=0xa5 || memcmp(before,input,sizeof input)) return 1;
    memset(output,0xa5,sizeof output);
    camera_nv12_to_bgr24_scaled(input,output+1,4,4,2,2);
    for(unsigned tile=0;tile<4;tile++) for(unsigned channel=0;channel<3;channel++)
        if(abs((int)output[1+tile*3+channel]-expected[tile][channel])>1) return 1;
    if(output[0]!=0xa5 || output[13]!=0xa5 || memcmp(before,input,sizeof input)) return 1;
    const uint8_t mixed[6]={16,235,235,16,128,128};
    camera_nv12_to_bgr24_scaled(mixed,output+1,2,2,1,1);
    for(unsigned channel=0;channel<3;channel++) if(output[1+channel]!=128) return 1;
    memset(input,0,sizeof input); camera_nv12_to_bgr24(input,output+1,4,4);
    if (output[0]!=0xa5 || output[49]!=0xa5) return 1;
    puts("NV12 to BGR24: black/white/red/blue, chroma rows, bounds and input preservation PASS");
    return 0;
}
