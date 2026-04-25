#pragma once
// Glue against the webOS Luna service bus for the bits the app actually needs:
//   * register with SAM so it shows up in launch lifecycle telemetry
//   * keep the screen on during playback (com.webos.service.tvpower screen lock)
//   * relay the relaunch parameters when the user re-launches an already-running app
//
// On the host (non-webOS) build the implementation is a no-op stub that just logs.
// The interface is identical so callers don't need #ifdef.

#include <functional>
#include <string>

namespace iptv::platform {

class AppLifecycle {
public:
    using RelaunchHandler = std::function<void(const std::string& payloadJson)>;

    AppLifecycle();
    ~AppLifecycle();

    AppLifecycle(const AppLifecycle&) = delete;
    AppLifecycle& operator=(const AppLifecycle&) = delete;

    // Initialise the bus connection and register the service. Returns false on failure.
    bool start(const std::string& appId);

    // Tear down. Idempotent.
    void stop();

    // Acquire / release a wake lock to prevent the screen from going off during playback.
    // Reference-counted internally so nested acquires are safe.
    void acquireWakeLock(const std::string& reason);
    void releaseWakeLock();
    // Re-émet un avBlock même si le refcount est déjà > 0. Nécessaire pour
    // refresh périodique car l'avBlock TV a un TTL en pratique.
    void pingWakeLock(const std::string& reason);

    void setRelaunchHandler(RelaunchHandler h) { on_relaunch_ = std::move(h); }

private:
    struct Impl;
    Impl* impl_ = nullptr;
    RelaunchHandler on_relaunch_;
};

}  // namespace iptv::platform
