#!/usr/bin/env node
/**
 * Simple frontend startup script
 */
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const frontendPath = path.join(__dirname, 'frontend');
process.chdir(frontendPath);

const port = process.env.PORT || process.argv[2] || '3000';
const backendUrl = process.env.REACT_APP_BACKEND_URL || process.argv[3] || 'http://localhost:8000';
const host = process.env.HOST || process.argv[4] || 'localhost';

console.log('='.repeat(70));
console.log('FRONTEND STARTUP SCRIPT');
console.log('='.repeat(70));
console.log();
console.log(`Port: ${port}`);
console.log(`Host: ${host}`);
console.log(`Backend URL: ${backendUrl}`);
console.log();

// Check if node_modules exists
if (!fs.existsSync(path.join(frontendPath, 'node_modules'))) {
    console.log('Installing dependencies...');
    try {
        execSync('npm install --legacy-peer-deps', { stdio: 'inherit' });
    } catch (e) {
        console.error('Failed to install dependencies');
        process.exit(1);
    }
}

console.log();
console.log('='.repeat(70));
console.log(`Starting React frontend on http://${host}:${port}`);
console.log('='.repeat(70));
console.log();

// Start frontend
execSync('npm start', {
    stdio: 'inherit',
    env: {
        ...process.env,
        PORT: port,
        HOST: host,
        REACT_APP_BACKEND_URL: backendUrl,
        BROWSER: 'none',
        FAST_REFRESH: 'true',
    },
});
