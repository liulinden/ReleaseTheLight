#pragma once
#include <string>
#include <unordered_map>
#include <vector>
#include <SDL.h>
#include "BitMask.h"

// Ported from asset_manager.py's AssetManager.
//
// Key differences from the Python version, per project decisions:
//   - No per-zoom pre-scaled image cache. Assets are loaded once at native
//     resolution as a single SDL_Texture; scaling happens at draw time via
//     SDL_RenderCopy's destination rect (GPU-accelerated), which is why
//     that whole cache pattern (visible throughout Cell/Enemy/Nest/Player/
//     Lighting in the Python) no longer needs a C++ equivalent.
//   - Assets whose filename ends in "_hitbox" additionally get a BitMask
//     built from their raw pixel data at load time (source PNGs are
//     guaranteed pure opaque-white-or-transparent, confirmed), for use in
//     collision code. Everything else only gets a texture.
//   - Decode parallelism uses a real std::thread pool instead of Python's
//     ThreadPoolExecutor (which doesn't get true multicore parallelism for
//     CPU-bound decode work under the GIL). Texture upload (SDL_Create-
//     TextureFromSurface) still happens serially on the main thread
//     afterward, same shape as the Python's "parallel load, serial
//     convert_alpha()" pattern -- SDL textures must be created on the
//     thread that owns the renderer.
struct Asset {
    SDL_Texture* texture = nullptr;
    int width = 0;
    int height = 0;

    // Only populated for assets whose name ends in "_hitbox". Native
    // resolution, 1 bit per pixel (opaque = true).
    bool hasMask = false;
    BitMask mask;
};

class AssetManager {
public:
    // root: directory to scan (matches Python's `root` param)
    // useCache: whether to read/write a disk cache (matches `use_cache`)
    AssetManager(std::string root, bool useCache = false, std::string cacheFile = ".asset_cache");

    // Discovers image files under root, decodes them in parallel on a
    // worker thread pool, then uploads textures serially on the calling
    // thread (which must own an active SDL_Renderer). Returns elapsed
    // seconds, matching the Python's return value.
    //
    // NOTE: unlike the Python version, this must be called with `renderer`
    // already created (SDL_CreateWindow + SDL_CreateRenderer done), since
    // texture upload needs it -- matches the "init() must run after the
    // display exists" constraint already present throughout the Python
    // codebase (lighting.py, nest.py, etc.), just made an explicit
    // parameter here instead of an implicit ordering requirement.
    double load(SDL_Renderer* renderer, bool verbose = true /*, loadingScreen hook added when LoadingScreen is ported */);

    // Throws std::runtime_error (with a message listing available assets,
    // matching the Python's KeyError message) if not found. This matches
    // the Python's get() exactly -- a missing asset name is a startup-time
    // bug (typo), not a runtime condition to handle gracefully, so it
    // should crash loudly here too rather than fail silently mid-frame.
    const Asset& get(const std::string& name);

    bool contains(const std::string& name) const;
    size_t size() const { return images_.size(); }

private:
    std::string root_;
    bool useCache_;
    std::string cacheFile_;

    std::unordered_map<std::string, Asset> images_;
    std::unordered_map<std::string, bool> unused_; // name -> still unused

    struct DiscoveredPath {
        std::string name; // matches Python's _name_for: relative path, no ext, '/' separators
        std::string path;
    };
    std::vector<DiscoveredPath> discover() const;
    static bool isImageExt(const std::string& ext);
    static std::string nameFor(const std::string& fullPath, const std::string& root);

    // Signature = name -> last-write-time (opaque, filesystem-native
    // comparable value; not necessarily a wall-clock epoch, we only ever
    // compare it to itself run-to-run, matching the Python's use of
    // os.path.getmtime purely as a change-detection signal, not a date).
    using Signature = std::unordered_map<std::string, int64_t>;
    static Signature computeSignature(const std::vector<DiscoveredPath>& paths);

    // Common shape produced by BOTH the fresh-decode path (IMG_Load ->
    // RGBA32 conversion, done per-asset on a worker thread) and the
    // cache-read path (raw bytes read back from disk). Unifying on this
    // one representation means the serial finalize step (texture upload)
    // and mask extraction don't need to know or care which path an asset
    // came from -- same logic either way. This directly avoids duplicating
    // "turn pixels into an Asset" between two near-identical code paths.
    struct RawImage {
        std::string name;
        int width = 0, height = 0;
        std::vector<uint8_t> rgba; // tightly packed, width*height*4 bytes
        bool hasMask = false;
        BitMask mask; // computed eagerly (in parallel, from rgba) regardless of source
    };

    bool tryLoadFromCache(const Signature& currentSig, std::vector<RawImage>& out) const;
    void writeCache(const Signature& sig, const std::vector<RawImage>& images) const;
};
