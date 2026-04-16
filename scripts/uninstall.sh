#!/bin/bash
# Cortex Uninstall — removes schedules, optionally archives data.
set -e

LEARNING_DIR="$HOME/.claude/learning"
OS="$(uname -s)"

echo "Uninstalling Cortex..."
echo ""

# --- Remove scheduled jobs ---

if [ "$OS" = "Darwin" ]; then
    echo "Removing launchd jobs..."
    COMPILE_PLIST="$HOME/Library/LaunchAgents/com.claude.cortex-compile.plist"
    PROMOTE_PLIST="$HOME/Library/LaunchAgents/com.claude.cortex-promote.plist"
    launchctl unload "$COMPILE_PLIST" 2>/dev/null && rm -f "$COMPILE_PLIST" && echo "  Removed compile schedule" || echo "  No compile schedule found"
    launchctl unload "$PROMOTE_PLIST" 2>/dev/null && rm -f "$PROMOTE_PLIST" && echo "  Removed promote schedule" || echo "  No promote schedule found"
else
    echo "Removing cron jobs..."
    (crontab -l 2>/dev/null | grep -v "cortex" || true) | crontab -
    echo "  Removed cron entries"
fi

# --- Remove runner script ---

rm -f "$LEARNING_DIR/cortex-runner.sh" 2>/dev/null

echo ""

# --- Remove Learned Rules from CLAUDE.md ---

CLAUDE_MD="$HOME/.claude/CLAUDE.md"
if [ -f "$CLAUDE_MD" ] && grep -q "## Learned Rules" "$CLAUDE_MD"; then
    echo "Removing Learned Rules section from CLAUDE.md..."
    # Remove everything between ## Learned Rules and <!-- END Learned Rules -->
    python3 -c "
import re
from pathlib import Path
p = Path('$CLAUDE_MD')
content = p.read_text()
content = re.sub(r'\n*## Learned Rules.*?<!-- END Learned Rules -->\n*', '\n', content, flags=re.DOTALL)
p.write_text(content)
print('  Learned Rules section removed')
"
fi

echo ""

# --- Archive or delete data ---

if [ -d "$LEARNING_DIR" ]; then
    echo "Your learning data is at: $LEARNING_DIR/"
    echo ""
    echo "Options:"
    echo "  1) Archive to $LEARNING_DIR.bak-$(date +%Y%m%d) (keeps data, stops learning)"
    echo "  2) Delete everything (irreversible)"
    echo "  3) Keep as-is (data stays, no active learning)"
    echo ""
    read -p "Choose [1/2/3, default 3]: " choice
    case "$choice" in
        1)
            mv "$LEARNING_DIR" "$LEARNING_DIR.bak-$(date +%Y%m%d)"
            echo "  Archived to $LEARNING_DIR.bak-$(date +%Y%m%d)"
            ;;
        2)
            rm -rf "$LEARNING_DIR"
            echo "  Deleted $LEARNING_DIR/"
            ;;
        *)
            echo "  Data kept at $LEARNING_DIR/"
            ;;
    esac
fi

echo ""
echo "Cortex uninstalled. Plugin hooks will no-op since the data directory is gone."
echo "To fully remove the plugin: claude plugin uninstall claude-cortex@claude-cortex"
