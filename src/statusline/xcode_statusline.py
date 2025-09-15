#!/usr/bin/env python3

import time
import sys
import subprocess
import os
import plistlib
import json
import gzip
import re
from datetime import datetime

APPLESCRIPT_TIMEOUT = 5
APPLESCRIPT_SHORT_TIMEOUT = 2
BUILD_ACTIVE_THRESHOLD = 300
MAX_ERROR_LENGTH = 500
DERIVED_DATA_PATH = "~/Library/Developer/Xcode/DerivedData"
BUILD_LOGS_SUBPATH = "Logs/Build"
MANIFEST_FILENAME = "LogStoreManifest.plist"
INFO_PLIST_FILENAME = "Info.plist"
LOG_FILENAME = "xcode_statusline_logs.json"

XCODE_PROCESS_NAME = "Xcode"
PROJECT_EXTENSIONS = ['.xcworkspace', '.xcodeproj']
SOURCE_DIRECTORIES = ["Sources", "src"]

COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_BLUE = "\033[34m"
COLOR_RESET = "\033[0m"

APPLESCRIPT_GET_PROJECT = '''
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

APPLESCRIPT_GET_WINDOW_TITLE = '''
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
'''

APPLESCRIPT_GET_DOCUMENT = '''
tell application "Xcode"
    try
        if exists front document then
            set currentDocument to front document
            if exists (contents of currentDocument) then
                set sourceFile to path of (contents of currentDocument)
                if sourceFile contains ":" then
                    return POSIX path of sourceFile
                else
                    return sourceFile as string
                end if
            end if
        end if
    end try
