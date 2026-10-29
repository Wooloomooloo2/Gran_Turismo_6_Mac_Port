# SPDX-License-Identifier: GPL-2.0-or-later
# The tree stamp (D72). gt6_tree_stamp(<name> SUB <ps3recomp> STAMP <file> TARGETS <t>...)
# adds a target <name> that runs on every build and rewrites STAMP when the submodule's
# working-tree hash changes (write_tree_stamp.cmake), and makes every source of each listed
# target depend on STAMP. A build tool decides from modification times, and a source copied
# back with its old time (`cp -p`) is older than its object, so without this an edit undone
# that way left the edited code in the binary while gt6.image named the undone tree
# (batch 11, run 20261029-001329). With it, any change of the tree hash recompiles every
# object that reads the submodule, and gt6.image (write_image.cmake) records the stamp.
function(gt6_tree_stamp name)
    cmake_parse_arguments(PARSE_ARGV 1 TS "" "SUB;STAMP" "TARGETS")
    add_custom_target(${name}
        BYPRODUCTS "${TS_STAMP}"
        COMMAND ${CMAKE_COMMAND} -DSUB=${TS_SUB} -DSTAMP=${TS_STAMP}
                -P "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/write_tree_stamp.cmake"
        COMMENT "ps3recomp tree stamp (D72)"
        VERBATIM)
    foreach(t IN LISTS TS_TARGETS)
        add_dependencies(${t} ${name})
        get_target_property(dir ${t} SOURCE_DIR)
        get_target_property(srcs ${t} SOURCES)
        foreach(s IN LISTS srcs)
            if(s MATCHES "\\$<")
                continue()
            endif()
            cmake_path(ABSOLUTE_PATH s BASE_DIRECTORY "${dir}" OUTPUT_VARIABLE abs)
            set_property(SOURCE "${abs}" TARGET_DIRECTORY ${t}
                         APPEND PROPERTY OBJECT_DEPENDS "${TS_STAMP}")
        endforeach()
    endforeach()
endfunction()
