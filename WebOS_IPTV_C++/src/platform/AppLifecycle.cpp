#include "platform/AppLifecycle.h"

#include <atomic>
#include <cstdio>
#include <mutex>

#if defined(IPTV_WEBOS)
#include <glib.h>
#include <luna-service2/lunaservice.h>
#endif

namespace iptv::platform {

#if defined(IPTV_WEBOS)

struct AppLifecycle::Impl {
    LSHandle*      handle    = nullptr;
    GMainContext*  ctx       = nullptr;
    std::string    appId;
    std::string    wakeToken;          // token returned by power.lockOn
    std::atomic<int> wake_refs{0};
    std::mutex     wake_mu;
};

namespace {

bool callOneShot(LSHandle* h, const char* uri, const char* payload) {
    LSError err;
    LSErrorInit(&err);
    bool ok = LSCallOneReply(h, uri, payload, nullptr, nullptr, nullptr, &err);
    if (!ok) {
        std::fprintf(stderr, "[luna] call %s failed: %s\n", uri, err.message ? err.message : "?");
        LSErrorFree(&err);
    }
    return ok;
}

}  // namespace

AppLifecycle::AppLifecycle() : impl_(new Impl) {}

AppLifecycle::~AppLifecycle() {
    stop();
    delete impl_;
}

bool AppLifecycle::start(const std::string& appId) {
    impl_->appId = appId;
    impl_->ctx = g_main_context_default();

    LSError err;
    LSErrorInit(&err);
    if (!LSRegister(appId.c_str(), &impl_->handle, &err)) {
        std::fprintf(stderr, "[luna] LSRegister failed: %s\n",
                     err.message ? err.message : "?");
        LSErrorFree(&err);
        return false;
    }
    if (!LSGmainContextAttach(impl_->handle, impl_->ctx, &err)) {
        std::fprintf(stderr, "[luna] LSGmainContextAttach failed: %s\n",
                     err.message ? err.message : "?");
        LSErrorFree(&err);
    }

    // Tell SAM we're up. We don't need the response — just fire and forget.
    std::string payload = "{\"appId\":\"" + appId + "\",\"appName\":\"" + appId + "\"}";
    callOneShot(impl_->handle,
                "luna://com.webos.applicationmanager/registerApp",
                payload.c_str());
    return true;
}

void AppLifecycle::stop() {
    if (!impl_->handle) return;
    if (impl_->wake_refs.load() > 0) {
        impl_->wake_refs = 1;
        releaseWakeLock();
    }
    LSError err;
    LSErrorInit(&err);
    LSUnregister(impl_->handle, &err);
    LSErrorFree(&err);
    impl_->handle = nullptr;
}

void AppLifecycle::acquireWakeLock(const std::string& reason) {
    std::lock_guard<std::mutex> lk(impl_->wake_mu);
    int prev = impl_->wake_refs.fetch_add(1);
    if (prev > 0 || !impl_->handle) return;
    std::string payload = "{\"clientId\":\"" + impl_->appId +
                          "\",\"requestType\":\"" + reason + "\"}";
    callOneShot(impl_->handle,
                "luna://com.webos.service.tvpower/power/avBlock",
                payload.c_str());
}

void AppLifecycle::releaseWakeLock() {
    std::lock_guard<std::mutex> lk(impl_->wake_mu);
    int prev = impl_->wake_refs.fetch_sub(1);
    if (prev > 1 || !impl_->handle) return;
    std::string payload = "{\"clientId\":\"" + impl_->appId + "\"}";
    callOneShot(impl_->handle,
                "luna://com.webos.service.tvpower/power/avUnblock",
                payload.c_str());
}

#else  // host (non-webOS) stub

struct AppLifecycle::Impl {
    std::string appId;
    std::atomic<int> wake_refs{0};
};

AppLifecycle::AppLifecycle()  : impl_(new Impl) {}
AppLifecycle::~AppLifecycle() { stop(); delete impl_; }

bool AppLifecycle::start(const std::string& appId) {
    impl_->appId = appId;
    std::fprintf(stderr, "[lifecycle/host] started as %s (no Luna)\n", appId.c_str());
    return true;
}

void AppLifecycle::stop() {
    if (impl_->wake_refs > 0) {
        std::fprintf(stderr, "[lifecycle/host] stop with wake_refs=%d\n",
                     impl_->wake_refs.load());
    }
}

void AppLifecycle::acquireWakeLock(const std::string& reason) {
    int prev = impl_->wake_refs.fetch_add(1);
    if (prev == 0) {
        std::fprintf(stderr, "[lifecycle/host] wake-lock acquired (%s)\n", reason.c_str());
    }
}

void AppLifecycle::releaseWakeLock() {
    int prev = impl_->wake_refs.fetch_sub(1);
    if (prev == 1) {
        std::fprintf(stderr, "[lifecycle/host] wake-lock released\n");
    }
}

#endif

}  // namespace iptv::platform
