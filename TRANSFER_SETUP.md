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

From the project root, use the checked-in launchers. They bind services for remote access and print the URL to use.

```bat
:: Terminal 1 - Backend
.\start_backend.bat

:: Terminal 2 - Frontend
.\start_frontend.bat
```

For a cloud VM, set `APP_HOST` to the public DNS name, public IP, or load-balancer hostname that browser users will open. Do not use `localhost` for remote users.

```bat
:: Public cloud VM IP
set APP_HOST=203.0.113.25
.\start_backend.bat
.\start_frontend.bat

:: DNS name behind a load balancer/reverse proxy
set APP_HOST=depo-demo.customer.com
.\start_backend.bat
.\start_frontend.bat
```

The backend binds to `0.0.0.0` by default. The frontend binds to `0.0.0.0` and sets `REACT_APP_BACKEND_URL` to `http://%APP_HOST%:8000` unless you pass an explicit backend URL.

```bat
:: Explicit values: port, backend URL, frontend bind host
.\start_frontend.bat 3000 http://203.0.113.25:8000 0.0.0.0
```

Open the frontend using the same host value:

```text
http://203.0.113.25:3000
```

If you manually open `http://localhost:3000`, the browser address bar will still show localhost. That only works on the VM itself, not from a customer machine.
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
---

## Cloud VM / Remote Access Checklist

Use this when installing on AWS, Azure, GCP, VMware, or any remote Windows VM.

1. Choose the user-facing host:
   - Private LAN VM: use the VM private IP, for example `192.168.1.50`.
   - Cloud VM direct access: use the VM public IP or public DNS.
   - Reverse proxy/load balancer: use the DNS name, for example `depo-demo.customer.com`.

2. Set runtime host before starting both services:

```bat
set APP_HOST=<public-ip-or-dns>
.\start_backend.bat
.\start_frontend.bat
```

3. Open firewall / security-group inbound rules:
   - TCP `3000` for the React UI, if serving the dev UI directly.
   - TCP `8000` for the FastAPI backend, if the browser calls the backend directly.
   - TCP `7687` only if Neo4j is remote and explicitly required; do not expose Neo4j publicly unless the customer security team approves it.
   - TCP `11434` only if Ollama is remote and explicitly required; prefer keeping Ollama private to the VM/VNet.

4. Configure CORS for the frontend origin in `backend/.env`:

```env
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
ALLOWED_ORIGINS=http://<public-ip-or-dns>:3000
```

5. Configure the frontend backend URL in `frontend/.env` when not using the launcher:

```env
HOST=0.0.0.0
REACT_APP_BACKEND_URL=http://<public-ip-or-dns>:8000
```

6. Validate from another machine, not from inside the VM:

```text
http://<public-ip-or-dns>:3000
http://<public-ip-or-dns>:8000/health
http://<public-ip-or-dns>:8000/docs
```

For production behind HTTPS, put Nginx/IIS/Application Gateway in front and expose only `443`. In that case set `APP_HOST`/`REACT_APP_BACKEND_URL` to the HTTPS DNS URL, and update `ALLOWED_ORIGINS` to the HTTPS frontend origin.
