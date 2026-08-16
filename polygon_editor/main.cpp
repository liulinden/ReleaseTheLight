#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <SDL_image.h>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace fs = std::filesystem;

struct Vertex {
    float x = 0.0f; // normalized image coordinate [0,1]
    float y = 0.0f;
};

struct ShapeData {
    std::string filename;
    std::vector<Vertex> vertices;
};

static constexpr int WINDOW_W = 1200;
static constexpr int WINDOW_H = 800;
static constexpr int DOT_RADIUS = 6;
static constexpr int DELETE_RADIUS = 14;
static constexpr int SIDE_PANEL_W = 270;

static float clamp01(float v) {
    return std::max(0.0f, std::min(1.0f, v));
}

static bool loadImageList(const std::string& path, std::vector<std::string>& files) {
    std::ifstream in(path);
    if (!in) return false;

    std::string line;
    while (std::getline(in, line)) {
        // Trim whitespace.
        auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        auto last = line.find_last_not_of(" \t\r\n");
        line = line.substr(first, last - first + 1);
        if (line.empty() || line[0] == '#') continue;
        files.push_back(line);
    }
    return !files.empty();
}

static bool loadData(const std::string& path,
                     std::unordered_map<std::string, ShapeData>& shapes) {
    std::ifstream in(path);
    if (!in) return false;

    std::string filename;
    while (std::getline(in, filename)) {
        if (!filename.empty() && filename.back() == '\r') filename.pop_back();
        if (filename.empty() || filename[0] == '#') continue;

        std::string countLine;
        if (!std::getline(in, countLine)) break;
        std::istringstream countStream(countLine);
        int count = 0;
        if (!(countStream >> count) || count < 0) return false;

        ShapeData shape;
        shape.filename = filename;
        shape.vertices.reserve(static_cast<size_t>(count));

        for (int i = 0; i < count; ++i) {
            std::string vertexLine;
            if (!std::getline(in, vertexLine)) return false;
            std::istringstream vs(vertexLine);
            Vertex v;
            if (!(vs >> v.x >> v.y)) return false;
            v.x = clamp01(v.x);
            v.y = clamp01(v.y);
            shape.vertices.push_back(v);
        }

        shapes[filename] = std::move(shape);
    }
    return true;
}

static bool saveData(const std::string& path,
                     const std::vector<std::string>& files,
                     const std::unordered_map<std::string, ShapeData>& shapes) {
    std::ofstream out(path);
    if (!out) return false;

    out << "# PNG Vector Editor polygon data\n";
    out << "# Each image is followed by a vertex count and normalized x y coordinates.\n\n";

    for (const auto& filename : files) {
        out << filename << '\n';
        auto it = shapes.find(filename);
        const auto& vertices = (it == shapes.end())
            ? std::vector<Vertex>{}
            : it->second.vertices;

        out << vertices.size() << '\n';
        for (const auto& v : vertices) {
            out << v.x << ' ' << v.y << '\n';
        }
        out << '\n';
    }
    return true;
}

static bool fileExists(const std::string& filename) {
    std::error_code ec;
    return fs::exists(filename, ec) && fs::is_regular_file(filename, ec);
}

static SDL_Texture* loadTexture(SDL_Renderer* renderer,
                                const std::string& filename,
                                int& width,
                                int& height) {
    SDL_Surface* surface = IMG_Load(filename.c_str());
    if (!surface) {
        std::cerr << "IMG_Load failed for " << filename << ": " << IMG_GetError() << '\n';
        return nullptr;
    }

    width = surface->w;
    height = surface->h;
    SDL_Texture* texture = SDL_CreateTextureFromSurface(renderer, surface);
    SDL_FreeSurface(surface);

    if (!texture) {
        std::cerr << "SDL_CreateTextureFromSurface failed: " << SDL_GetError() << '\n';
    }
    return texture;
}

static SDL_FPoint imageToScreen(const Vertex& v, const SDL_Rect& imageRect) {
    return {
        imageRect.x + v.x * imageRect.w,
        imageRect.y + v.y * imageRect.h
    };
}

static Vertex screenToImage(int mouseX, int mouseY, const SDL_Rect& imageRect) {
    return {
        clamp01((mouseX - imageRect.x) / static_cast<float>(imageRect.w)),
        clamp01((mouseY - imageRect.y) / static_cast<float>(imageRect.h))
    };
}

static float distanceSquared(float x1, float y1, float x2, float y2) {
    float dx = x1 - x2;
    float dy = y1 - y2;
    return dx * dx + dy * dy;
}

