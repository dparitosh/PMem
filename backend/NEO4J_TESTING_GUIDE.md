# Neo4j Configuration - Testing & Verification Guide

## ✅ Verification Steps

### Step 1: Check Configuration File

```bash
# Navigate to backend directory
cd backend

# Verify .env file exists
ls -la .env

# View current configuration (hide password)
grep "NEO4J_" .env | grep -v "PASS\|PASSWORD"
```

Expected output:
```
NEO4J_URI=neo4j+s://...
NEO4J_USER=...
NEO4J_DATABASE=...
```

### Step 2: Test Configuration Module

```bash
# Run configuration test
python -m core.db_config
```

Expected output:
```
🔍 Checking Neo4j Configuration...

✅ Configuration loaded:
   URI: neo4j+s://09a689b3.databases.neo4j.io
   User: 09a689b3
   Database: 09a689b3
   Deployment: aura

🔌 Testing connection...

✅ Driver created successfully
✅ Connection test successful: {'test': 1}

✅ All checks passed!
```

### Step 3: Test Python Import

```python
# Test configuration import
python3 << 'EOF'
from backend.core.db_config import get_config, get_driver, get_connection_info

# 1. Get configuration
config = get_config()
print(f"✅ Config loaded: {config}")

# 2. Get driver
driver = get_driver()
print(f"✅ Driver created: {driver}")

# 3. Get connection info
info = get_connection_info()
print(f"✅ Connection info: {info}")

# 4. Test basic query
with driver.session() as session:
    result = session.run("RETURN 1 as test")
    record = result.single()
    print(f"✅ Query result: {dict(record)}")

print("\n✅ All tests passed!")
EOF
```

### Step 4: Test Context Manager

```python
python3 << 'EOF'
from backend.core.db_config import Neo4jConnection

with Neo4jConnection() as session:
    result = session.run("MATCH (n) RETURN count(n) as node_count")
    record = result.single()
    print(f"✅ Total nodes in graph: {record['node_count']}")

print("✅ Context manager test passed!")
EOF
```

### Step 5: Test Deployment Detection

```python
python3 << 'EOF'
from backend.core.db_config import get_config, Neo4jDeploymentType

config = get_config()
print(f"Deployment Type: {config.deployment_type.value}")

if config.deployment_type == Neo4jDeploymentType.AURA:
    print("✅ Detected: Neo4j Aura (Cloud)")
elif config.deployment_type == Neo4jDeploymentType.ENTERPRISE:
    print("✅ Detected: Neo4j Enterprise (On-Premises with TLS)")
elif config.deployment_type == Neo4jDeploymentType.ON_PREMISES:
    print("✅ Detected: Neo4j Community (On-Premises without TLS)")

print(f"✅ URI: {config.uri}")
print(f"✅ Encrypted: {config.encrypted}")
print(f"✅ Pool size: {config.max_connection_pool_size}")
EOF
```

### Step 6: Test Connection Pooling

```python
python3 << 'EOF'
import time
from backend.core.db_config import get_driver

driver = get_driver()

# Run multiple queries to test pooling
for i in range(5):
    with driver.session() as session:
        result = session.run(f"RETURN {i+1} as count")
        print(f"✅ Query {i+1}: {dict(result.single())}")
    time.sleep(0.1)

print("✅ Connection pooling test passed!")
EOF
```

## 🔄 Switching Deployments

### Switch from Aura to On-Premises

1. **Update .env**:
```bash
# From:
NEO4J_URI=neo4j+s://instance.databases.neo4j.io
NEO4J_ENCRYPTED=true

# To:
NEO4J_URI=bolt://localhost:7687
NEO4J_ENCRYPTED=false
NEO4J_TRUST_SYSTEM_CA=false
```

2. **Reset driver**:
```python
from backend.core.db_config import reset_driver
reset_driver()
```

3. **Test new connection**:
```bash
python -m core.db_config
```

### Switch from On-Premises to Aura

1. **Update .env**:
```bash
# From:
NEO4J_URI=bolt://localhost:7687
NEO4J_ENCRYPTED=false

# To:
NEO4J_URI=neo4j+s://instance.databases.neo4j.io
NEO4J_ENCRYPTED=true
NEO4J_TRUST_SYSTEM_CA=true
```

2. **Reset driver**:
```python
from backend.core.db_config import reset_driver
reset_driver()
```

3. **Test new connection**:
```bash
python -m core.db_config
```

## 🧪 Unit Test Examples

### Test 1: Configuration Loading

```python
import pytest
from backend.core.db_config import get_config, Neo4jConfigError

def test_config_loading():
    """Test configuration loads successfully"""
    config = get_config()
    assert config.uri is not None
    assert config.username is not None
    assert config.password is not None
    assert config.database is not None
    assert config.deployment_type is not None

def test_config_required_fields():
    """Test required fields are present"""
    config = get_config()
    assert len(config.uri) > 0
    assert len(config.username) > 0
    assert len(config.password) > 0
```

### Test 2: Driver Creation

