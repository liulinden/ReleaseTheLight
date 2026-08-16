#include "AssetManager.h"
#include <SDL_image.h>
#include <filesystem>
#include <fstream>
#include <thread>
#include <mutex>
#include <chrono>
#include <stdexcept>
#include <sstream>
#include <algorithm>
#include <cstdint>
#include <cstring>

namespace fs = std::filesystem;

namespace {
const std::vector<std::string> kImageExts = {".png", ".bmp", ".jpg", ".jpeg", ".gif", ".webp"};

bool endsWith(const std::string& s, const std::string& suffix) {
    if (s.size() < suffix.size()) return false;
    return s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

std::string toLower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
    return s;
}

// Builds a BitMask directly from a tightly-packed RGBA byte buffer.
// Pure CPU work, no SDL surface/renderer involved -- safe to run on a
// worker thread. Threshold matches the terrain/laser pixel-sample code
// elsewhere in the port (_sample_chunk's `> 128`, laser.py's `[3] > 128`),
// and is exact (not an approximation) since hitbox source PNGs are
// guaranteed pure opaque-white-or-transparent (confirmed).
BitMask maskFromRawRGBA(int width, int height, const std::vector<uint8_t>& rgba) {
    BitMask mask(width, height);
    for (int y = 0; y < height; ++y) {
        const uint8_t* row = rgba.data() + static_cast<size_t>(y) * width * 4;
        for (int x = 0; x < width; ++x) {
            if (row[x * 4 + 3] > 128) mask.set(x, y, true);
        }
    }
    return mask;
}

// Converts an SDL_Surface (any format) to a tightly-packed RGBA32 byte
// buffer. Pure CPU work -- safe on a worker thread.
std::vector<uint8_t> surfaceToRawRGBA(SDL_Surface* surf, int& outW, int& outH) {
    SDL_Surface* converted = surf;
    bool ownsConverted = false;
    if (surf->format->format != SDL_PIXELFORMAT_RGBA32) {
        converted = SDL_ConvertSurfaceFormat(surf, SDL_PIXELFORMAT_RGBA32, 0);
        ownsConverted = true;
    }

    outW = converted->w;
    outH = converted->h;
    std::vector<uint8_t> out(static_cast<size_t>(outW) * outH * 4);

    SDL_LockSurface(converted);
    const uint8_t* pixels = static_cast<const uint8_t*>(converted->pixels);
    for (int y = 0; y < outH; ++y) {
        std::memcpy(out.data() + static_cast<size_t>(y) * outW * 4,
                    pixels + static_cast<size_t>(y) * converted->pitch,
                    static_cast<size_t>(outW) * 4);
    }
    SDL_UnlockSurface(converted);

    if (ownsConverted) SDL_FreeSurface(converted);
    return out;
}

// --- tiny binary I/O helpers for the cache file format ---------------
// Local to this file since AssetManager's cache is currently the only
// consumer of a custom binary format in the codebase. If a second
// consumer shows up later (e.g. a save-game format), these are small
// enough to lift into a shared BinaryIO util at that point rather than
// duplicating them -- flagging so it's not forgotten, not promoting
// prematurely for a single caller.
void writeU32(std::ostream& os, uint32_t v) { os.write(reinterpret_cast<const char*>(&v), sizeof(v)); }
void writeI32(std::ostream& os, int32_t v)  { os.write(reinterpret_cast<const char*>(&v), sizeof(v)); }
void writeI64(std::ostream& os, int64_t v)  { os.write(reinterpret_cast<const char*>(&v), sizeof(v)); }
void writeStr(std::ostream& os, const std::string& s) {
    writeU32(os, static_cast<uint32_t>(s.size()));
    os.write(s.data(), static_cast<std::streamsize>(s.size()));
}
bool readU32(std::istream& is, uint32_t& v) { is.read(reinterpret_cast<char*>(&v), sizeof(v)); return static_cast<bool>(is); }
bool readI32(std::istream& is, int32_t& v)  { is.read(reinterpret_cast<char*>(&v), sizeof(v)); return static_cast<bool>(is); }
bool readI64(std::istream& is, int64_t& v)  { is.read(reinterpret_cast<char*>(&v), sizeof(v)); return static_cast<bool>(is); }
bool readStr(std::istream& is, std::string& s) {
    uint32_t len = 0;
    if (!readU32(is, len)) return false;
    s.resize(len);
    if (len > 0) is.read(&s[0], len);
    return static_cast<bool>(is);
}

constexpr char kMagic[4] = {'A', 'C', 'C', '1'};
} // namespace

