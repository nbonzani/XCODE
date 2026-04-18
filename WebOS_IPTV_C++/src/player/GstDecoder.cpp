#include "player/GstDecoder.h"

#include <cstdio>
#include <cstring>

#include <SDL2/SDL_log.h>

#include <gst/gst.h>
#include <gst/app/gstappsink.h>
#include <gst/video/video.h>

namespace iptv {

GstDecoder::GstDecoder() {
    static bool inited = false;
    if (!inited) {
        setenv("GST_PLUGIN_FEATURE_RANK", "lxvideodec:NONE,dvbin:NONE", 1);
        gst_init(nullptr, nullptr);

        // Also downrank LG's hardware decoders in the live registry — the env var
        // is read at registry build time but some factories are registered after.
        GstRegistry* reg = gst_registry_get();
        for (const char* name : {"lxvideodec", "dvbin", "lxaudiodec", "lxvideodecmpeg4",
                                  "lxvideodech264", "lxvideodech265"}) {
            if (GstElementFactory* f = gst_element_factory_find(name)) {
                gst_plugin_feature_set_rank(GST_PLUGIN_FEATURE(f), GST_RANK_NONE);
                SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] downrank %s -> NONE", name);
                gst_object_unref(f);
            }
        }
        // Boost software decoder ranks so decodebin picks them.
        for (const char* name : {"avdec_mpeg4", "avdec_h264", "avdec_h265", "avdec_mpeg2video"}) {
            if (GstElementFactory* f = gst_element_factory_find(name)) {
                gst_plugin_feature_set_rank(GST_PLUGIN_FEATURE(f),
                                             static_cast<guint>(GST_RANK_PRIMARY + 10));
                SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] boost %s rank", name);
                gst_object_unref(f);
            } else {
                SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] %s not found on TV", name);
            }
        }
        // Enumerate EVERY decoder the TV actually has so we know what else exists
        // (useful to find lxvideodec sub-types like lxvp9, lxav1, etc.).
        GList* list = gst_element_factory_list_get_elements(
            GST_ELEMENT_FACTORY_TYPE_DECODER, GST_RANK_MARGINAL);
        for (GList* l = list; l; l = l->next) {
            auto* f = GST_ELEMENT_FACTORY(l->data);
            SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] decoder present: %s (rank=%u)",
                        GST_OBJECT_NAME(f),
                        gst_plugin_feature_get_rank(GST_PLUGIN_FEATURE(f)));
        }
        gst_plugin_feature_list_free(list);
        (void)reg;
        inited = true;
    }
}

GstDecoder::~GstDecoder() {
    stop();
}

namespace {
// Convert a local path to a file:// URI; pass through full URIs unchanged.
std::string toUri(const std::string& path) {
    if (path.compare(0, 7, "http://") == 0 ||
        path.compare(0, 8, "https://") == 0 ||
        path.compare(0, 7, "file://") == 0 ||
        path.compare(0, 6, "rtsp://") == 0 ||
        path.compare(0, 7, "rtmp://") == 0) {
        return path;
    }
    gchar* uri = gst_filename_to_uri(path.c_str(), nullptr);
    std::string out = uri ? uri : ("file://" + path);
    if (uri) g_free(uri);
    return out;
}

// Wrap a sink chain inside a bin with a ghost "sink" pad so playbin can use it
// as a single video-sink / audio-sink. Pipeline: ghost-sink -> first -> ... -> last.
GstElement* makeSinkBin(const char* binName, GstElement* first, GstElement* /*last*/) {
    GstElement* bin = gst_bin_new(binName);
    GstPad* pad = gst_element_get_static_pad(first, "sink");
    gst_element_add_pad(bin, gst_ghost_pad_new("sink", pad));
    gst_object_unref(pad);
    return bin;
}

// playbin "flags" bits — keep only what we explicitly want enabled.
constexpr int PLAY_FLAG_VIDEO = (1 << 0);
constexpr int PLAY_FLAG_AUDIO = (1 << 1);
constexpr int PLAY_FLAG_TEXT  = (1 << 2);
}  // namespace

