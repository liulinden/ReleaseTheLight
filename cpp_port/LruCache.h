#pragma once
#include <unordered_map>
#include <list>
#include <utility>
#include <cstddef>

// Simple LRU-capped cache, generic over key/value/hash. Used where many
// ephemeral objects (e.g. particles) share a smaller set of expensive-to-
// build resources (e.g. a color-tinted texture): look up by key, and on a
// miss the caller builds and inserts. Once `capacity` is exceeded, the
// least-recently-used entry is evicted -- so a value that drifts
// continuously (like a charge-based color that's snapped/quantized to
// reduce churn but still slowly changes) doesn't grow the cache
// unboundedly over a long play session. Ported originally from lighting.py's
// GradientCache/MistParticleCache (OrderedDict-based LRU), generalized
// since the same need is likely to recur elsewhere.
template <typename Key, typename Value, typename Hash = std::hash<Key>>
class LruCache {
public:
    explicit LruCache(size_t capacity) : capacity_(capacity) {}

    // Returns a pointer to the existing value (and marks it most-recently-
    // used), or nullptr on a miss. Caller builds and calls insert() on a miss.
    Value* get(const Key& key) {
        auto it = index_.find(key);
        if (it == index_.end()) return nullptr;
        order_.splice(order_.begin(), order_, it->second);
        return &it->second->second;
    }

    Value& insert(const Key& key, Value&& value) {
        order_.emplace_front(key, std::move(value));
        index_[key] = order_.begin();
        if (order_.size() > capacity_) {
            auto& lru = order_.back();
            index_.erase(lru.first);
            order_.pop_back();
        }
        return order_.front().second;
    }

private:
    using ListType = std::list<std::pair<Key, Value>>;
    size_t capacity_;
    ListType order_; // front = most recently used
    std::unordered_map<Key, typename ListType::iterator, Hash> index_;
};
