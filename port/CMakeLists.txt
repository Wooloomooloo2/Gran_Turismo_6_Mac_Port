# SPDX-License-Identifier: GPL-2.0-or-later
# Adapted from ps3recomp templates/project/CMakeLists.txt at commit
# 4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514. That file: Copyright (c) 2026 Ned Heller / sp00nznet,
# MIT licence (full text in THIRD-PARTY-NOTICES.md and third_party/ps3recomp/LICENSE).
#
# The GT6 port: the lifted EMAIN program, ps3recomp's runtime and a small runner, built into
# one native executable, gt6. Configure from the repository root:
#
#   cmake -S . -B "$GT6_TREE/port-build" -G Ninja -DGT6_BUILD_PORT=ON \
#         -DGT6_TREE="$GT6_TREE" -DCMAKE_BUILD_TYPE=Release
#   cmake --build "$GT6_TREE/port-build" --target gt6
#   "$GT6_TREE/port-build/port/gt6" "$GT6_TREE/decrypted/.../USRDIR/EMAIN.SELF.elf"
#
# GT6_TREE is a gt6unpack build tree translated by scripts/translate_game.py (it has
# recomp/translate.json). Everything this build writes lives in the build folder, which must
# be outside the repository (D26). Changes from the template: the GT6_TREE checks, the
# configure-time patch step (D28), the VFS defaults, SPU images chosen from the inventory,
# explicit -O1/-O2 levels (D30), macOS arm64 only.

if(NOT APPLE OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)$")
    message(FATAL_ERROR "The GT6 port builds on macOS arm64 only "
                        "(this host: ${CMAKE_SYSTEM_NAME} ${CMAKE_SYSTEM_PROCESSOR}).")
endif()

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
# The template and the runtime build with the compiler's default (GNU) extensions; the
# repository root turns them off for its own tools.
set(CMAKE_CXX_EXTENSIONS ON)

# ---------------------------------------------------------------------------
# GT6_TREE: where the translated program is, and where everything generated goes
# ---------------------------------------------------------------------------
set(GT6_TREE "" CACHE PATH "gt6unpack build tree translated by scripts/translate_game.py")
if(NOT GT6_TREE)
    message(FATAL_ERROR "GT6_BUILD_PORT needs -DGT6_TREE=<your gt6unpack build tree>.")
