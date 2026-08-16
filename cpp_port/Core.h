#pragma once
#include <cstdint>

struct Vec2 {
    double x = 0.0;
    double y = 0.0;
};

struct Color {
    uint8_t r = 0, g = 0, b = 0, a = 255;
};

// Int-backed to match pygame.Rect's truncating int semantics exactly.
// See conversation notes: this is a deliberate fidelity choice, not an
// oversight -- pygame truncates x/y/w/h to int on assignment, and several
// physics/collision routines depend on that truncation behavior.
struct Rect {
    int x = 0, y = 0, w = 0, h = 0;

    int left()   const { return x; }
    int right()  const { return x + w; }   // exclusive, matches pygame.Rect.right
    int top()    const { return y; }
    int bottom() const { return y + h; }   // exclusive, matches pygame.Rect.bottom

    bool collideRect(const Rect& other) const {
        return x < other.x + other.w && x + w > other.x &&
               y < other.y + other.h && y + h > other.y;
    }
    bool collidePoint(int px, int py) const {
        return px >= x && px < x + w && py >= y && py < y + h;
    }
};
