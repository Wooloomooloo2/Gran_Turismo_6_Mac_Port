# SPDX-License-Identifier: GPL-2.0-or-later
# Writes gt6.image (D44, D47): the pending record made at configure time plus
# "ps3recomp_tree", the hash of the submodule's working tree as it is now, at link time.
# Run by the gt6 target's POST_BUILD step:
#   cmake -DSUB=<ps3recomp> -DIN=<gt6.image.pending> -DOUT=<gt6.image> -P write_image.cmake
# The hash (scripts/boot_game.py ps3recomp_tree_hash computes the same): SHA-256 of
# `git diff --no-ext-diff --no-textconv HEAD --binary` (no user diff driver can change it,
# review M-2), then for each untracked file git lists (--exclude-standard, git's
# order, __pycache__ and .pyc left out) "<path>\n<sha256 of its content>\n".
execute_process(COMMAND git -C "${SUB}" diff --no-ext-diff --no-textconv HEAD --binary
                OUTPUT_VARIABLE diff RESULT_VARIABLE rc)
if(NOT rc EQUAL 0)
    message(FATAL_ERROR "git diff in ${SUB} failed (${rc})")
endif()
execute_process(COMMAND git -C "${SUB}" ls-files --others --exclude-standard
                OUTPUT_VARIABLE others RESULT_VARIABLE rc)
if(NOT rc EQUAL 0)
    message(FATAL_ERROR "git ls-files in ${SUB} failed (${rc})")
endif()
set(state "${diff}")
string(REPLACE "\n" ";" others "${others}")
foreach(f IN LISTS others)
    if(f STREQUAL "" OR f MATCHES "(^|/)__pycache__/" OR f MATCHES "\\.pyc$")
        continue()
    endif()
    file(SHA256 "${SUB}/${f}" h)
    string(APPEND state "${f}\n${h}\n")
endforeach()
string(SHA256 tree "${state}")
file(READ "${IN}" rec)
string(REGEX REPLACE "}[ \t\r\n]*$" ", \"ps3recomp_tree\": \"${tree}\"}\n" rec "${rec}")
file(WRITE "${OUT}" "${rec}")