bool GstDecoder::open(const std::string& path) {
    pipeline_ = gst_element_factory_make("playbin", "iptv-playbin");
    if (!pipeline_) {
        last_error_ = "failed to create playbin (gst-plugins-base missing?)";
        error_ = true;
        return false;
    }

    // Video sink bin: videoconvert -> appsink (I420).
    video_convert_ = gst_element_factory_make("videoconvert", "vconvert");
    video_sink_    = gst_element_factory_make("appsink",      "vsink");
    if (!video_convert_ || !video_sink_) {
        last_error_ = "failed to create video sink elements";
        error_ = true;
        return false;
    }
    GstCaps* caps = gst_caps_new_simple("video/x-raw",
                                        "format", G_TYPE_STRING, "I420",
                                        nullptr);
    g_object_set(video_sink_,
                 "caps",         caps,
                 "emit-signals", TRUE,
                 "sync",         realtime_ ? TRUE : FALSE,
                 "max-buffers",  2,
                 "drop",         FALSE,
                 nullptr);
    gst_caps_unref(caps);
    g_signal_connect(video_sink_, "new-sample", G_CALLBACK(&GstDecoder::onNewSample), this);

    video_sink_bin_ = gst_bin_new("vbin");
    gst_bin_add_many(GST_BIN(video_sink_bin_), video_convert_, video_sink_, nullptr);
    if (!gst_element_link(video_convert_, video_sink_)) {
        last_error_ = "link videoconvert -> appsink failed"; error_ = true; return false;
    }
    {
        GstPad* p = gst_element_get_static_pad(video_convert_, "sink");
        gst_element_add_pad(video_sink_bin_, gst_ghost_pad_new("sink", p));
        gst_object_unref(p);
    }
    g_object_set(pipeline_, "video-sink", video_sink_bin_, nullptr);

    int flags = PLAY_FLAG_VIDEO;
    if (audio_enabled_) {
        audio_convert_  = gst_element_factory_make("audioconvert",  "aconvert");
        audio_resample_ = gst_element_factory_make("audioresample", "aresample");
        audio_sink_     = gst_element_factory_make("autoaudiosink", "asink");
        if (!audio_convert_ || !audio_resample_ || !audio_sink_) {
            SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] audio branch unavailable, video-only\n");
            if (audio_convert_)  gst_object_unref(audio_convert_);
            if (audio_resample_) gst_object_unref(audio_resample_);
            if (audio_sink_)     gst_object_unref(audio_sink_);
            audio_convert_ = audio_resample_ = audio_sink_ = nullptr;
        } else {
            g_object_set(audio_sink_, "sync", realtime_ ? TRUE : FALSE, nullptr);
            audio_sink_bin_ = gst_bin_new("abin");
            gst_bin_add_many(GST_BIN(audio_sink_bin_),
                             audio_convert_, audio_resample_, audio_sink_, nullptr);
            gst_element_link_many(audio_convert_, audio_resample_, audio_sink_, nullptr);
            GstPad* p = gst_element_get_static_pad(audio_convert_, "sink");
            gst_element_add_pad(audio_sink_bin_, gst_ghost_pad_new("sink", p));
            gst_object_unref(p);
            g_object_set(pipeline_, "audio-sink", audio_sink_bin_, nullptr);
            flags |= PLAY_FLAG_AUDIO;
        }
    }
    flags |= PLAY_FLAG_TEXT;  // let playbin overlay subtitles into the video stream
    g_object_set(pipeline_, "flags", flags, nullptr);

    std::string uri = toUri(path);
    g_object_set(pipeline_, "uri", uri.c_str(), nullptr);

    // Configure the HTTP source when playbin spins it up (user-agent, cookies,
    // timeouts). Xtream CDNs often reject default GStreamer UAs and require
    // following a 302 that souphttpsrc handles itself if automatic-redirect is on.
    g_signal_connect(pipeline_, "source-setup",
        G_CALLBACK(+[](GstElement*, GstElement* source, gpointer) {
            if (!source) return;
            GObjectClass* cls = G_OBJECT_GET_CLASS(source);
            if (g_object_class_find_property(cls, "user-agent")) {
                g_object_set(source, "user-agent", "VLC/3.0.16 LibVLC/3.0.16", nullptr);
            }
            if (g_object_class_find_property(cls, "automatic-redirect")) {
                g_object_set(source, "automatic-redirect", TRUE, nullptr);
            }
            if (g_object_class_find_property(cls, "timeout")) {
                g_object_set(source, "timeout", 15u, nullptr);
            }
            SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION,
                        "[gst] source-setup on %s", GST_ELEMENT_NAME(source));
        }), nullptr);

    GstBus* bus = gst_pipeline_get_bus(GST_PIPELINE(pipeline_));
    bus_watch_id_ = gst_bus_add_watch(bus, &GstDecoder::onBusMessage, this);
    gst_object_unref(bus);

    return true;
}

