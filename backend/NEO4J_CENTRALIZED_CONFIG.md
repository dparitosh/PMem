# Neo4j Centralized Configuration Guide

## Overview

This guide explains the centralized Neo4j database configuration system that replaces scattered driver instances throughout the codebase.

**Status**: ✅ All Neo4j connections now use centralized configuration through `backend/core/db_config.py`

## Key Features

✅ **Single Configuration Point** - All settings in `.env` file  
✅ **Automatic Fallback** - Detects Aura vs on-premises deployments  
✅ **Connection Pooling** - Optimized for performance  
✅ **Environment Variable Aliases** - Supports multiple naming conventions  
✅ **Graceful Degradation** - Works with legacy code patterns  
✅ **SSL/TLS Support** - Configurable encryption  

## Architecture

```
backend/.env (Configuration)
    ↓
backend/core/db_config.py (Centralized Management)
    ├── Neo4jConfig (Data class)
    ├── Neo4jDriverPool (Singleton)
    ├── get_driver() (Convenience function)
    └── Neo4jConnection (Context manager)
    ↓
All backend modules
    ├── backend/core/graph.py
    ├── backend/Services/graph_embeddings.py
    ├── backend/Services/neo4j_schema_cleaner.py
    └── Other services...
```

## Configuration (.env)

### Basic Setup (Aura)

```env
# For Neo4j Aura
NEO4J_URI=neo4j+s://YOUR_INSTANCE_ID.databases.neo4j.io
NEO4J_USER=YOUR_USERNAME
NEO4J_PASS=YOUR_PASSWORD
NEO4J_DATABASE=YOUR_DATABASE_NAME
```

### Basic Setup (On-Premises with TLS)

```env
# For on-premises Enterprise with TLS
NEO4J_URI=bolt+s://your-server.com:7687
NEO4J_USER=neo4j
NEO4J_PASS=your_password
NEO4J_DATABASE=neo4j
```

### Basic Setup (On-Premises without TLS)

```env
# For on-premises Community Edition (no TLS)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=your_password
NEO4J_DATABASE=neo4j
NEO4J_ENCRYPTED=false
NEO4J_TRUST_SYSTEM_CA=false
```

### Advanced Configuration

```env
# ========== REQUIRED ==========
NEO4J_URI=neo4j+s://...              # Connection URI
NEO4J_USER=username                   # Username
NEO4J_PASS=password                   # Password
NEO4J_DATABASE=database_name          # Database name (default: neo4j)

# ========== CONNECTION POOL ==========
NEO4J_MAX_POOL_SIZE=50               # Connection pool size (default: 50)
NEO4J_CONNECTION_ACQUISITION_TIMEOUT=60  # Timeout in seconds (default: 60)
NEO4J_CONNECTION_TIMEOUT=30          # Socket timeout (default: 30)
NEO4J_SOCKET_KEEP_ALIVE=true         # Keep-alive (default: true)
NEO4J_SOCKET_CONNECTION_TIMEOUT=15   # Socket timeout in seconds (default: 15)

# ========== QUERY SETTINGS ==========
NEO4J_QUERY_TIMEOUT=30               # Query timeout in seconds (default: 30)

# ========== SSL/TLS ==========
NEO4J_ENCRYPTED=true                 # Enable TLS (default: true)
NEO4J_TRUST_SYSTEM_CA=true          # Trust system CA (default: true)
NEO4J_CUSTOM_CA_PATH=/path/to/ca-cert.pem  # Optional: custom CA for self-signed certs
```

### Environment Variable Aliases

The system supports multiple naming conventions for compatibility:

| Primary | Aliases |
|---------|---------|
| `NEO4J_URI` | `NEO4J_URL`, `Neo4j_url` |
| `NEO4J_USER` | `NEO4J_USERNAME`, `Neo4j_user` |
| `NEO4J_PASS` | `NEO4J_PASSWORD`, `Neo4j_password` |
| `NEO4J_DATABASE` | `Neo4j_database` |

## Usage Examples

### 1. Using the Driver Directly

```python
from backend.core.db_config import get_driver

# Get the singleton driver
driver = get_driver()

# Use with session
with driver.session(database="neo4j") as session:
    result = session.run("MATCH (n) RETURN count(n) as count")
    print(result.single())
```

### 2. Using Context Manager (Recommended)

```python
from backend.core.db_config import Neo4jConnection

# Automatically handles session lifecycle
with Neo4jConnection() as session:
    result = session.run("MATCH (n) RETURN count(n) as count")
    print(result.single())
```

