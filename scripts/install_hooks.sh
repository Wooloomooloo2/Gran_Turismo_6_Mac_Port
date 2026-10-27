#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Installs a pre-commit hook that blocks PS3 game files from being committed.
set -e
root=$(git rev-parse --show-toplevel)
cat > "$root/.git/hooks/pre-commit" <<'H'
#!/bin/sh
exec python3 "$(git rev-parse --show-toplevel)/scripts/check_no_game_files.py"
H
chmod +x "$root/.git/hooks/pre-commit"
echo "pre-commit guard installed"
