# SPDX-License-Identifier: GPL-2.0-or-later
# Writes gt6.image (D44, D47, D72): the pending record made at configure time plus
# "ps3recomp_tree", the ps3recomp working tree's hash as the tree stamp holds it. Every
# object of the binary was compiled after the stamp last changed (tree_stamp.cmake), so this
# is the tree the binary's code was built from, not merely the tree at link time.
# Run by the gt6 target's POST_BUILD step:
#   cmake -DSTAMP=<tree stamp> -DIN=<gt6.image.pending> -DOUT=<gt6.image> -P write_image.cmake
file(READ "${STAMP}" tree)
string(STRIP "${tree}" tree)
if(NOT tree MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "tree stamp ${STAMP} holds no hash")
endif()
file(READ "${IN}" rec)
string(REGEX REPLACE "}[ \t\r\n]*$" ", \"ps3recomp_tree\": \"${tree}\"}\n" rec "${rec}")
file(WRITE "${OUT}" "${rec}")
