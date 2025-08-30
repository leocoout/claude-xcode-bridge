#!/usr/bin/env python3
"""
Xcode Build Watcher
Monitors DerivedData for build status changes and reports to the monitor server
"""

import os
import json
import time
import plistlib
import requests
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import hashlib

SERVER_URL = "http://localhost:8765"

class BuildWatcher(FileSystemEventHandler):
    def __init__(self):
        self.derived_data_path = None
        self.last_build_state = {"status": "idle", "errors": 0}
        self.project_path = None
        
    def find_active_derived_data(self):
        """Find the DerivedData path for the active Xcode project"""
        try:
            # Get active project from Xcode
            applescript = '''
            tell application "System Events"
                if exists (process "Xcode") then
                    tell application "Xcode"
                        try
                            if exists active workspace document then
                                return path of active workspace document
                            end if
                        end try
                    end tell
                end if
            end tell
            return ""
            '''
            
            result = subprocess.run(['osascript', '-e', applescript], 
                                  capture_output=True, text=True, timeout=5)
            project_path = result.stdout.strip()
            
            if not project_path:
                return None
            
            # If project hasn't changed, return cached path
            if project_path == self.project_path and self.derived_data_path:
                if os.path.exists(self.derived_data_path):
                    return self.derived_data_path
            
            self.project_path = project_path
            
            # Find corresponding DerivedData directory
            derived_data_dir = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
            project_name = os.path.basename(project_path).replace('.xcworkspace', '').replace('.xcodeproj', '')
            
            # Look for matching directory
            for item in os.listdir(derived_data_dir):
                if not item.startswith(project_name):
                    continue
                    
                derived_path = os.path.join(derived_data_dir, item)
                info_plist = os.path.join(derived_path, "Info.plist")
                
                if os.path.exists(info_plist):
                    try:
                        with open(info_plist, 'rb') as f:
                            info = plistlib.load(f)
                            workspace_path = info.get('WorkspacePath', '')
                            if workspace_path and os.path.samefile(workspace_path, project_path):
                                self.derived_data_path = derived_path
                                return derived_path
                    except:
                        continue
            
            return None
        except Exception as e:
            print(f"Error finding DerivedData: {e}")
            return None
    
    def parse_build_status(self, manifest_path):
        """Parse build status from LogStoreManifest.plist"""
        try:
            with open(manifest_path, 'rb') as f:
                manifest = plistlib.load(f)
            
            current_time = time.time()
            
            # Check for active builds
            for build_id, build_info in manifest.get('logs', {}).items():
                start_time = build_info.get('timeStartedRecording', 0)
                if 'timeStoppedRecording' not in build_info and start_time > current_time - 300:
                    return "building", 0
            
            # Find latest completed build
            latest_build = None
            latest_time = 0
            
            for build_id, build_info in manifest.get('logs', {}).items():
                stop_time = build_info.get('timeStoppedRecording', 0)
                if stop_time > latest_time:
                    latest_time = stop_time
                    latest_build = build_info
            
            if not latest_build:
                return "idle", 0
            
            # Parse build result
            status = latest_build.get('primaryObservable', {})
            high_level_status = status.get('highLevelStatus', 'S')
            error_count = status.get('totalNumberOfErrors', 0)
            
            status_map = {'S': 'succeeded', 'E': 'failed', 'W': 'warning'}
            build_status = status_map.get(high_level_status, 'unknown')
            
            return build_status, error_count
            
        except Exception as e:
            print(f"Error parsing build status: {e}")
            return self.last_build_state["status"], self.last_build_state["errors"]
    
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
            
        # Check if it's a build log file
        if "LogStoreManifest.plist" in event.src_path or ".xcactivitylog" in event.src_path:
            self.check_build_status()
    
    def on_created(self, event):
        """Handle file creation events"""
        if event.is_directory:
            return
            
        # New build log created
        if ".xcactivitylog" in event.src_path:
            # Build started
            self.update_server(build_status="building", build_errors=0)
        elif "LogStoreManifest.plist" in event.src_path:
            self.check_build_status()
    
    def check_build_status(self):
        """Check and update build status"""
        if not self.derived_data_path:
            return
            
        manifest_path = os.path.join(self.derived_data_path, "Logs", "Build", "LogStoreManifest.plist")
        if os.path.exists(manifest_path):
            status, errors = self.parse_build_status(manifest_path)
            
            # Only update if status changed
            if status != self.last_build_state["status"] or errors != self.last_build_state["errors"]:
                self.last_build_state = {"status": status, "errors": errors}
                self.update_server(build_status=status, build_errors=errors)
    
    def update_server(self, **data):
        """Send update to monitor server"""
        try:
            # Add derived data path if available
            if self.derived_data_path:
                data["derived_data_path"] = self.derived_data_path
            
            response = requests.post(f"{SERVER_URL}/update", json=data, timeout=1)
            if response.status_code == 200:
                print(f"Updated server: {data}")
            else:
                print(f"Failed to update server: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Could not connect to server: {e}")
        except Exception as e:
            print(f"Error updating server: {e}")

def watch_builds():
    """Main function to watch for build changes"""
    watcher = BuildWatcher()
    observer = Observer()
    
    print("Xcode Build Watcher starting...")
    print(f"Connecting to server at {SERVER_URL}")
    
    # Test server connection
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=1)
        if response.status_code != 200:
            print("Warning: Server not responding")
    except:
        print("Warning: Could not connect to server. Make sure xcode_monitor_server.py is running.")
    
    while True:
        try:
            # Find active DerivedData path
            derived_data = watcher.find_active_derived_data()
            
            if derived_data:
                build_logs_path = os.path.join(derived_data, "Logs", "Build")
                
                if os.path.exists(build_logs_path):
                    print(f"Watching: {build_logs_path}")
                    
                    # Stop previous observer if running
                    if observer.is_alive():
                        observer.stop()
                        observer.join()
                    
                    # Start watching
                    observer = Observer()
                    observer.schedule(watcher, build_logs_path, recursive=False)
                    observer.start()
                    
                    # Initial status check
                    watcher.check_build_status()
                    
                    # Wait for changes or project switch
                    for _ in range(10):  # Check every 10 seconds for project changes
                        time.sleep(1)
                        if not observer.is_alive():
                            break
                else:
                    print(f"Build logs not found at: {build_logs_path}")
                    time.sleep(5)
            else:
                print("No active Xcode project found")
                time.sleep(5)
                
        except KeyboardInterrupt:
            print("\nStopping watcher...")
            if observer.is_alive():
                observer.stop()
                observer.join()
            break
        except Exception as e:
            print(f"Error in watch loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    watch_builds()