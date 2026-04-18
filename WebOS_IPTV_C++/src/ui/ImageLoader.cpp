#include "ui/ImageLoader.h"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <system_error>

#include <SDL2/SDL.h>
#include <SDL2/SDL_image.h>
#include <curl/curl.h>

#include "store/Paths.h"

namespace iptv::ui {

namespace fs = std::filesystem;

namespace {

// DJB2 hash — good enough for filename-safe digest, no external deps.
std::string shortHash(const std::string& s) {
    uint64_t h = 5381;
    for (unsigned char c : s) h = ((h << 5) + h) + c;
    std::ostringstream oss;
    oss << std::hex << h;
    return oss.str();
}

std::size_t curlWrite(char* ptr, std::size_t size, std::size_t nmemb, void* userdata) {
    auto* out = static_cast<std::vector<uint8_t>*>(userdata);
    size_t n = size * nmemb;
    size_t cur = out->size();
    out->resize(cur + n);
    std::memcpy(out->data() + cur, ptr, n);
    return n;
}

bool downloadUrl(const std::string& url, std::vector<uint8_t>& out) {
    CURL* curl = curl_easy_init();
    if (!curl) return false;
    out.clear();
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 8L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, curlWrite);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &out);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "IPTVPlayer-Native/0.1");
    CURLcode rc = curl_easy_perform(curl);
    long http = 0;
    if (rc == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http);
    curl_easy_cleanup(curl);
    return rc == CURLE_OK && http >= 200 && http < 300 && !out.empty();
}

}  // namespace

fs::path ImageLoader::cacheDir() {
    auto d = store::Paths::dataDir() / "images";
    std::error_code ec;
    fs::create_directories(d, ec);
    return d;
}

ImageLoader::ImageLoader()  = default;
ImageLoader::~ImageLoader() { stop(); }

void ImageLoader::start(SDL_Renderer* r, int n) {
    renderer_ = r;
    // SDL_image init (PNG + JPG).
    IMG_Init(IMG_INIT_PNG | IMG_INIT_JPG);
    running_ = true;
    for (int i = 0; i < n; ++i) {
        workers_.emplace_back([this]{ workerLoop(); });
    }
}

void ImageLoader::stop() {
    if (!running_) return;
    running_ = false;
    q_cv_.notify_all();
    for (auto& t : workers_) if (t.joinable()) t.join();
    workers_.clear();
    IMG_Quit();
}

void ImageLoader::request(const std::string& url, ResultCb cb) {
    if (!running_) return;
    {
        std::lock_guard<std::mutex> lk(q_mu_);
        queue_.push_back({url, std::move(cb)});
    }
    q_cv_.notify_one();
}

void ImageLoader::clearPending() {
    std::lock_guard<std::mutex> lk(q_mu_);
    queue_.clear();
}

bool ImageLoader::readDiskCache(const std::string& url, std::vector<uint8_t>& out) {
    fs::path p = cacheDir() / (shortHash(url) + ".bin");
    std::ifstream f(p, std::ios::binary);
    if (!f) return false;
    f.seekg(0, std::ios::end);
    std::streamoff n = f.tellg();
    if (n <= 0) return false;
    f.seekg(0);
    out.resize(static_cast<size_t>(n));
    f.read(reinterpret_cast<char*>(out.data()), n);
    return static_cast<std::streamoff>(f.gcount()) == n;
}

void ImageLoader::writeDiskCache(const std::string& url, const std::vector<uint8_t>& in) {
    fs::path p = cacheDir() / (shortHash(url) + ".bin");
    std::ofstream f(p, std::ios::binary | std::ios::trunc);
    if (!f) return;
    f.write(reinterpret_cast<const char*>(in.data()),
            static_cast<std::streamsize>(in.size()));
}

void ImageLoader::workerLoop() {
    while (running_) {
        Pending item;
        {
            std::unique_lock<std::mutex> lk(q_mu_);
            q_cv_.wait(lk, [this]{ return !running_ || !queue_.empty(); });
            if (!running_) return;
            item = std::move(queue_.front());
            queue_.pop_front();
        }

        std::vector<uint8_t> bytes;
        bool ok = readDiskCache(item.url, bytes);
        if (!ok) {
            ok = downloadUrl(item.url, bytes);
            if (ok) writeDiskCache(item.url, bytes);
        }

        Completed c;
        c.cb = std::move(item.cb);
        c.bytes = std::move(bytes);
        c.ok = ok;
        std::lock_guard<std::mutex> lk(done_mu_);
        done_.push_back(std::move(c));
    }
}

void ImageLoader::pump() {
    std::deque<Completed> batch;
    {
        std::lock_guard<std::mutex> lk(done_mu_);
        batch.swap(done_);
    }
    for (auto& c : batch) {
        SDL_Texture* tex = nullptr;
        int w = 0, h = 0;
        if (c.ok && !c.bytes.empty() && renderer_) {
            SDL_RWops* rw = SDL_RWFromConstMem(c.bytes.data(),
                                               static_cast<int>(c.bytes.size()));
            SDL_Surface* surf = rw ? IMG_Load_RW(rw, 1) : nullptr;
            if (surf) {
                tex = SDL_CreateTextureFromSurface(renderer_, surf);
                w = surf->w;
                h = surf->h;
                SDL_FreeSurface(surf);
            }
        }
        if (c.cb) c.cb(tex, w, h);
    }
}

}  // namespace iptv::ui
