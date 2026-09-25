# API Configuration & Usage Guide

This guide explains how to use the centralized API configuration system for the Depo_onto frontend.

## Overview

The frontend now uses a **centralized, environment-driven API configuration** that makes it easy to:
- Switch between development, staging, and production environments
- Manage API endpoints without code changes
- Support multiple backend versions
- Debug API interactions easily

## Configuration Files

### 1. `.env.local` (Local Development)
Located: `frontend/.env.local`
- **Purpose**: Development environment configuration (do NOT commit to git)
- **Usage**: Automatically loaded by Vite at build time
- **Variables**: 50+ API endpoint mappings

### 2. `.env.example` (Template/Documentation)
Located: `frontend/.env.example`
- **Purpose**: Template showing all available configuration options
- **Usage**: Reference and starting point for new environments
- **Status**: Safe to commit (no sensitive data)

### 3. `src/config.js` (Runtime Configuration)
Located: `frontend/src/config.js`
- **Purpose**: Centralized configuration loader at runtime
- **Features**:
  - Reads from `import.meta.env.VITE_*` variables
  - Organizes endpoints by category
  - Provides utility functions (`buildUrl()`, `replaceParams()`)
  - Logs configuration in debug mode

### 4. `src/services/apiClient.js` (API Client)
Located: `frontend/src/services/apiClient.js`
- **Purpose**: Axios wrapper with all API methods pre-configured
- **Features**:
  - Request/response interceptors
  - Automatic debug logging
  - Error handling
  - Organized by API category

## Environment Variables Reference

### Base Configuration
```env
VITE_API_GATEWAY_URL=
# For direct local service mode, leave the gateway empty.
# Services use ports 8010 through 8019; port 8000 is not part of the standard topology.
```

### API Endpoints (Full List in .env.example)
All endpoints are configurable via environment variables:

**Ontology APIs:**
```env
REACT_APP_API_ONTOLOGY_UPLOAD=/api/v1/ontology/upload
REACT_APP_API_ONTOLOGY_REGISTERED=/api/v1/ontology/registered
REACT_APP_API_ONTOLOGY_MAP_ENTITY=/api/v1/ontology/{ontology}/map-entity
```

**Import APIs:**
```env
REACT_APP_API_IMPORT_UPLOAD=/api/v1/import/upload
REACT_APP_API_IMPORT_STATUS=/api/v1/import/status/{task_id}
REACT_APP_API_IMPORT_PREVIEW=/api/v1/import/preview/{task_id}
```

**Graph APIs:**
```env
REACT_APP_API_GRAPHVIS=/graphvis
REACT_APP_API_GRAPHFILTER=/graphfilter
REACT_APP_API_GRAPHTRAVERSE=/graphtraverse
```

See `frontend/.env.example` for complete list of 50+ endpoint variables.

## Usage Guide

### 1. Basic Usage - Import from Config

```javascript
// Get API endpoints
import { API, config } from '../config';

// Access organized endpoints
const ontologyUploadUrl = API.ontology.upload;  // '/api/v1/ontology/upload'
const importStatusUrl = API.import.status;       // '/api/v1/import/status/{task_id}'
const backendUrl = config.backendUrl;            // direct mode uses service URLs on 8010-8019
```

### 2. Using the API Client (Recommended)

```javascript
import { API_METHODS } from '../services/apiClient';

// Example: List registered ontologies
const response = await API_METHODS.ontology.listRegistered();
console.log(response.data.ontologies);

// Example: Upload a file
const file = new File(['content'], 'schema.xsd');
const metadata = {
  ontology_name: 'ap239',
  prefix: 'ap',
  generation_type: 'auto'
};
const response = await API_METHODS.ontology.upload(file, metadata);
console.log(response.data.message);

// Example: Import data
const importFile = new File(['data'], 'parts.csv');
const response = await API_METHODS.import.upload(importFile, { ontology_id: 'ap239' });
console.log(`Task ID: ${response.data.task_id}`);

// Example: Check import status
const status = await API_METHODS.import.getStatus('task-123');
console.log(`Progress: ${status.data.progress}%`);
```

### 3. Using Helper Functions

```javascript
import { buildUrl, replaceParams, API } from '../config';

// Build full URL from endpoint
const fullUrl = buildUrl(API.ontology.upload);
// Result: a configured ontology service URL (normally port 8011)

// Replace path parameters
const taskStatusUrl = replaceParams(API.import.status, { task_id: 'abc-123' });
// Result: '/api/v1/import/status/abc-123'

// Combine them
const fullStatusUrl = buildUrl(taskStatusUrl);
// Result: a configured ingestion service URL (normally port 8014)
```

### 4. Custom Axios Requests

```javascript
import { apiClient } from '../services/apiClient';

// If you need to make custom requests not covered by API_METHODS
const response = await apiClient.post('/api/v1/custom/endpoint', {
  data: 'value'
});

// apiClient automatically includes:
// - Base URL from VITE_API_GATEWAY_URL or direct service routing
// - Request timeout
// - Debug logging
// - Error handling
```

## Updating Frontend Components

