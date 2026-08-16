# PNG Vector / Box2D Polygon Editor

A small C++17 + SDL2 + SDL2_image editor for creating polygon vertices over PNG images.

The PNG is only a visual reference. The saved data contains normalized polygon vertices, making it easy for another C++ program to convert them into Box2D polygon shapes.

## Controls

- **Left click**: add a vertex
- **Right click**: delete the nearest vertex
- **Left / Right arrow**: change image
- **S**: save all polygon data
- **Escape**: quit

Vertices are connected in the order they were created, and the last vertex is connected back to the first.

## Files

`images.txt` contains one image path per line.

`shapes.txt` contains the polygon data. Example:

```
player.png
4
0.10 0.20
0.90 0.20
0.90 0.90
0.10 0.90
```

Coordinates are normalized from 0 to 1 relative to the image's width and height. This means another program can reconstruct the polygon at any desired physical scale.

## Build

Requires:

- C++17 compiler
- SDL2
- SDL2_image with PNG support
- CMake 3.16+

Typical CMake build:

```bash
cmake -S . -B build
cmake --build build --config Release
```

Run:

```bash
./build/png_vector_editor images.txt shapes.txt
```

On Windows, the exact executable location depends on the generator, commonly:

```text
build/Release/png_vector_editor.exe
```

## Important Box2D consideration

Box2D polygons have restrictions on vertex count and polygon geometry. Before feeding these polygons to Box2D, your game program should validate/simplify them as necessary. In particular, avoid self-intersecting polygons and ensure the vertices form a valid convex polygon when creating a single Box2D polygon shape.

For complex PNG outlines, the editor can later be extended to automatically decompose a concave polygon into multiple convex Box2D polygons.
