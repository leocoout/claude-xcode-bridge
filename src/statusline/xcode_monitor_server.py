#!/usr/bin/env python3
"""
Xcode Monitor Server
Provides a local HTTP server for real-time Xcode status monitoring
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import subprocess
import os

class XcodeStatus:
    """Singleton to hold current Xcode status"""
    def __init__(self):
        self.data = {
            "xcode_running": False,
            "current_file": "",
            "build_status": "idle",
            "build_errors": 0,
            "last_update": time.time(),
            "project_name": "",
            "derived_data_path": ""
        }
        self.lock = threading.Lock()
    
    def update(self, **kwargs):
        with self.lock:
            self.data.update(kwargs)
            self.data["last_update"] = time.time()
    
    def get(self):
        with self.lock:
            return self.data.copy()

# Global status instance
status = XcodeStatus()

class StatusHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging
        pass
    
    def do_GET(self):
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status.get()).encode())
        
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == "/update":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode())
                status.update(**data)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

def poll_xcode_status():
    """Background thread to poll basic Xcode status"""
    while True:
        try:
            # Check if Xcode is running
            result = subprocess.run(['pgrep', '-x', 'Xcode'], 
                                  capture_output=True, text=True)
            xcode_running = result.returncode == 0
            
            current_file = ""
            project_name = ""
            
            if xcode_running:
                # Get current file from window title
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
                
                # Parse window title (format: "ProjectName — FileName.ext")
                if " — " in window_title:
                    parts = window_title.split(" — ")
                    project_name = parts[0]
                    current_file = parts[-1]
            
            status.update(
                xcode_running=xcode_running,
                current_file=current_file,
                project_name=project_name
            )
            
        except Exception as e:
            print(f"Error polling Xcode status: {e}")
        
        time.sleep(1)  # Poll every second

def run_server(port=8765):
    """Start the HTTP server"""
    # Start background polling thread
    poll_thread = threading.Thread(target=poll_xcode_status, daemon=True)
    poll_thread.start()
    
    # Start HTTP server
    server = HTTPServer(('localhost', port), StatusHandler)
    print(f"Xcode Monitor Server running on http://localhost:{port}")
    print(f"Endpoints:")
    print(f"  GET  /status - Get current status")
    print(f"  GET  /health - Health check")
    print(f"  POST /update - Update status")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()

if __name__ == "__main__":
    run_server()