### 3. Getting Configuration Info

```python
from backend.core.db_config import get_config, get_connection_info

# Get configuration object
config = get_config()
print(f"Connected to: {config.uri}")
print(f"Deployment: {config.deployment_type.value}")  # aura, on_premises, or enterprise

# Get connection info for debugging
info = get_connection_info()
print(info)
# Output: {
#   'uri': 'neo4j+s://...',
#   'username': '...',
#   'password': '***REDACTED***',
#   'database': 'neo4j',
#   'deployment_type': 'aura',
#   'connected': True
# }
```

### 4. Resetting Configuration (Testing)

```python
from backend.core.db_config import reset_driver

# For testing - resets driver and clears cache
reset_driver()
```

## Deployment Scenarios

### Scenario 1: Neo4j Aura

**Use Case**: Cloud-hosted managed database

```env
NEO4J_URI=neo4j+s://09a689b3.databases.neo4j.io
NEO4J_USER=09a689b3
NEO4J_PASS=YOUR_SECURE_PASSWORD
NEO4J_DATABASE=09a689b3
NEO4J_ENCRYPTED=true
NEO4J_TRUST_SYSTEM_CA=true
```

**Characteristics**:
- Uses `neo4j+s://` scheme with automatic TLS
- Managed SSL certificates
- Built-in connection pooling
- High availability

### Scenario 2: On-Premises Enterprise (with TLS)

**Use Case**: Self-hosted Enterprise Edition with SSL

```env
NEO4J_URI=bolt+s://production.company.com:7687
NEO4J_USER=neo4j
NEO4J_PASS=YOUR_SECURE_PASSWORD
NEO4J_DATABASE=neo4j
NEO4J_ENCRYPTED=true
NEO4J_TRUST_SYSTEM_CA=true
# Optional: For self-signed certificates
# NEO4J_CUSTOM_CA_PATH=/etc/ssl/certs/company-ca.pem
```

**Characteristics**:
- Uses `bolt+s://` scheme with TLS
- Full control over database
- Custom SSL certificates supported
- Manual backup/recovery

### Scenario 3: On-Premises Community (no TLS)

**Use Case**: Development/testing with Community Edition

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=your_password
NEO4J_DATABASE=neo4j
NEO4J_ENCRYPTED=false
NEO4J_TRUST_SYSTEM_CA=false
```

**Characteristics**:
- Uses `bolt://` scheme (no TLS)
- Typically localhost for development
- No SSL/encryption
- Suitable for local development only

## Module Integration

### Updated Modules

The following modules now use centralized configuration:

1. **backend/core/graph.py**
   - Uses `Neo4jConfig` and lazy initialization
   - Backward compatible with legacy code
   - Automatic fallback to legacy if centralized config unavailable

2. **backend/Services/graph_embeddings.py**
   - Uses `get_driver()` for connection pooling
   - Supports standalone mode for testing
   - Imports configuration automatically

3. **backend/Services/neo4j_schema_cleaner.py**
   - Reads from centralized config in `__init__`
   - Falls back to env vars if needed
   - No more hardcoded credentials

### Backward Compatibility

Modules continue to work with legacy patterns:
- Direct environment variable reading still supported
- Fallback to legacy config if centralized unavailable
- Gradual migration path for other scripts

## Troubleshooting

### Connection Fails

```python
from backend.core.db_config import get_connection_info, reset_driver

# Check current configuration
info = get_connection_info()
print(info)

# If error: Reset and retry (may trigger reconnection)
reset_driver()
```

### AuraDB Paused

```
Error: Neo4j connection unavailable (retry in 45s). 
AuraDB may be paused — check console.neo4j.io
```

**Solution**:
- Check Neo4j Aura console
- Resume database instance
- Wait 60 seconds for cooldown
- Retry operation

### Self-Signed Certificates

For on-premises with self-signed certificates:

```bash
# 1. Get the certificate
openssl s_client -connect your-server.com:7687 -showcerts

# 2. Add to .env
NEO4J_CUSTOM_CA_PATH=/path/to/ca-cert.pem
NEO4J_ENCRYPTED=true
NEO4J_TRUST_SYSTEM_CA=false
```

### Configuration Not Loading

