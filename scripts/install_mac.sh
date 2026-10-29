#!/bin/bash
# Installs the fetcher as a background job for the current macOS user. Safe to run again after editing config.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL=in.tricity.fetcher
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ "$(uname)" = "Darwin" ] || { echo "This installer is for macOS."; exit 1; }
case "$DIR" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Downloads"*|*"/Library/Mobile Documents"*)
    echo "Move this folder out of Documents, Desktop, Downloads or iCloud Drive first (for example to ~/tricity-fetcher)."
    echo "macOS privacy rules stop background jobs from reading those folders."
    exit 1;;
esac

PY="$(command -v python3 || true)"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  echo "Python 3.9 or newer is needed. Run: xcode-select --install   (or install from python.org), then run this again."
  exit 1
fi
echo "Using $PY ($("$PY" --version))"

if [ ! -f "$DIR/config.local.json" ]; then
  read -r -p "Contact email to put in the crawler's User-Agent (site operators use it to reach you): " EMAIL
  [[ "$EMAIL" == *@*.* ]] || { echo "That doesn't look like an email address."; exit 1; }
  printf '{\n  "contact_email": "%s"\n}\n' "$EMAIL" > "$DIR/config.local.json"
  echo "Wrote config.local.json. Per-source overrides (enabled, publish, pages) can go in the same file."
fi

echo "Running tests..."
(cd "$DIR" && "$PY" -W ignore -m unittest discover -s tests) || { echo "Tests failed; not installing."; exit 1; }

mkdir -p "$DIR/data/logs" "$HOME/Library/LaunchAgents"
sed -e "s|__PYTHON__|$PY|g" -e "s|__DIR__|$DIR|g" "$DIR/launchd/$LABEL.plist" > "$PLIST"
plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo
echo "Installed. First run started in the background."
echo "  Status:   $PY \"$DIR/fetcher.py\" status"
echo "  Log:      tail -f \"$DIR/data/logs/fetcher.log\""
echo "  Changes:  open \"$DIR/data/latest_changes.md\""
echo "  Remove:   \"$DIR/scripts/uninstall_mac.sh\""
