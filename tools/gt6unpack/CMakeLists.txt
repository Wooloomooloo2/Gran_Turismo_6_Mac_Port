add_library(gt6crypto STATIC src/crypto.cpp src/keys.cpp src/self.cpp src/sfo.cpp src/pkg.cpp)
target_include_directories(gt6crypto PUBLIC src)
target_compile_options(gt6crypto PRIVATE -Wall -Wextra)
find_package(ZLIB REQUIRED)
target_link_libraries(gt6crypto PUBLIC ZLIB::ZLIB)

add_executable(gt6unpack_tests
  tests/main.cpp
  tests/test_crypto.cpp
  tests/test_keys.cpp
  tests/test_self.cpp
  tests/test_sfo.cpp
  tests/test_pkg.cpp)
target_include_directories(gt6unpack_tests PRIVATE ${PROJECT_SOURCE_DIR}/third_party/doctest tests)
target_compile_options(gt6unpack_tests PRIVATE -Wall -Wextra)
target_link_libraries(gt6unpack_tests PRIVATE gt6crypto)

# Integration tests read GT6_DISC_DIR / GT6_UPDATES_DIR at runtime and skip when unset.
add_test(NAME gt6unpack_tests COMMAND gt6unpack_tests)
