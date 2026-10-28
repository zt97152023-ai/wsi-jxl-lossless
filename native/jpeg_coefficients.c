/* Research adapter around the public libjpeg coefficient transcoding API. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <jpeglib.h>

struct errors { struct jpeg_error_mgr base; jmp_buf jump; };
static void fail(j_common_ptr info) {
    struct errors *error=(struct errors *)info->err;
    longjmp(error->jump,1);
}

int64_t wsi_coefficients(const unsigned char *jpeg, unsigned long size,
                         int16_t *output, size_t capacity, uint32_t *shape) {
    struct jpeg_decompress_struct src;
    struct errors error;
    memset(&src,0,sizeof(src));
    src.err=jpeg_std_error(&error.base);error.base.error_exit=fail;
    if(setjmp(error.jump)) { jpeg_destroy_decompress(&src);return -1; }
    jpeg_create_decompress(&src);jpeg_mem_src(&src,jpeg,size);
    jpeg_read_header(&src,TRUE);
    if(src.num_components<1 || src.num_components>4 || src.image_width>4096 || src.image_height>4096) {
        jpeg_destroy_decompress(&src);return -2;
    }
    jvirt_barray_ptr *arrays=jpeg_read_coefficients(&src);
    shape[0]=src.image_width;shape[1]=src.image_height;shape[2]=src.num_components;
    size_t total=0;
    for(int c=0;c<src.num_components;c++) {
        jpeg_component_info *comp=&src.comp_info[c];
        shape[3+3*c]=comp->width_in_blocks;
        shape[4+3*c]=comp->height_in_blocks;
        shape[5+3*c]=comp->quant_tbl_no;
        total+=(size_t)comp->width_in_blocks*comp->height_in_blocks*DCTSIZE2;
    }
    if(total<=capacity) {
        size_t pos=0;
        for(int c=0;c<src.num_components;c++) {
            jpeg_component_info *comp=&src.comp_info[c];
            for(JDIMENSION y=0;y<comp->height_in_blocks;y++) {
                JBLOCKARRAY row=(*src.mem->access_virt_barray)((j_common_ptr)&src,arrays[c],y,1,FALSE);
                for(JDIMENSION x=0;x<comp->width_in_blocks;x++) {
                    for(int k=0;k<DCTSIZE2;k++)output[pos++]=(int16_t)row[0][x][k];
                }
            }
        }
    }
    jpeg_finish_decompress(&src);jpeg_destroy_decompress(&src);
    return (int64_t)total;
}

/* A complete template supplies JPEG coding parameters. Replacement coefficients
   are never transformed or quantized. The caller checks entropy-byte equality. */
int wsi_write_coefficients(const unsigned char *jpeg, unsigned long size,
                           const int16_t *input, size_t count,
                           unsigned char **output, unsigned long *output_size) {
    struct jpeg_decompress_struct src;
    struct jpeg_compress_struct dst;
    struct errors error;
    memset(&src,0,sizeof(src));memset(&dst,0,sizeof(dst));
    *output=NULL;*output_size=0;
    src.err=jpeg_std_error(&error.base);error.base.error_exit=fail;dst.err=&error.base;
    if(setjmp(error.jump)) {
        jpeg_destroy_compress(&dst);jpeg_destroy_decompress(&src);
        free(*output);*output=NULL;return -1;
    }
    jpeg_create_decompress(&src);jpeg_mem_src(&src,jpeg,size);jpeg_read_header(&src,TRUE);
    if(src.progressive_mode || src.arith_code || src.num_components<1 || src.num_components>4 ||
       src.image_width>4096 || src.image_height>4096) {
        jpeg_destroy_decompress(&src);return -2;
    }
    jvirt_barray_ptr *arrays=jpeg_read_coefficients(&src);
    size_t required=0;
    for(int c=0;c<src.num_components;c++)required+=(size_t)src.comp_info[c].width_in_blocks*src.comp_info[c].height_in_blocks*64;
    if(required!=count) {jpeg_destroy_decompress(&src);return -3;}
    size_t pos=0;
    for(int c=0;c<src.num_components;c++) {
        jpeg_component_info *comp=&src.comp_info[c];
        for(JDIMENSION y=0;y<comp->height_in_blocks;y++) {
            JBLOCKARRAY row=(*src.mem->access_virt_barray)((j_common_ptr)&src,arrays[c],y,1,TRUE);
            for(JDIMENSION x=0;x<comp->width_in_blocks;x++)
                for(int k=0;k<64;k++)row[0][x][k]=(JCOEF)input[pos++];
        }
    }
    jpeg_create_compress(&dst);jpeg_mem_dest(&dst,output,output_size);
    jpeg_copy_critical_parameters(&src,&dst);
    dst.optimize_coding=FALSE;dst.restart_interval=src.restart_interval;
    for(int c=0;c<src.num_components;c++) {
        dst.comp_info[c].dc_tbl_no=src.comp_info[c].dc_tbl_no;
        dst.comp_info[c].ac_tbl_no=src.comp_info[c].ac_tbl_no;
    }
    for(int t=0;t<NUM_HUFF_TBLS;t++) {
        if(src.dc_huff_tbl_ptrs[t]) {
            if(!dst.dc_huff_tbl_ptrs[t])dst.dc_huff_tbl_ptrs[t]=jpeg_alloc_huff_table((j_common_ptr)&dst);
            *dst.dc_huff_tbl_ptrs[t]=*src.dc_huff_tbl_ptrs[t];dst.dc_huff_tbl_ptrs[t]->sent_table=FALSE;
        }
        if(src.ac_huff_tbl_ptrs[t]) {
            if(!dst.ac_huff_tbl_ptrs[t])dst.ac_huff_tbl_ptrs[t]=jpeg_alloc_huff_table((j_common_ptr)&dst);
            *dst.ac_huff_tbl_ptrs[t]=*src.ac_huff_tbl_ptrs[t];dst.ac_huff_tbl_ptrs[t]->sent_table=FALSE;
        }
    }
    jpeg_write_coefficients(&dst,arrays);jpeg_finish_compress(&dst);
    jpeg_finish_decompress(&src);jpeg_destroy_compress(&dst);jpeg_destroy_decompress(&src);
    return 0;
}

void wsi_free(void *pointer) { free(pointer); }
