#pragma once
// Minimal GStreamer-backed video decoder for the PoC.
// Pipeline: filesrc -> decodebin -> videoconvert -> appsink (I420)
// Frames are pulled from the appsink and pushed to a callback supplied by the caller.

#include <atomic>
#include <cstdint>
#include <functional>
#include <string>

#include <glib.h>

extern "C" {
struct _GstElement;
typedef struct _GstElement GstElement;
struct _GstBus;
typedef struct _GstBus GstBus;
struct _GstPad;
typedef struct _GstPad GstPad;
struct _GstMessage;
typedef struct _GstMessage GstMessage;
}

namespace iptv {

struct VideoFrame {
    int width = 0;
    int height = 0;
    // I420 / IYUV planes. Y full size, U and V half-width/half-height.
    const uint8_t* y = nullptr;
    const uint8_t* u = nullptr;
    const uint8_t* v = nullptr;
    int y_stride = 0;
    int u_stride = 0;
    int v_stride = 0;
    int64_t pts_ns = 0;  // PTS in nanoseconds (GST_CLOCK_TIME)
};

class GstDecoder {
public:
    using FrameCallback = std::function<void(const VideoFrame&)>;

    GstDecoder();
    ~GstDecoder();

    GstDecoder(const GstDecoder&) = delete;
    GstDecoder& operator=(const GstDecoder&) = delete;

    // Toggle real-time playback (sync=TRUE on sinks, AV synced) vs. fast-as-possible
    // (sync=FALSE, useful for benchmarks). Default: real-time. Must be called before open().
    void setRealtime(bool realtime) { realtime_ = realtime; }

    // Toggle audio output. Default: enabled. Must be called before open().
    void setAudioEnabled(bool enabled) { audio_enabled_ = enabled; }

    // Open a local file. Returns false on error.
    bool open(const std::string& uri_or_path);

    void setFrameCallback(FrameCallback cb) { on_frame_ = std::move(cb); }

    bool play();
    bool pause();
    void stop();

    // Seek to an absolute position in seconds. Returns false if the pipeline is not seekable.
    bool seekSeconds(double seconds);
    // Relative seek in seconds (negative = rewind).
    bool seekRelative(double delta_seconds);

    // Current playback position in seconds (0 if unknown).
    double positionSeconds() const;
    // Total duration in seconds (0 if unknown — live streams typically return 0).
    double durationSeconds() const;

    bool eos() const { return eos_.load(); }
    bool hasError() const { return error_.load(); }
    std::string lastError() const { return last_error_; }

    int width() const { return width_; }
    int height() const { return height_; }

    // Track enumeration / selection. Available after the pipeline reaches PAUSED state.
    int audioTrackCount() const;
    int currentAudioTrack() const;
    void setAudioTrack(int index);   // -1 disables audio

    int subtitleTrackCount() const;
    int currentSubtitleTrack() const;  // -1 = off
    void setSubtitleTrack(int index);  // -1 disables subtitles
    void setSubtitlesVisible(bool visible);

private:
    static int onNewSample(GstElement* sink, gpointer user);  // returns GstFlowReturn (int)
    static int onBusMessage(GstBus* bus, GstMessage* msg, gpointer user);  // gboolean

    // Pipeline = playbin with custom video/audio sink bins.
    GstElement* pipeline_      = nullptr;   // playbin
    GstElement* video_sink_bin_ = nullptr;
    GstElement* audio_sink_bin_ = nullptr;
    GstElement* video_convert_ = nullptr;
    GstElement* video_sink_    = nullptr;   // appsink we pull frames from
    GstElement* audio_convert_ = nullptr;
    GstElement* audio_resample_ = nullptr;
    GstElement* audio_sink_    = nullptr;
    unsigned int bus_watch_id_ = 0;

    FrameCallback on_frame_;
    std::atomic<bool> eos_{false};
    std::atomic<bool> error_{false};
    std::string last_error_;
    int width_ = 0;
    int height_ = 0;
    bool realtime_      = true;
    bool audio_enabled_ = true;
};

}  // namespace iptv
