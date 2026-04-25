#include "platform/AppLifecycle.h"

#include <atomic>
#include <csignal>
#include <cstdio>
#include <fcntl.h>
#include <mutex>
#include <sys/wait.h>
#include <unistd.h>

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

    // LSRegister peut échouer si un process précédent (SIGKILL, crash) garde
    // l'enregistrement côté hub Luna. Dans ce cas on laisse le handle NULL
    // et pingWakeLock() bascule sur un fallback subprocess luna-send-pub.
    LSError err;
    LSErrorInit(&err);
    if (!LSRegister(appId.c_str(), &impl_->handle, &err)) {
        std::fprintf(stderr, "[luna] LSRegister(%s) failed: %s — pingWakeLock "
                              "utilisera luna-send-pub en fallback\n",
                     appId.c_str(), err.message ? err.message : "?");
        LSErrorFree(&err);
        impl_->handle = nullptr;
        // Pas d'erreur fatale : on continue sans callback bus mais le fallback
        // luna-send-pub assure l'avBlock.
        return true;
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

void AppLifecycle::pingWakeLock(const std::string& reason) {
    std::lock_guard<std::mutex> lk(impl_->wake_mu);
    std::string payload = "{\"clientId\":\"" + impl_->appId +
                          "\",\"requestType\":\"" + reason + "\"}";
    if (impl_->handle) {
        callOneShot(impl_->handle,
                    "luna://com.webos.service.tvpower/power/avBlock",
                    payload.c_str());
        return;
    }
    // Fallback : LSRegister a échoué (collision de nom). On lance un
    // subprocess luna-send-pub (binaire système, pas de registration).
    // fork+exec en async : on ne bloque pas la boucle principale.
    pid_t pid = fork();
    if (pid == 0) {
        // Enfant : stderr/stdout -> /dev/null pour éviter le bruit
        int devnull = open("/dev/null", O_WRONLY);
        if (devnull >= 0) { dup2(devnull, 1); dup2(devnull, 2); close(devnull); }
        execl("/usr/bin/luna-send-pub", "luna-send-pub", "-n", "1",
              "luna://com.webos.service.tvpower/power/avBlock",
              payload.c_str(), (char*)nullptr);
        _exit(127);
    } else if (pid > 0) {
        // Parent : reap async (waitpid WNOHANG dans un timer ou juste
        // SIGCHLD→SIG_IGN pour auto-reap). On laisse zombie-proof :
        signal(SIGCHLD, SIG_IGN);
    }
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

void AppLifecycle::pingWakeLock(const std::string& reason) {
    std::fprintf(stderr, "[lifecycle/host] wake-lock ping (%s)\n", reason.c_str());
}

#endif

}  // namespace iptv::platform
