#include "player/SwDecoder.h"

#include <cstring>
#include <unistd.h>

#include <SDL2/SDL_log.h>
#include <gst/video/video.h>

namespace iptv {

SwDecoder::SwDecoder() {
    gst_init(nullptr, nullptr);
    // Partage la même politique de rank que GstDecoder : on pousse les HW
    // decoders (lxvideodec* & co) à NONE pour que decodebin choisisse nos
    // décodeurs software avdec_X. Sinon lxvideodec est autoplugged et écrit
    // vers l'overlay HW — invisible pour l'appsink + le renderer SDL.
    static bool ranked = false;
    if (!ranked) {
        // Force-load du libgstlibav bundlé (mêmes raisons que GstDecoder :
        // GST_PLUGIN_PATH n'override pas le libav système). Nécessaire pour
        // avoir avdec_mpeg4, avdec_msmpeg4v3, etc. côté decodebin.
        char selfdir[512] = {0};
        ssize_t n = readlink("/proc/self/exe", selfdir, sizeof(selfdir) - 1);
        if (n > 0) {
            selfdir[n] = 0;
            if (char* slash = strrchr(selfdir, '/')) *slash = 0;
            std::string path = std::string(selfdir) + "/lib/gstreamer-1.0/libgstlibav.so";
            GError* err = nullptr;
            GstPlugin* p = gst_plugin_load_file(path.c_str(), &err);
            if (p) {
                SDL_Log("[sw] force-loaded bundled libav: %s", path.c_str());
                gst_object_unref(p);
            } else {
                SDL_Log("[sw] bundled libav load failed: %s",
                        err ? err->message : "?");
                if (err) g_error_free(err);
            }
        }
        GstRegistry* reg = gst_registry_get();
        for (const char* name : {"lxvideodec", "dvbin", "lxaudiodec",
                                  "lxvideodecmpeg4", "lxvideodech264",
                                  "lxvideodech265", "omx_lxvideodec",
                                  "lxaudiodecac3", "lxaudiodecaac",
                                  "lxaudiodecmp3", "ac3_audiodec",
                                  "aac_audiodec"}) {
            if (GstElementFactory* f = gst_element_factory_find(name)) {
                gst_plugin_feature_set_rank(GST_PLUGIN_FEATURE(f), GST_RANK_NONE);
                gst_object_unref(f);
            }
        }
        for (const char* name : {"avdec_mpeg4", "avdec_h264", "avdec_h265",
                                  "avdec_mpeg2video", "avdec_msmpeg4",
                                  "avdec_msmpeg4v1", "avdec_msmpeg4v2",
                                  "avdec_msmpeg4v3",
                                  "avdec_ac3", "avdec_aac", "avdec_mp3"}) {
            if (GstElementFactory* f = gst_element_factory_find(name)) {
                gst_plugin_feature_set_rank(GST_PLUGIN_FEATURE(f),
                                             GST_RANK_PRIMARY + 10);
                gst_object_unref(f);
            }
        }
        (void)reg;
        ranked = true;
    }
}

SwDecoder::~SwDecoder() { stop(); }

bool SwDecoder::open(const std::string& uri, const std::string& codec) {
    stop();

    auto ends_with = [&uri](const char* suf) {
        size_t n = std::strlen(suf);
        return uri.size() >= n && uri.compare(uri.size() - n, n, suf) == 0;
    };
    const bool is_http = uri.compare(0, 7, "http://") == 0 ||
                         uri.compare(0, 8, "https://") == 0;

    std::string src;
    if (is_http) {
        // use-buffering=true requiert qu'un owner gère les messages de
        // buffering (playbin le fait). Ici on a un pipeline manuel :
        // avec use-buffering=true la transition PAUSED→PLAYING reste
        // bloquée tant que la queue2 n'a pas atteint 100%, et le
        // video appsink (sync=true, max-buffers=4) bloque upstream,
        // créant un deadlock. On désactive donc use-buffering.
        src = "souphttpsrc location=" + uri + " automatic-redirect=true ! "
              "queue2 max-size-buffers=0 max-size-bytes=16777216 "
              "max-size-time=10000000000";
    } else {
        std::string path = uri;
        if (path.compare(0, 7, "file://") == 0) path.erase(0, 7);
        src = "filesrc location=\"" + path + "\"";
    }

    const char* demux;
    if (ends_with(".mp4") || ends_with(".m4v")) demux = "qtdemux";
    else if (ends_with(".avi"))                 demux = "avidemux";
    else                                        demux = "matroskademux";

    // On laisse decodebin autoplug le parseur + décodeur vidéo du codec qu'il
    // détecte sur le pad vidéo. On préfixe le pad avec queue pour découpler
    // demuxer/décodeur (évite quelques dead-locks). À la sortie du décodeur
    // on force I420 via videoconvert + capsfilter, puis appsink qui délivre
    // à notre callback.
    // On définit codec-specific parser+decoder explicites (pas decodebin) parce
    // que gst-parse-launch + decodebin sur deux pads dynamiques se négocie mal
    // (observé : pipeline coince à PAUSED sans erreur).
    const char* vchain;
    if (codec == "msmpeg4" || codec == "msmpeg4v3") {
        vchain = "queue ! avdec_msmpeg4v3 ! videoconvert ! "
                 "video/x-raw,format=I420 ! "
                 "appsink name=vsink emit-signals=true sync=true max-buffers=4 drop=false";
    } else {  // mpeg4 ASP / SP
        vchain = "queue ! mpeg4vparse ! avdec_mpeg4 ! videoconvert ! "
                 "video/x-raw,format=I420 ! "
                 "appsink name=vsink emit-signals=true sync=true max-buffers=4 drop=false";
    }

    // Audio : si skip_audio → fakesink ; sinon pulsesink avec chaîne explicite
    // si on connaît le codec (ac3/eac3 surtout — evite le decodebin qui
    // rechoisit lxaudiodec* et sort des caps 5.1(side) qui craquent).
    const char* aparse = nullptr;
    const char* adec   = nullptr;
    if (audio_codec_ == "ac3")       { aparse = "ac3parse";       adec = "avdec_ac3"; }
    else if (audio_codec_ == "eac3") { aparse = "ac3parse";       adec = "avdec_eac3"; }
    else if (audio_codec_ == "aac")  { aparse = "aacparse";       adec = "avdec_aac"; }
    else if (audio_codec_ == "mp3")  { aparse = "mpegaudioparse"; adec = "avdec_mp3"; }
    std::string audio_branch;
    if (skip_audio_) {
        audio_branch = "demux. ! queue ! fakesink sync=false async=false";
    } else if (aparse && adec) {
        // Capsfilter downmix ≤2ch + rate 48k avant pulsesink : évite les
        // "wrong size" quand avdec sort du 5.1 ou d'un rate atypique.
        audio_branch = std::string("demux. ! queue ! ") + aparse + " ! " + adec +
                       " ! audioconvert ! audioresample ! "
                       "audio/x-raw,format=S16LE,channels=2,rate=48000 ! "
                       "pulsesink sync=false provide-clock=false async-handling=true";
    } else {
        audio_branch = "demux. ! queue ! decodebin ! audioconvert ! audioresample ! "
                       "audio/x-raw,format=S16LE,channels=2,rate=48000 ! "
                       "pulsesink sync=true provide-clock=false async-handling=true";
    }
    std::string desc =
        src + " ! " + demux + " name=demux "
        "demux. ! " + vchain + " " + audio_branch;

    (void)codec;  // decodebin autoplug : on n'a pas besoin du codec exact ici.

    SDL_Log("[sw] open: parse_launch desc=%s", desc.c_str());
    GError* err = nullptr;
    pipeline_ = gst_parse_launch(desc.c_str(), &err);
    if (!pipeline_) {
        last_error_ = err ? err->message : "parse_launch failed";
        SDL_Log("[sw] parse_launch FAILED: %s", last_error_.c_str());
        if (err) g_error_free(err);
        return false;
    }
    GstElement* vsink = gst_bin_get_by_name(GST_BIN(pipeline_), "vsink");
    if (vsink) {
        g_signal_connect(vsink, "new-sample",
                         G_CALLBACK(&SwDecoder::onVideoSampleStatic), this);
        gst_object_unref(vsink);
    }

    // Bus watcher identique au NdlDecoder : state transitions + warnings +
    // errors pour faciliter le diagnostic.
    GstBus* bus = gst_pipeline_get_bus(GST_PIPELINE(pipeline_));
    gst_bus_add_watch(bus, [](GstBus*, GstMessage* msg, gpointer) -> gboolean {
        const gchar* s = GST_MESSAGE_SRC_NAME(msg) ? GST_MESSAGE_SRC_NAME(msg) : "?";
        if (GST_MESSAGE_TYPE(msg) == GST_MESSAGE_ERROR) {
            GError* e = nullptr; gchar* dbg = nullptr;
            gst_message_parse_error(msg, &e, &dbg);
            SDL_Log("[sw-bus] ERROR from %s: %s (%s)", s,
                    e ? e->message : "?", dbg ? dbg : "");
            if (e) g_error_free(e);
            if (dbg) g_free(dbg);
        } else if (GST_MESSAGE_TYPE(msg) == GST_MESSAGE_WARNING) {
            GError* e = nullptr; gchar* dbg = nullptr;
            gst_message_parse_warning(msg, &e, &dbg);
            SDL_Log("[sw-bus] WARN from %s: %s", s, e ? e->message : "?");
            if (e) g_error_free(e);
            if (dbg) g_free(dbg);
        } else if (GST_MESSAGE_TYPE(msg) == GST_MESSAGE_STATE_CHANGED) {
            GstState oldS, newS;
            gst_message_parse_state_changed(msg, &oldS, &newS, nullptr);
            SDL_Log("[sw-bus] %s state %s -> %s", s,
                    gst_element_state_get_name(oldS),
                    gst_element_state_get_name(newS));
        } else if (GST_MESSAGE_TYPE(msg) == GST_MESSAGE_QOS) {
            guint64 processed = 0, dropped = 0;
            gst_message_parse_qos_stats(msg, nullptr, &processed, &dropped);
            SDL_Log("[sw-bus] QoS %s processed=%llu dropped=%llu", s,
                    (unsigned long long)processed, (unsigned long long)dropped);
        }
        return TRUE;
    }, nullptr);
    gst_object_unref(bus);

    return true;
}

bool SwDecoder::play() {
    if (!pipeline_) return false;
    if (start_seek_sec_ > 0) {
        gst_element_set_state(pipeline_, GST_STATE_PAUSED);
        gst_element_get_state(pipeline_, nullptr, nullptr, 5 * GST_SECOND);
        gint64 target_ns = (gint64)start_seek_sec_ * GST_SECOND;
        SDL_Log("[sw] pre-play seek to %ds", start_seek_sec_);
        gst_element_seek_simple(
            pipeline_, GST_FORMAT_TIME,
            (GstSeekFlags)(GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT),
            target_ns);
        start_seek_sec_ = 0;
    }
    GstStateChangeReturn r = gst_element_set_state(pipeline_, GST_STATE_PLAYING);
    SDL_Log("[sw] play set_state=%d", (int)r);
    return r != GST_STATE_CHANGE_FAILURE;
}

void SwDecoder::stop() {
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
        pipeline_ = nullptr;
    }
    sample_count_ = 0;
}

