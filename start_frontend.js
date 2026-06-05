#!/usr/bin/env node
"""
Simple frontend startup script
"""
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const frontendPath = path.join(__dirname, 'frontend');
process.chdir(frontendPath);

console.log('='.repeat(70));
console.log('FRONTEND STARTUP SCRIPT');
console.log('='.repeat(70));
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
console.log('Starting React frontend on http://localhost:3000');
console.log('='.repeat(70));
console.log();

// Start frontend
execSync('npm start', { stdio: 'inherit' });
