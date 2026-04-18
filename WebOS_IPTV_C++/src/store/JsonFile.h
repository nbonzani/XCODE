#pragma once
// Atomic read/write helpers for nlohmann::json files. Write goes to <path>.tmp then
// std::filesystem::rename(). Reads return an empty object/array on missing/corrupt file —
// no exceptions reach the caller, since these stores are best-effort.

#include <filesystem>

#include <nlohmann/json.hpp>

namespace iptv::store {

using json = nlohmann::json;

// Returns the parsed JSON, or `fallback` (default = empty object) on missing/corrupt file.
json readJson(const std::filesystem::path& path, json fallback = json::object());

// Returns true on success. Failures are logged to stderr and the file is left intact.
bool writeJson(const std::filesystem::path& path, const json& value);

}  // namespace iptv::store
