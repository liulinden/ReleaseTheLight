#pragma once
#include <string>

// Ported from config.py.
namespace Config {
constexpr bool DEV_MODE = true;
constexpr int CHUNK_SIZE = 400;
inline const std::string WINDOW_NAME = "Release the Light";
inline const std::string WINDOW_ICON_PATH = "assets/player_idle_1.png";
} // namespace Config
