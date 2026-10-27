# SPDX-License-Identifier: GPL-2.0-only
add_library(gt6crypto STATIC src/crypto.cpp src/keys.cpp src/self.cpp src/sfo.cpp src/pkg.cpp)
target_include_directories(gt6crypto PUBLIC src)
target_compile_options(gt6crypto PRIVATE -Wall -Wextra)
find_package(ZLIB REQUIRED)
target_link_libraries(gt6crypto PUBLIC ZLIB::ZLIB)

add_library(gt6build STATIC src/json_util.cpp src/updates.cpp src/klic.cpp src/build_tree.cpp src/manifest.cpp)
target_include_directories(gt6build PUBLIC src)
target_compile_options(gt6build PRIVATE -Wall -Wextra)
target_link_libraries(gt6build PUBLIC gt6crypto)

add_executable(gt6unpack src/main.cpp)
target_compile_options(gt6unpack PRIVATE -Wall -Wextra)
target_compile_definitions(gt6unpack PRIVATE GT6_REPO_EDITIONS="${PROJECT_SOURCE_DIR}/editions")
target_link_libraries(gt6unpack PRIVATE gt6build)

add_executable(gt6unpack_tests
  tests/main.cpp
  tests/test_crypto.cpp
  tests/test_keys.cpp
  tests/test_self.cpp
  tests/test_sfo.cpp
  tests/test_pkg.cpp
  tests/test_build_tree.cpp
  tests/test_klic.cpp
  tests/test_manifest.cpp)
target_include_directories(gt6unpack_tests PRIVATE ${PROJECT_SOURCE_DIR}/third_party/doctest tests)
target_compile_options(gt6unpack_tests PRIVATE -Wall -Wextra)
target_link_libraries(gt6unpack_tests PRIVATE gt6build)

# Integration tests read GT6_DISC_DIR / GT6_UPDATES_DIR at runtime and skip when unset.
add_test(NAME gt6unpack_tests COMMAND gt6unpack_tests)
