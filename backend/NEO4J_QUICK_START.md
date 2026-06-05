# Quick Reference - Neo4j Centralized Configuration

## 🚀 Quick Start

### For Neo4j Aura

```env
# backend/.env
NEO4J_URI=neo4j+s://YOUR_INSTANCE_ID.databases.neo4j.io
NEO4J_USER=YOUR_USERNAME
NEO4J_PASS=YOUR_PASSWORD
NEO4J_DATABASE=YOUR_DATABASE_NAME
```

### For On-Premises with TLS

```env
# backend/.env
NEO4J_URI=bolt+s://your-server.com:7687
NEO4J_USER=neo4j
NEO4J_PASS=your_password
NEO4J_DATABASE=neo4j
```

### For On-Premises without TLS

```env
# backend/.env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=your_password
NEO4J_DATABASE=neo4j
NEO4J_ENCRYPTED=false
NEO4J_TRUST_SYSTEM_CA=false
```

## 📋 Environment Variables

| Variable | Required | Default | Example |
|----------|----------|---------|---------|
| NEO4J_URI | ✅ Yes | - | neo4j+s://instance.databases.neo4j.io |
| NEO4J_USER | ✅ Yes | - | username |
| NEO4J_PASS | ✅ Yes | - | password |
| NEO4J_DATABASE | ❌ No | neo4j | neo4j |
| NEO4J_MAX_POOL_SIZE | ❌ No | 50 | 100 |
| NEO4J_QUERY_TIMEOUT | ❌ No | 30 | 60 |
| NEO4J_ENCRYPTED | ❌ No | true | false |
| NEO4J_TRUST_SYSTEM_CA | ❌ No | true | false |

## 💻 Code Examples

### Connect to Database

```python
from backend.core.db_config import get_driver

driver = get_driver()
with driver.session() as session:
    result = session.run("MATCH (n) RETURN count(n) as count")
    print(result.single())
```

### Use Context Manager

```python
from backend.core.db_config import Neo4jConnection

with Neo4jConnection() as session:
    result = session.run("MATCH (n) RETURN count(n)")
    print(result.single())
```

### Get Configuration

```python
from backend.core.db_config import get_config

config = get_config()
print(f"URI: {config.uri}")
print(f"Database: {config.database}")
print(f"Deployment: {config.deployment_type.value}")
```

## 🔍 Deployment Detection

| URI Scheme | Deployment Type | Encryption | Use Case |
|-----------|-----------------|-----------|----------|
| neo4j+s:// | AURA | Automatic TLS | Neo4j Aura (cloud) |
| bolt+s:// | ENTERPRISE | TLS | On-premises Enterprise |
| bolt:// | ON_PREMISES | None | On-premises Community |

## ✅ Verification

Test configuration:
```bash
cd backend
python -m core.db_config
```

Should output:
```
✅ Configuration loaded
✅ Driver created successfully
✅ Connection test successful
✅ All checks passed!
```

## 🔒 Configuration Examples by Scenario

### Scenario 1: Development (Local)
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=password123
NEO4J_DATABASE=neo4j
NEO4J_ENCRYPTED=false
NEO4J_MAX_POOL_SIZE=25
NEO4J_QUERY_TIMEOUT=30
```

### Scenario 2: Staging (On-Premises)
```env
NEO4J_URI=bolt+s://staging.company.com:7687
NEO4J_USER=neo4j
NEO4J_PASS=secure_password
NEO4J_DATABASE=neo4j
NEO4J_ENCRYPTED=true
NEO4J_MAX_POOL_SIZE=50
NEO4J_QUERY_TIMEOUT=60
```

### Scenario 3: Production (Aura)
```env
NEO4J_URI=neo4j+s://09a689b3.databases.neo4j.io
NEO4J_USER=09a689b3
NEO4J_PASS=secure_password
NEO4J_DATABASE=09a689b3
NEO4J_ENCRYPTED=true
NEO4J_TRUST_SYSTEM_CA=true
NEO4J_MAX_POOL_SIZE=100
NEO4J_QUERY_TIMEOUT=30
```

### Scenario 4: Production (Enterprise with Self-Signed Certs)
```env
NEO4J_URI=bolt+s://prod.company.com:7687
NEO4J_USER=neo4j
NEO4J_PASS=secure_password
NEO4J_DATABASE=neo4j
NEO4J_ENCRYPTED=true
NEO4J_CUSTOM_CA_PATH=/etc/ssl/certs/company-ca.pem
NEO4J_TRUST_SYSTEM_CA=false
NEO4J_MAX_POOL_SIZE=150
NEO4J_QUERY_TIMEOUT=60
```

## 🐛 Troubleshooting

| Error | Check |
|-------|-------|
| Missing NEO4J_URI | Set in backend/.env |
| Connection timeout | URI is correct, network accessible |
| Authentication failed | Username/password correct |
| AuraDB paused | Resume in console.neo4j.io |
| SSL error | NEO4J_ENCRYPTED=true, certificates valid |

## 📚 Files Updated

- ✅ `backend/core/db_config.py` - New centralized config module
- ✅ `backend/.env` - Enhanced with config options
- ✅ `backend/core/graph.py` - Uses centralized config
- ✅ `backend/Services/graph_embeddings.py` - Uses get_driver()
- ✅ `backend/Services/neo4j_schema_cleaner.py` - Uses centralized config

## 🔗 Related Files

- See `NEO4J_CENTRALIZED_CONFIG.md` for detailed documentation
- See `backend/core/db_config.py` for implementation details
- See `.env` for configuration templates

## 📞 Support

For issues:
1. Check `.env` configuration
2. Run `python -m core.db_config` to verify
3. Review logs in `backend/logs/`
4. Refer to `NEO4J_CENTRALIZED_CONFIG.md` for detailed docs

---
**Status**: ✅ All Neo4j connections now use centralized configuration  
**Last Updated**: 2026-05-28
