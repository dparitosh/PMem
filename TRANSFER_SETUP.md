# Project Transfer & Setup Guide

This project has been cleaned and is ready to transfer to another computer.

## What Was Cleaned
✅ Python cache files (`__pycache__`, `.pyc`, `.pyo`)  
✅ Virtual environments (`.dt_venv`, `venv`, `.venv`)  
✅ Node modules and build artifacts  
✅ IDE settings (`.vscode`, `.idea`)  
✅ OS-specific files (`.DS_Store`, `Thumbs.db`)  
✅ Test cache (`.pytest_cache`)  
✅ Egg-info and cache directories  

**Final project size: ~1.4 GB** (ready for transfer)

---

## Setup on New Computer

### 1. **Backend Setup**
```bash
cd Depo_onto/backend

# Create virtual environment
python -m venv .dt_venv

# Activate virtual environment
# On Windows:
.dt_venv\Scripts\activate
# On macOS/Linux:
source .dt_venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify .env file exists with correct credentials
# Check: NEO4J_URI, NEO4J_USER, NEO4J_PASS, NEO4J_DATABASE
```

### 2. **Frontend Setup**
```bash
cd ../frontend

# Install dependencies
npm install

# Build (if needed)
npm run build
```

### 3. **Verify Neo4j Connection**
- Check that your Neo4j AuraDB instance is running at console.neo4j.io
- Verify credentials in `backend/.env` match your database
- The database name in `.env` should match your AuraDB instance

### 4. **Start Services**
```bash
# Terminal 1 - Backend
cd Depo_onto/backend
.dt_venv\Scripts\activate
python start_backend.py

# Terminal 2 - Frontend
cd Depo_onto/frontend
npm start
```

---

## Important Files to Check

- `Depo_onto/backend/.env` - Database credentials (keep secure)
- `Depo_onto/backend/requirements.txt` - Python dependencies
- `Depo_onto/frontend/package.json` - Node dependencies
- `.gitignore` - Prevents cache files in version control

---

## If Backend Won't Start

Check `Depo_onto/logs/error.log` for issues. Common problems:
- ❌ Neo4j database is paused → Resume at console.neo4j.io
- ❌ Wrong credentials in `.env` → Update with correct values
- ❌ Network issue → Check internet connection
- ❌ Python version mismatch → Use Python 3.9+

---

## Transfer Checklist

- [ ] Copy entire `Depo_onto` folder to new computer
- [ ] Verify `.env` file has correct database credentials
- [ ] Run backend setup (Python venv + pip install)
- [ ] Run frontend setup (npm install)
- [ ] Test Neo4j connection before starting
- [ ] Start backend and frontend services
