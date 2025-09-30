#!/usr/bin/env node

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const zlib = require('zlib');
const plist = require('plist');

const APPLESCRIPT_TIMEOUT = 5000;
const APPLESCRIPT_SHORT_TIMEOUT = 2000;
const BUILD_ACTIVE_THRESHOLD = 300;
const MAX_ERROR_LENGTH = 500;
const DERIVED_DATA_PATH = path.join(os.homedir(), 'Library/Developer/Xcode/DerivedData');
const BUILD_LOGS_SUBPATH = 'Logs/Build';
const MANIFEST_FILENAME = 'LogStoreManifest.plist';
const INFO_PLIST_FILENAME = 'Info.plist';
const LOG_FILENAME = 'statusline_context.json';
const XCODE_LOGS_PATH = '.claude-xcode-build-infra';

const XCODE_PROCESS_NAME = 'Xcode';
const PROJECT_EXTENSIONS = ['.xcworkspace', '.xcodeproj'];
const SOURCE_DIRECTORIES = ['Sources', 'src'];

const COLOR_RED = '\x1b[31m';
const COLOR_GREEN = '\x1b[32m';
const COLOR_BLUE = '\x1b[94m';
const COLOR_RESET = '\x1b[0m';

const APPLESCRIPT_GET_PROJECT = `
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
`;

const APPLESCRIPT_GET_WINDOW_TITLE = `
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
`;

const APPLESCRIPT_GET_XCODE_WINDOW = `
tell application "Xcode"
    try
        return name of window 1
    on error
        return ""
    end try
end tell
`;

const APPLESCRIPT_GET_SOURCE_DOCUMENT = `
tell application "Xcode"
    try
        set sourceDoc to source document 1
        return path of sourceDoc
    on error
        return ""
    end try
end tell
`;

const APPLESCRIPT_GET_DOCUMENT = `
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
`;

function runAppleScript(script, timeout = APPLESCRIPT_TIMEOUT) {
    try {
        const result = execSync(`osascript -e '${script.replace(/'/g, "'\\''")}'`, {
            encoding: 'utf8',
            timeout: timeout,
            stdio: ['pipe', 'pipe', 'pipe']
        });
        return result.trim();
    } catch (error) {
        return '';
    }
}

function findActiveDerivedData() {
    try {
        const projectPath = runAppleScript(APPLESCRIPT_GET_PROJECT);

        if (!projectPath) {
            return null;
        }

        let projectName = path.basename(projectPath);
        for (const ext of PROJECT_EXTENSIONS) {
            projectName = projectName.replace(ext, '');
        }

        const normalizedProjectName = projectName.replace(/ /g, '_');

        const items = fs.readdirSync(DERIVED_DATA_PATH);
        for (const item of items) {
            if (!item.startsWith(projectName) && !item.startsWith(normalizedProjectName)) {
                continue;
            }

            const derivedPath = path.join(DERIVED_DATA_PATH, item);
            const infoPlist = path.join(derivedPath, INFO_PLIST_FILENAME);

            if (fs.existsSync(infoPlist)) {
                try {
                    const content = fs.readFileSync(infoPlist, 'utf8');
                    const info = plist.parse(content);
                    const workspacePath = info.WorkspacePath || '';
                    if (workspacePath && fs.realpathSync(workspacePath) === fs.realpathSync(projectPath)) {
                        return derivedPath;
                    }
                } catch (error) {
                    continue;
                }
            }
        }

        return null;
    } catch (error) {
        return null;
    }
}

function checkBuildFailed(manifestPath) {
    try {
        const content = fs.readFileSync(manifestPath, 'utf8');
        const manifest = plist.parse(content);

        let latestBuild = null;
        let latestTime = 0;

        const logs = manifest.logs || {};
        for (const [buildId, buildInfo] of Object.entries(logs)) {
            const stopTime = buildInfo.timeStoppedRecording || 0;
            if (stopTime > latestTime) {
                latestTime = stopTime;
                latestBuild = buildInfo;
            }
        }

        if (!latestBuild) {
            return [false, 0];
        }

        const status = latestBuild.primaryObservable || {};
        const highLevelStatus = status.highLevelStatus || 'S';
        const errorCount = status.totalNumberOfErrors || 0;

        return [highLevelStatus === 'E', errorCount];
    } catch (error) {
        return [false, 0];
    }
}