bool GstDecoder::play() {
    if (!pipeline_) return false;
    GstStateChangeReturn r = gst_element_set_state(pipeline_, GST_STATE_PLAYING);
    return r != GST_STATE_CHANGE_FAILURE;
}

bool GstDecoder::pause() {
    if (!pipeline_) return false;
    return gst_element_set_state(pipeline_, GST_STATE_PAUSED) != GST_STATE_CHANGE_FAILURE;
}

void GstDecoder::stop() {
    if (bus_watch_id_) {
        g_source_remove(bus_watch_id_);
        bus_watch_id_ = 0;
    }
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
        pipeline_ = nullptr;
    }
}

bool GstDecoder::seekSeconds(double seconds) {
    if (!pipeline_ || seconds < 0) return false;
    gint64 pos_ns = static_cast<gint64>(seconds * GST_SECOND);
    return gst_element_seek_simple(
        pipeline_, GST_FORMAT_TIME,
        static_cast<GstSeekFlags>(GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT),
        pos_ns);
}

bool GstDecoder::seekRelative(double delta_seconds) {
    double cur = positionSeconds();
    double target = cur + delta_seconds;
    if (target < 0) target = 0;
    double dur = durationSeconds();
    if (dur > 0 && target > dur - 1) target = dur - 1;
    return seekSeconds(target);
}

double GstDecoder::positionSeconds() const {
    if (!pipeline_) return 0.0;
    gint64 ns = 0;
    if (!gst_element_query_position(pipeline_, GST_FORMAT_TIME, &ns)) return 0.0;
    return static_cast<double>(ns) / static_cast<double>(GST_SECOND);
}

double GstDecoder::durationSeconds() const {
    if (!pipeline_) return 0.0;
    gint64 ns = 0;
    if (!gst_element_query_duration(pipeline_, GST_FORMAT_TIME, &ns)) return 0.0;
    return static_cast<double>(ns) / static_cast<double>(GST_SECOND);
}

int GstDecoder::audioTrackCount() const {
    if (!pipeline_) return 0;
    gint n = 0;
    g_object_get(pipeline_, "n-audio", &n, nullptr);
    return n;
}

int GstDecoder::currentAudioTrack() const {
    if (!pipeline_) return -1;
    gint cur = -1;
    g_object_get(pipeline_, "current-audio", &cur, nullptr);
    return cur;
}

void GstDecoder::setAudioTrack(int index) {
    if (!pipeline_) return;
    g_object_set(pipeline_, "current-audio", index, nullptr);
}

int GstDecoder::subtitleTrackCount() const {
    if (!pipeline_) return 0;
    gint n = 0;
    g_object_get(pipeline_, "n-text", &n, nullptr);
    return n;
}

int GstDecoder::currentSubtitleTrack() const {
    if (!pipeline_) return -1;
    gint cur = -1;
    g_object_get(pipeline_, "current-text", &cur, nullptr);
    return cur;
}

