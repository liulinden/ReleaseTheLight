#pragma once
#include <SDL.h>
#include <cstdint>

// Replaces the many `pygame.time.get_ticks()` call sites throughout the
// codebase (health_bar.py, interaction_display.py, laser.py's LaserImpact,
// Game's frame timing, loading_screen.py, etc.). Centralized here rather
// than calling SDL_GetTicks() directly at each site, so there's a single
// point to swap in a higher-resolution clock later if millisecond
// precision ever becomes limiting.
namespace Time {
inline uint32_t nowMs() { return SDL_GetTicks(); }
}
