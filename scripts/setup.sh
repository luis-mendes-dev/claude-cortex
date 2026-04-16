#!/bin/bash
# Cortex Setup — creates directories, copies config, schedules background jobs.
set -e

LEARNING_DIR="$HOME/.claude/learning"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Setting up Cortex..."
echo ""

# --- Prerequisites ---

echo "Checking prerequisites..."

# Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+ first."
    exit 1
fi
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo "ERROR: Python 3.10+ required, found $PY_VERSION"
    exit 1
fi
echo "  Python $PY_VERSION OK"

# PyYAML
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "  PyYAML not found. Installing..."
    pip3 install pyyaml --quiet
    echo "  PyYAML installed"
else
    echo "  PyYAML OK"
fi

# Claude CLI
CLAUDE_CLI=""
for candidate in claude "$HOME/.local/bin/claude" /usr/local/bin/claude; do
    if command -v "$candidate" &>/dev/null; then
        CLAUDE_CLI="$candidate"
        break
    fi
done
if [ -z "$CLAUDE_CLI" ]; then
    echo "WARNING: claude CLI not found. Capture will fall back to regex extraction."
    echo "         Install Claude Code for full LLM-powered extraction."
else
    echo "  Claude CLI OK ($CLAUDE_CLI)"
fi

echo ""

# --- Create directories ---

echo "Creating directories..."
mkdir -p "$LEARNING_DIR"/{daily,knowledge,rules/active,rules/retired,logs}
mkdir -p "$HOME/.claude/rules"
echo "  $LEARNING_DIR/ created"

# --- Copy config ---

if [ ! -f "$LEARNING_DIR/config.yaml" ]; then
    cp "$PLUGIN_ROOT/config/config.default.yaml" "$LEARNING_DIR/config.yaml"
    echo "  Config copied to $LEARNING_DIR/config.yaml"
else
    echo "  Config already exists, skipping"
fi

echo ""

# --- Schedule background jobs ---

PYTHON3_PATH=$(which python3)
CORTEX_PY="$LEARNING_DIR/cortex-runner.sh"

# Create a runner script that handles PATH
cat > "$CORTEX_PY" << RUNNER
#!/bin/bash
export PATH="/usr/local/bin:/usr/bin:/bin:\$HOME/.local/bin:\$PATH"
export HOME="$HOME"
$PYTHON3_PATH "$PLUGIN_ROOT/scripts/cortex.py" "\$@"
RUNNER
chmod +x "$CORTEX_PY"

OS="$(uname -s)"

if [ "$OS" = "Darwin" ]; then
    echo "Scheduling background jobs (macOS launchd)..."

    # Compile — daily at 2am
    COMPILE_PLIST="$HOME/Library/LaunchAgents/com.claude.cortex-compile.plist"
    cat > "$COMPILE_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.cortex-compile</string>
    <key>ProgramArguments</key>
    <array>
        <string>$CORTEX_PY</string>
        <string>compile</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LEARNING_DIR/logs/compile-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LEARNING_DIR/logs/compile-stderr.log</string>
</dict>
</plist>
PLIST

    # Promote + decay — weekly Sunday 3am
    PROMOTE_PLIST="$HOME/Library/LaunchAgents/com.claude.cortex-promote.plist"
    cat > "$PROMOTE_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.cortex-promote</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>$CORTEX_PY promote &amp;&amp; $CORTEX_PY decay</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LEARNING_DIR/logs/promote-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LEARNING_DIR/logs/promote-stderr.log</string>
</dict>
</plist>
PLIST

    # Load plists (unload first if they exist)
    launchctl unload "$COMPILE_PLIST" 2>/dev/null || true
    launchctl unload "$PROMOTE_PLIST" 2>/dev/null || true
    launchctl load "$COMPILE_PLIST"
    launchctl load "$PROMOTE_PLIST"
    echo "  Compile: daily at 2:00am"
    echo "  Promote + decay: Sunday at 3:00am"

else
    echo "Scheduling background jobs (cron)..."

    # Remove any existing cortex cron entries
    (crontab -l 2>/dev/null | grep -v "cortex.py" || true) | crontab -

    # Add new entries
    (crontab -l 2>/dev/null || true; echo "0 2 * * * $CORTEX_PY compile >> $LEARNING_DIR/logs/compile-cron.log 2>&1") | crontab -
    (crontab -l 2>/dev/null || true; echo "0 3 * * 0 $CORTEX_PY promote && $CORTEX_PY decay >> $LEARNING_DIR/logs/promote-cron.log 2>&1") | crontab -
    echo "  Compile: daily at 2:00am (cron)"
    echo "  Promote + decay: Sunday at 3:00am (cron)"
fi

echo ""

# --- Verify ---

echo "Verifying..."
python3 "$PLUGIN_ROOT/scripts/cortex.py" status

echo ""
echo "Cortex is live. Learnings will be captured from every session automatically."
echo ""
echo "  Hooks:    SessionEnd (capture) + SessionStart (inject)"
echo "  Schedule: compile daily 2am, promote+decay weekly Sunday 3am"
echo "  Data:     $LEARNING_DIR/"
echo "  Logs:     $LEARNING_DIR/logs/cortex.log"
echo "  Status:   /cortex"
