---
allowed-tools: Read, Bash(*), TodoWrite, Edit, MultiEdit, Glob, Grep
description: Analyze Xcode build errors and fix them systematically
---

Please analyze the Xcode build logs and errors in `~/.claude-xcode-build-infra/statusline_context.json` and provide a comprehensive report.

If build errors are found:
1. Create a todo list with all the issues that need to be fixed
2. Work through each issue systematically, one by one
3. Mark each todo as completed when fixed
4. Provide a summary of what was fixed
5. Since the context file only gets updated after the build, you can give two options: "1. Ask Claude to rebuild the project" "2. Build by myself". 
6. If the user selected the first option, trigger the `xcodebuild` command. 

If no errors are found, provide a brief status report confirming the build is clean.