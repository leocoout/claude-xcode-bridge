#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const LOG_FILENAME = 'statusline_context.json';
const XCODE_LOGS_PATH = '.claude-xcode-build-infra';

function setStatuslineEnabled(enabled) {
    const logsPath = XCODE_LOGS_PATH;
    const logDir = path.join(os.homedir(), logsPath);
    const logFile = path.join(logDir, LOG_FILENAME);

    if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
    }

    let logData = {};
    if (fs.existsSync(logFile)) {
        try {
            const content = fs.readFileSync(logFile, 'utf8');
            logData = JSON.parse(content);
        } catch (error) {
        }
    }

    logData.enabled = enabled;

    try {
        fs.writeFileSync(logFile, JSON.stringify(logData, null, 2));
        const status = enabled ? 'enabled' : 'disabled';
        console.log(`Statusline ${status}`);
    } catch (error) {
        console.error(`Error updating statusline: ${error.message}`);
    }
}

function main() {
    if (process.argv.length !== 3) {
        console.log('Usage: claude-xcode-toggle <true|false>');
        console.log('  true  - Enable the statusline');
        console.log('  false - Disable the statusline');
        process.exit(1);
    }

    const enabledStr = process.argv[2].toLowerCase();
    if (enabledStr === 'true') {
        setStatuslineEnabled(true);
    } else if (enabledStr === 'false') {
        setStatuslineEnabled(false);
    } else {
        console.error("Error: Argument must be 'true' or 'false'");
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}