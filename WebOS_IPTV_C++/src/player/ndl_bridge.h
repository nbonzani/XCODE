#pragma once
// C bridge over <libndl-media/NDL_directmedia_v2.h>: the NDL header uses
// `_REPLACE_ENUM` macros that collide with typedef names when compiled in
// C++ mode. Wrapping the NDL calls in a pure-C translation unit avoids it
// entirely and gives us a small, stable surface.

#ifdef __cplusplus
extern "C" {
#endif

int  ndl_bridge_init(const char* appid);
// Reset complet : Unload + Quit + Init. Entre 2 films 4K→1080p, sinon le
// driver LG garde l'état et refuse Load (rc=-1).
int  ndl_bridge_reset(const char* appid);
// Combined load: call once per session with video codec + PCM audio params.
// sample_rate: 48000 / 44100 / 32000 / 24000 / 22050 / 16000 / 12000 / 8000.
// channels: 1 or 2. Pass sample_rate=0 to disable audio.
int  ndl_bridge_load(int video_is_h265, int width, int height,
                     int sample_rate, int channels);
int  ndl_bridge_play_video(const void* data, unsigned size, long long pts_us);
int  ndl_bridge_play_audio_pcm(const void* data, unsigned size, long long pts_us);
int  ndl_bridge_set_area(int x, int y, int w, int h);
int  ndl_bridge_flush(void);
void ndl_bridge_unload(void);
void ndl_bridge_quit(void);
const char* ndl_bridge_last_error(void);

// Symboles exportés par libndl-media.so mais non publiés dans l'header :
// résolus en dlsym à la première invocation. Renvoient -1 si absents.
// SetFrameDropThreshold(n) = tolérance de retard avant drop silencieux ;
// recommandé N=10 pour VOD (anti-micro-hitches sur travellings).
// GetRenderBufferLength() = profondeur de la queue NDL (diag : 0 = starve,
// >4 = on feed trop vite).
int ndl_bridge_set_frame_drop_threshold(int n);
int ndl_bridge_get_render_buffer_length(void);

#ifdef __cplusplus
}
#endif
