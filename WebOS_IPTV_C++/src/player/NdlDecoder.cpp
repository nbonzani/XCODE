#include "player/NdlDecoder.h"

#include <atomic>
#include <cstring>
#include <unistd.h>
#include <dlfcn.h>

#include <SDL2/SDL_log.h>
#include <SDL2/SDL_timer.h>
#include <gst/gst.h>
#include <gst/app/gstappsink.h>

#include "player/ndl_bridge.h"

namespace iptv {

namespace {
constexpr int kAudioSampleRate = 48000;
constexpr int kAudioChannels   = 2;
}  // namespace

NdlDecoder::NdlDecoder() = default;
NdlDecoder::~NdlDecoder() {
    stop();
    shutdown();
}

bool NdlDecoder::init(const std::string& appId) {
    if (initialized_) return true;
    gst_init(nullptr, nullptr);
    // Force-load libgstlibav + downrank ac3_audiodec (HW LG) en faveur de
    // avdec_ac3/avdec_eac3 : le HW LG décode AC3/EAC3 mais sort des caps
    // multichannel (5.1, channel-mask=0, acmod=7) que pulsesink n'avale
    // qu'avec crackle / buffer-size errors. avdec_* sort du F32LE non-
    // interleaved avec channel-mask correct → audioconvert downmixe
    // proprement en stéréo pour pulsesink.
    // Pas de force-load libgstlibav ici : ça casse NDL (libavcodec FFmpeg 4.4
    // bundled vs 4.0 TV requise par libndl-media). DivX MPEG-4 ASP ne marchera
    // que si l'utilisateur réencode en H.264 — compromis assumé v0.1.0.
    static bool libav_loaded = false;
    if (!libav_loaded) {
        libav_loaded = true;
        // Pre-load le plugin lxaudiodec pour que ses factories soient
        // disponibles avant le downrank (sinon gst_element_factory_find
        // retourne NULL et le downrank ne prend pas effet).
        if (GstPlugin* p = gst_plugin_load_by_name("lxaudiodec")) {
            SDL_Log("[ndl] pre-loaded lxaudiodec");
            gst_object_unref(p);
        }
        // Downrank TOUS les décodeurs HW audio LG : ils sortent des caps
        // multichannel (5.1, channel-mask atypique, acmod=7) que webOS
        // pulsesink n'arrive pas à downmixer → "wrong size" en boucle ou
        // son absent. avdec_* de libav sort des caps standards downmixable.
        // Downrank ciblé (noms connus) :
        for (const char* name : {"ac3_audiodec", "eac3_audiodec",
                                  "aac_audiodec", "mp3_audiodec",
                                  "ac4_audiodec", "flac_audiodec",
                                  "opus_audiodec", "vorbis_audiodec",
                                  "alac_audiodec", "amr_audiodec",
                                  "adpcm_audiodec", "wma_audiodec",
                                  "pcm_audiodec", "mpegh_audiodec"}) {
            if (GstElementFactory* f = gst_element_factory_find(name)) {
                gst_plugin_feature_set_rank(GST_PLUGIN_FEATURE(f), GST_RANK_NONE);
                gst_object_unref(f);
                SDL_Log("[ndl] downranked %s", name);
            }
        }
        // Downrank générique : tout factory dont le nom commence par
        // "lxaudiodec" (famille complète `lxaudiodecaac3`, `lxaudiodecac3`,
        // `lxaudiodecmp3`, …). Observé 2026-04-24 : decodebin auto-pluggait
        // `lxaudiodecaac3` malgré downrank `aac_audiodec` → pipeline stall.
        {
            GstRegistry* reg = gst_registry_get();
            GList* all = gst_registry_feature_filter(reg,
                [](GstPluginFeature* f, gpointer) -> gboolean {
                    if (!GST_IS_ELEMENT_FACTORY(f)) return FALSE;
                    const gchar* n = gst_plugin_feature_get_name(f);
                    return n && g_str_has_prefix(n, "lxaudiodec") ? TRUE : FALSE;
                }, FALSE, nullptr);
            for (GList* l = all; l; l = l->next) {
                GstPluginFeature* f = GST_PLUGIN_FEATURE(l->data);
                gst_plugin_feature_set_rank(f, GST_RANK_NONE);
                SDL_Log("[ndl] downranked %s (lxaudiodec*)",
                        gst_plugin_feature_get_name(f));
            }
            gst_plugin_feature_list_free(all);
        }
        for (const char* name : {"avdec_ac3", "avdec_eac3", "avdec_aac",
                                  "avdec_mp3", "avdec_dca"}) {
            if (GstElementFactory* f = gst_element_factory_find(name)) {
                gst_plugin_feature_set_rank(GST_PLUGIN_FEATURE(f),
                                             GST_RANK_PRIMARY + 10);
                gst_object_unref(f);
                SDL_Log("[ndl] upranked %s", name);
            }
        }
    }
    // Reset plutôt que init simple : entre 2 films (surtout 4K→1080p HEVC)
    // le driver LG NDL garde l'état du décodage précédent et refuse Load
    // rc=-1. ndl_bridge_reset fait Unload+Quit+Init → driver fresh.
    int rc = ndl_bridge_reset(appId.c_str());
    if (rc != 0) {
        last_error_ = ndl_bridge_last_error();
        SDL_Log("[ndl] init(reset) failed rc=%d err=%s", rc, last_error_.c_str());
        return false;
    }
    SDL_Log("[ndl] init(reset) OK appId=%s", appId.c_str());
    initialized_ = true;
    return true;
}

void NdlDecoder::shutdown() {
    if (!initialized_) return;
    ndl_bridge_quit();
    initialized_ = false;
}

bool NdlDecoder::open(const std::string& uri, int width, int height,
                      const std::string& codec) {
    if (!initialized_) {
        SDL_Log("[ndl] open: not initialized");
        return false;
    }
    stop();
    const bool is_h265 = (codec == "hevc" || codec == "h265");

    // Pick source + demuxer based on URI scheme and extension.
    const bool is_http = uri.compare(0, 7, "http://") == 0 ||
                         uri.compare(0, 8, "https://") == 0;
    std::string src;
    if (is_http) {
        // Inline inline-quoted strings in gst_parse_launch are tricky ; on
        // passe par uridecodebin qui configure souphttpsrc via ses propriétés
        // par défaut. Pour les specs Xtream on patchera le user-agent via
        // source-setup plus tard si besoin.
        // Buffer HTTP 16 MB sans use-buffering pour démarrer rapidement.
        // use-buffering=true fait attendre 99% du buffer AVANT de passer en
        // PLAYING → ajoute 10 s de pré-roll sur 1080p/4K ce qui est pire
        // que quelques saccades.
        src = "souphttpsrc location=" + uri + " automatic-redirect=true ! "
              "queue2 max-size-buffers=0 max-size-bytes=16777216 "
              "max-size-time=5000000000";
    } else {
        // filesrc wants a path, not a URI — strip the "file://" scheme prefix.
        std::string path = uri;
        if (path.compare(0, 7, "file://") == 0) path.erase(0, 7);
        src = "filesrc location=\"" + path + "\"";
    }

    auto ends_with = [&uri](const char* suf) {
        size_t n = std::strlen(suf);
        return uri.size() >= n && uri.compare(uri.size() - n, n, suf) == 0;
    };
    const char* demux;
    if (ends_with(".mp4") || ends_with(".m4v")) {
        demux = "qtdemux";
    } else if (ends_with(".avi")) {
        demux = "avidemux";
    } else {
        demux = "matroskademux";
    }

    const char* vparse = is_h265 ? "h265parse" : "h264parse";
    const char* vcaps  = is_h265
        ? "video/x-h265,stream-format=byte-stream,alignment=au"
        : "video/x-h264,stream-format=byte-stream,alignment=au";

    // Pour les .avi et les containers avec codec audio problématique (DTS),
    // on branche fakesink direct sur le pad audio — pas de décodage, juste
    // un drain. Évite que decodebin bloque la pipeline.
    const bool drain_audio = ends_with(".avi") || skip_audio_;
    const char* aparse = nullptr;
    const char* adec   = nullptr;
    if (audio_codec_ == "ac3") {
        aparse = "ac3parse";
        adec   = "avdec_ac3";
    } else if (audio_codec_ == "eac3") {
        aparse = "ac3parse";
        adec   = "avdec_eac3";
    } else if (audio_codec_ == "aac") {
        aparse = "aacparse";
        adec   = "avdec_aac";
    } else if (audio_codec_ == "mp3") {
        aparse = "mpegaudioparse";
        adec   = "avdec_mp3";
    }
    std::string audio_branch;
    if (drain_audio) {
        audio_branch =
            " demux. ! queue max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
            "fakesink sync=false async=false";
    } else if (aparse && adec) {
        // Chaîne statique : demux produit un pad audio avec des caps connues
        // (ex : audio/x-ac3), parse normalise en frames, avdec_X décode en
        // F32/S16 non-interleaved. audioconvert fait le downmix 5.1→2 proprement.
        // Le capsfilter AVANT pulsesink fige channels=2 (force downmix) +
        // rate=48000 + format S16LE interleaved. Sans ce capsfilter strict,
        // le webOS pulsesink se retrouvait avec des buffers de taille
        // différente de ce qu'il avait négocié → "sink received buffer of
        // wrong size" en boucle (souvent silence + craquements).
        // sync=false : sync A/V côté vidéo. async-handling=true : évite
        // que set_state(PLAYING) bloque sur la pré-roll pulsesink.
        audio_branch = std::string(" demux. ! queue ! ") + aparse + " ! " + adec +
                       " ! audioconvert ! audioresample ! "
                       "audio/x-raw,format=S16LE,channels=2,rate=48000 ! "
                       "pulsesink sync=false provide-clock=false async-handling=true";
    } else {
        audio_branch =
            " demux. ! queue ! decodebin ! audioconvert ! audioresample ! "
            "audio/x-raw,format=S16LE,channels=2,rate=48000 ! "
            "pulsesink sync=true provide-clock=false async-handling=true";
    }

    // Hybrid pipeline : NDL for hardware video decode + pulsesink for audio.
    std::string desc =
        src + " ! " +
        demux + " name=demux "
        "demux. ! queue max-size-buffers=0 max-size-bytes=33554432 max-size-time=10000000000 ! " +
        vparse + " config-interval=-1 ! " +
        vcaps + " ! "
        // sync=true (ROLLBACK) : NDL sur notre build webOS 6.5.3 n'a pas
        // NDL_DirectVideoSetFrameDropThreshold exporté (rc=-1), donc pas de
        // drop interne si on le noie. Sans appsink pacing, écran noir.
        // Le recommandation SS4S (sync=false) suppose des builds avec
        // l'API drop-threshold active — pas le cas ici.
        "appsink name=vsink emit-signals=true sync=true max-buffers=0 drop=false" +
        audio_branch;

    SDL_Log("[ndl] open: parse_launch");
    GError* err = nullptr;
    pipeline_ = gst_parse_launch(desc.c_str(), &err);
    if (!pipeline_) {
        last_error_ = err ? err->message : "parse_launch failed";
        SDL_Log("[ndl] parse_launch FAILED: %s", last_error_.c_str());
        if (err) g_error_free(err);
        return false;
    }

    // Attach a bus watcher so we see state transitions, warnings, errors.
    // Certains flux audio (AVI + AC3 multichannel, échantillonnage atypique)
    // produisent en boucle "sink received buffer of wrong size" depuis
    // pulsesink : on les détecte pour ne pas saturer les logs et fermer la
    // branche audio proprement.
    static std::atomic<int> g_pulse_err_count{0};
    static std::atomic<uint32_t> g_pulse_first_ms{0};
    GstBus* bus = gst_pipeline_get_bus(GST_PIPELINE(pipeline_));
    gst_bus_add_watch(bus, [](GstBus*, GstMessage* msg, gpointer) -> gboolean {
        const gchar* src = GST_MESSAGE_SRC_NAME(msg) ? GST_MESSAGE_SRC_NAME(msg) : "?";
        switch (GST_MESSAGE_TYPE(msg)) {
            case GST_MESSAGE_ERROR: {
                GError* e = nullptr; gchar* dbg = nullptr;
                gst_message_parse_error(msg, &e, &dbg);
                const char* msgStr = e ? e->message : "";
                bool isWrongSize = msgStr &&
                    (strstr(msgStr, "wrong size") || strstr(msgStr, "different type"));
                if (isWrongSize) {
                    int n = ++g_pulse_err_count;
                    uint32_t now = SDL_GetTicks();
                    uint32_t first = g_pulse_first_ms.load();
                    if (first == 0) { g_pulse_first_ms = now; first = now; }
                    // Log seulement 1 fois + 1 toutes les 100 pour debug
                    if (n == 1 || n % 100 == 0) {
                        SDL_Log("[ndl-bus] pulsesink wrong-size ×%d (src=%s)", n, src);
                    }
                } else {
                    SDL_Log("[ndl-bus] ERROR from %s: %s (%s)", src,
                            e ? e->message : "?", dbg ? dbg : "");
                }
                if (e) g_error_free(e);
                if (dbg) g_free(dbg);
                break;
            }
            case GST_MESSAGE_WARNING: {
                GError* e = nullptr; gchar* dbg = nullptr;
                gst_message_parse_warning(msg, &e, &dbg);
                SDL_Log("[ndl-bus] WARN from %s: %s", src, e ? e->message : "?");
                if (e) g_error_free(e);
                if (dbg) g_free(dbg);
                break;
            }
            case GST_MESSAGE_STATE_CHANGED: {
                GstState oldS, newS;
                gst_message_parse_state_changed(msg, &oldS, &newS, nullptr);
                SDL_Log("[ndl-bus] %s state %s -> %s", src,
                        gst_element_state_get_name(oldS),
                        gst_element_state_get_name(newS));
                break;
            }
            case GST_MESSAGE_BUFFERING: {
                gint pct = -1;
                gst_message_parse_buffering(msg, &pct);
                SDL_Log("[ndl-bus] buffering %s = %d%%", src, pct);
                break;
            }
            case GST_MESSAGE_QOS: {
                guint64 processed = 0, dropped = 0;
                gst_message_parse_qos_stats(msg, nullptr, &processed, &dropped);
                SDL_Log("[ndl-bus] QoS %s processed=%llu dropped=%llu", src,
                        (unsigned long long)processed,
                        (unsigned long long)dropped);
                break;
            }
            default:
                break;
        }
        return TRUE;
    }, nullptr);
    gst_object_unref(bus);

    GstElement* vsink = gst_bin_get_by_name(GST_BIN(pipeline_), "vsink");
    if (vsink) {
        g_signal_connect(vsink, "new-sample",
                         G_CALLBACK(&NdlDecoder::onVideoSampleStatic), this);
        gst_object_unref(vsink);
    }
    GstElement* asink = gst_bin_get_by_name(GST_BIN(pipeline_), "asink");
    if (asink) {
        g_signal_connect(asink, "new-sample",
                         G_CALLBACK(&NdlDecoder::onAudioSampleStatic), this);
        gst_object_unref(asink);
    }

    // DirectMediaLoad est déplacé vers play() : on a besoin des vraies caps
    // vidéo (width/height) livrées par le demux après preroll. Si on Load avec
    // les mauvaises dimensions, le driver NDL attend des frames d'une autre
    // taille et ne sort rien (cas 720p/4K/SD qui échouait silencieusement).
    // open() stocke juste les hints reçus ; play() fait PAUSED → probe caps
    // → Load(real_w, real_h) → PLAYING.
    is_h265_ = is_h265;
    video_width_ = width;
    video_height_ = height;
    SDL_Log("[ndl] open OK uri=%s (Load deferred to play() for caps probe)",
            uri.c_str());
    return true;
}

bool NdlDecoder::play() {
    if (!pipeline_) return false;

    // IMPORTANT : Load NDL est FAIT DANS onVideoSample sur le premier buffer
    // reçu — c'est le seul endroit où on a à la fois les vraies caps
    // (via gst_sample_get_caps) ET la garantie que ce buffer est une IDR
    // (frame 0 ou frame après KEY_UNIT seek). Faire Load avant le premier
    // sample laissait tomber la 1re IDR entre PAUSED et Load → rc=-1
    // "player is not loaded" → écran noir jusqu'à la prochaine GOP.

    // Pre-play seek si demandé : PAUSED → seek KEY_UNIT → PLAYING.
    if (start_seek_sec_ > 0) {
        SDL_Log("[ndl] pre-play seek to %ds (PAUSED→KEY_UNIT→PLAYING)",
                start_seek_sec_);
        gst_element_set_state(pipeline_, GST_STATE_PAUSED);
        GstState cur;
        gst_element_get_state(pipeline_, &cur, nullptr, 3 * GST_SECOND);
        gint64 target_ns = (gint64)start_seek_sec_ * GST_SECOND;
        gboolean sk = gst_element_seek_simple(
            pipeline_, GST_FORMAT_TIME,
            (GstSeekFlags)(GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT),
            target_ns);
        SDL_Log("[ndl] seek_simple target_ns=%lld ok=%d",
                (long long)target_ns, (int)sk);
        start_seek_sec_ = 0;
    }

    GstStateChangeReturn r = gst_element_set_state(pipeline_, GST_STATE_PLAYING);
    SDL_Log("[ndl] play set_state=%d (Load fera dans onVideoSample)", (int)r);
    paused_.store(false);
    return r != GST_STATE_CHANGE_FAILURE;
}

bool NdlDecoder::pause() {
    if (!pipeline_) return false;
    GstStateChangeReturn r = gst_element_set_state(pipeline_, GST_STATE_PAUSED);
    SDL_Log("[ndl] pause set_state=%d", (int)r);
    if (r != GST_STATE_CHANGE_FAILURE) paused_.store(true);
    return r != GST_STATE_CHANGE_FAILURE;
}

bool NdlDecoder::resume() {
    if (!pipeline_) return false;
    GstStateChangeReturn r = gst_element_set_state(pipeline_, GST_STATE_PLAYING);
    SDL_Log("[ndl] resume set_state=%d", (int)r);
    if (r != GST_STATE_CHANGE_FAILURE) paused_.store(false);
    return r != GST_STATE_CHANGE_FAILURE;
}

double NdlDecoder::positionSeconds() const {
    if (!pipeline_) return 0.0;
    gint64 pos_ns = 0;
    if (gst_element_query_position(pipeline_, GST_FORMAT_TIME, &pos_ns) && pos_ns >= 0) {
        return pos_ns / 1e9;
    }
    // Fallback : dernier PTS vu par onVideoSample.
    long long p = last_pts_ns_.load();
    if (p >= 0) return p / 1e9;
    return 0.0;
}

double NdlDecoder::durationSeconds() const {
    if (!pipeline_) return 0.0;
    gint64 dur_ns = 0;
    if (gst_element_query_duration(pipeline_, GST_FORMAT_TIME, &dur_ns) && dur_ns > 0) {
        return dur_ns / 1e9;
    }
    return 0.0;
}

bool NdlDecoder::seekRelative(int delta_seconds) {
    if (!pipeline_) return false;
    gint64 pos_ns = 0;
    if (!gst_element_query_position(pipeline_, GST_FORMAT_TIME, &pos_ns)) {
        SDL_Log("[ndl] seek: query_position failed");
        return false;
    }
    gint64 target_ns = pos_ns + (gint64)delta_seconds * GST_SECOND;
    if (target_ns < 0) target_ns = 0;
    SDL_Log("[ndl] seek %+ds: %lld -> %lld ns (reload NDL)",
            delta_seconds, (long long)pos_ns, (long long)target_ns);
    // NDL doesn't recover from PTS jumps. Go through NULL, unload+reload NDL,
    // then re-enter PAUSED to do the seek, then PLAYING. This blocks until the
    // streaming thread has drained, so NDL calls don't race with sample pushes.
    gst_element_set_state(pipeline_, GST_STATE_NULL);
    ndl_bridge_unload();
    media_loaded_ = false;
    int rc = ndl_bridge_load(is_h265_ ? 1 : 0, video_width_, video_height_, 0, 0);
    if (rc != 0) {
        SDL_Log("[ndl] seek: reload failed rc=%d", rc);
        return false;
    }
    ndl_bridge_set_area(0, 0, 1920, 1080);
    media_loaded_ = true;
    gst_element_set_state(pipeline_, GST_STATE_PAUSED);
    gst_element_get_state(pipeline_, nullptr, nullptr, 3 * GST_SECOND);
    gboolean ok = gst_element_seek_simple(
        pipeline_, GST_FORMAT_TIME,
        (GstSeekFlags)(GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT),
        target_ns);
    gst_element_set_state(pipeline_, GST_STATE_PLAYING);
    first_pts_ns_ = -1;
    sample_count_ = 0;
    return ok;
}

void NdlDecoder::stop() {
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
        pipeline_ = nullptr;
    }
    if (media_loaded_) {
        // Flush render buffer + cache l'overlay (set area 1×1 hors écran)
        // AVANT unload : sinon le plane HW garde la dernière frame visible
        // jusqu'à ce que le test suivant en dessine par-dessus. Le flush
        // seul ne suffit pas (cf observation utilisateur : 7 Winchester
        // montrait Dangereuse Mission figé).
        ndl_bridge_flush();
        ndl_bridge_set_area(-2, -2, 1, 1);
        ndl_bridge_unload();
        media_loaded_ = false;
    }
    first_pts_ns_ = -1;
    sample_count_ = 0;
    audio_sample_count_ = 0;
}

