#define NDL_DIRECTMEDIA_API_VERSION 2
#include <libndl-media/NDL_directmedia.h>

#include "ndl_bridge.h"

#include <dlfcn.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>


static int g_loaded = 0;

int ndl_bridge_init(const char* appid) {
    if (!NDL_DirectMedia_DL_Initialize()) return -1;
    return NDL_DirectMediaInit(appid, NULL);
}

// Reset complet : Quit + Init. À appeler entre 2 films d'encodages vidéo
// différents (ex 4K HEVC → 1080p HEVC) : sans ce reset le driver LG NDL
// garde l'état de décodage précédent et refuse NDL_DirectMediaLoad (rc=-1).
int ndl_bridge_reset(const char* appid) {
    if (g_loaded) {
        NDL_DirectMediaUnload();
        g_loaded = 0;
    }
    NDL_DirectMediaQuit();
    return NDL_DirectMediaInit(appid, NULL);
}

int ndl_bridge_load(int video_is_h265, int width, int height,
                    int sample_rate, int channels) {
    NDL_DIRECTMEDIA_DATA_INFO_T info;
    memset(&info, 0, sizeof(info));
    info.video.type = video_is_h265 ? NDL_VIDEO_TYPE_H265 : NDL_VIDEO_TYPE_H264;
    info.video.width = width;
    info.video.height = height;
    if (sample_rate > 0 && channels > 0) {
        info.audio.pcm.type = NDL_AUDIO_TYPE_PCM;
        info.audio.pcm.format = NDL_DIRECTMEDIA_AUDIO_PCM_FORMAT_S16LE;  // "S16LE"
        info.audio.pcm.layout = "interleaved";
        info.audio.pcm.channelMode = (channels == 1) ? "mono" : NDL_DIRECTMEDIA_AUDIO_PCM_MODE_STEREO;
        info.audio.pcm.sampleRate = NDL_DIRECTMEDIA_AUDIO_PCM_SAMPLE_RATE_OF(sample_rate);
    } else {
        // no audio path : memset above sets type=0, leave as-is.
    }
    int rc = NDL_DirectMediaLoad(&info, NULL);
    if (rc == 0) g_loaded = 1;
    return rc;
}

int ndl_bridge_play_video(const void* data, unsigned size, long long pts_us) {
    return NDL_DirectVideoPlay((void*)data, size, pts_us);
}

int ndl_bridge_play_audio_pcm(const void* data, unsigned size, long long pts_us) {
    return NDL_DirectAudioPlay((void*)data, size, pts_us);
}

int ndl_bridge_set_area(int x, int y, int w, int h) {
    return NDL_DirectVideoSetArea(x, y, w, h);
}

int ndl_bridge_flush(void) {
    return NDL_DirectVideoFlushRenderBuffer();
}

void ndl_bridge_unload(void) {
    if (g_loaded) {
        NDL_DirectMediaUnload();
        g_loaded = 0;
    }
}

void ndl_bridge_quit(void) {
    NDL_DirectMediaQuit();
    NDL_DirectMedia_DL_Finalize();
}

const char* ndl_bridge_last_error(void) {
    const char* e = NDL_DirectMediaGetError();
    return e ? e : "(no error message)";
}

// Résolution paresseuse de symboles non publics (exportés par libndl-media.so
// mais absents du header). Si le symbole n'existe pas dans cette build LG,
// on revient en no-op (-1).
typedef int (*fn_set_drop_t)(int);
typedef int (*fn_get_bufl_t)(void);

static void* _get_libhandle(void) {
    static void* h = NULL;
    static int tried = 0;
    if (!tried) {
        tried = 1;
        h = dlopen("libndl-media.so.1", RTLD_NOW | RTLD_NOLOAD);
        if (!h) h = dlopen("libndl-media.so.1", RTLD_NOW);
        if (!h) h = dlopen("libndl-media.so",   RTLD_NOW);
    }
    return h;
}

int ndl_bridge_set_frame_drop_threshold(int n) {
    static fn_set_drop_t fn = NULL;
    static int resolved = 0;
    if (!resolved) {
        resolved = 1;
        void* h = _get_libhandle();
        if (h) fn = (fn_set_drop_t)dlsym(h, "NDL_DirectVideoSetFrameDropThreshold");
    }
    return fn ? fn(n) : -1;
}

int ndl_bridge_get_render_buffer_length(void) {
    static fn_get_bufl_t fn = NULL;
    static int resolved = 0;
    if (!resolved) {
        resolved = 1;
        void* h = _get_libhandle();
        if (h) fn = (fn_get_bufl_t)dlsym(h, "NDL_DirectVideoGetRenderBufferLength");
    }
    return fn ? fn() : -1;
}