AssetManager::AssetManager(std::string root, bool useCache, std::string cacheFile)
    : root_(std::move(root)), useCache_(useCache), cacheFile_(std::move(cacheFile)) {}

bool AssetManager::isImageExt(const std::string& ext) {
    std::string lower = toLower(ext);
    return std::find(kImageExts.begin(), kImageExts.end(), lower) != kImageExts.end();
}

std::string AssetManager::nameFor(const std::string& fullPath, const std::string& root) {
    fs::path rel = fs::relative(fullPath, root);
    rel.replace_extension();
    return rel.generic_string(); // generic_string() always uses '/'
}

std::vector<AssetManager::DiscoveredPath> AssetManager::discover() const {
    std::vector<DiscoveredPath> result;
    if (!fs::exists(root_)) return result;
    for (auto& entry : fs::recursive_directory_iterator(root_)) {
        if (!entry.is_regular_file()) continue;
        std::string ext = entry.path().extension().string();
        if (!isImageExt(ext)) continue;
        result.push_back({ nameFor(entry.path().string(), root_), entry.path().string() });
    }
    return result;
}

AssetManager::Signature AssetManager::computeSignature(const std::vector<DiscoveredPath>& paths) {
    Signature sig;
    for (auto& p : paths) {
        auto t = fs::last_write_time(p.path);
        sig[p.name] = static_cast<int64_t>(t.time_since_epoch().count());
    }
    return sig;
}

bool AssetManager::tryLoadFromCache(const Signature& currentSig, std::vector<RawImage>& out) const {
    std::ifstream in(fs::path(root_) / cacheFile_, std::ios::binary);
    if (!in) return false;

    char magic[4];
    in.read(magic, 4);
    if (!in || std::memcmp(magic, kMagic, 4) != 0) return false;

    uint32_t numEntries = 0;
    if (!readU32(in, numEntries)) return false;

    std::vector<RawImage> entries;
    Signature cachedSig;
    entries.reserve(numEntries);

    for (uint32_t i = 0; i < numEntries; ++i) {
        RawImage img;
        int64_t mtime = 0;
        int32_t w = 0, h = 0;
        uint32_t dataLen = 0;
        if (!readStr(in, img.name)) return false;
        if (!readI64(in, mtime)) return false;
        if (!readI32(in, w)) return false;
        if (!readI32(in, h)) return false;
        if (!readU32(in, dataLen)) return false;
        img.width = w;
        img.height = h;
        img.rgba.resize(dataLen);
        if (dataLen > 0) in.read(reinterpret_cast<char*>(img.rgba.data()), dataLen);
        if (!in) return false;

        cachedSig[img.name] = mtime;
        entries.push_back(std::move(img));
    }

    // Exact signature equality (same names, same mtimes) -- matches the
    // Python's `if blob.get("sig") != self._signature(paths): return False`,
    // where dict equality means "no missing keys, no extra keys, no
    // changed values".
    if (cachedSig != currentSig) return false;

    // Mask extraction wasn't stored in the cache file (recomputing from
    // raw bytes is cheap and keeps the on-disk format simpler than storing
    // two parallel representations) -- do it now.
    for (auto& img : entries) {
        if (endsWith(img.name, "_hitbox")) {
            img.hasMask = true;
            img.mask = maskFromRawRGBA(img.width, img.height, img.rgba);
        }
    }

    out = std::move(entries);
    return true;
}

void AssetManager::writeCache(const Signature& sig, const std::vector<RawImage>& images) const {
    std::ofstream out(fs::path(root_) / cacheFile_, std::ios::binary | std::ios::trunc);
    if (!out) {
        SDL_Log("[assets] could not write cache");
        return;
    }
    out.write(kMagic, 4);
    writeU32(out, static_cast<uint32_t>(images.size()));
    for (auto& img : images) {
        writeStr(out, img.name);
        writeI64(out, sig.at(img.name));
        writeI32(out, img.width);
        writeI32(out, img.height);
        writeU32(out, static_cast<uint32_t>(img.rgba.size()));
        out.write(reinterpret_cast<const char*>(img.rgba.data()), static_cast<std::streamsize>(img.rgba.size()));
    }
}

