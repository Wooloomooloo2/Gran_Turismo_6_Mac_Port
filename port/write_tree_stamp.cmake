# SPDX-License-Identifier: GPL-2.0-or-later
# The tree stamp (D72): writes the ps3recomp working tree's hash (tree_hash.cmake) to
# ${STAMP}, and only when it differs from what the stamp holds, so the stamp's time changes
# exactly when the tree's content does. Every object built from or against the submodule
# depends on the stamp (tree_stamp.cmake), so a changed tree recompiles them all, whatever
# the sources' modification times say. Run before each build:
#   cmake -DSUB=<ps3recomp> -DSTAMP=<file> -P write_tree_stamp.cmake
include("${CMAKE_CURRENT_LIST_DIR}/tree_hash.cmake")
set(old "")
if(EXISTS "${STAMP}")
    file(READ "${STAMP}" old)
    string(STRIP "${old}" old)
endif()
if(NOT old STREQUAL tree)
    file(WRITE "${STAMP}" "${tree}\n")
endif()
