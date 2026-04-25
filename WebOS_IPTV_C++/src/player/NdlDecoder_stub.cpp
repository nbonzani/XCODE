// Host build stub — NDL n'existe que sur webOS. Toutes les méthodes
// retournent false/ne font rien. main.cpp continue de compiler et route
// simplement vers GstDecoder/SwDecoder à l'exécution sur host.
#include "player/NdlDecoder.h"

namespace iptv {

NdlDecoder::NdlDecoder() = default;
NdlDecoder::~NdlDecoder() = default;

bool NdlDecoder::init(const std::string&) { return false; }
void NdlDecoder::shutdown() {}
bool NdlDecoder::open(const std::string&, int, int, const std::string&) { return false; }
bool NdlDecoder::play() { return false; }
bool NdlDecoder::seekRelative(int) { return false; }
void NdlDecoder::stop() {}

GstFlowReturn NdlDecoder::onVideoSampleStatic(GstAppSink*, void*) { return GST_FLOW_OK; }
GstFlowReturn NdlDecoder::onAudioSampleStatic(GstAppSink*, void*) { return GST_FLOW_OK; }
void NdlDecoder::onVideoSample(GstSample*) {}
void NdlDecoder::onAudioSample(GstSample*) {}

}  // namespace iptv