### Before (Hardcoded URLs)
```javascript
const response = await axios.get('http://127.0.0.1:8014/api/v1/ontology/registered');
```

### After (Using API Client)
```javascript
import { API_METHODS } from '../services/apiClient';

const response = await API_METHODS.ontology.listRegistered();
```

**Benefits:**
- ✅ No hardcoded URLs
- ✅ Automatic base URL from environment
- ✅ Built-in error handling
- ✅ Debug logging in development
- ✅ Easy to change endpoints by editing .env
- ✅ Request/response interceptors work automatically

## Environment Switching

### Development (localhost)
`frontend/.env.local`:
```env
VITE_API_GATEWAY_URL=
# Direct local mode uses 127.0.0.1 service ports 8010-8019.
```

### Staging
`frontend/.env.local` for gateway mode:
```env
VITE_API_GATEWAY_URL=https://staging-api.example.com
```

### Production
`frontend/.env.local` for production:
```env
VITE_API_GATEWAY_URL=https://api.example.com
```

**Build with specific environment:**
```bash
# Direct local development
npm run dev -- --host 127.0.0.1 --port 3000

# Staging or production: set VITE_API_GATEWAY_URL in .env.local, then build
npm run build
```

## API Categories

### 1. Health & Status
- `healthAPI.check()` - Health check endpoint
- `healthAPI.ready()` - Readiness check

### 2. Graph Visualization
- `graphAPI.getGraph()` - Get entire graph
- `graphAPI.filterGraph(term)` - Search graph
- `graphAPI.filterMulti(filters)` - Multi-criteria filter
- `graphAPI.traverse(nodeId)` - Traverse from node

### 3. Schema Management
- `schemaAPI.getSchema()` - Get database schema
- `schemaAPI.getAP242RotorPmi()` - Get AP242 data
- `schemaAPI.searchAP242(query)` - Search AP242

### 4. Chat
- `chatAPI.sendMessage(msg)` - Send chat message
- `chatAPI.streamChat(msg)` - Stream response

### 5. Ontology Management
- `ontologyAPI.upload(file, metadata)` - Upload ontology
- `ontologyAPI.listRegistered()` - List ontologies
- `ontologyAPI.get(id)` - Get specific ontology
- `ontologyAPI.getDataDictionary(id)` - Get data dictionary
- `ontologyAPI.getMappings(id, type)` - Get mappings
- `ontologyAPI.mapEntity(id, data)` - Map entity

### 6. Data Import
- `importAPI.upload(file, metadata)` - Upload data
- `importAPI.getStatus(taskId)` - Get status
- `importAPI.getPreview(taskId)` - Get preview
- `importAPI.commit(taskId)` - Commit import
- `importAPI.cancel(taskId)` - Cancel import
- `importAPI.getOWL(taskId)` - Get OWL output
- `importAPI.getFormats()` - Get formats

### 7. Documents
- `documentAPI.getSupportedFormats()` - Get formats
- `documentAPI.upload(files)` - Upload files
- `documentAPI.uploadSingle(file)` - Upload one file
- `documentAPI.checkHealth()` - Health check

## Debug Mode

Enable debug logging using the supported Vite variables in `frontend/.env.local`:
```env
REACT_APP_DEBUG=true
REACT_APP_LOG_LEVEL=debug
```

This enables:
- Console logs for all API requests
- Console logs for all API responses
- Configuration dump on startup
- Error details in console

## Error Handling

The API client includes automatic error handling for common cases:

```javascript
try {
  const response = await API_METHODS.ontology.listRegistered();
} catch (error) {
  const status = error.response?.status;
  const message = error.response?.data?.detail || error.message;
  
  if (status === 404) {
    console.log('Resource not found');
  } else if (status === 500) {
    console.log('Server error');
  } else {
    console.log(`Error: ${message}`);
  }
}
```

## Testing

When testing frontend components, mock the API client:

```javascript
import { API_METHODS } from '../services/apiClient';

jest.mock('../services/apiClient', () => ({
  API_METHODS: {
    ontology: {
      listRegistered: jest.fn().mockResolvedValue({
        data: { ontologies: [...] }
      })
    }
  }
}));
```

## Troubleshooting

### 1. API calls return 404
**Check:**
- `VITE_API_GATEWAY_URL` is empty for direct local mode or points to the gateway
- Endpoint path in `.env` is correct
- Backend service is running

### 2. CORS errors
**Check:**
- Backend allows CORS from frontend origin
- Gateway URLs include the correct protocol (http/https)

### 3. API returns 400/422 errors
**Check:**
- Request payload matches backend expectations
- Form data is properly formatted (use API_METHODS which handles this)
- Required fields are included

### 4. Debug logs not showing
**Check:**
- `REACT_APP_DEBUG=true` in `.env`
- Browser console is open (F12)
- Not running production build (npm run build)

## Summary

The centralized API configuration system provides:
1. **Single source of truth** for all backend endpoints
2. **Easy environment switching** via .env files
3. **Organized API methods** by category
4. **Automatic request/response handling**
5. **Built-in debugging** for development
6. **Type-safe endpoint management**

This makes the codebase more maintainable, scalable, and easier to work with across multiple environments.
