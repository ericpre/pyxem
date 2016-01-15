/*
 * mrc.c
 *
 * Read the MRC tomography format
 *
 * (c) 2007-2008 Thomas White <taw27@cam.ac.uk>
 *
 *  dtr - Diffraction Tomography Reconstruction
 *
 */

#ifdef HAVE_CONFIG_H
#include <config.h>
#endif

#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <string.h>

#include "mrc.h"
#include "control.h"
#include "imagedisplay.h"
#include "itrans.h"
#include "reflections.h"
#include "utils.h"
#include "image.h"

int mrc_read(ControlContext *ctx) {

	FILE *fh;
	MRCHeader mrc;
	MRCExtHeader ext[1024];
	unsigned int i;
	unsigned int extsize;
	double pixel_size;
	int x, y;

	fh = fopen(ctx->filename, "rb");

	/* Read primary header */
	fread(&mrc, sizeof(MRCHeader), 1, fh);
	printf("%i images in series\n", mrc.nz);
	if ( mrc.mode != 1 ) {
		fprintf(stderr, "MR: Unknown MRC image mode (must be 16-bit signed)\n");
		fclose(fh);
		return -1;
	}
	if ( (mrc.nxstart != 0) || (mrc.nystart != 0) ) {
		fclose(fh);
		fprintf(stderr, "MR: Image origin must be at zero: found at %i,%i\n", mrc.nxstart, mrc.nystart);
		return -1;
	}

	/* Read all extended headers, one by one */
	extsize = 4*mrc.numintegers + 4*mrc.numfloats;
	if ( extsize > sizeof(MRCExtHeader) ) {
		fclose(fh);
		fprintf(stderr, "MR: MRC extended header is too big - tweak mrc.h\n");
		return -1;
	}
	for ( i=0; i<mrc.nz; i++ ) {
		fread(&ext[i], extsize, 1, fh);
	}

	pixel_size = ext[0].pixel_size;
	printf("pixel_size = %f m^-1\n", pixel_size);
	ctx->fmode = FORMULATION_PIXELSIZE;

	for ( i=0; i<mrc.nz; i++ ) {

		int16_t *image = malloc(mrc.ny * mrc.nx * sizeof(uint16_t));
		uint16_t *uimage = malloc(mrc.ny * mrc.nx * sizeof(uint16_t));

		printf("Image #%3i: tilt=%f deg omega=%f deg L=%f m\n", i, ext[i].a_tilt, ext[i].tilt_axis,
									ext[i].magnification);
		ctx->camera_length = ext[i].magnification;
		if ( ext[i].voltage == 0 ) {
			ctx->lambda = lambda(200000);
		} else {
			ctx->lambda = lambda(1000*ext[i].voltage);
		}
		ctx->omega = deg2rad(ext[i].tilt_axis);
		ctx->pixel_size = ext[i].pixel_size;

		fseek(fh, mrc.next + sizeof(MRCHeader) + mrc.nx*mrc.ny*2*i, SEEK_SET);
		fread(image, mrc.nx*mrc.ny*2, 1, fh);

		for ( x=0; x<mrc.nx; x++ ) {
			for ( y=0; y<mrc.ny; y++ ) {
			
				if ( image[x + mrc.nx*y] < 0 ) {
					uimage[x + mrc.nx*y] = 0;
				} else {
					uimage[x + mrc.nx*y] = image[x + mrc.nx*y];
				}
				
			}
		}
		free(image);

		image_add(ctx->images, uimage, mrc.nx, mrc.ny, deg2rad(ext[i].a_tilt), ctx);

	}

	fclose(fh);

	return 0;

}

unsigned int mrc_is_mrcfile(const char *filename) {

	if ( strcmp(filename+(strlen(filename)-4), ".mrc") == 0 ) {
		return 1;
	}

	return 0;

}
