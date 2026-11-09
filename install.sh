#!/usr/bin/env bash
# Install KROKO into the default Hermes profile and every named profile.
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
NAME="kroko"

echo "KROKO install from: $SOURCE"
echo

echo "== 1. Gate check: the source must be green before it polices anything =="
python3 "$SOURCE/scripts/kroko_selftest.py"
echo

echo "== 2. Targets =="
TARGETS=("$HERMES_HOME/skills/$NAME")
for profile in "$HERMES_HOME"/profiles/*/; do
  if [ -d "$profile/skills" ]; then
    TARGETS+=("${profile}skills/$NAME")
  fi
done
for target in "${TARGETS[@]}"; do
  echo "   $target"
done
echo

echo "== 3. Install and verify from the installed location =="
for target in "${TARGETS[@]}"; do
  mkdir -p "$target"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
      "$SOURCE/SKILL.md" "$SOURCE/README.md" "$SOURCE/LICENSE" \
      "$SOURCE/install-hook.sh" "$SOURCE/assets" "$SOURCE/references" \
      "$SOURCE/scripts" "$SOURCE/templates" "$SOURCE/tests" "$SOURCE/tools" "$target/"
  else
    rm -rf "$target"
    mkdir -p "$target"
    cp -R "$SOURCE/SKILL.md" "$SOURCE/README.md" "$SOURCE/LICENSE" \
      "$SOURCE/install-hook.sh" "$SOURCE/assets" "$SOURCE/references" \
      "$SOURCE/scripts" "$SOURCE/templates" "$SOURCE/tests" "$SOURCE/tools" "$target/"
  fi
  python3 "$target/scripts/kroko_selftest.py" > /dev/null
  echo "   ok, verified in place: $target"
done

echo
echo "KROKO installed and verified in ${#TARGETS[@]} location(s)."