end tell
return ""
'''

def find_active_derived_data():
    try:
        result = subprocess.run(['osascript', '-e', APPLESCRIPT_GET_PROJECT], 
                              capture_output=True, text=True, timeout=APPLESCRIPT_TIMEOUT)
        project_path = result.stdout.strip()
        
        if not project_path:
            return None
        
        derived_data_dir = os.path.expanduser(DERIVED_DATA_PATH)
        project_name = os.path.basename(project_path)
        for ext in PROJECT_EXTENSIONS:
            project_name = project_name.replace(ext, '')
        
        normalized_project_name = project_name.replace(' ', '_')
        
        for item in os.listdir(derived_data_dir):
            if not (item.startswith(project_name) or item.startswith(normalized_project_name)):
                continue
                
            derived_path = os.path.join(derived_data_dir, item)
            info_plist = os.path.join(derived_path, INFO_PLIST_FILENAME)
            
            if os.path.exists(info_plist):
                try:
                    with open(info_plist, 'rb') as f:
                        info = plistlib.load(f)
                        workspace_path = info.get('WorkspacePath', '')
                        if workspace_path and os.path.samefile(workspace_path, project_path):
                            return derived_path
                except:
                    continue
        
        return None
    except:
        return None

def check_build_failed(manifest_path):
    try:
        with open(manifest_path, 'rb') as f:
            manifest = plistlib.load(f)
        
        latest_build = None
        latest_time = 0
        
        for build_id, build_info in manifest.get('logs', {}).items():
            stop_time = build_info.get('timeStoppedRecording', 0)
            if stop_time > latest_time:
                latest_time = stop_time
                latest_build = build_info
        
        if not latest_build:
            return False, 0
        
        status = latest_build.get('primaryObservable', {})
        high_level_status = status.get('highLevelStatus', 'S')
        error_count = status.get('totalNumberOfErrors', 0)
        
        return high_level_status == 'E', error_count
        
    except:
        return False, 0

def parse_build_errors_detailed(manifest_path):
    try:
        with open(manifest_path, 'rb') as f:
            manifest = plistlib.load(f)
        
        errors = []
        build_logs_dir = os.path.dirname(manifest_path)
        
        latest_build = None
        latest_time = 0
        
        for build_id, build_info in manifest.get('logs', {}).items():
            stop_time = build_info.get('timeStoppedRecording', 0)
            if stop_time > latest_time:
                status = build_info.get('primaryObservable', {})
                high_level_status = status.get('highLevelStatus', 'S')
                if high_level_status == 'E':
                    latest_time = stop_time
                    latest_build = build_info
        
        if latest_build:
            log_file = latest_build.get('fileName', '')
            if log_file:
                log_path = os.path.join(build_logs_dir, log_file)
                if os.path.exists(log_path):
                    errors = extract_errors_from_log(log_path)
        
        return errors
    except Exception as e:
        return []

def extract_errors_from_log(log_path):
    errors = []
    try:
        try:
            with gzip.open(log_path, 'rt', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        
        lines = content.split('\n')
        swift_errors = []
        generic_errors = []
        
        swift_error_patterns = [
            r'(.+\.swift:\d+:\d+):\s+error:\s+(.+)',
            r'(.+\.swift:\d+:\d+):\s+(.+)',
            r'(/[^:]+\.swift:\d+:\d+):\s+error:\s+(.+)',
            r'(/[^:]+\.swift:\d+:\d+):\s+(.+)'
        ]
        
        for line in lines:
            for pattern in swift_error_patterns:
                match = re.search(pattern, line)
                if match:
                    file_location = match.group(1)
                    error_message = match.group(2) if len(match.groups()) >= 2 else ""
                    
                    if "warning:" in error_message.lower():
                        continue
                        
                    if error_message:
                        full_error = f"{file_location}: {error_message}"
                    else:
                        full_error = file_location
                    
                    if (len(full_error) < MAX_ERROR_LENGTH and 
                        not re.search(r'[0-9A-F]{20,}', full_error) and
                        full_error not in swift_errors):
                        swift_errors.append(full_error)
                        break
        
        if not swift_errors:
            error_patterns = [
                r'error:\s+(.+)',
                r'Error:\s+(.+)',
                r'fatal error:\s+(.+)',
                r'compilation failed:\s+(.+)'
            ]
            
            for line in lines:
                for pattern in error_patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        error_message = match.group(1).strip()
                        
                        if (len(error_message) < MAX_ERROR_LENGTH and 
                            not re.search(r'[0-9A-F]{20,}', error_message) and
                            error_message not in generic_errors):
                            generic_errors.append(error_message)
        
        if swift_errors:
            errors = swift_errors
        else:
            errors = generic_errors
            
        if errors and not any(':' in error and '.swift:' in error for error in errors):
            pass
        
    except Exception as e:
        pass
    
    return errors

def get_current_file_path():
    try:
        result = subprocess.run(['osascript', '-e', APPLESCRIPT_GET_DOCUMENT], 
                              capture_output=True, text=True, timeout=APPLESCRIPT_SHORT_TIMEOUT)
        file_path = result.stdout.strip()
        
        current_file = ""
        project_path = ""
        
        result = subprocess.run(['osascript', '-e', APPLESCRIPT_GET_WINDOW_TITLE], 
                              capture_output=True, text=True, timeout=APPLESCRIPT_SHORT_TIMEOUT)
        window_title = result.stdout.strip()
        
        if " — " in window_title:
            parts = window_title.split(" — ")
            current_file = parts[-1]
            
            derived_data_path = find_active_derived_data()
            if derived_data_path:
                try:
                    info_plist = os.path.join(derived_data_path, INFO_PLIST_FILENAME)
                    if os.path.exists(info_plist):
                        with open(info_plist, 'rb') as f:
                            info = plistlib.load(f)
                            project_path = info.get('WorkspacePath', '')
                            
                            if project_path and current_file:
                                project_dir = os.path.dirname(project_path)
                                project_name = os.path.basename(project_path)
                                for ext in PROJECT_EXTENSIONS:
                                    project_name = project_name.replace(ext, '')
                                
                                try:
                                    result = subprocess.run(['find', project_dir, 
                                                          '-path', '*/.build', '-prune', '-o',
                                                          '-path', '*/.git', '-prune', '-o',
                                                          '-path', '*/DerivedData', '-prune', '-o',
                                                          '-name', current_file, '-type', 'f', '-print'], 
                                                          capture_output=True, text=True, timeout=3)
                                    if result.returncode == 0 and result.stdout.strip():
                                        found_paths = [p for p in result.stdout.strip().split('\n') if p]
                                        if found_paths:
                                            return found_paths[0]
                                except:
                                    pass
                                
                                possible_paths = [
                                    os.path.join(project_dir, project_name, current_file),
                                    os.path.join(project_dir, current_file),
                                ]
                                
                                for src_dir in SOURCE_DIRECTORIES:
                                    possible_paths.extend([
                                        os.path.join(project_dir, src_dir, current_file),
                                        os.path.join(project_dir, project_name, src_dir, current_file)
                                    ])
                                
                                for path in possible_paths:
                                    if os.path.exists(path):
                                        return path
                except:
                    pass
        
        if file_path and file_path != "missing value" and not any(ext in file_path for ext in PROJECT_EXTENSIONS):
            return file_path
        return ""
    except:
        return ""

def write_logs(status, project_path="", current_file_path=""):
    logs_path = os.environ.get('XCODE_LOGS_PATH', '')
    if not logs_path:
        return
    
    log_dir = os.path.expanduser(f"~/{logs_path}")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, LOG_FILENAME)
    
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "xcode_running": status.get("xcode_running", False),
        "project_name": status.get("project_name", ""),
        "project_path": project_path,
        "current_file": status.get("current_file", ""),
        "current_file_path": current_file_path,
        "build_errors": status.get("build_errors", 0),
        "detailed_errors": status.get("detailed_errors", [])
    }
    
    try:
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
    except Exception as e:
        pass

def get_xcode_status():
    try:
        result = subprocess.run(['pgrep', '-x', XCODE_PROCESS_NAME], 
                              capture_output=True, text=True)
        xcode_running = result.returncode == 0
        
        if not xcode_running:
            return {"xcode_running": False}
        
        result = subprocess.run(['osascript', '-e', APPLESCRIPT_GET_WINDOW_TITLE], 
                              capture_output=True, text=True, timeout=APPLESCRIPT_SHORT_TIMEOUT)
        window_title = result.stdout.strip()
        
        current_file = ""
        project_name = ""
        
        if " — " in window_title:
            parts = window_title.split(" — ")
            project_name = parts[0]
            current_file = parts[-1]
        
        build_errors = 0
        detailed_errors = []
        
        derived_data_path = find_active_derived_data()
        if derived_data_path:
            manifest_path = os.path.join(derived_data_path, BUILD_LOGS_SUBPATH, MANIFEST_FILENAME)
            if os.path.exists(manifest_path):
                build_failed, error_count = check_build_failed(manifest_path)
                if build_failed:
                    detailed_errors = parse_build_errors_detailed(manifest_path)
                    build_errors = len(detailed_errors) if detailed_errors else error_count
        
        current_file_path = get_current_file_path()
        
        project_path = ""
        if derived_data_path:
            try:
                info_plist = os.path.join(derived_data_path, INFO_PLIST_FILENAME)
                if os.path.exists(info_plist):
                    with open(info_plist, 'rb') as f:
                        info = plistlib.load(f)
                        project_path = info.get('WorkspacePath', '')
            except:
                pass
        
        status_data = {
            "xcode_running": True,
            "current_file": current_file,
            "project_name": project_name,
            "build_errors": build_errors,
            "detailed_errors": detailed_errors,
            "project_path": project_path,
            "current_file_path": current_file_path
        }
        
        write_logs(status_data, project_path, current_file_path)
        
        return status_data
    except:
        return {"xcode_running": False}

def format_status_line(status):
    logs_path = os.environ.get('XCODE_LOGS_PATH', '')
    if not logs_path:
        return f"{COLOR_RED}⏺{COLOR_RESET} Add XCODE_LOGS_PATH in settings.json first."
    
    if not status.get("xcode_running", False):
        # OSC 8 hyperlink format: \033]8;;URI\033\\text\033]8;;\033\\
        # Using file:// with a command to execute
        open_link = "\033]8;;file:///Applications/Xcode.app\033\\open now\033]8;;\033\\"
        return f"{COLOR_RED}⏺{COLOR_RESET} xcode closed | {open_link}"
    
    project_name = status.get("project_name", "")
    if project_name:
        parts = [f"{COLOR_GREEN}⏺{COLOR_RESET} {project_name}"]
    else:
        parts = [f"{COLOR_GREEN}⏺{COLOR_RESET} xcode opened but not focused"]
    
    if status.get("current_file"):
        current_file_path = status.get("current_file_path", "")
        if current_file_path:
            file_link = f"\033]8;;file://{current_file_path}\033\\{status['current_file']}\033]8;;\033\\"
            parts.append(f" | {COLOR_BLUE}⧉ In {file_link}{COLOR_RESET}")
        else:
            parts.append(f" | {COLOR_BLUE}⧉ In {status['current_file']}{COLOR_RESET}")
    
    detailed_errors = status.get("detailed_errors", [])
    if detailed_errors:
        error_count = len(detailed_errors)
        error_word = "error" if error_count == 1 else "errors"
        parts.append(f" | {error_count} build {error_word}")
    else:
        build_errors = status.get("build_errors", 0)
        if build_errors > 0:
            error_word = "error" if build_errors == 1 else "errors"
            parts.append(f" | {build_errors} build {error_word}")
    
    return "".join(parts)

def update_status_line(status_text):
    print(status_text, flush=True)

def get_status_once():
    status = get_xcode_status()
    return format_status_line(status)

if __name__ == "__main__":
    print(get_status_once())