static int findVertexAt(const std::vector<Vertex>& vertices,
                        int mouseX, int mouseY,
                        const SDL_Rect& imageRect) {
    const float radiusSq = static_cast<float>(DELETE_RADIUS * DELETE_RADIUS);
    int best = -1;
    float bestDist = radiusSq;

    for (int i = 0; i < static_cast<int>(vertices.size()); ++i) {
        SDL_FPoint p = imageToScreen(vertices[i], imageRect);
        float d = distanceSquared(p.x, p.y,
                                  static_cast<float>(mouseX),
                                  static_cast<float>(mouseY));
        if (d <= bestDist) {
            bestDist = d;
            best = i;
        }
    }
    return best;
}

static void drawFilledCircle(SDL_Renderer* renderer, int cx, int cy, int radius) {
    for (int dy = -radius; dy <= radius; ++dy) {
        int dx = static_cast<int>(std::sqrt(radius * radius - dy * dy));
        SDL_RenderDrawLine(renderer, cx - dx, cy + dy, cx + dx, cy + dy);
    }
}

static void drawText(SDL_Renderer*, const std::string&, int, int) {
    // Intentionally empty: this version has no font dependency.
    // Controls are also printed to stdout when the program starts.
}

int main(int argc, char* argv[]) {
    std::string imageListPath = (argc >= 2) ? argv[1] : "polygon_editor/images.txt";
    std::string dataPath = (argc >= 3) ? argv[2] : "polygon_editor/shapes.txt";

    std::vector<std::string> files;
    if (!loadImageList(imageListPath, files)) {
        std::cerr << "Could not read image list: " << imageListPath << '\n';
        std::cerr << "Put one PNG filename/path per line in images.txt.\n";
        return 1;
    }

    std::unordered_map<std::string, ShapeData> shapes;
    if (!loadData(dataPath, shapes)) {
        std::cout << "No existing data file found. Starting with empty polygons.\n";
    }

    for (const auto& file : files) {
        if (!shapes.count(file)) {
            shapes[file] = ShapeData{file, {}};
        }
    }

    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        std::cerr << "SDL_Init failed: " << SDL_GetError() << '\n';
        return 1;
    }

    const int imgFlags = IMG_INIT_PNG;
    if ((IMG_Init(imgFlags) & imgFlags) != imgFlags) {
        std::cerr << "IMG_Init failed: " << IMG_GetError() << '\n';
        SDL_Quit();
        return 1;
    }

    SDL_Window* window = SDL_CreateWindow(
        "PNG Vector / Box2D Polygon Editor",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        WINDOW_W, WINDOW_H,
        SDL_WINDOW_RESIZABLE
    );

    if (!window) {
        std::cerr << "SDL_CreateWindow failed: " << SDL_GetError() << '\n';
        IMG_Quit();
        SDL_Quit();
        return 1;
    }

    SDL_Renderer* renderer = SDL_CreateRenderer(
        window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC
    );

    if (!renderer) {
        std::cerr << "SDL_CreateRenderer failed: " << SDL_GetError() << '\n';
        SDL_DestroyWindow(window);
        IMG_Quit();
        SDL_Quit();
        return 1;
    }

    int current = 0;
    SDL_Texture* texture = nullptr;
    int textureW = 1;
    int textureH = 1;
    bool running = true;
    bool dirty = false;

    auto loadCurrentTexture = [&]() {
        if (texture) {
            SDL_DestroyTexture(texture);
            texture = nullptr;
        }

        texture = loadTexture(renderer, files[current], textureW, textureH);
        if (!texture) {
            textureW = textureH = 1;
        }
    };

    loadCurrentTexture();

    std::cout << "\n=== PNG Vector / Box2D Polygon Editor ===\n";
    std::cout << "Left click       Add vertex\n";
    std::cout << "Right click      Delete nearest vertex\n";
    std::cout << "Left/Right       Previous/next image\n";
    std::cout << "S                Save shapes\n";
    std::cout << "Escape           Quit\n";
    std::cout << "Image list       " << imageListPath << "\n";
    std::cout << "Data file        " << dataPath << "\n\n";

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                running = false;
            }
            else if (event.type == SDL_KEYDOWN) {
                switch (event.key.keysym.sym) {
                    case SDLK_ESCAPE:
                        running = false;
                        break;

                    case SDLK_s:
                        if (saveData(dataPath, files, shapes)) {
                            dirty = false;
                            std::cout << "Saved: " << dataPath << '\n';
                        } else {
                            std::cerr << "Could not save: " << dataPath << '\n';
                        }
                        break;

                    case SDLK_LEFT:
                        if (current > 0) {
                            --current;
                            loadCurrentTexture();
                            std::cout << "Image: " << files[current] << '\n';
                        }
                        break;

                    case SDLK_RIGHT:
                        if (current + 1 < static_cast<int>(files.size())) {
                            ++current;
                            loadCurrentTexture();
                            std::cout << "Image: " << files[current] << '\n';
                        }
                        break;

                    default:
                        break;
                }
            }
            else if (event.type == SDL_MOUSEBUTTONDOWN && texture) {
                int windowW, windowH;
                SDL_GetWindowSize(window, &windowW, &windowH);

                SDL_Rect imageRect;
                imageRect.x = SIDE_PANEL_W;
                imageRect.y = 0;
                imageRect.w = windowW - SIDE_PANEL_W;
                imageRect.h = windowH;

                // Preserve image aspect ratio.
                const float availableW = static_cast<float>(imageRect.w);
                const float availableH = static_cast<float>(imageRect.h);
                const float scale = std::min(
                    availableW / textureW,
                    availableH / textureH
                );

                imageRect.w = static_cast<int>(textureW * scale);
                imageRect.h = static_cast<int>(textureH * scale);
                imageRect.x = SIDE_PANEL_W + (windowW - SIDE_PANEL_W - imageRect.w) / 2;
                imageRect.y = (windowH - imageRect.h) / 2;

                if (event.button.button == SDL_BUTTON_LEFT) {
                    if (event.button.x >= imageRect.x &&
                        event.button.x < imageRect.x + imageRect.w &&
                        event.button.y >= imageRect.y &&
                        event.button.y < imageRect.y + imageRect.h) {
                        auto& vertices = shapes[files[current]].vertices;
                        vertices.push_back(screenToImage(
                            event.button.x, event.button.y, imageRect
                        ));
                        dirty = true;
                    }
                }
                else if (event.button.button == SDL_BUTTON_RIGHT) {
                    auto& vertices = shapes[files[current]].vertices;
                    int index = findVertexAt(
                        vertices, event.button.x, event.button.y, imageRect
                    );
                    if (index >= 0) {
                        vertices.erase(vertices.begin() + index);
                        dirty = true;
                    }
                }
            }
        }

        int windowW, windowH;
        SDL_GetWindowSize(window, &windowW, &windowH);

        SDL_SetRenderDrawColor(renderer, 25, 25, 25, 255);
        SDL_RenderClear(renderer);

        // Sidebar.
        SDL_Rect sidebar{0, 0, SIDE_PANEL_W, windowH};
        SDL_SetRenderDrawColor(renderer, 38, 38, 38, 255);
        SDL_RenderFillRect(renderer, &sidebar);

        // Image area.
        SDL_Rect imageRect{SIDE_PANEL_W, 0, windowW - SIDE_PANEL_W, windowH};
        if (texture) {
            const float scale = std::min(
                imageRect.w / static_cast<float>(textureW),
                imageRect.h / static_cast<float>(textureH)
            );
            imageRect.w = static_cast<int>(textureW * scale);
            imageRect.h = static_cast<int>(textureH * scale);
            imageRect.x = SIDE_PANEL_W + (windowW - SIDE_PANEL_W - imageRect.w) / 2;
            imageRect.y = (windowH - imageRect.h) / 2;

            SDL_RenderCopy(renderer, texture, nullptr, &imageRect);

            const auto& vertices = shapes[files[current]].vertices;

            // Connections. With 2+ points, the last point connects back to the first,
            // making the result directly usable as a polygon.
            if (vertices.size() >= 2) {
                SDL_SetRenderDrawColor(renderer, 0, 255, 100, 255);
                for (size_t i = 0; i < vertices.size(); ++i) {
                    const Vertex& a = vertices[i];
                    const Vertex& b = vertices[(i + 1) % vertices.size()];
                    SDL_FPoint pa = imageToScreen(a, imageRect);
                    SDL_FPoint pb = imageToScreen(b, imageRect);
                    SDL_RenderDrawLineF(renderer, pa.x, pa.y, pb.x, pb.y);
                }
            }

            // Vertices.
            SDL_SetRenderDrawColor(renderer, 255, 80, 80, 255);
            for (const auto& v : vertices) {
                SDL_FPoint p = imageToScreen(v, imageRect);
                drawFilledCircle(renderer, static_cast<int>(p.x),
                                 static_cast<int>(p.y), DOT_RADIUS);
            }
        }

        SDL_RenderPresent(renderer);
    }

    if (dirty) {
        std::cout << "Unsaved changes were discarded. Press S before quitting to save.\n";
    }

    if (texture) SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    IMG_Quit();
    SDL_Quit();
    return 0;
}
