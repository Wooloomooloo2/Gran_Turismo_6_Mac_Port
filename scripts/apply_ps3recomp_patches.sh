#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Apply patches/ps3recomp/*.patch, in filename order, to the ps3recomp submodule (D28).
#
#   scripts/apply_ps3recomp_patches.sh           apply what is not applied yet
#   scripts/apply_ps3recomp_patches.sh --check   change nothing; exit 1 if a patch neither
#                                                applies nor is already applied
#   scripts/apply_ps3recomp_patches.sh --verify  change nothing; exit 1 unless every patch
#                                                is already applied
#
# Safe to run any number of times: a patch whose reverse applies cleanly is already in and is
# skipped. The submodule's commit is never changed, only its working tree, so the
# superproject's pointer stays at the pin. scripts/translate_game.py runs it (then --verify)
# before it lifts, and the port's configure step runs it too. Undo, including the files the
# patches add (a plain checkout leaves them, and a later apply then fails):
#   git -C third_party/ps3recomp checkout . && git -C third_party/ps3recomp clean -fd
#
# GT6_PS3RECOMP_PATCHES and GT6_PS3RECOMP_DIR override the two folders (used by the tests).
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
patches="${GT6_PS3RECOMP_PATCHES:-$repo/patches/ps3recomp}"
sub="${GT6_PS3RECOMP_DIR:-$repo/third_party/ps3recomp}"

check=0
verify=0
case "${1:-}" in
  "") ;;
  --check) check=1 ;;
  --verify) verify=1 ;;
  *) echo "usage: $0 [--check | --verify]" >&2; exit 2 ;;
esac

if [ ! -e "$sub/.git" ]; then
  echo "error: no ps3recomp checkout at $sub (git submodule update --init third_party/ps3recomp)" >&2
  exit 1
fi

shopt -s nullglob
failed=0
for p in "$patches"/*.patch; do
  name="$(basename "$p")"
  if git -C "$sub" apply --reverse --check "$p" 2>/dev/null; then
    echo "already applied: $name"
  elif [ "$verify" = 1 ]; then
    echo "error: $name is not applied to $sub" >&2
    failed=1
  elif git -C "$sub" apply --check "$p" 2>/dev/null; then
    if [ "$check" = 1 ]; then
      echo "applies: $name"
    else
      git -C "$sub" apply --whitespace=nowarn "$p"
      echo "applied: $name"
    fi
  else
    echo "error: $name neither applies to $sub nor is already applied" >&2
    failed=1
  fi
done
exit "$failed"
