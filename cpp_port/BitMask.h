#pragma once
#include <vector>
#include <cstdint>
#include <algorithm>
#include <cmath>

// Packed 1-bit-per-pixel mask. Backs:
//   - hitbox asset masks loaded by AssetManager (nest/air-pocket/enemy-
//     attack hitbox PNGs, which are guaranteed pure opaque-white-or-
//     transparent -- see conversation notes)
//   - later: per-chunk terrain occupancy grids (Terrain's collision
//     bitsets), and the enemy attack-hitbox-vs-player-rect overlap check
//     (was pygame.mask.overlap())
//
// A bit set to 1 means "solid" / "opaque" -- matches the Python
// convention of alpha > 128 (or, for terrain hitboxes, color channel >
// 128) meaning collidable.
class BitMask {
public:
    BitMask() = default;
    BitMask(int width, int height)
        : w_(width), h_(height), wordsPerRow_((width + 63) / 64),
          bits_(static_cast<size_t>(wordsPerRow_) * std::max(height, 0), 0) {}

    int width()  const { return w_; }
    int height() const { return h_; }

    bool get(int x, int y) const {
        if (x < 0 || y < 0 || x >= w_ || y >= h_) return false;
        size_t idx = static_cast<size_t>(y) * wordsPerRow_ + (x / 64);
        return (bits_[idx] >> (x % 64)) & 1ULL;
    }

    void set(int x, int y, bool value = true) {
        if (x < 0 || y < 0 || x >= w_ || y >= h_) return;
        size_t idx = static_cast<size_t>(y) * wordsPerRow_ + (x / 64);
        uint64_t bit = 1ULL << (x % 64);
        if (value) bits_[idx] |= bit;
        else       bits_[idx] &= ~bit;
    }

    // Sets every bit to `value`. Safe even though this touches unused
    // trailing bits beyond the last valid column in each row's final
    // word (get()/set() always bounds-check x < w_, so those phantom
    // bits are never observably read).
    void fill(bool value) {
        std::fill(bits_.begin(), bits_.end(), value ? ~0ULL : 0ULL);
    }

    // Clears (subtractCircle) or sets (orCircle) every bit within radius
    // `r` of (cx, cy), in this mask's own coordinate space. Used for
    // air-pocket carving -- see Terrain.h for why a mathematical circle
    // is used here instead of an irregular hitbox-image-derived mask.
    void subtractCircle(double cx, double cy, double r) {
        circleOp(cx, cy, r, false);
    }
    void orCircle(double cx, double cy, double r) {
        circleOp(cx, cy, r, true);
    }

    // OR `other` into this mask at pixel offset (ox, oy).
    // Matches pygame's BLEND_RGBA_MAX usage for "add solid region"
    // (e.g. Terrain._reblit_solid_structures_on_chunk, nest hitbox reblit).
    void orInto(const BitMask& other, int ox, int oy) {
        for (int y = 0; y < other.h_; ++y) {
            int dy = y + oy;
            if (dy < 0 || dy >= h_) continue;
            for (int x = 0; x < other.w_; ++x) {
                if (!other.get(x, y)) continue;
                int dx = x + ox;
                if (dx < 0 || dx >= w_) continue;
                set(dx, dy, true);
            }
        }
    }

    // Clear bits in this mask wherever `other` has a set bit, at pixel
    // offset (ox, oy). Matches pygame's BLEND_RGBA_SUB usage for carving
    // (Terrain._carve_hitbox).
    void subtractFrom(const BitMask& other, int ox, int oy) {
        for (int y = 0; y < other.h_; ++y) {
            int dy = y + oy;
            if (dy < 0 || dy >= h_) continue;
            for (int x = 0; x < other.w_; ++x) {
                if (!other.get(x, y)) continue;
                int dx = x + ox;
                if (dx < 0 || dx >= w_) continue;
                set(dx, dy, false);
            }
        }
    }

    // True if any set bit in this mask overlaps a set bit in `other` at
    // pixel offset (ox, oy). Matches pygame.mask.Mask.overlap() used by
    // Enemy.attack_collide_rect and Terrain.nests_collide_rect.
    bool overlaps(const BitMask& other, int ox, int oy) const {
        for (int y = 0; y < other.h_; ++y) {
            int dy = y + oy;
            if (dy < 0 || dy >= h_) continue;
            for (int x = 0; x < other.w_; ++x) {
                if (other.get(x, y) && get(x + ox, dy)) return true;
            }
        }
        return false;
    }

    // Nearest-neighbor resize to (newW, newH). Used to scale a native-
    // resolution asset mask (e.g. an enemy's attack hitbox) to whatever
    // size it needs to be drawn/tested at -- exact, no interpolation
    // needed since source hitbox data is always binary (see AssetManager
    // notes on hitbox PNGs being pure opaque-or-transparent).
    BitMask scaledTo(int newW, int newH) const {
        BitMask result(newW, newH);
        for (int y = 0; y < newH; ++y) {
            int srcY = (h_ > 0) ? std::min(h_ - 1, y * h_ / newH) : 0;
            for (int x = 0; x < newW; ++x) {
                int srcX = (w_ > 0) ? std::min(w_ - 1, x * w_ / newW) : 0;
                if (get(srcX, srcY)) result.set(x, y, true);
            }
        }
        return result;
    }

    // Horizontal mirror -- used for facing="left" enemy attack hitboxes
    // (matches pygame.transform.flip(img, True, False) applied to hitbox
    // art in the original).
    BitMask flippedX() const {
        BitMask result(w_, h_);
        for (int y = 0; y < h_; ++y) {
            for (int x = 0; x < w_; ++x) {
                if (get(x, y)) result.set(w_ - 1 - x, y, true);
            }
        }
        return result;
    }

private:
    void circleOp(double cx, double cy, double r, bool value) {
        int minX = std::max(0, static_cast<int>(std::floor(cx - r)));
        int maxX = std::min(w_ - 1, static_cast<int>(std::ceil(cx + r)));
        int minY = std::max(0, static_cast<int>(std::floor(cy - r)));
        int maxY = std::min(h_ - 1, static_cast<int>(std::ceil(cy + r)));
        double r2 = r * r;
        for (int y = minY; y <= maxY; ++y) {
            for (int x = minX; x <= maxX; ++x) {
                double dx = x + 0.5 - cx, dy = y + 0.5 - cy;
                if (dx * dx + dy * dy <= r2) set(x, y, value);
            }
        }
    }

    int w_ = 0, h_ = 0;
    size_t wordsPerRow_ = 0;
    std::vector<uint64_t> bits_;
};
