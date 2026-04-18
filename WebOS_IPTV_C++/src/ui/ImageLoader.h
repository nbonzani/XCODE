#pragma once
// Asynchronous poster/image loader. Worker threads pull URLs from a queue, download
// with libcurl, decode via SDL_image, and publish the resulting SDL_Texture through
// a callback dispatched on the main thread.
//
// A disk cache (<data>/images/<sha1>.bin) avoids re-downloading on each cold start.
// Textures for posters are typically ≤ 400x600 so memory use is bounded by the
// PosterGrid's visible window.

#include <atomic>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

struct SDL_Renderer;
struct SDL_Texture;

namespace iptv::ui {

class ImageLoader {
public:
    // Called on the main thread (via pump()) with the resulting texture, or nullptr on failure.
    using ResultCb = std::function<void(SDL_Texture* tex, int w, int h)>;

    ImageLoader();
    ~ImageLoader();

    ImageLoader(const ImageLoader&) = delete;
    ImageLoader& operator=(const ImageLoader&) = delete;

    void start(SDL_Renderer* renderer, int numThreads = 2);
    void stop();

    // Enqueue a request. The callback fires on the main thread after pump().
    void request(const std::string& url, ResultCb cb);

    // Call from the main thread each frame. Drains completed downloads and
    // creates GPU textures from the decoded surfaces.
    void pump();

    // Cancel all pending requests (in-flight downloads still complete but are discarded).
    void clearPending();

    static std::filesystem::path cacheDir();

private:
    struct Pending {
        std::string url;
        ResultCb cb;
    };
    struct Completed {
        ResultCb cb;
        std::vector<uint8_t> bytes;   // decoded SDL_image input bytes
        bool ok = false;
    };

    void workerLoop();
    bool readDiskCache(const std::string& url, std::vector<uint8_t>& out);
    void writeDiskCache(const std::string& url, const std::vector<uint8_t>& in);

    SDL_Renderer* renderer_ = nullptr;
    std::vector<std::thread> workers_;
    std::atomic<bool> running_{false};

    std::mutex q_mu_;
    std::condition_variable q_cv_;
    std::deque<Pending> queue_;

    std::mutex done_mu_;
    std::deque<Completed> done_;
};

}  // namespace iptv::ui
