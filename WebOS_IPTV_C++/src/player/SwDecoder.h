#pragma once
// SwDecoder — lecteur software via un pipeline GStreamer MANUEL (pas playbin).
// Utilisé pour les codecs que NdlDecoder ne supporte pas (mpeg4 ASP, msmpeg4v3,
// h264 AVI qui renégocie mal avec NDL). Le pipeline décode en SW puis convertit
// en I420 et livre les frames à un callback que main.cpp rend via SDL
// (comme GstDecoder). Aucune branche audio — fakesink uniquement — on évite
// ainsi le bug AC3 stall de playbin.

#include <atomic>
#include <functional>
#include <string>
#include <vector>

#include <gst/gst.h>
#include <gst/app/gstappsink.h>

namespace iptv {

struct SwFrame {
    int width = 0, height = 0;
    int y_stride = 0, u_stride = 0, v_stride = 0;
    const uint8_t* y = nullptr;
    const uint8_t* u = nullptr;
    const uint8_t* v = nullptr;
};

class SwDecoder {
public:
    using FrameCb = std::function<void(const SwFrame&)>;

    SwDecoder();
    ~SwDecoder();

    bool open(const std::string& uri, const std::string& codec);
    bool play();
    void stop();
    void setStartSeek(int seconds) { start_seek_sec_ = seconds; }
    void setSkipAudio(bool v) { skip_audio_ = v; }
    // Hint codec audio : "ac3"|"eac3"|"aac"|"mp3" → chaîne parse+avdec_*
    // explicite ; sinon decodebin.
    void setAudioCodec(const std::string& c) { audio_codec_ = c; }

    void setFrameCallback(FrameCb cb) { on_frame_ = std::move(cb); }
    bool hasError() const { return error_.load(); }
    const std::string& lastError() const { return last_error_; }
    unsigned int videoSampleCount() const { return sample_count_; }

    // Seek relatif ±sec via gst_element_seek_simple. Pour ←/→ player MPEG-4.
    bool seekRelative(double delta_seconds);
    double positionSeconds() const;
    double durationSeconds() const;

private:
    static GstFlowReturn onVideoSampleStatic(GstAppSink* sink, void* user);
    void onVideoSample(GstSample* sample);

    GstElement* pipeline_ = nullptr;
    int start_seek_sec_ = 0;
    bool skip_audio_ = false;
    std::string audio_codec_;
    FrameCb on_frame_;
    std::atomic<bool> error_{false};
    std::string last_error_;
    unsigned int sample_count_ = 0;
};

}  // namespace iptv
