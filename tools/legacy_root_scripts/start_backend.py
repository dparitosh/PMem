#!/usr/bin/env python3
"""
Simple backend startup script that handles import errors gracefully
"""
import subprocess
import sys
import os

workspace_root = os.path.dirname(__file__)
backend_dir = os.path.join(workspace_root, 'backend')

# Run from workspace root so `backend.main` package imports work.
os.chdir(workspace_root)

print("=" * 70)
print("BACKEND STARTUP SCRIPT")
print("=" * 70)
print()

# Try to install missing packages
print("Ensuring all dependencies are installed...")
packages_to_install = [
    'langchain-openai',
    'langchain-core', 
    'langchain-neo4j',
    'fastapi',
    'uvicorn',
    'neo4j',
    'pydantic',
]

for package in packages_to_install:
    try:
        __import__(package.replace('-', '_'))
        print(f"✓ {package}")
    except ImportError:
        print(f"✗ {package} - installing...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '-q'])

print()
print("=" * 70)
print("Starting FastAPI backend on http://localhost:8000")
print("=" * 70)
print()

# Start uvicorn (list form avoids path quoting issues on Windows)
subprocess.call([
    sys.executable,
    '-m',
    'uvicorn',
    'backend.main:app',
    '--host',
    '0.0.0.0',
    '--port',
    '8000',
    '--reload',
    '--reload-dir',
    backend_dir,
])
