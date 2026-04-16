#!/bin/bash
# Interactive compile wrapper — shows progress to stdout
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Compiling learnings..."
python3 "$SCRIPT_DIR/cortex.py" compile 2>&1
echo ""
echo "Done. Run /cortex to see updated status."
