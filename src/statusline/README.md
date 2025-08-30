# Xcode Bridge for Claude Code Status Line

A Python script that provides real-time Xcode status information to Claude Code's status line.

## Features

- **Xcode Detection**: Shows if Xcode is running or not
- **Current File**: Displays the currently focused file
- **Build Status**: Shows build status and error counts
- **Precise Path Detection**: Uses `xcodebuild` to get exact DerivedData paths

## Installation

1. Ensure Python 3 is installed
2. The script uses only built-in Python modules (no external dependencies)
3. Make sure the script is executable:
   ```bash
   chmod +x xcode_statusline.py
   ```

## Usage

Run the script directly:
```bash
python3 xcode_statusline.py
```

## Output Format

- `[red] xcode` - Xcode is not running
- `[green] xcode filename build succeeded` - Build successful
- `[green] xcode filename build failed (X errors)` - Build failed with errors
- `[green] xcode filename` - No build status available

## Integration with Claude Code

The script is already configured in `.claude/settings.local.json`:
```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/bytedance/claude-xcode-bridge/src/statusline/xcode_statusline.py"
  }
}
```

## Testing

Test the script manually:
```bash
# With Xcode running
python3 xcode_statusline.py

# With Xcode closed
python3 xcode_statusline.py
```