endif()
get_filename_component(GT6_REPO "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
file(REAL_PATH "${GT6_REPO}" GT6_REPO_REAL)
get_filename_component(GT6_TREE "${GT6_TREE}" ABSOLUTE)
file(REAL_PATH "${GT6_TREE}" GT6_TREE_REAL)
file(REAL_PATH "${CMAKE_BINARY_DIR}" GT6_BUILD_REAL)
# True if path, or its nearest existing ancestor, is inside any git work tree (as the
# scripts' in_git_work_tree).
function(gt6_in_git_work_tree out path)
    set(probe "${path}")
    while(NOT EXISTS "${probe}")
        get_filename_component(parent "${probe}" DIRECTORY)
        if(parent STREQUAL probe)
            break()
        endif()
        set(probe "${parent}")
    endwhile()
    execute_process(COMMAND git -C "${probe}" rev-parse --is-inside-work-tree
                    OUTPUT_VARIABLE git_out OUTPUT_STRIP_TRAILING_WHITESPACE
                    ERROR_QUIET RESULT_VARIABLE rc)
    if(rc EQUAL 0 AND git_out STREQUAL "true")
        set(${out} TRUE PARENT_SCOPE)
    else()
        set(${out} FALSE PARENT_SCOPE)
    endif()
endfunction()
foreach(path IN ITEMS "${GT6_TREE}" "${GT6_TREE_REAL}" "${CMAKE_BINARY_DIR}" "${GT6_BUILD_REAL}")
    set(inside FALSE)
    foreach(repo IN ITEMS "${GT6_REPO}" "${GT6_REPO_REAL}")
        cmake_path(IS_PREFIX repo "${path}" NORMALIZE in_repo)
        if(in_repo)
            set(inside TRUE)
        endif()
    endforeach()
    if(NOT inside)
        gt6_in_git_work_tree(inside "${path}")
    endif()
    if(inside)
        message(FATAL_ERROR
            "GT6_TREE must be outside the repository and any other git work tree, and so must "
            "the build folder: translated code and everything built from it is derived from "
            "the game (D26).\n"
            "  GT6_TREE: ${GT6_TREE} (${GT6_TREE_REAL})\n"
            "  build:    ${CMAKE_BINARY_DIR} (${GT6_BUILD_REAL})\n  repo:     ${GT6_REPO}")
    endif()
endforeach()

# The translated program: <tree>/recomp by default; GT6_RECOMP names another translation of
# the same tree (the post-install EMAIN, D44).
set(GT6_RECOMP "${GT6_TREE}/recomp" CACHE PATH "translate_game.py output folder to build")
set(GT6_TRANSLATE_JSON "${GT6_RECOMP}/translate.json")
if(NOT EXISTS "${GT6_TRANSLATE_JSON}")
    message(FATAL_ERROR
        "No translated program in ${GT6_TREE} (no recomp/translate.json).\n"
        "Run: .venv/bin/python scripts/translate_game.py \"${GT6_TREE}\"")
endif()
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${GT6_TRANSLATE_JSON}")
file(READ "${GT6_TRANSLATE_JSON}" GT6_TRANSLATE)
string(JSON GT6_LIFT_COMMIT  ERROR_VARIABLE err GET "${GT6_TRANSLATE}" ps3recomp_commit)
string(JSON GT6_LIFT_PATCHES ERROR_VARIABLE err GET "${GT6_TRANSLATE}" ps3recomp_patches)
string(JSON GT6_LIFT_ELF     ERROR_VARIABLE err GET "${GT6_TRANSLATE}" elf)
string(JSON GT6_LIFT_ELF_SHA ERROR_VARIABLE err GET "${GT6_TRANSLATE}" elf_sha256)

set(PS3RECOMP_DIR "${GT6_REPO}/third_party/ps3recomp")
execute_process(COMMAND git -C "${PS3RECOMP_DIR}" rev-parse HEAD
                OUTPUT_VARIABLE GT6_PS3RECOMP_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE
                RESULT_VARIABLE rc)
if(NOT rc EQUAL 0 OR NOT GT6_PS3RECOMP_COMMIT)
    message(FATAL_ERROR "No ps3recomp checkout at ${PS3RECOMP_DIR} "
                        "(git submodule update --init third_party/ps3recomp).")
endif()
# The command that re-makes this build's translation: the default one, or (D44) the -o/--elf
# form for another executable. After any patch or submodule change every image needs it
# (README step 4b).
if(GT6_LIFT_ELF AND NOT GT6_RECOMP STREQUAL "${GT6_TREE}/recomp")
    set(GT6_RETRANSLATE "Re-run: .venv/bin/python scripts/translate_game.py \"${GT6_TREE}\" "
                        "-o \"${GT6_RECOMP}\" --elf ${GT6_LIFT_ELF}")
    string(CONCAT GT6_RETRANSLATE ${GT6_RETRANSLATE})
else()
    set(GT6_RETRANSLATE "Re-run: .venv/bin/python scripts/translate_game.py \"${GT6_TREE}\"")
endif()
string(APPEND GT6_RETRANSLATE
    "\n(after a patch or submodule change, re-translate and rebuild every image: README step 4b)")
if(NOT GT6_LIFT_COMMIT STREQUAL GT6_PS3RECOMP_COMMIT)
    message(FATAL_ERROR
        "GT6_TREE was translated with a different ps3recomp: commit '${GT6_LIFT_COMMIT}', "
        "this checkout is ${GT6_PS3RECOMP_COMMIT}.\n${GT6_RETRANSLATE}")
endif()

# ---------------------------------------------------------------------------
# ps3recomp patches (D28): applied to the submodule's working tree, never committed there.
# Applied before the hash check below, so the build compiles the patch set the hash names.
# ---------------------------------------------------------------------------
execute_process(COMMAND bash "${GT6_REPO}/scripts/apply_ps3recomp_patches.sh"
                OUTPUT_VARIABLE out ERROR_VARIABLE err RESULT_VARIABLE rc)
if(NOT rc EQUAL 0)
    message(FATAL_ERROR "Could not apply the ps3recomp patches:\n${out}${err}"
        "To start over from the pinned commit (this also removes the files the patches add):\n"
        "  git -C third_party/ps3recomp checkout . && git -C third_party/ps3recomp clean -fd")
endif()
string(STRIP "${out}" out)
message(STATUS "ps3recomp patches: ${out}")

# The same hash as translate_game.patches_hash: SHA-256 over patches/ps3recomp/*.patch,
# concatenated in filename order (file(GLOB) sorts lexicographically).
file(GLOB GT6_PATCHES "${GT6_REPO}/patches/ps3recomp/*.patch")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${GT6_PATCHES})
set(GT6_PATCHES_CAT "${CMAKE_CURRENT_BINARY_DIR}/ps3recomp_patches.cat")
file(WRITE "${GT6_PATCHES_CAT}" "")
if(GT6_PATCHES)
    # cat, not file(READ)/file(APPEND): the hash is over the raw bytes.
    execute_process(COMMAND cat ${GT6_PATCHES} OUTPUT_FILE "${GT6_PATCHES_CAT}"
                    RESULT_VARIABLE rc)
    if(NOT rc EQUAL 0)
        message(FATAL_ERROR "Could not read patches/ps3recomp")
    endif()