void GstDecoder::setSubtitleTrack(int index) {
    if (!pipeline_) return;
    g_object_set(pipeline_, "current-text", index, nullptr);
}

void GstDecoder::setSubtitlesVisible(bool visible) {
    if (!pipeline_) return;
    gint flags = 0;
    g_object_get(pipeline_, "flags", &flags, nullptr);
    if (visible) flags |=  PLAY_FLAG_TEXT;
    else         flags &= ~PLAY_FLAG_TEXT;
    g_object_set(pipeline_, "flags", flags, nullptr);
}

int GstDecoder::onNewSample(GstElement* sink, gpointer user) {
    auto* self = static_cast<GstDecoder*>(user);
    GstSample* sample = gst_app_sink_pull_sample(GST_APP_SINK(sink));
    if (!sample) return 1;  // GST_FLOW_ERROR

    GstBuffer* buf = gst_sample_get_buffer(sample);
    GstCaps* caps = gst_sample_get_caps(sample);
    GstVideoInfo info;
    if (!gst_video_info_from_caps(&info, caps)) {
        gst_sample_unref(sample);
        return 1;
    }

    GstVideoFrame vf;
    if (!gst_video_frame_map(&vf, &info, buf, GST_MAP_READ)) {
        gst_sample_unref(sample);
        return 1;
    }

    self->width_  = vf.info.width;
    self->height_ = vf.info.height;

    VideoFrame f;
    f.width    = vf.info.width;
    f.height   = vf.info.height;
    f.y        = static_cast<uint8_t*>(GST_VIDEO_FRAME_PLANE_DATA(&vf, 0));
    f.u        = static_cast<uint8_t*>(GST_VIDEO_FRAME_PLANE_DATA(&vf, 1));
    f.v        = static_cast<uint8_t*>(GST_VIDEO_FRAME_PLANE_DATA(&vf, 2));
    f.y_stride = GST_VIDEO_FRAME_PLANE_STRIDE(&vf, 0);
    f.u_stride = GST_VIDEO_FRAME_PLANE_STRIDE(&vf, 1);
    f.v_stride = GST_VIDEO_FRAME_PLANE_STRIDE(&vf, 2);
    f.pts_ns   = static_cast<int64_t>(GST_BUFFER_PTS(buf));

    if (self->on_frame_) self->on_frame_(f);

    gst_video_frame_unmap(&vf);
    gst_sample_unref(sample);
    return 0;  // GST_FLOW_OK
}

int GstDecoder::onBusMessage(GstBus*, GstMessage* msg, gpointer user) {
    auto* self = static_cast<GstDecoder*>(user);
    switch (GST_MESSAGE_TYPE(msg)) {
        case GST_MESSAGE_EOS:
            self->eos_ = true;
            SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] EOS\n");
            break;
        case GST_MESSAGE_ERROR: {
            GError* err = nullptr;
            gchar* dbg = nullptr;
            gst_message_parse_error(msg, &err, &dbg);
            self->last_error_ = err ? err->message : "unknown gst error";
            self->error_ = true;
            SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] ERROR: %s (%s)\n",
                         err ? err->message : "?", dbg ? dbg : "");
            if (err) g_error_free(err);
            if (dbg) g_free(dbg);
            break;
        }
        case GST_MESSAGE_STATE_CHANGED:
            if (GST_MESSAGE_SRC(msg) == GST_OBJECT(self->pipeline_)) {
                GstState oldS, newS;
                gst_message_parse_state_changed(msg, &oldS, &newS, nullptr);
                SDL_LogInfo(SDL_LOG_CATEGORY_APPLICATION, "[gst] state %s -> %s\n",
                             gst_element_state_get_name(oldS),
                             gst_element_state_get_name(newS));
            }
            break;
        default:
            break;
    }
    return 1;  // TRUE = keep watching
}

}  // namespace iptv
