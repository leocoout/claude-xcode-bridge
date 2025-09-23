---
allowed-tools: Bash(python3 src/window_manager.py*)
description: Arrange workspace with any window and terminal side by side
argument-hint: [LEFT|RIGHT] [--proportion PERCENT] [--preferred-app APP_NAME]
---

Arrange your workspace by positioning any window and terminal side by side for optimal development workflow.

Usage examples:
- `/window` - Default. No parameters required.
- `/window LEFT` - Terminal on left side
- `/window RIGHT 25` - Terminal on right, 25% width
- `/window LEFT 25 Xcode` - Left side, 25% width, target Xcode

Arguments: [position] [proportion] [preferred-app]
- $1: LEFT or RIGHT (default: RIGHT)
- $2: Width percentage (default: 25)
- $3: App name (default: Xcode)

'python3 src/window_manager.py $1 --proportion $2 --preferred-app $3'

If the user doesn't have python3, try python. If it fails again, look for a solution.