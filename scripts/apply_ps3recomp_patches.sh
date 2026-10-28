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
# Safe to run any number of times: the patches already in (found by walking the series
# backwards on a scratch copy, so a patch may rewrite an earlier one's lines) are skipped. The submodule's commit is never changed, only its working tree, so the
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
all=("$patches"/*.patch)
n=${#all[@]}

# Which patches are in? Later patches may rewrite lines an earlier one added, so a patch
# is not checked on its own against the final tree. The files the series touches are copied
# to a scratch folder and the series is walked backwards there: a patch whose reverse applies
# (after every later applied patch was reversed) is in. The applied ones must be a prefix
# 0001..k of the series; the rest are applied in order.
scratch="$(mktemp -d "${TMPDIR:-/tmp}/ps3recomp-patches-XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
# Copy the files the series touches (from its ---/+++ headers) from the submodule to $1.
copy_touched() {
  mkdir -p "$1"
  for p in "${all[@]}"; do
    sed -n -e 's|^--- a/\([^[:space:]]*\).*$|\1|p' -e 's|^+++ b/\([^[:space:]]*\).*$|\1|p' "$p"
  done | sort -u | while IFS= read -r f; do
    if [ -e "$sub/$f" ]; then
      mkdir -p "$1/$(dirname "$f")"
      cp -p "$sub/$f" "$1/$f"
    fi
  done
}
copy_touched "$scratch/tree"
applied=()
for ((i = n - 1; i >= 0; i--)); do
  if (cd "$scratch/tree" && git apply --reverse --check "${all[$i]}" 2>/dev/null); then
    (cd "$scratch/tree" && git apply --reverse --whitespace=nowarn "${all[$i]}")
    applied[$i]=1
  else
    applied[$i]=0
  fi
done
k=0
while [ "$k" -lt "$n" ] && [ "${applied[$k]}" = 1 ]; do k=$((k + 1)); done
failed=0
for ((i = k; i < n; i++)); do
  if [ "${applied[$i]}" = 1 ]; then
    echo "error: $(basename "${all[$i]}") is applied but an earlier patch is not" >&2
    failed=1
  fi
done
[ "$failed" = 0 ] || exit 1

for ((i = 0; i < k; i++)); do echo "already applied: $(basename "${all[$i]}")"; done
# The not-applied rest, in order, on a copy of the tree as it is now (--check, --verify) or
# on the tree itself.
if [ "$check" = 1 ] || [ "$verify" = 1 ]; then
  rm -rf "$scratch/tree"
  copy_touched "$scratch/tree"
fi
for ((i = k; i < n; i++)); do
  p="${all[$i]}"
  name="$(basename "$p")"
  if [ "$verify" = 1 ]; then
    echo "error: $name is not applied to $sub" >&2
    failed=1
  elif [ "$check" = 1 ]; then
    if (cd "$scratch/tree" && git apply --check "$p" 2>/dev/null) &&
       (cd "$scratch/tree" && git apply --whitespace=nowarn "$p"); then
      echo "applies: $name"
    else
      echo "error: $name neither applies to $sub nor is already applied" >&2
      failed=1
    fi
  elif git -C "$sub" apply --check "$p" 2>/dev/null; then
    git -C "$sub" apply --whitespace=nowarn "$p"
    echo "applied: $name"
  else
    echo "error: $name neither applies to $sub nor is already applied" >&2
    failed=1
  fi
done
exit "$failed"