function extractErrorsFromLog(logPath) {
    const errors = [];
    try {
        let content;
        try {
            const compressed = fs.readFileSync(logPath);
            content = zlib.gunzipSync(compressed).toString('utf8');
        } catch (error) {
            content = fs.readFileSync(logPath, 'utf8');
        }

        const lines = content.split('\n');
        const swiftErrors = [];
        const genericErrors = [];

        const swiftErrorPatterns = [
            /(.+\.swift:\d+:\d+):\s+error:\s+(.+)/,
            /(.+\.swift:\d+:\d+):\s+(.+)/,
            /(\/[^:]+\.swift:\d+:\d+):\s+error:\s+(.+)/,
            /(\/[^:]+\.swift:\d+:\d+):\s+(.+)/
        ];

        for (const line of lines) {
            for (const pattern of swiftErrorPatterns) {
                const match = line.match(pattern);
                if (match) {
                    const fileLocation = match[1];
                    const errorMessage = match[2] || '';

                    if (errorMessage.toLowerCase().includes('warning:')) {
                        continue;
                    }

                    const fullError = errorMessage ? `${fileLocation}: ${errorMessage}` : fileLocation;

                    if (fullError.length < MAX_ERROR_LENGTH &&
                        !/[0-9A-F]{20,}/.test(fullError) &&
                        !swiftErrors.includes(fullError)) {
                        swiftErrors.push(fullError);
                        break;
                    }
                }
            }
        }

        if (swiftErrors.length === 0) {
            const errorPatterns = [
                /error:\s+(.+)/i,
                /Error:\s+(.+)/,
                /fatal error:\s+(.+)/i,
                /compilation failed:\s+(.+)/i
            ];

            for (const line of lines) {
                for (const pattern of errorPatterns) {
                    const match = line.match(pattern);
                    if (match) {
                        const errorMessage = match[1].trim();

                        if (errorMessage.length < MAX_ERROR_LENGTH &&
                            !/[0-9A-F]{20,}/.test(errorMessage) &&
                            !genericErrors.includes(errorMessage)) {
                            genericErrors.push(errorMessage);
                        }
                    }
                }
            }
        }

        return swiftErrors.length > 0 ? swiftErrors : genericErrors;
    } catch (error) {
        return [];
    }
}

function parseBuildErrorsDetailed(manifestPath) {
    try {
        const content = fs.readFileSync(manifestPath, 'utf8');
        const manifest = plist.parse(content);

        let errors = [];
        const buildLogsDir = path.dirname(manifestPath);

        let latestBuild = null;
        let latestTime = 0;

        const logs = manifest.logs || {};
        for (const [buildId, buildInfo] of Object.entries(logs)) {
            const stopTime = buildInfo.timeStoppedRecording || 0;
            if (stopTime > latestTime) {
                const status = buildInfo.primaryObservable || {};
                const highLevelStatus = status.highLevelStatus || 'S';
                if (highLevelStatus === 'E') {
                    latestTime = stopTime;
                    latestBuild = buildInfo;
                }
            }
        }

        if (latestBuild) {
            const logFile = latestBuild.fileName || '';
            if (logFile) {
                const logPath = path.join(buildLogsDir, logFile);
                if (fs.existsSync(logPath)) {
                    errors = extractErrorsFromLog(logPath);
                }
            }
        }

        return errors;
    } catch (error) {
        return [];
    }
}

