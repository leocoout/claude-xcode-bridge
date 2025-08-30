#!/bin/bash
# Start the Xcode monitoring system

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting Xcode Monitoring System..."

# Kill any existing processes
echo "Stopping any existing monitors..."
pkill -f "xcode_monitor_server.py"
pkill -f "xcode_build_watcher.py"
pkill -f "xcode_statusline.py"

sleep 1

# Start the monitor server
echo "Starting monitor server on localhost:8765..."
python3 "$SCRIPT_DIR/xcode_monitor_server.py" &
SERVER_PID=$!
echo "  Server PID: $SERVER_PID"

# Wait for server to start
sleep 2

# Start the build watcher
echo "Starting build watcher..."
python3 "$SCRIPT_DIR/xcode_build_watcher.py" &
WATCHER_PID=$!
echo "  Watcher PID: $WATCHER_PID"

# Start the statusline (this will run in foreground)
echo "Starting statusline display..."
echo "---"
python3 "$SCRIPT_DIR/xcode_statusline.py"

# Cleanup on exit
echo "Cleaning up..."
kill $SERVER_PID 2>/dev/null
kill $WATCHER_PID 2>/dev/null