#include "Canvas.h"
#include "BlendModes.h"
#include <cmath>

namespace {
constexpr int kCircleSegments = 32;

SDL_Color toSDLColor(Color c) { return SDL_Color{ c.r, c.g, c.b, c.a }; }

SDL_Vertex makeVertex(double x, double y, SDL_Color c) {
    SDL_Vertex v;
    v.position = SDL_FPoint{ static_cast<float>(x), static_cast<float>(y) };
    v.color = c;
    v.tex_coord = SDL_FPoint{ 0.0f, 0.0f };
    return v;
}
} // namespace

namespace Canvas {

void circle(SDL_Renderer* renderer, Vec2 center, double radius, Color color, int width) {
    if (radius <= 0) return;
    SDL_Color sc = toSDLColor(color);
    // pygame.draw.* writes pixels directly (no alpha compositing against
    // existing content) -- matching this required an explicit NONE blend
    // mode; SDL_RenderGeometry otherwise honors the renderer's current
    // draw blend mode (defaults to BLEND), which would silently attenuate
    // any partially-transparent fill against whatever was underneath.
    // Caught via pixel-level testing, not visually -- see conversation notes.
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);

    if (width <= 0) {
        // Filled: triangle fan from the center.
        std::vector<SDL_Vertex> verts;
        verts.reserve(kCircleSegments + 1);
        verts.push_back(makeVertex(center.x, center.y, sc));
        for (int i = 0; i <= kCircleSegments; ++i) {
            double a = (2.0 * M_PI * i) / kCircleSegments;
            verts.push_back(makeVertex(center.x + radius * std::cos(a),
                                        center.y + radius * std::sin(a), sc));
        }
        std::vector<int> indices;
        indices.reserve(kCircleSegments * 3);
        for (int i = 1; i <= kCircleSegments; ++i) {
            indices.push_back(0);
            indices.push_back(i);
            indices.push_back(i + 1);
        }
        SDL_RenderGeometry(renderer, nullptr, verts.data(), static_cast<int>(verts.size()),
                            indices.data(), static_cast<int>(indices.size()));
    } else {
        // Outline: a ring between (radius - width/2) and (radius + width/2).
        double inner = std::max(0.0, radius - width / 2.0);
        double outer = radius + width / 2.0;
        std::vector<SDL_Vertex> verts;
        verts.reserve((kCircleSegments + 1) * 2);
        for (int i = 0; i <= kCircleSegments; ++i) {
            double a = (2.0 * M_PI * i) / kCircleSegments;
            double ca = std::cos(a), sa = std::sin(a);
            verts.push_back(makeVertex(center.x + inner * ca, center.y + inner * sa, sc));
            verts.push_back(makeVertex(center.x + outer * ca, center.y + outer * sa, sc));
        }
        std::vector<int> indices;
        indices.reserve(kCircleSegments * 6);
        for (int i = 0; i < kCircleSegments; ++i) {
            int i0 = i * 2, i1 = i * 2 + 1, i2 = i * 2 + 2, i3 = i * 2 + 3;
            indices.push_back(i0); indices.push_back(i1); indices.push_back(i2);
            indices.push_back(i1); indices.push_back(i3); indices.push_back(i2);
        }
        SDL_RenderGeometry(renderer, nullptr, verts.data(), static_cast<int>(verts.size()),
                            indices.data(), static_cast<int>(indices.size()));
    }
}

void line(SDL_Renderer* renderer, Vec2 start, Vec2 end, Color color, int thickness) {
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE); // see circle() note
    SDL_Color sc = toSDLColor(color);
    double dx = end.x - start.x, dy = end.y - start.y;
    double len = std::sqrt(dx * dx + dy * dy);
    if (len == 0.0) return;
    double nx = -dy / len * (thickness / 2.0);
    double ny = dx / len * (thickness / 2.0);

    SDL_Vertex verts[4] = {
        makeVertex(start.x + nx, start.y + ny, sc),
        makeVertex(start.x - nx, start.y - ny, sc),
        makeVertex(end.x + nx, end.y + ny, sc),
        makeVertex(end.x - nx, end.y - ny, sc),
    };
    int indices[6] = { 0, 1, 2, 1, 3, 2 };
    SDL_RenderGeometry(renderer, nullptr, verts, 4, indices, 6);
}

void polygon(SDL_Renderer* renderer, const std::vector<Vec2>& points, Color color) {
    if (points.size() < 3) return;
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE); // see circle() note
    SDL_Color sc = toSDLColor(color);

    std::vector<SDL_Vertex> verts;
    verts.reserve(points.size());
    for (auto& p : points) verts.push_back(makeVertex(p.x, p.y, sc));

    std::vector<int> indices;
    indices.reserve((points.size() - 2) * 3);
    for (size_t i = 1; i + 1 < points.size(); ++i) {
        indices.push_back(0);
        indices.push_back(static_cast<int>(i));
        indices.push_back(static_cast<int>(i + 1));
    }
    SDL_RenderGeometry(renderer, nullptr, verts.data(), static_cast<int>(verts.size()),
                        indices.data(), static_cast<int>(indices.size()));
}

void polygonOutline(SDL_Renderer* renderer, const std::vector<Vec2>& points, Color color, int width) {
    if (points.size() < 2) return;
    for (size_t i = 0; i < points.size(); ++i) {
        Vec2 a = points[i];
        Vec2 b = points[(i + 1) % points.size()];
        line(renderer, a, b, color, width);
    }
}

void rectFilled(SDL_Renderer* renderer, Rect r, Color color) {
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE); // see circle() note
    SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a);
    SDL_Rect sr{ r.x, r.y, r.w, r.h };
    SDL_RenderFillRect(renderer, &sr);
}

void rectOutline(SDL_Renderer* renderer, Rect r, Color color, int width) {
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE); // see circle() note
    for (int i = 0; i < width; ++i) {
        Rect shrunk{ r.x + i, r.y + i, r.w - 2 * i, r.h - 2 * i };
        if (shrunk.w <= 0 || shrunk.h <= 0) break;
        SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a);
        SDL_Rect sr{ shrunk.x, shrunk.y, shrunk.w, shrunk.h };
        SDL_RenderDrawRect(renderer, &sr);
    }
}

void multiplyTint(SDL_Renderer* renderer, Rect region, Color color) {
    SDL_SetRenderDrawBlendMode(renderer, BlendModes::rgbMult());
    SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, 255);
    SDL_Rect r{ region.x, region.y, region.w, region.h };
    SDL_RenderFillRect(renderer, &r);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

} // namespace Canvas