function getCurrentFilePath() {
    try {
        let windowTitle = runAppleScript(APPLESCRIPT_GET_XCODE_WINDOW, APPLESCRIPT_SHORT_TIMEOUT);

        let currentFileName = '';
        if (windowTitle.includes(' — ')) {
            const parts = windowTitle.split(' — ');
            currentFileName = parts[parts.length - 1];
        }

        if (currentFileName && !PROJECT_EXTENSIONS.some(ext => currentFileName.includes(ext))) {
            const script = `tell application "Xcode"
                try
                    set sourceDoc to source document 1 whose name is "${currentFileName}"
                    return path of sourceDoc
                on error
                    repeat with i from 1 to 10
                        try
                            set sourceDoc to source document i
                            if name of sourceDoc is "${currentFileName}" then
                                return path of sourceDoc
                            end if
                        end try
                    end repeat
                    return ""
                end try
            end tell`;

            const filePath = runAppleScript(script, APPLESCRIPT_SHORT_TIMEOUT);

            if (filePath && fs.existsSync(filePath)) {
                return filePath;
            }
        }

        const sourceFilePath = runAppleScript(APPLESCRIPT_GET_SOURCE_DOCUMENT, APPLESCRIPT_SHORT_TIMEOUT);

        if (sourceFilePath && fs.existsSync(sourceFilePath)) {
            return sourceFilePath;
        }

        let filePath = runAppleScript(APPLESCRIPT_GET_DOCUMENT, APPLESCRIPT_SHORT_TIMEOUT);

        let currentFile = '';
        let projectPath = '';

        windowTitle = runAppleScript(APPLESCRIPT_GET_XCODE_WINDOW, APPLESCRIPT_SHORT_TIMEOUT);

        if (!windowTitle) {
            windowTitle = runAppleScript(APPLESCRIPT_GET_WINDOW_TITLE, APPLESCRIPT_SHORT_TIMEOUT);
        }

        if (windowTitle.includes(' — ')) {
            const parts = windowTitle.split(' — ');
            currentFile = parts[parts.length - 1];

            const derivedDataPath = findActiveDerivedData();
            if (derivedDataPath) {
                try {
                    const infoPlist = path.join(derivedDataPath, INFO_PLIST_FILENAME);
                    if (fs.existsSync(infoPlist)) {
                        const content = fs.readFileSync(infoPlist, 'utf8');
                        const info = plist.parse(content);
                        projectPath = info.WorkspacePath || '';

                        if (projectPath && currentFile) {
                            const projectDir = path.dirname(projectPath);
                            let projectName = path.basename(projectPath);
                            for (const ext of PROJECT_EXTENSIONS) {
                                projectName = projectName.replace(ext, '');
                            }

                            try {
                                const result = execSync(
                                    `find "${projectDir}" -path '*/.build' -prune -o -path '*/.git' -prune -o -path '*/DerivedData' -prune -o -name "${currentFile}" -type f -print`,
                                    { encoding: 'utf8', timeout: 3000, stdio: ['pipe', 'pipe', 'pipe'] }
                                );
                                const foundPaths = result.trim().split('\n').filter(p => p);
                                if (foundPaths.length > 0) {
                                    return foundPaths[0];
                                }
                            } catch (error) {
                            }

                            const possiblePaths = [
                                path.join(projectDir, projectName, currentFile),
                                path.join(projectDir, currentFile)
                            ];

                            for (const srcDir of SOURCE_DIRECTORIES) {
                                possiblePaths.push(path.join(projectDir, srcDir, currentFile));
                                possiblePaths.push(path.join(projectDir, projectName, srcDir, currentFile));
                            }

                            for (const p of possiblePaths) {
                                if (fs.existsSync(p)) {
                                    return p;
                                }
                            }
                        }
                    }
                } catch (error) {
                }
            }
        }

        if (filePath && filePath !== 'missing value' && !PROJECT_EXTENSIONS.some(ext => filePath.includes(ext))) {
            return filePath;
        }
        return '';
    } catch (error) {
        return '';
    }
}

function writeLogs(status, projectPath = '', currentFilePath = '') {
    const logsPath = XCODE_LOGS_PATH;
    if (!logsPath) {
        return;
    }

    const logDir = path.join(os.homedir(), logsPath);
    if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
    }

    const logFile = path.join(logDir, LOG_FILENAME);

    const logData = {
        enabled: true,
        timestamp: new Date().toISOString(),
        xcode_running: status.xcode_running || false,
        project_name: status.project_name || '',
        project_path: projectPath,
        current_file: status.current_file || '',
        current_file_path: currentFilePath,
        build_errors: status.build_errors || 0,
        detailed_errors: status.detailed_errors || []
    };

    try {
        fs.writeFileSync(logFile, JSON.stringify(logData, null, 2));
    } catch (error) {
    }
}

