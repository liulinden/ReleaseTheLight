cmake_minimum_required(VERSION 3.16)

project(ReleaseTheLight)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(SDL2 REQUIRED)
find_package(SDL2_image REQUIRED)
find_package(SDL2_ttf REQUIRED)
find_package(Threads REQUIRED)


# -------------------------
# Polygon editor
# -------------------------

add_executable(polygon_editor
    polygon_editor/main.cpp
)

target_link_libraries(polygon_editor
    PRIVATE
        SDL2::SDL2
        SDL2_image::SDL2_image
)


# -------------------------
# C++ port
# -------------------------

file(GLOB CPP_PORT_SOURCES CONFIGURE_DEPENDS
    cpp_port/*.cpp
)

add_executable(cpp_port
    ${CPP_PORT_SOURCES}
)

target_link_libraries(cpp_port
    PRIVATE
        SDL2::SDL2
        SDL2_image::SDL2_image
        SDL2_ttf::SDL2_ttf
        Threads::Threads
)