endif()
file(SHA256 "${GT6_PATCHES_CAT}" GT6_PATCHES_HASH)
if(NOT GT6_LIFT_PATCHES STREQUAL GT6_PATCHES_HASH)
    message(FATAL_ERROR
        "GT6_TREE was translated with a different ps3recomp: same commit, but its patches "
        "(patches/ps3recomp) have changed since (hash '${GT6_LIFT_PATCHES}', now "
        "${GT6_PATCHES_HASH}).\n${GT6_RETRANSLATE}")
endif()

set(GT6_ELF "${GT6_TREE}/${GT6_LIFT_ELF}")
if(NOT EXISTS "${GT6_ELF}")
    message(FATAL_ERROR "The translated ELF is missing: ${GT6_ELF}")
endif()
file(SHA256 "${GT6_ELF}" GT6_ELF_SHA)
if(NOT GT6_ELF_SHA STREQUAL GT6_LIFT_ELF_SHA)
    message(FATAL_ERROR
        "${GT6_ELF} has changed since it was translated (SHA-256 ${GT6_ELF_SHA}, "
        "translate.json has ${GT6_LIFT_ELF_SHA}).\n${GT6_RETRANSLATE}")
endif()

# ---------------------------------------------------------------------------
# The two directories the template builds from
# ---------------------------------------------------------------------------
set(RECOMP_DIR "${GT6_RECOMP}/ppu")
set(SPU_DIR    "${GT6_RECOMP}/spu")
message(STATUS "ps3recomp SDK:   ${PS3RECOMP_DIR} (${GT6_PS3RECOMP_COMMIT})")
message(STATUS "Lifted output:   ${RECOMP_DIR}")

if(NOT EXISTS "${RECOMP_DIR}/ppu_recomp.h")
    message(FATAL_ERROR "No ppu_recomp.h in ${RECOMP_DIR}.\n${GT6_RETRANSLATE}")
endif()
file(GLOB RECOMP_SOURCES CONFIGURE_DEPENDS "${RECOMP_DIR}/*.c" "${RECOMP_DIR}/*.cpp")
if(NOT RECOMP_SOURCES)
    message(FATAL_ERROR "${RECOMP_DIR} has a ppu_recomp.h but no lifted sources.\n${GT6_RETRANSLATE}")
endif()
list(LENGTH RECOMP_SOURCES RECOMP_SOURCE_COUNT)
message(STATUS "Lifted sources:  ${RECOMP_SOURCE_COUNT} file(s)")
# ps3recomp's SPURS taskset generator can write the libsre policy module's bytes here. They
# are Sony firmware: never compiled or linked (D27).
if(EXISTS "${SPU_DIR}/taskset_policy_bytes.c")
    message(FATAL_ERROR
        "${SPU_DIR}/taskset_policy_bytes.c holds Sony firmware bytes (libsre's taskset policy "
        "module); the port never links firmware (D27). Delete it.\n${GT6_RETRANSLATE}")
endif()

# ---------------------------------------------------------------------------
# ps3recomp runtime library
# ---------------------------------------------------------------------------
add_subdirectory("${PS3RECOMP_DIR}" "${CMAKE_BINARY_DIR}/ps3recomp_sdk" EXCLUDE_FROM_ALL)