function getXcodeStatus() {
    try {
        let xcodeRunning = false;
        try {
            execSync(`pgrep -x ${XCODE_PROCESS_NAME}`, { stdio: 'pipe' });
            xcodeRunning = true;
        } catch (error) {
            xcodeRunning = false;
        }

        if (!xcodeRunning) {
            return { xcode_running: false };
        }

        let windowTitle = runAppleScript(APPLESCRIPT_GET_XCODE_WINDOW, APPLESCRIPT_SHORT_TIMEOUT);

        if (!windowTitle) {
            windowTitle = runAppleScript(APPLESCRIPT_GET_WINDOW_TITLE, APPLESCRIPT_SHORT_TIMEOUT);
        }

        let currentFile = '';
        let projectName = '';

        if (windowTitle.includes(' — ')) {
            const parts = windowTitle.split(' — ');
            projectName = parts[0];
            currentFile = parts[parts.length - 1];
        }

        let buildErrors = 0;
        let detailedErrors = [];

        const derivedDataPath = findActiveDerivedData();
        if (derivedDataPath) {
            const manifestPath = path.join(derivedDataPath, BUILD_LOGS_SUBPATH, MANIFEST_FILENAME);
            if (fs.existsSync(manifestPath)) {
                const [buildFailed, errorCount] = checkBuildFailed(manifestPath);
                if (buildFailed) {
                    detailedErrors = parseBuildErrorsDetailed(manifestPath);
                    buildErrors = detailedErrors.length > 0 ? detailedErrors.length : errorCount;
                }
            }
        }

        const currentFilePath = getCurrentFilePath();

        let projectPath = '';
        if (derivedDataPath) {
            try {
                const infoPlist = path.join(derivedDataPath, INFO_PLIST_FILENAME);
                if (fs.existsSync(infoPlist)) {
                    const content = fs.readFileSync(infoPlist, 'utf8');
                    const info = plist.parse(content);
                    projectPath = info.WorkspacePath || '';
                }
            } catch (error) {
            }
        }

        const statusData = {
            xcode_running: true,
            current_file: currentFile,
            project_name: projectName,
            build_errors: buildErrors,
            detailed_errors: detailedErrors,
            project_path: projectPath,
            current_file_path: currentFilePath
        };

        writeLogs(statusData, projectPath, currentFilePath);

        return statusData;
    } catch (error) {
        return { xcode_running: false };
    }
}

function formatStatusLine(status) {
    const logsPath = XCODE_LOGS_PATH;
    if (!logsPath) {
        return `${COLOR_RED}⏺${COLOR_RESET} Using logs path: ${XCODE_LOGS_PATH}`;
    }

    if (!status.xcode_running) {
        const openLink = '\x1b]8;;file:///Applications/Xcode.app\x1b\\\x1b[24mopen now\x1b[24m\x1b]8;;\x1b\\';
        return `${COLOR_RED}⏺${COLOR_RESET} xcode closed, ${openLink}`;
    }

    const projectName = status.project_name || '';
    let parts = [];

    if (projectName) {
        parts.push(`${COLOR_GREEN}⏺${COLOR_RESET} ${projectName}`);
    } else {
        parts.push(`${COLOR_GREEN}⏺${COLOR_RESET} xcode opened but not focused`);
    }

    if (status.current_file) {
        const currentFilePath = status.current_file_path || '';
        if (currentFilePath) {
            const fileLink = `\x1b]8;;file://${currentFilePath}\x1b\\\x1b[24m${COLOR_BLUE}${status.current_file}${COLOR_RESET}\x1b[24m\x1b]8;;\x1b\\`;
            parts.push(` | ${COLOR_BLUE}⧉ In ${COLOR_RESET}${fileLink}`);
        } else {
            parts.push(` | ${COLOR_BLUE}⧉ In ${status.current_file}${COLOR_RESET}`);
        }
    }

    const detailedErrors = status.detailed_errors || [];
    if (detailedErrors.length > 0) {
        const errorCount = detailedErrors.length;
        const errorWord = errorCount === 1 ? 'error' : 'errors';
        parts.push(` | ${errorCount} build ${errorWord}`);
    } else {
        const buildErrors = status.build_errors || 0;
        if (buildErrors > 0) {
            const errorWord = buildErrors === 1 ? 'error' : 'errors';
            parts.push(` | ${buildErrors} build ${errorWord}`);
        }
    }

    return parts.join('');
}

function isStatuslineEnabled() {
    try {
        const logsPath = XCODE_LOGS_PATH;
        const logDir = path.join(os.homedir(), logsPath);
        const logFile = path.join(logDir, LOG_FILENAME);

        if (fs.existsSync(logFile)) {
            const content = fs.readFileSync(logFile, 'utf8');
            const logData = JSON.parse(content);
            return logData.enabled !== false;
        }
        return true;
    } catch (error) {
        return true;
    }
}

function getStatusOnce() {
    if (!isStatuslineEnabled()) {
        return '';
    }

    const status = getXcodeStatus();
    return formatStatusLine(status);
}

if (require.main === module) {
    console.log(getStatusOnce());
}