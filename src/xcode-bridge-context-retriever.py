#!/usr/bin/env python3

import json
import os
from datetime import datetime

def read_xcode_context():
    logs_path = os.environ.get('XCODE_LOGS_PATH', '')
    if not logs_path:
        return "No XCODE_LOGS_PATH configured"

    log_dir = os.path.expanduser(f"~/{logs_path}")
    log_file = os.path.join(log_dir, "xcode_statusline_logs.json")

    if not os.path.exists(log_file):
        return "No Xcode context available (logs not found)"

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        context_parts = []

        if not data.get("xcode_running", False):
            return "Xcode is currently closed"

        context_parts.append("Xcode is running")
        project_name = data.get("project_name")
        if project_name:
            context_parts.append(f"Current project: {project_name}")
        current_file = data.get("current_file")
        current_file_path = data.get("current_file_path")

        if current_file:
            context_parts.append(f"Current file: {current_file}")
            if current_file_path:
                context_parts.append(f"File path: {current_file_path}")
        build_errors = data.get("build_errors", 0)
        detailed_errors = data.get("detailed_errors", [])

        if build_errors > 0:
            error_word = "error" if build_errors == 1 else "errors"
            context_parts.append(f"Build status: {build_errors} {error_word}")

            if detailed_errors:
                context_parts.append("Recent build errors:")
                for i, error in enumerate(detailed_errors[:3]):
                    context_parts.append(f"   {i+1}. {error}")

                if len(detailed_errors) > 3:
                    context_parts.append(f"   ... and {len(detailed_errors) - 3} more errors")
        else:
            context_parts.append("Build status: No errors")
        timestamp = data.get("timestamp")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime("%H:%M:%S")
                context_parts.append(f"Last updated: {time_str}")
            except ValueError:
                pass

        return "\n".join(context_parts)

    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        return f"Error reading Xcode context: {e}"

def main():
    """Output Xcode context for hooks"""
    context = read_xcode_context()
    print(f"<xcode-context>\n{context}\n</xcode-context>")

if __name__ == "__main__":
    main()