# ---------------------------------------------------------------------------
# The HLE NID table: the canonical every-module table, as the template generates it
# ---------------------------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter REQUIRED)
set(HLE_NID_TABLE "${CMAKE_CURRENT_BINARY_DIR}/ppu_hle_nids.cpp")
file(GLOB_RECURSE HLE_NID_SOURCES CONFIGURE_DEPENDS "${PS3RECOMP_DIR}/libs/*.c")
set(HLE_NID_SOURCE_LIST "${CMAKE_CURRENT_BINARY_DIR}/hle_nid_sources.txt")
file(GENERATE OUTPUT "${HLE_NID_SOURCE_LIST}" CONTENT "${HLE_NID_SOURCES}\n")
add_custom_command(
    OUTPUT "${HLE_NID_TABLE}"
    COMMAND "${Python3_EXECUTABLE}" "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
            --out "${HLE_NID_TABLE}" --all
    DEPENDS "${PS3RECOMP_DIR}/tools/gen_hle_nids.py" "${PS3RECOMP_DIR}/tools/nid_database.py"
            ${HLE_NID_SOURCES} "${HLE_NID_SOURCE_LIST}"
    COMMENT "Generating the HLE NID -> handler table")

set(PS3RECOMP_SCAFFOLD
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_loader.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_hle.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_fs.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_sysprx.cpp"
)

# ---------------------------------------------------------------------------
# Lifted SPU images
# ---------------------------------------------------------------------------
# Only images the SPU registry can dispatch are compiled: the SPU programs the inventory
# marks registered (or handled), and every job module lift_jobmods registered. An image
# build_spu_workloads refused (3 of GT6's 4 programs, translate.json "partial") is not in
# spu_workloads.c, so its spu_recomp.c would be dead code; it runs in the SPU interpreter
# (D9, D27). recomp/spu/sources.cmake is not used: it names the staging folder.
set(SPU_SOURCES "")
file(READ "${SPU_DIR}/inventory.json" spu_inv)
string(JSON n_programs LENGTH "${spu_inv}" programs)
set(spu_programs 0)
if(n_programs GREATER 0)
    math(EXPR last "${n_programs} - 1")
    foreach(i RANGE ${last})
        string(JSON name ERROR_VARIABLE no_name GET "${spu_inv}" programs ${i} name)
        string(JSON status GET "${spu_inv}" programs ${i} status)
        if(NOT no_name AND status MATCHES "^(registered|handled)$")
            list(APPEND SPU_SOURCES "${SPU_DIR}/${name}/spu_recomp.c")
            math(EXPR spu_programs "${spu_programs} + 1")
        endif()
    endforeach()
endif()
set(spu_jobmods 0)
if(EXISTS "${SPU_DIR}/jobmods_manifest.json")
    file(READ "${SPU_DIR}/jobmods_manifest.json" spu_mods)
    string(JSON n_mods LENGTH "${spu_mods}")
    if(n_mods GREATER 0)
        math(EXPR last "${n_mods} - 1")
        foreach(i RANGE ${last})
            string(JSON name GET "${spu_mods}" ${i} name)
            list(APPEND SPU_SOURCES "${SPU_DIR}/${name}/spu_recomp.c")
        endforeach()
        set(spu_jobmods ${n_mods})
    endif()
endif()
# SPU images the game ran with no lifted code, dumped to <tree>/spu-missed and lifted by the
# translate step (D33); spu_missed_register.c registers them by fingerprint.
set(spu_missed 0)
if(EXISTS "${SPU_DIR}/spu_missed_manifest.json")
    file(READ "${SPU_DIR}/spu_missed_manifest.json" spu_miss)
    string(JSON n_miss LENGTH "${spu_miss}")
    if(n_miss GREATER 0)
        math(EXPR last "${n_miss} - 1")
        foreach(i RANGE ${last})
            string(JSON name GET "${spu_miss}" ${i} name)
            list(APPEND SPU_SOURCES "${SPU_DIR}/${name}/spu_recomp.c")
        endforeach()
        set(spu_missed ${n_miss})
    endif()
endif()
message(STATUS "Lifted SPU:      ${spu_programs} of ${n_programs} program(s), ${spu_jobmods} job module(s), ${spu_missed} image(s) from spu-missed")
# The musttail indirect-branch fast path; it must be built here, by clang (template note).
list(APPEND SPU_SOURCES "${PS3RECOMP_DIR}/runtime/spu/spu_dispatch_mt.c")
foreach(gen IN ITEMS spu_workloads.c jobmods_register.c spu_missed_register.c)
    if(EXISTS "${SPU_DIR}/${gen}")
        list(APPEND SPU_SOURCES "${SPU_DIR}/${gen}")
    else()
        message(STATUS "  (no ${gen} -- not registered)")
    endif()
