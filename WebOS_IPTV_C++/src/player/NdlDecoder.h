#pragma once
// Hardware-decoded video path via webOS LG NDL DirectMedia v2.
// PoC: feeds H.264 byte-stream samples (parsed by GStreamer) to NDL_DirectVideoPlay,
// which renders to the HW overlay plane below the SDL window. SDL window must be
// transparent on the video region for the overlay to show through.

#include <atomic>
#include <string>
#include <vector>

#include <gst/gst.h>
#include <gst/app/gstappsink.h>

namespace iptv {

class NdlDecoder {
public:
    NdlDecoder();
    ~NdlDecoder();

    // Initialize the NDL library + register our appId. Must be called once.
    bool init(const std::string& appId);
    void shutdown();

    // Build a pipeline that demuxes + parses (no decoding) and feeds raw
    // byte-stream samples to NDL. codec is "h264" or "hevc".
    bool open(const std::string& filePath, int width, int height,
              const std::string& codec = "h264");
    bool play();
    // Pause / reprise du pipeline GStreamer. NDL video continue à jouer les
    // buffers déjà envoyés sauf si on passe en PAUSED.
    bool pause();
    bool resume();
    bool isPaused() const { return paused_.load(); }
    void stop();
    bool seekRelative(int delta_seconds);

    // Position courante en secondes (depuis le début du stream). -1 si
    // pas encore de frame décodée.
    double positionSeconds() const;
    double durationSeconds() const;

    // Liste des pistes audio détectées (via tag 'language' sur les pads
    // audio du demuxer). Remplie au 1er tick du pad-added signal.
    struct AudioTrack {
        int index = 0;             // ordre d'apparition des pads audio
        std::string language;      // code ISO ("fra", "eng" ou vide)
        std::string codec;         // "ac3", "aac", ...
    };
    const std::vector<AudioTrack>& audioTracks() const { return audio_tracks_; }
    int currentAudioTrack() const { return current_audio_track_; }
    // Sélectionne une piste audio. Sur pipeline statique actuel, nécessite
    // un reload → on le fait via stop() + reopen() avec l'index sauvegardé.
    // Pour la 1re version, on ne fait qu'un no-op visuel ; l'impl complète
    // viendra avec la refonte pad-added.
    void setAudioTrack(int idx) { current_audio_track_ = idx; }
    // Pre-play seek : si > 0, on seek le pipeline à cet offset avant de
    // passer en PLAYING. Évite la pénalité reload NDL d'un seek post-play.
    void setStartSeek(int seconds) { start_seek_sec_ = seconds; }

    bool hasError() const { return error_.load(); }
    const std::string& lastError() const { return last_error_; }
    // Nombre de samples vidéo déjà poussés à NDL. Un watchdog côté app
    // peut surveiller ça pour déclencher un fallback (ex : matroskademux
    // échec de linking quand le codec détecté ne matche pas h264parse).
    unsigned int videoSampleCount() const { return sample_count_; }
    // If set before open(), the audio pad is fakesinked (useful for streams
    // that carry a codec we can't decode: DTS, Dolby TrueHD, etc.).
    void setSkipAudio(bool v) { skip_audio_ = v; }
    // Explicit audio codec hint. Si "ac3"/"eac3", on bâtit une chaîne statique
    // ac3parse ! avdec_{ac3,eac3} ! audioconvert ! audioresample ! pulsesink
    // au lieu de decodebin. Motivation : decodebin autoplug mixait parfois
    // lxaudiodecac3 et/ou sortait des caps 5.1(side) qui craquaient à la
    // downmix pulsesink. La chaîne statique + avdec évite ce trou.
    void setAudioCodec(const std::string& c) { audio_codec_ = c; }

private:
    static GstFlowReturn onVideoSampleStatic(GstAppSink* sink, void* user);
    static GstFlowReturn onAudioSampleStatic(GstAppSink* sink, void* user);
    void onVideoSample(GstSample* sample);
    void onAudioSample(GstSample* sample);

    bool initialized_ = false;
    std::atomic<bool> media_loaded_{false};  // écrit depuis GStreamer callback
    bool is_h265_ = false;
    bool skip_audio_ = false;
    std::atomic<bool> paused_{false};
    std::string audio_codec_;  // "auto"|"ac3"|"eac3"|"aac"|"mp3"|"dts"|...
    int video_width_ = 1920;
    int video_height_ = 1080;
    int start_seek_sec_ = 0;
    GstElement* pipeline_ = nullptr;
    std::atomic<bool> error_{false};
    std::string last_error_;
    long long first_pts_ns_ = -1;
    std::atomic<long long> last_pts_ns_{-1};  // dernier PTS vidéo vu
    unsigned int sample_count_ = 0;
    unsigned int audio_sample_count_ = 0;
    std::vector<AudioTrack> audio_tracks_;
    int current_audio_track_ = 0;
};

}  // namespace iptv