```python
import pytest
from backend.core.db_config import get_driver, reset_driver

@pytest.fixture(autouse=True)
def reset_neo4j():
    """Reset driver before and after each test"""
    reset_driver()
    yield
    reset_driver()

def test_driver_creation():
    """Test driver is created successfully"""
    driver = get_driver()
    assert driver is not None

def test_driver_connection():
    """Test driver can execute query"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("RETURN 1 as test")
        record = result.single()
        assert record['test'] == 1
```

### Test 3: Deployment Detection

```python
from backend.core.db_config import get_config, Neo4jDeploymentType

def test_aura_detection():
    """Test Aura deployment detection"""
    # Note: This test assumes .env is set to Aura
    config = get_config()
    if config.uri.startswith("neo4j+s://"):
        assert config.deployment_type == Neo4jDeploymentType.AURA
        assert config.encrypted is True

def test_deployment_type_valid():
    """Test deployment type is valid"""
    config = get_config()
    valid_types = [
        Neo4jDeploymentType.AURA,
        Neo4jDeploymentType.ON_PREMISES,
        Neo4jDeploymentType.ENTERPRISE
    ]
    assert config.deployment_type in valid_types
```

### Test 4: Connection Manager

```python
from backend.core.db_config import Neo4jConnection

def test_connection_manager():
    """Test connection context manager"""
    with Neo4jConnection() as session:
        assert session is not None
        result = session.run("RETURN 1")
        assert result.single() is not None

def test_connection_manager_session_closed():
    """Test session is closed after context"""
    from backend.core.db_config import Neo4jConnection
    import pytest
    
    session = None
    with Neo4jConnection() as s:
        session = s
        assert not session.closed
    
    # Session should be closed after context
    with pytest.raises(Exception):
        session.run("RETURN 1")
```

## 📊 Performance Testing

### Connection Pooling Performance

```python
import time
from backend.core.db_config import get_driver

driver = get_driver()

# Test with pooled connections
start = time.time()
for _ in range(100):
    with driver.session() as session:
        session.run("RETURN 1")
pooled_time = time.time() - start

print(f"✅ 100 queries with pooling: {pooled_time:.2f}s")
print(f"✅ Average per query: {(pooled_time/100)*1000:.2f}ms")
```

### Query Timeout Testing

```python
from backend.core.db_config import get_driver

driver = get_driver()

# This should timeout if query takes > 30 seconds
with driver.session() as session:
    try:
        # Simulate slow query
        result = session.run("UNWIND range(0, 10000000) as x RETURN count(x)")
        result.consume()
        print("❌ Query completed unexpectedly")
    except Exception as e:
        print(f"✅ Query timed out as expected: {type(e).__name__}")
```

## 🔍 Debugging

### Enable Debug Logging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("backend.core.db_config")
logger.setLevel(logging.DEBUG)

# Now run operations to see debug output
from backend.core.db_config import get_driver
driver = get_driver()
```

### Check Configuration

```python
from backend.core.db_config import get_connection_info, get_config

# Get configuration
config = get_config()
print(f"URI: {config.uri}")
print(f"Database: {config.database}")
print(f"Deployment: {config.deployment_type.value}")
print(f"Encrypted: {config.encrypted}")
print(f"Pool Size: {config.max_connection_pool_size}")

# Get connection info
info = get_connection_info()
for key, value in info.items():
    print(f"{key}: {value}")
```

### Test Specific Scenarios

```python
# Test 1: Configuration not found
import os
os.environ.clear()
# This should raise Neo4jConfigError

# Test 2: Connection timeout
# Temporarily make database unavailable
# Should wait for cooldown

# Test 3: SSL verification
# Test with self-signed certificates
# Should work with NEO4J_CUSTOM_CA_PATH
```

## ✅ Checklist for Deployment

Before deploying to production:

- [ ] Verify `.env` has correct NEO4J_URI
- [ ] Verify NEO4J_USER and NEO4J_PASS are set
- [ ] Run `python -m core.db_config` - all checks pass
- [ ] Run unit tests - all pass
- [ ] Test connection with actual queries
- [ ] Verify deployment type detected correctly
- [ ] Check logs for any warnings
- [ ] Verify SSL/TLS settings
- [ ] Test with connection pool at expected size
- [ ] Load test with expected query rate
- [ ] Monitor for connection pool exhaustion
- [ ] Set up alerts for connection failures
- [ ] Document configuration for ops team

## 📋 Test Report Template

```
Neo4j Configuration Test Report
==============================

Date: YYYY-MM-DD
Environment: [development/staging/production]
Deployment Type: [aura/on-premises/enterprise]

✅ Configuration Loading: PASS
   - URI: _______________
   - Database: _______________
   - Deployment: _______________

✅ Driver Creation: PASS
   - Pool Size: _______________
   - Encrypted: _______________

✅ Connection Test: PASS
   - Query Time: _____ ms
   - Nodes in DB: _______________

✅ Deployment Detection: PASS
   - Detected Type: _______________
   - Expected Type: _______________

✅ Performance: PASS
   - 100 Queries Time: _____ s
   - Average Per Query: _____ ms

Issues: [None]

Signed: _______________
```

---

**Verification Status**: Ready for testing  
**Last Updated**: 2026-05-28
