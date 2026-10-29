# SPDX-License-Identifier: GPL-2.0-or-later
# Included by write_tree_stamp.cmake: sets `tree` to the hash of the ps3recomp working tree
# at ${SUB} (D47, D56). scripts/boot_game.py ps3recomp_tree_hash computes the same: SHA-256
# of `git diff --no-ext-diff --no-textconv HEAD --binary` (no user diff driver can change
# it, review M-2) with carriage returns removed, then for each untracked file git lists
# (--exclude-standard, git's order, __pycache__ and .pyc left out)
# "<path>\n<sha256 of its content>\n".
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
# execute_process already drops carriage returns on capture; say so, and make sure of it
# (scripts/boot_game.py removes them too, so CRLF files hash the same on both sides).
string(REPLACE "\r" "" diff "${diff}")
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