```python
# Check if env file exists
from pathlib import Path
env_path = Path("backend/.env")
print(f"Env file exists: {env_path.exists()}")

# Check if variable is set
import os
print(f"NEO4J_URI: {os.getenv('NEO4J_URI')}")

# Check configuration directly
from backend.core.db_config import get_config
try:
    config = get_config()
    print(f"Config loaded: {config}")
except Exception as e:
    print(f"Error: {e}")
```

## Testing

### Test Connection

```bash
cd backend
python -m core.db_config
```

Expected output:
```
🔍 Checking Neo4j Configuration...

✅ Configuration loaded:
   URI: neo4j+s://...
   User: ...
   Database: ...
   Deployment: aura

🔌 Testing connection...

✅ Driver created successfully
✅ Connection test successful: {'test': 1}

✅ All checks passed!
```

### Unit Test Example

```python
import pytest
from backend.core.db_config import reset_driver, get_connection_info

@pytest.fixture(autouse=True)
def reset_neo4j():
    """Reset driver before and after each test"""
    reset_driver()
    yield
    reset_driver()

def test_neo4j_connection():
    """Test Neo4j connection"""
    from backend.core.db_config import get_driver
    driver = get_driver()
    assert driver is not None
    
    info = get_connection_info()
    assert info.get('connected') or 'error' not in info
```

## Migration Path for Legacy Scripts

If you have scripts outside `backend/` that create their own drivers:

### Before (Legacy)

```python
from neo4j import GraphDatabase
import os

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(uri, auth=(user, password))
```

### After (Centralized)

```python
import sys
sys.path.insert(0, "path/to/backend")

from backend.core.db_config import get_driver, Neo4jConnection

# Option 1: Get driver directly
driver = get_driver()

# Option 2: Use context manager (recommended)
with Neo4jConnection() as session:
    result = session.run("MATCH (n) RETURN count(n)")
```

## Performance Tuning

### Connection Pool Sizing

Adjust based on your workload:

```env
# Light workload (development)
NEO4J_MAX_POOL_SIZE=25

# Medium workload (small production)
NEO4J_MAX_POOL_SIZE=50

# Heavy workload (large production)
NEO4J_MAX_POOL_SIZE=100
```

### Query Timeouts

Adjust based on expected query duration:

```env
# Short queries (default)
NEO4J_QUERY_TIMEOUT=30

# Longer queries (analytics, large graphs)
NEO4J_QUERY_TIMEOUT=120
```

### Connection Timeouts

For slow networks:

```env
# Faster network
NEO4J_CONNECTION_TIMEOUT=15

# Slow network
NEO4J_CONNECTION_TIMEOUT=60

# Very slow network
NEO4J_CONNECTION_TIMEOUT=120
```

## Security Best Practices

1. **Never Commit .env**
   ```bash
   echo "backend/.env" >> .gitignore
   ```

2. **Use Strong Passwords**
   - Minimum 12 characters
   - Mix of uppercase, lowercase, numbers, special chars
   - Rotate periodically

3. **Restrict .env Permissions**
   ```bash
   chmod 600 backend/.env
   ```

4. **Use Environment Variables in Production**
   ```bash
   # Don't use .env file in production
   export NEO4J_URI="neo4j+s://..."
   export NEO4J_USER="username"
   export NEO4J_PASS="password"
   python main.py
   ```

5. **SSL/TLS in Production**
   ```env
   NEO4J_ENCRYPTED=true
   NEO4J_TRUST_SYSTEM_CA=true
   ```

## Monitoring & Logging

Connection information is logged at module startup:

```
INFO - Neo4j configuration loaded: Neo4jConfig(uri=neo4j+s://..., username=..., database=neo4j, deployment=aura)
INFO - Neo4j driver created successfully (Deployment: aura)
```

Check logs for:
- Configuration loading status
- Driver creation success/failure
- Connection timeouts or failures

## Support & Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("backend.core.db_config")
logger.setLevel(logging.DEBUG)
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Missing NEO4J_URI" | Env var not set | Set in .env or environment |
| Connection timeout | Network issue | Check URI, firewall, AuraDB status |
| "AuraDB may be paused" | Database paused | Resume in Aura console |
| SSL verification error | Certificate issue | Check NEO4J_CUSTOM_CA_PATH |
| Connection pool exhausted | Too many queries | Increase NEO4J_MAX_POOL_SIZE |

## Summary

✅ **Before**: Multiple scattered driver instances, inconsistent configuration, hardcoded credentials  
✅ **After**: Single configuration point, automatic pooling, secure credential handling, easy switching between deployments

The centralized configuration system provides a robust foundation for managing Neo4j connections across the entire application.
