#pragma once
#include "Core.h"

// General-purpose 9-point anchor for positioning UI/drawn elements.
// Generalizes interaction_display.py's "centered" / "top_centered" align
// strings into a reusable type other UI code can share instead of each
// redefining its own ad-hoc alignment scheme (HealthBar's blit-position
// formula turns out to be exactly a Center anchor once factored out --
// see HealthBar::draw).
enum class Anchor {
    TopLeft, TopCenter, TopRight,
    CenterLeft, Center, CenterRight,
    BottomLeft, BottomCenter, BottomRight,
};

// Given an item of size (w, h) to be anchored at some reference point via
// `anchor`, returns the offset to ADD to that reference point to get the
// item's top-left corner for blitting. E.g. Anchor::Center -> (-w/2, -h/2).
inline Vec2 anchorOffset(Anchor anchor, double w, double h) {
    double dx = 0.0, dy = 0.0;
    switch (anchor) {
        case Anchor::TopLeft:      dx = 0.0;    dy = 0.0;    break;
        case Anchor::TopCenter:    dx = -w/2.0; dy = 0.0;    break;
        case Anchor::TopRight:     dx = -w;     dy = 0.0;    break;
        case Anchor::CenterLeft:   dx = 0.0;    dy = -h/2.0; break;
        case Anchor::Center:       dx = -w/2.0; dy = -h/2.0; break;
        case Anchor::CenterRight:  dx = -w;     dy = -h/2.0; break;
        case Anchor::BottomLeft:   dx = 0.0;    dy = -h;     break;
        case Anchor::BottomCenter: dx = -w/2.0; dy = -h;     break;
        case Anchor::BottomRight:  dx = -w;     dy = -h;     break;
    }
    return { dx, dy };
}
