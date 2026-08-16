#include "GlobalAssets.h"

namespace GlobalAssets {

AssetManager& manager() {
    static AssetManager instance("assets", true);
    return instance;
}

} // namespace GlobalAssets