GstFlowReturn SwDecoder::onVideoSampleStatic(GstAppSink* sink, void* user) {
    auto* self = static_cast<SwDecoder*>(user);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_ERROR;
    self->onVideoSample(sample);
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}

void SwDecoder::onVideoSample(GstSample* sample) {
    GstBuffer* buf = gst_sample_get_buffer(sample);
    GstCaps* caps  = gst_sample_get_caps(sample);
    if (!buf || !caps) return;

    GstVideoInfo info;
    if (!gst_video_info_from_caps(&info, caps)) return;

    GstVideoFrame vframe;
    if (!gst_video_frame_map(&vframe, &info, buf, GST_MAP_READ)) return;

    SwFrame f;
    f.width    = GST_VIDEO_FRAME_WIDTH(&vframe);
    f.height   = GST_VIDEO_FRAME_HEIGHT(&vframe);
    f.y_stride = GST_VIDEO_FRAME_PLANE_STRIDE(&vframe, 0);
    f.u_stride = GST_VIDEO_FRAME_PLANE_STRIDE(&vframe, 1);
    f.v_stride = GST_VIDEO_FRAME_PLANE_STRIDE(&vframe, 2);
    f.y = (const uint8_t*)GST_VIDEO_FRAME_PLANE_DATA(&vframe, 0);
    f.u = (const uint8_t*)GST_VIDEO_FRAME_PLANE_DATA(&vframe, 1);
    f.v = (const uint8_t*)GST_VIDEO_FRAME_PLANE_DATA(&vframe, 2);

    sample_count_++;
    if (sample_count_ == 1) {
        SDL_Log("[sw] first frame %dx%d strides=%d/%d/%d",
                f.width, f.height, f.y_stride, f.u_stride, f.v_stride);
    } else if (sample_count_ % 60 == 0) {
        SDL_Log("[sw] frames=%u", sample_count_);
    }
    if (on_frame_) on_frame_(f);

    gst_video_frame_unmap(&vframe);
}

}  // namespace iptv
