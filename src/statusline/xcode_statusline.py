#!/usr/bin/env python3
"""
Xcode Status Line for Claude Code
Displays real-time Xcode status in the terminal
"""

import time
import sys
import subprocess
import requests

SERVER_URL = "http://localhost:8765"

def get_status_from_server():
    """Get status from monitor server"""
    try:
        response = requests.get(f"{SERVER_URL}/status", timeout=0.5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def get_fallback_status():
    """Fallback to direct detection if server is not available"""
    try:
        # Check if Xcode is running
        result = subprocess.run(['pgrep', '-x', 'Xcode'], 
                              capture_output=True, text=True)
        xcode_running = result.returncode == 0
        
        if not xcode_running:
            return {"xcode_running": False}
        
        # Try to get window title
        applescript = '''
        tell application "System Events"
            if exists (process "Xcode") then
                tell process "Xcode"
                    try
                        return value of attribute "AXTitle" of window 1
                    on error
                        return ""
                    end try
                end tell
            end if
        end tell
        return ""
        '''
        
        result = subprocess.run(['osascript', '-e', applescript], 
                              capture_output=True, text=True, timeout=2)
        window_title = result.stdout.strip()
        
        current_file = ""
        project_name = ""
        
        if " — " in window_title:
            parts = window_title.split(" — ")
            project_name = parts[0]
            current_file = parts[-1]
        
        return {
            "xcode_running": True,
            "current_file": current_file,
            "project_name": project_name,
            "build_status": "unknown",
            "build_errors": 0
        }
    except:
        return {"xcode_running": False}

def format_status_line(status):
    """Format status into a colored status line"""
    if not status.get("xcode_running", False):
        return "[red] xcode"
    
    parts = ["[green] xcode"]
    
    # Add current file if available
    if status.get("current_file"):
        parts.append(f" {status['current_file']}")
    
    # Add build status
    build_status = status.get("build_status", "idle")
    if build_status == "building":
        parts.append(" 🔨 building...")
    elif build_status == "failed":
        errors = status.get("build_errors", 0)
        parts.append(f" ❌ build failed ({errors} errors)")
    elif build_status == "succeeded":
        parts.append(" ✅ build succeeded")
    elif build_status == "warning":
        parts.append(" ⚠️ build with warnings")
    
    return "".join(parts)

def update_status_line(status_text):
    """Update the status line output"""
    print(status_text, flush=True)

def watch_and_update():
    """Main loop to watch and update status"""
    last_status = None
    server_available = False
    last_server_check = 0
    
    print("Xcode Status Line starting...", file=sys.stderr)
    
    while True:
        try:
            current_time = time.time()
            
            # Check server availability every 5 seconds
            if current_time - last_server_check > 5:
                status = get_status_from_server()
                if status:
                    if not server_available:
                        print("Connected to monitor server", file=sys.stderr)
                    server_available = True
                else:
                    if server_available:
                        print("Server disconnected, using fallback", file=sys.stderr)
                    server_available = False
                last_server_check = current_time
            elif server_available:
                status = get_status_from_server()
            else:
                status = None
            
            # Use fallback if server not available
            if not status:
                status = get_fallback_status()
            
            # Format and update if changed
            current_status = format_status_line(status)
            if current_status != last_status:
                update_status_line(current_status)
                last_status = current_status
                
                # Debug output
                if sys.stderr.isatty():
                    debug_info = {
                        "xcode": "running" if status.get("xcode_running") else "closed",
                        "file": status.get("current_file", "none"),
                        "build": status.get("build_status", "unknown"),
                        "server": "connected" if server_available else "disconnected"
                    }
                    print(f"DEBUG: {debug_info}", file=sys.stderr)
            
            time.sleep(0.5)  # Update twice per second
            
        except KeyboardInterrupt:
            print("\nShutting down...", file=sys.stderr)
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Single status check
        status = get_status_from_server() or get_fallback_status()
        print(format_status_line(status))
    else:
        # Continuous monitoring
        watch_and_update()