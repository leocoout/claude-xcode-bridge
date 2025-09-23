#!/usr/bin/env python3

import argparse
import subprocess
import sys
import time

def run_applescript(script, timeout=10):
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, Exception):
        return None

def get_available_terminals():
    terminal_candidates = [
        'iTerm2', 'Terminal', 'iTerm', 'Alacritty', 'Kitty', 'Hyper',
        'Warp', 'WezTerm', 'Tabby', 'Termius', 'Rio', 'Ghostty',
        'Wave Terminal', 'Contour', 'Foot', 'Cool Retro Term', 'Upterm',
        'Zellij', 'Terminal.app', 'OpenTerm', 'SSH Files'
    ]

    running_processes = run_applescript('tell application "System Events" to get name of processes')
    if not running_processes:
        return ['Terminal']

    available_terminals = []
    for terminal in terminal_candidates:
        if terminal in running_processes:
            available_terminals.append(terminal)

    return available_terminals if available_terminals else ['Terminal']

def get_current_terminal():
    available_terminals = get_available_terminals()
    for terminal in available_terminals:
        windows_script = f'''
        tell application "{terminal}"
            try
                return count of windows
            on error
                return "0"
            end try
        end tell
        '''
        window_count = run_applescript(windows_script)
        if window_count and int(window_count) > 0:
            return terminal

    return available_terminals[0]

def get_current_screen_bounds():
    terminal_app = get_current_terminal()
    terminal_pos_script = f'''
    tell application "System Events"
        tell process "{terminal_app}"
            try
                tell window 1
                    return position
                end tell
            on error
                return "0,0"
            end try
        end tell
    end tell
    '''

    terminal_pos = run_applescript(terminal_pos_script)
    if not terminal_pos:
        terminal_pos = "0,0"

    try:
        term_x, term_y = map(int, terminal_pos.split(','))
    except:
        term_x, term_y = 0, 0
    screens_script = '''
    tell application "System Events"
        try
            set screenCount to count of desktops
            set allBounds to {}
            repeat with i from 1 to screenCount
                set screenBounds to bounds of desktop i
                set end of allBounds to screenBounds
            end repeat
            return allBounds
        on error
            tell application "Finder"
                return bounds of window of desktop
            end tell
        end try
    end tell
    '''

    screens_result = run_applescript(screens_script)
    if not screens_result:
        return 0, 0, 1920, 1080
    try:
        bounds_str = screens_result.strip('{}').split('}, {')
        for bounds in bounds_str:
            coords = bounds.strip('{}').split(', ')
            if len(coords) >= 4:
                x1, y1, x2, y2 = map(int, coords[:4])
                if x1 <= term_x <= x2 and y1 <= term_y <= y2:
                    return x1, y1, x2, y2
    except:
        pass
    primary_screen = run_applescript('''
    tell application "Finder"
        set screenBounds to bounds of window of desktop
        return screenBounds
    end tell
    ''')

    if primary_screen:
        try:
            coords = primary_screen.strip('{}').split(', ')
            if len(coords) >= 4:
                return tuple(map(int, coords))
        except:
            pass
    return 0, 0, 1920, 1080

def get_screen_dimensions():
    x1, y1, x2, y2 = get_current_screen_bounds()
    return x2 - x1, y2 - y1, x1, y1

def get_frontmost_app():
    script = '''
    tell application "System Events"
        return name of first process whose frontmost is true
    end tell
    '''
    return run_applescript(script)