GstFlowReturn NdlDecoder::onVideoSampleStatic(GstAppSink* sink, void* user) {
    auto* self = static_cast<NdlDecoder*>(user);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_ERROR;
    self->onVideoSample(sample);
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}

GstFlowReturn NdlDecoder::onAudioSampleStatic(GstAppSink* sink, void* user) {
    auto* self = static_cast<NdlDecoder*>(user);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_ERROR;
    self->onAudioSample(sample);
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}

void NdlDecoder::onVideoSample(GstSample* sample) {
    GstBuffer* buf = gst_sample_get_buffer(sample);
    if (!buf) return;

    // Si Load a déjà échoué, on ne retente plus — le watchdog main.cpp
    // basculera vers GstDecoder. Sinon on entrait en boucle infinie de
    // "lazy Load failed" (1 tentative par sample).
    if (error_.load()) return;

    // Lazy Load NDL au premier sample : on utilise les caps attachées au
    // sample (qui sont présentes dès le 1er buffer, pas besoin de preroll).
    // Garantit que le tout 1er sample poussé à NDL est l'IDR H.264 (frame 0
    // ou après KEY_UNIT seek), obligatoire pour que le HW decoder démarre.
    if (!media_loaded_.load()) {
        GstCaps* caps = gst_sample_get_caps(sample);
        int lw = video_width_, lh = video_height_;
        if (caps && gst_caps_get_size(caps) > 0) {
            GstStructure* s = gst_caps_get_structure(caps, 0);
            int w = 0, h = 0;
            if (gst_structure_get_int(s, "width", &w) &&
                gst_structure_get_int(s, "height", &h) && w > 0 && h > 0) {
                lw = w; lh = h;
            }
        }
        SDL_Log("[ndl] Load (lazy) %s %dx%d (hint %dx%d)",
                is_h265_ ? "H265" : "H264", lw, lh,
                video_width_, video_height_);
        int rc = ndl_bridge_load(is_h265_ ? 1 : 0, lw, lh, 0, 0);
        if (rc != 0) {
            // Retry une fois pour HEVC en ajustant la hauteur à un multiple
            // de 16 (certains drivers LG refusent 1080 non-aligné ; Load
            // avec 1088 a été observé OK quand 1080 rc=-1).
            if (is_h265_ && (lh % 16) != 0) {
                int lh16 = ((lh + 15) / 16) * 16;
                SDL_Log("[ndl] retry Load H265 %dx%d (aligned 16)", lw, lh16);
                rc = ndl_bridge_load(1, lw, lh16, 0, 0);
            }
            if (rc != 0) {
                last_error_ = ndl_bridge_last_error();
                SDL_Log("[ndl] lazy Load failed rc=%d err=%s",
                        rc, last_error_.c_str());
                error_.store(true);
                return;
            }
        }
        // Letterbox : respecte l'aspect ratio source, centre avec bandes
        // noires. Sans ça un film 2.40:1 (1920x800) est stretché en 16:9 et
        // apparait étiré verticalement (observation utilisateur 2026-04-24
        // "À cœur ouvert image étirée verticale").
        {
            const int screen_w = 1920, screen_h = 1080;
            int aw = screen_w, ah = screen_h, ax = 0, ay = 0;
            if (lw > 0 && lh > 0) {
                // fit = min(screen_w/lw, screen_h/lh)
                double sx = (double)screen_w / lw;
                double sy = (double)screen_h / lh;
                double s  = (sx < sy) ? sx : sy;
                aw = (int)(lw * s);
                ah = (int)(lh * s);
                ax = (screen_w - aw) / 2;
                ay = (screen_h - ah) / 2;
            }
            SDL_Log("[ndl] set_area letterbox %dx%d -> (%d,%d %dx%d)",
                    lw, lh, ax, ay, aw, ah);
            ndl_bridge_set_area(ax, ay, aw, ah);
        }
        int fd_rc = ndl_bridge_set_frame_drop_threshold(10);
        SDL_Log("[ndl] SetFrameDropThreshold(10) rc=%d", fd_rc);
        video_width_ = lw;
        video_height_ = lh;
        media_loaded_.store(true);
    }

    GstMapInfo map;
    if (!gst_buffer_map(buf, &map, GST_MAP_READ)) return;
    long long pts_ns = GST_BUFFER_PTS(buf);
    // PTS en microsecondes : confirmé par hw_poc (140+ runs smooth en
    // us-stream). L'expérience ms n'apportait rien, on revient au us.
    long long pts_us = (pts_ns != (long long)GST_CLOCK_TIME_NONE) ? (pts_ns / 1000) : 0;
    if (first_pts_ns_ < 0 && pts_ns != (long long)GST_CLOCK_TIME_NONE) {
        first_pts_ns_ = pts_ns;
        bool is_keyframe = !GST_BUFFER_FLAG_IS_SET(buf, GST_BUFFER_FLAG_DELTA_UNIT);
        SDL_Log("[ndl] first video sample size=%u pts_ns=%lld pts_us=%lld IDR=%d",
                (unsigned)map.size, pts_ns, pts_us, (int)is_keyframe);
    }
    if (pts_ns != (long long)GST_CLOCK_TIME_NONE) last_pts_ns_.store(pts_ns);
    sample_count_++;
    if (sample_count_ % 60 == 0) {
        int bufl = ndl_bridge_get_render_buffer_length();
        SDL_Log("[ndl] video samples=%u pts_us=%lld ndl_buf=%d",
                sample_count_, pts_us, bufl);
    }
    int rc = ndl_bridge_play_video(map.data, (unsigned)map.size, pts_us);
    if (rc != 0) {
        last_error_ = ndl_bridge_last_error();
        SDL_Log("[ndl] play_video rc=%d err=%s", rc, last_error_.c_str());
        error_.store(true);
    }
    gst_buffer_unmap(buf, &map);
}

void NdlDecoder::onAudioSample(GstSample* sample) {
    GstBuffer* buf = gst_sample_get_buffer(sample);
    if (!buf) return;
    GstMapInfo map;
    if (!gst_buffer_map(buf, &map, GST_MAP_READ)) return;
    long long pts_ns = GST_BUFFER_PTS(buf);
    long long pts_us = (pts_ns != (long long)GST_CLOCK_TIME_NONE) ? (pts_ns / 1000) : 0;
    audio_sample_count_++;
    if (audio_sample_count_ == 1) {
        SDL_Log("[ndl] first audio sample size=%u pts_us=%lld", (unsigned)map.size, pts_us);
    }
    if (audio_sample_count_ % 100 == 0) {
        SDL_Log("[ndl] audio samples=%u pts_us=%lld", audio_sample_count_, pts_us);
    }
    int rc = ndl_bridge_play_audio_pcm(map.data, (unsigned)map.size, pts_us);
    if (rc != 0) {
        last_error_ = ndl_bridge_last_error();
        SDL_Log("[ndl] play_audio rc=%d err=%s", rc, last_error_.c_str());
    }
    gst_buffer_unmap(buf, &map);
}

}  // namespace iptv
