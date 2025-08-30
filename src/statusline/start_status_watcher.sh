#!/bin/bash

# Start the Xcode status line watcher daemon
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/xcode_statusline.py"

# Kill any existing watcher
pkill -f "xcode_statusline.py --watch"

# Start new watcher in background
nohup python3 "$PYTHON_SCRIPT" --watch > /dev/null 2>&1 &
echo "Xcode status line watcher started (PID: $!)"

# Wait a moment for it to initialize
sleep 1