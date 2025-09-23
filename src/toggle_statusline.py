#!/usr/bin/env python3

import json
import os
import sys

LOG_FILENAME = "statusline_context.json"
XCODE_LOGS_PATH = ".claude-xcode-build-infra"

def set_statusline_enabled(enabled):
    logs_path = XCODE_LOGS_PATH
    log_dir = os.path.expanduser(f"~/{logs_path}")
    log_file = os.path.join(log_dir, LOG_FILENAME)

    os.makedirs(log_dir, exist_ok=True)

    log_data = {}
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                log_data = json.load(f)
        except:
            pass

    log_data["enabled"] = enabled

    try:
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)

        status = "enabled" if enabled else "disabled"
        print(f"Statusline {status}")
    except Exception as e:
        print(f"Error updating statusline: {e}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 toggle_statusline.py <ENABLED>")
        print("  ENABLED: true or false")
        sys.exit(1)

    enabled_str = sys.argv[1].lower()
    if enabled_str == 'true':
        set_statusline_enabled(True)
    elif enabled_str == 'false':
        set_statusline_enabled(False)
    else:
        print("Error: ENABLED must be 'true' or 'false'")
        sys.exit(1)

if __name__ == "__main__":
    main()