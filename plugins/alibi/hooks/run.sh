#!/usr/bin/env bash
# Alibi hook entrypoint. Fails open: if anything is missing, exit 0 silently
# so a half-installed plugin never disrupts a session.
#
# Deliberately no `set -e` -- a non-zero exit from the script below would be
# reported by Claude Code as a hook error on every single turn.

# Resolve the plugin root from $0 rather than trusting $CLAUDE_PLUGIN_ROOT,
# which is not set when the script is run by hand or from a test.
HOOK_DIR=$(cd "$(dirname "$0" 2>/dev/null)" 2>/dev/null && pwd 2>/dev/null) || exit 0
SCRIPT="$HOOK_DIR/../scripts/alibi.py"

[ -f "$SCRIPT" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

exec python3 "$SCRIPT" "$@"
