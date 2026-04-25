#include "player/SwDecoder.h"

#include <cstring>
#include <unistd.h>
#include <dlfcn.h>

#include <SDL2/SDL_log.h>
#include <gst/video/video.h>

namespace iptv {

SwDecoder::SwDecoder() {
    gst_init(nullptr, nullptr);
    static bool ranked = false;
    if (!ranked) {
        // Évincer libav TV (qui rejette DivX) AVANT de charger libaviptv
        // pour éviter conflit de factory names avdec_mpeg4 etc.
        GstRegistry* reg0 = gst_registry_get();
        if (GstPlugin* old = gst_registry_find_plugin(reg0, "libav")) {
            gst_registry_remove_plugin(reg0, old);
            gst_object_unref(old);
            SDL_Log("[sw] evicted TV libav plugin");
        }
        // Force-load notre libgstlibaviptv.so (FFmpeg 4.4 sans check anti-DivX)
        char selfdir[512] = {0};
        ssize_t nr = readlink("/proc/self/exe", selfdir, sizeof(selfdir) - 1);
        if (nr > 0) {
            selfdir[nr] = 0;
            if (char* slash = strrchr(selfdir, '/')) *slash = 0;
            std::string path = std::string(selfdir) + "/lib/gstreamer-1.0/libgstlibaviptv.so";
            GError* err = nullptr;
            GstPlugin* p = gst_plugin_load_file(path.c_str(), &err);
            if (p) {
                SDL_Log("[sw] force-loaded gst-libav-iptv");
                gst_object_unref(p);
            } else {
                SDL_Log("[sw] gst-libav-iptv load failed: %s", err ? err->message : "?");
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
        // Pas de parser : matroska/avi/mp4 fournissent déjà le codec_data adéquat
        // au décodeur. mpeg4vparse était un alias non résolu sur webOS 6.5
        // (factory réelle = mpeg4videoparse), parse_launch le droppait silencieusement.
        vchain = "queue ! avdec_mpeg4 ! videoconvert ! "
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

    // Pour mpeg4 ASP : pad probe sur la sortie de mpeg4vparse pour patcher
    // le codec_data (extradata) en supprimant le marqueur "DivX" qui fait
    // crasher avdec_mpeg4 de la TV (FFmpeg 4.0 a un check anti-DivX
    // historique : `mpeg4 video DivX in extradata! Stop decode due to DivX
    // license`). On remplace les 4 octets ASCII "DivX" par "Xviv" → ffmpeg
    // ne reconnaît plus le marqueur et procède au décodage normalement.
    // Pad probe sur sortie mpeg4vparse pour neutraliser les marqueurs DivX
    // dans codec_data (caps) ET dans chaque buffer. ffmpeg/libavcodec 4.0
    // de la TV refuse de décoder si "DivX" est trouvé en extradata ou en
    // user_data (check anti-DivX historique). On remplace les 4 octets
    // "DivX" par "Xviv" en mémoire — le décodeur ne reconnaît plus le
    // marqueur et procède au décodage normal.
    if (codec == "mpeg4" || codec == "msmpeg4" || codec == "msmpeg4v3") {
        // Iterate through bin to find mpeg4vparse element by class name
        GstElement* parse = nullptr;
        GstIterator* it = gst_bin_iterate_elements(GST_BIN(pipeline_));
        GValue v = G_VALUE_INIT;
        while (gst_iterator_next(it, &v) == GST_ITERATOR_OK) {
            GstElement* e = GST_ELEMENT(g_value_get_object(&v));
            const gchar* name = GST_OBJECT_NAME(e);
            SDL_Log("[sw] pipeline element: %s", name ? name : "?");
            if (name && strstr(name, "mpeg4vparse")) {
                parse = GST_ELEMENT(g_object_ref(e));
            }
            g_value_reset(&v);
        }
        g_value_unset(&v);
        gst_iterator_free(it);
        SDL_Log("[sw] mpeg4vparse: %s", parse ? GST_OBJECT_NAME(parse) : "NOT FOUND");
        if (parse) {
            GstPad* srcpad = gst_element_get_static_pad(parse, "src");
            if (srcpad) {
                auto patch_divx = [](GstBuffer* buf) -> int {
                    GstMapInfo m;
                    if (!gst_buffer_map(buf, &m, GST_MAP_WRITE)) return 0;
                    int patched = 0;
                    for (gsize i = 0; i + 4 <= m.size; ++i) {
                        if (m.data[i]=='D' && m.data[i+1]=='i' &&
                            m.data[i+2]=='v' && m.data[i+3]=='X') {
                            m.data[i]='X'; m.data[i+1]='v';
                            m.data[i+2]='i'; m.data[i+3]='v';
                            patched++;
                        }
                    }
                    gst_buffer_unmap(buf, &m);
                    return patched;
                };
                gst_pad_add_probe(srcpad,
                    (GstPadProbeType)(GST_PAD_PROBE_TYPE_BUFFER |
                                      GST_PAD_PROBE_TYPE_EVENT_DOWNSTREAM),
                    +[](GstPad*, GstPadProbeInfo* info, gpointer user) -> GstPadProbeReturn {
                        auto* patch = static_cast<std::function<int(GstBuffer*)>*>(user);
                        if (info->type & GST_PAD_PROBE_TYPE_EVENT_DOWNSTREAM) {
                            GstEvent* ev = GST_PAD_PROBE_INFO_EVENT(info);
                            if (GST_EVENT_TYPE(ev) != GST_EVENT_CAPS) return GST_PAD_PROBE_OK;
                            GstCaps* caps = nullptr;
                            gst_event_parse_caps(ev, &caps);
                            if (!caps) return GST_PAD_PROBE_OK;
                            // Caps writeable copy
                            GstCaps* w = gst_caps_make_writable(gst_caps_copy(caps));
                            GstStructure* s = gst_caps_get_structure(w, 0);
                            const GValue* cdv = gst_structure_get_value(s, "codec_data");
                            if (cdv) {
                                GstBuffer* cd = gst_value_get_buffer(cdv);
                                if (cd) {
                                    GstBuffer* cdcopy = gst_buffer_copy(cd);
                                    int n = (*patch)(cdcopy);
                                    if (n > 0) {
                                        SDL_Log("[sw] DivX strip codec_data %d occ", n);
                                        GValue v = G_VALUE_INIT;
                                        g_value_init(&v, GST_TYPE_BUFFER);
                                        gst_value_set_buffer(&v, cdcopy);
                                        gst_structure_set_value(s, "codec_data", &v);
                                        g_value_unset(&v);
                                    }
                                    gst_buffer_unref(cdcopy);
                                }
                            }
                            // Replace event with patched caps
                            GstEvent* nev = gst_event_new_caps(w);
                            gst_caps_unref(w);
                            gst_event_unref(ev);
                            GST_PAD_PROBE_INFO_DATA(info) = nev;
                        } else if (info->type & GST_PAD_PROBE_TYPE_BUFFER) {
                            GstBuffer* buf = GST_PAD_PROBE_INFO_BUFFER(info);
                            // Make writable
                            GstBuffer* wbuf = gst_buffer_make_writable(buf);
                            int n = (*patch)(wbuf);
                            if (n > 0) {
                                static int total = 0; total++;
                                if (total <= 3 || total % 100 == 0)
                                    SDL_Log("[sw] DivX strip buf #%d (%d occ)", total, n);
                            }
                            GST_PAD_PROBE_INFO_DATA(info) = wbuf;
                        }
                        return GST_PAD_PROBE_OK;
                    },
                    new std::function<int(GstBuffer*)>(patch_divx),
                    +[](gpointer p){
                        delete static_cast<std::function<int(GstBuffer*)>*>(p);
                    });
                gst_object_unref(srcpad);
                SDL_Log("[sw] DivX-strip pad probe armed on mpeg4vparse");
            }
            gst_object_unref(parse);
        }
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

double SwDecoder::positionSeconds() const {
    if (!pipeline_) return 0.0;
    gint64 pos = 0;
    if (!gst_element_query_position(pipeline_, GST_FORMAT_TIME, &pos)) return 0.0;
    return (double)pos / GST_SECOND;
}

double SwDecoder::durationSeconds() const {
    if (!pipeline_) return 0.0;
    gint64 dur = 0;
    if (!gst_element_query_duration(pipeline_, GST_FORMAT_TIME, &dur)) return 0.0;
    return (double)dur / GST_SECOND;
}

bool SwDecoder::seekRelative(double delta_seconds) {
    if (!pipeline_) return false;
    gint64 pos = 0;
    if (!gst_element_query_position(pipeline_, GST_FORMAT_TIME, &pos)) {
        SDL_Log("[sw] seek: query_position failed");
        return false;
    }
    gint64 target = pos + (gint64)(delta_seconds * GST_SECOND);
    if (target < 0) target = 0;
    SDL_Log("[sw] seek %+ds: %lld -> %lld ns",
            (int)delta_seconds, (long long)pos, (long long)target);
    return gst_element_seek_simple(
        pipeline_, GST_FORMAT_TIME,
        (GstSeekFlags)(GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT),
        target);
}

}  // namespace iptv