double AssetManager::load(SDL_Renderer* renderer, bool verbose) {
    auto start = std::chrono::steady_clock::now();

    auto paths = discover();
    auto currentSig = computeSignature(paths);

    std::vector<RawImage> images;
    bool usedCache = false;

    if (useCache_) {
        usedCache = tryLoadFromCache(currentSig, images);
    }

    if (!usedCache) {
        // --- Parallel phase: decode + RGBA32 convert + mask extraction --
        // All pure CPU work, no renderer needed -- genuinely spread across
        // hardware_concurrency() threads (unlike Python's GIL-limited
        // ThreadPoolExecutor).
        images.resize(paths.size());
        std::mutex logMutex;
        unsigned numThreads = std::max(1u, std::thread::hardware_concurrency());

        auto worker = [&](size_t begin, size_t end) {
            for (size_t i = begin; i < end; ++i) {
                const auto& p = paths[i];
                SDL_Surface* surf = IMG_Load(p.path.c_str());
                if (!surf) {
                    std::lock_guard<std::mutex> lock(logMutex);
                    SDL_Log("[assets] failed to load %s: %s", p.path.c_str(), IMG_GetError());
                    continue;
                }
                RawImage img;
                img.name = p.name;
                img.rgba = surfaceToRawRGBA(surf, img.width, img.height);
                SDL_FreeSurface(surf);

                if (endsWith(img.name, "_hitbox")) {
                    img.hasMask = true;
                    img.mask = maskFromRawRGBA(img.width, img.height, img.rgba);
                }
                images[i] = std::move(img);
            }
        };

        {
            std::vector<std::thread> pool;
            size_t chunkSize = (paths.size() + numThreads - 1) / std::max<size_t>(1, numThreads);
            for (unsigned t = 0; t < numThreads; ++t) {
                size_t begin = t * chunkSize;
                size_t end = std::min(paths.size(), begin + chunkSize);
                if (begin >= end) continue;
                pool.emplace_back(worker, begin, end);
            }
            for (auto& th : pool) th.join();
        }

        // Drop entries whose decode failed (left as default-constructed,
        // empty-name RawImage by the worker's `continue`).
        images.erase(std::remove_if(images.begin(), images.end(),
                                     [](const RawImage& im) { return im.name.empty(); }),
                     images.end());

        if (useCache_) {
            writeCache(currentSig, images);
        }
    }

    // --- Serial phase: texture upload only (must own `renderer`) -------
    for (auto& img : images) {
        SDL_Surface* wrapper = SDL_CreateRGBSurfaceWithFormatFrom(
            img.rgba.data(), img.width, img.height, 32, img.width * 4, SDL_PIXELFORMAT_RGBA32);
        if (!wrapper) {
            SDL_Log("[assets] failed to wrap pixels for %s: %s", img.name.c_str(), SDL_GetError());
            continue;
        }

        Asset asset;
        asset.width = img.width;
        asset.height = img.height;
        asset.hasMask = img.hasMask;
        asset.mask = std::move(img.mask);
        asset.texture = SDL_CreateTextureFromSurface(renderer, wrapper);
        SDL_FreeSurface(wrapper); // does not free img.rgba (surface doesn't own "From" pixel data)

        if (!asset.texture) {
            SDL_Log("[assets] failed to create texture for %s: %s", img.name.c_str(), SDL_GetError());
            continue;
        }
        SDL_SetTextureBlendMode(asset.texture, SDL_BLENDMODE_BLEND);

        images_[img.name] = std::move(asset);
        unused_[img.name] = true;
    }

    auto elapsedSec = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    if (verbose) {
        SDL_Log("[assets] loaded %zu images (%s) in %.2fs",
                images_.size(), usedCache ? "from cache" : "decoded", elapsedSec);
    }
    return elapsedSec;
}

const Asset& AssetManager::get(const std::string& name) {
    auto it = images_.find(name);
    if (it == images_.end()) {
        std::ostringstream oss;
        oss << "No asset named '" << name << "'. Available: ";
        std::vector<std::string> names;
        names.reserve(images_.size());
        for (auto& kv : images_) names.push_back(kv.first);
        std::sort(names.begin(), names.end());
        int count = 0;
        for (auto& n : names) {
            if (count++ >= 10) break;
            oss << n << ", ";
        }
        oss << "...";
        throw std::runtime_error(oss.str());
    }
    unused_[name] = false;
    return it->second;
}

bool AssetManager::contains(const std::string& name) const {
    return images_.find(name) != images_.end();
}
