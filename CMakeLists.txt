# SPDX-License-Identifier: GPL-2.0-or-later
cmake_minimum_required(VERSION 3.24)
project(gt6mac LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

enable_testing()
add_subdirectory(tools/gt6unpack)

# The game port: the translated program plus ps3recomp's runtime, built into one native
# executable. Needs a translated tree outside the repository (port/CMakeLists.txt).
option(GT6_BUILD_PORT "Build the game port (needs GT6_TREE)" OFF)
if(GT6_BUILD_PORT)
    add_subdirectory(port)
endif()