endforeach()

# ---------------------------------------------------------------------------
# Default VFS roots, baked in at configure time; PS3_VFS_ROOT and PS3_HDD0_ROOT override
# ---------------------------------------------------------------------------
function(gt6_c_string out value)
    string(REPLACE "\\" "\\\\" value "${value}")
    string(REPLACE "\"" "\\\"" value "${value}")
    set(${out} "\"${value}\"" PARENT_SCOPE)
endfunction()
gt6_c_string(GT6_DEFAULT_VFS_ROOT  "${GT6_TREE}/dev_bdvd")
# /dev_hdd0 is the play folder made by scripts/prepare_play.py, never the verified tree (D32).
gt6_c_string(GT6_DEFAULT_HDD0_ROOT "${GT6_TREE}/play/dev_hdd0")
# SPU images with no lifted code are dumped here at run time and lifted by the next translate (D33).
gt6_c_string(GT6_DEFAULT_SPU_MISSED "${GT6_TREE}/spu-missed")
# Which executable this binary is (D44): the SELF in the verified tree that translate.json's
# decrypted ELF came from (decrypted/<path>.elf <- <path>), by SHA-256. At start and on each
# exit-spawn the port hashes the play folder's USRDIR/EMAIN.SELF and, when it is another
# executable, re-executes the binary built for that one (GT6_IMAGES, set by boot_game.py from
# the gt6.image file written here beside each binary).
string(REGEX REPLACE "^decrypted/(.*)\\.elf$" "\\1" GT6_SELF_REL "${GT6_LIFT_ELF}")
if(GT6_SELF_REL STREQUAL GT6_LIFT_ELF OR NOT EXISTS "${GT6_TREE}/${GT6_SELF_REL}")
    message(FATAL_ERROR "translate.json names ${GT6_LIFT_ELF}, whose SELF "
                        "${GT6_TREE}/${GT6_SELF_REL} is not in the tree")
endif()
file(SHA256 "${GT6_TREE}/${GT6_SELF_REL}" GT6_SELF_SHA256)
gt6_c_string(GT6_SELF_SHA256_C "${GT6_SELF_SHA256}")
gt6_c_string(GT6_LIFT_ELF_PATH_C "${GT6_TREE}/${GT6_LIFT_ELF}")
gt6_c_string(GT6_PATCHES_HASH_C "${GT6_PATCHES_HASH}")
gt6_c_string(GT6_PS3RECOMP_COMMIT_C "${GT6_PS3RECOMP_COMMIT}")
file(CONFIGURE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/gt6_paths.h" CONTENT
"/* Generated by port/CMakeLists.txt. */
#define GT6_DEFAULT_VFS_ROOT  @GT6_DEFAULT_VFS_ROOT@
#define GT6_DEFAULT_HDD0_ROOT @GT6_DEFAULT_HDD0_ROOT@
#define GT6_DEFAULT_SPU_MISSED @GT6_DEFAULT_SPU_MISSED@
#define GT6_SELF_SHA256 @GT6_SELF_SHA256_C@
#define GT6_LIFT_ELF_PATH @GT6_LIFT_ELF_PATH_C@
#define GT6_PATCHES_HASH @GT6_PATCHES_HASH_C@
#define GT6_PS3RECOMP_COMMIT @GT6_PS3RECOMP_COMMIT_C@
")
# gt6.image names the build's SELF and the ps3recomp commit and patch set it was made from
# (D47). It is written beside the binary only after a successful link (POST_BUILD below), so a
# failed build never leaves a new gt6.image next to an old binary.
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/gt6.image.pending"
     "{\"self\": \"${GT6_SELF_REL}\", \"self_sha256\": \"${GT6_SELF_SHA256}\", "
     "\"elf\": \"${GT6_LIFT_ELF}\", \"ps3recomp_commit\": \"${GT6_PS3RECOMP_COMMIT}\", "
     "\"ps3recomp_patches\": \"${GT6_PATCHES_HASH}\"}\n")