def has_main_window(app_name):
    process_check_script = f'''
    tell application "System Events"
        try
            set processExists to exists process "{app_name}"
            return processExists
        on error
            return false
        end try
    end tell
    '''

    process_exists = run_applescript(process_check_script)
    if not process_exists or process_exists.lower() == 'false':
        return False

    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            try
                return count of windows
            on error
                return "0"
            end try
        end tell
    end tell
    '''
    window_count = run_applescript(script)
    if window_count and int(window_count) > 0:
        return True

    return True

def activate_app(app_name):
    script = f'''
    tell application "{app_name}"
        activate
    end tell
    '''
    return run_applescript(script)

def open_terminal():
    terminal_app = get_current_terminal()
    script = f'''
    tell application "{terminal_app}"
        activate
    end tell
    '''
    return run_applescript(script)

def get_best_main_app(preferred_app=None):
    available_terminals = get_available_terminals()
    system_apps = [
        'Finder', 'Dock', 'SystemUIServer', 'ControlCenter', 'NotificationCenter',
        'Spotlight', 'loginwindow', 'WindowManager', 'Siri', 'MenuBarExtra'
    ]

    if preferred_app:
        if has_main_window(preferred_app):
            return preferred_app

        all_apps_script = '''
        tell application "System Events"
            set appList to {}
            repeat with proc in (processes whose visible is true)
                set end of appList to name of proc
            end repeat
            return appList
        end tell
        '''

        all_apps = run_applescript(all_apps_script)
        if all_apps:
            apps_list = [app.strip() for app in all_apps.split(', ')]
            preferred_lower = preferred_app.lower()

            for app in apps_list:
                if (preferred_lower in app.lower() or app.lower() in preferred_lower):
                    if has_main_window(app):
                        return app

        print(f"Could not find application '{preferred_app}'. Available apps:")
        if all_apps:
            for app in sorted(apps_list):
                if app not in available_terminals and app not in system_apps:
                    print(f"  - {app}")
        return None

    recent_apps_script = '''
    tell application "System Events"
        set recentApps to {}
        repeat with proc in (processes whose visible is true)
            if background only of proc is false then
                set end of recentApps to name of proc
            end if
        end repeat
        return recentApps
    end tell
    '''

    all_apps = run_applescript(recent_apps_script)
    if not all_apps:
        return None

    apps_list = [app.strip() for app in all_apps.split(', ')]

    if 'Xcode' in apps_list and has_main_window('Xcode'):
        return 'Xcode'

    frontmost_app = get_frontmost_app()
    if (frontmost_app and
        frontmost_app not in available_terminals and
        frontmost_app not in system_apps and
        has_main_window(frontmost_app)):
        return frontmost_app

    priority_apps = ['Visual Studio Code', 'Cursor', 'Sublime Text', 'Atom', 'IntelliJ IDEA']

    for priority_app in priority_apps:
        if (priority_app in apps_list and
            priority_app not in available_terminals and
            has_main_window(priority_app)):
            return priority_app

    for app in apps_list:
        if (app not in available_terminals and
            app not in system_apps and
            has_main_window(app)):
            return app

    return None

def arrange_windows(terminal_position='RIGHT', preferred_app=None, terminal_proportion=25):
    terminal_app = get_current_terminal()
    main_app = get_best_main_app(preferred_app)
    available_terminals = get_available_terminals()

    if not main_app:
        if preferred_app:
            print(f"Could not find or arrange application '{preferred_app}'")
        else:
            print("No suitable main application found with windows")
        return

    if not (10 <= terminal_proportion <= 90):
        print(f"Invalid proportion {terminal_proportion}%. Must be between 10 and 90.")
        return

    screen_width, screen_height, x_offset, y_offset = get_screen_dimensions()
    terminal_width = int(screen_width * terminal_proportion / 100)
    main_width = screen_width - terminal_width
    usable_height = screen_height - 80
    menu_bar_height = 24
    final_y_offset = y_offset + menu_bar_height

    print(f"Arranging {main_app} and {terminal_app} (terminal on {terminal_position.lower()} side)")

    if terminal_position.upper() == 'LEFT':
        terminal_x = x_offset
        main_x = x_offset + terminal_width
    else:
        main_x = x_offset
        terminal_x = x_offset + main_width

    open_terminal()
    time.sleep(1)

    terminal_script = f'''
    tell application "System Events"
        tell process "{terminal_app}"
            try
                set frontmost to true
                tell window 1
                    set position to {{{terminal_x}, {final_y_offset}}}
                    set size to {{{terminal_width}, {usable_height}}}
                end tell
            end try
        end tell
    end tell
    '''

    run_applescript(terminal_script)
    time.sleep(0.5)

    if main_app and main_app != terminal_app and has_main_window(main_app):
        main_script = f'''
        tell application "System Events"
            tell process "{main_app}"
                try
                    tell window 1
                        set position to {{{main_x}, {final_y_offset}}}
                        set size to {{{main_width}, {usable_height}}}
                    end tell
                end try
            end tell
        end tell
        '''
        run_applescript(main_script)
        time.sleep(0.3)
        main_proportion = 100 - terminal_proportion
        print(f"Arranged {main_app} ({main_proportion}% width) and {terminal_app} ({terminal_proportion}% width)")
    else:
        print(f"Terminal positioned ({terminal_proportion}% width). No suitable main app found to auto-resize.")

    if main_app and main_app != terminal_app:
        activate_app(main_app)

def main():
    parser = argparse.ArgumentParser(
        description='Arrange windows: main application and terminal side by side'
    )
    parser.add_argument(
        'position',
        nargs='?',
        default='RIGHT',
        choices=['LEFT', 'RIGHT', 'left', 'right'],
        help='Position of terminal: LEFT or RIGHT (default: RIGHT)'
    )
    parser.add_argument(
        '--preferred-app',
        help='Any application to arrange with terminal. Supports exact names, partial matches, and case-insensitive search.'
    )
    parser.add_argument(
        '--proportion',
        type=int,
        default=25,
        metavar='PERCENT',
        help='Terminal width as percentage of screen (default: 25)'
    )

    args = parser.parse_args()

    try:
        arrange_windows(args.position.upper(), args.preferred_app, args.proportion)
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()