# ---------------------------------------------------------------------------
# The game executable
# ---------------------------------------------------------------------------
add_executable(gt6
    main.cpp
    gt6_overrides.cpp
    gt6_spurs.cpp
    ${PS3RECOMP_SCAFFOLD}
    ${HLE_NID_TABLE}
    ${RECOMP_SOURCES}
    ${SPU_SOURCES}
)

# SPU sources: their own include directory and the musttail define, scoped to them so the
# lifted PPU TUs' compile commands do not change; -O2 because they are small and hot (D30).
set_source_files_properties(${SPU_SOURCES} PROPERTIES
    INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/spu"
    COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT
    COMPILE_OPTIONS "-O2")

target_include_directories(gt6 PRIVATE
    "${RECOMP_DIR}"
    "${PS3RECOMP_DIR}/include"
    "${PS3RECOMP_DIR}/runtime/ppu"
    "${PS3RECOMP_DIR}/runtime/spu"
    "${PS3RECOMP_DIR}/runtime/memory"
    "${PS3RECOMP_DIR}/runtime/syscalls"
    "${PS3RECOMP_DIR}/runtime/platform"
    "${PS3RECOMP_DIR}/libs/video"
    "${PS3RECOMP_DIR}/libs/filesystem"
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${CMAKE_CURRENT_BINARY_DIR}"
)
target_link_libraries(gt6 PRIVATE ps3recomp_runtime)
# The tree stamp (D72): every object of gt6 and of the runtime depends on a file that changes
# when the submodule's working-tree hash does, so a changed tree recompiles them all even when
# a source's modification time is older than its object (a `cp -p` restore).
include("${CMAKE_CURRENT_SOURCE_DIR}/tree_stamp.cmake")
set(GT6_TREE_STAMP "${CMAKE_CURRENT_BINARY_DIR}/ps3recomp_tree.stamp")
gt6_tree_stamp(gt6_tree_stamp SUB "${PS3RECOMP_DIR}" STAMP "${GT6_TREE_STAMP}"
               TARGETS gt6 ps3recomp_runtime)
# The POST_BUILD step records the tree hash from the stamp, the tree every object was compiled
# from, so an edit outside the patch series (a debug line) makes the other builds stale (D47).
add_custom_command(TARGET gt6 POST_BUILD
    COMMAND ${CMAKE_COMMAND} -DSTAMP=${GT6_TREE_STAMP}
                             -DIN=${CMAKE_CURRENT_BINARY_DIR}/gt6.image.pending
                             -DOUT=$<TARGET_FILE_DIR:gt6>/gt6.image
                             -P ${CMAKE_CURRENT_SOURCE_DIR}/write_image.cmake
    COMMENT "gt6.image: the SELF, patch set and ps3recomp tree this binary was built from (D44, D47)")
set_target_properties(gt6 PROPERTIES LINKER_LANGUAGE CXX)

target_compile_options(gt6 PRIVATE
    -Wall -Wextra -Wno-unused-parameter
    -fno-strict-aliasing
    # The lift spells PPC arithmetic as signed C arithmetic, which must wrap.
    -fwrapv
    $<$<NOT:$<CONFIG:Debug,Release,RelWithDebInfo,MinSizeRel>>:-O1>
)

# Lifted PPU TUs: warnings off, no FP contraction (a PPC fmadd is spelt as one where the
# lifter means one), and -O1 in every configuration (D30: 65 chunks of up to 16 s each at
# -O1; the level is revisited in milestone 5 with measurements). The last -O wins.
set_source_files_properties(${RECOMP_SOURCES} PROPERTIES
    COMPILE_OPTIONS "-w;-ffp-contract=off;-O1")

# ---------------------------------------------------------------------------
# The window launcher (macOS), as in the template: holds the window across an exec
# ---------------------------------------------------------------------------
enable_language(OBJC)
add_executable(gt6_window "${PS3RECOMP_DIR}/tools/host_window/host_window.m")
target_include_directories(gt6_window PRIVATE "${PS3RECOMP_DIR}/libs/video")
target_compile_definitions(gt6_window PRIVATE HOST_WINDOW_TITLE="Gran Turismo 6")
target_compile_options(gt6_window PRIVATE -fobjc-arc -Wall -Wextra -Wno-unused-parameter)
target_link_libraries(gt6_window PRIVATE
    "-framework AppKit" "-framework Metal" "-framework QuartzCore" "-framework IOSurface")
