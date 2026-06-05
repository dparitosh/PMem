# Technical Audit - Detailed Remediation Guide

## CRITICAL FIX #1: Remove Console Logging

### Current State (Performance Issue)
```javascript
// GraphHEB_og_2.js has 100+ direct console.log calls
console.log(`Creating hierarchical data from ${nodes.length} nodes and ${links.length} links`);
console.log(`[Hierarchy] Processing link: ...`);
console.log(`Built hierarchy for root...`);
// ... causes 132+ second renders
```

### Step 1: Create Logger Utility
**File:** `src/utils/logger.ts`
```typescript
type LogLevel = 'debug' | 'info' | 'warn' | 'error';

class Logger {
  private level: LogLevel = process.env.REACT_APP_LOG_LEVEL as LogLevel || 'error';
  
  private levels = { debug: 0, info: 1, warn: 2, error: 3 };
  
  private shouldLog(level: LogLevel): boolean {
    return this.levels[level] >= this.levels[this.level];
  }

  debug(message: string, ...args: any[]) {
    if (this.shouldLog('debug') && process.env.NODE_ENV === 'development') {
      console.log(`[DEBUG] ${message}`, ...args);
    }
  }

  info(message: string, ...args: any[]) {
    if (this.shouldLog('info') && process.env.NODE_ENV === 'development') {
      console.info(`[INFO] ${message}`, ...args);
    }
  }

  warn(message: string, ...args: any[]) {
    if (this.shouldLog('warn')) {
      console.warn(`[WARN] ${message}`, ...args);
    }
  }

  error(message: string, error?: Error, ...args: any[]) {
    console.error(`[ERROR] ${message}`, error, ...args);
    // Send to error tracking service (Sentry, etc.)
  }
}

export default new Logger();
```

### Step 2: Update Components
**Before:**
```javascript
console.log(`Creating hierarchical data from ${nodes.length} nodes`);
```

**After:**
```javascript
import logger from '../utils/logger';
logger.debug(`Creating hierarchical data from ${nodes.length} nodes`);
```

### Step 3: Update .env Files
```env
# .env.development
REACT_APP_LOG_LEVEL=debug

# .env.production
REACT_APP_LOG_LEVEL=error
```

### Step 4: Build Configuration
**package.json:**
```json
{
  "scripts": {
    "build": "NODE_ENV=production react-scripts build",
    "build:no-debug": "NODE_ENV=production GENERATE_SOURCEMAP=false react-scripts build"
  },
  "devDependencies": {
    "babel-plugin-transform-remove-console": "^6.9.4"
  }
}
```

**.babelrc (optional - for complete console removal):**
```json
{
  "env": {
    "production": {
      "plugins": [
        ["transform-remove-console", { "exclude": ["error", "warn"] }]
      ]
    }
  }
}
```

---

## CRITICAL FIX #2: XSS Vulnerability in Chat

### Step 1: Install Sanitization Libraries
```bash
npm install dompurify sanitize-html react-markdown
npm install --save-dev @types/dompurify
```

### Step 2: Create Safe Markdown Parser
**File:** `src/utils/markdownParser.ts`
```typescript
import DOMPurify from 'dompurify';
import sanitizeHtml from 'sanitize-html';

// Whitelist of allowed HTML tags and attributes
const ALLOWED_TAGS = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'p', 'br', 'strong', 'em', 'u', 'code',
  'ul', 'ol', 'li', 'blockquote', 'hr',
  'a', 'span', 'div', 'table', 'tr', 'td', 'th'
];

const ALLOWED_ATTRIBUTES = {
  'a': ['href', 'title', 'target'],
  'span': ['class'],
  'div': ['class'],
};

export function safeParseMarkdown(text: string): string {
  if (!text || typeof text !== 'string') return '';

  // First pass: Basic markdown to HTML (your existing parseMarkdown)
  let html = text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/^- (.*$)/gim, '<li>$1</li>')
    .replace(/(<li[^>]*>.*<\/li>)/gs, (match) => {
      return '<ul>' + match + '</ul>';
    });

  // Second pass: Sanitize to prevent XSS
  const cleaned = sanitizeHtml(html, {
    allowedTags: ALLOWED_TAGS,
    allowedAttributes: ALLOWED_ATTRIBUTES,
    disallowedTagsMode: 'discard',
  });

  // Third pass: DOMPurify double-check
  return DOMPurify.sanitize(cleaned, { ALLOWED_TAGS, ALLOWED_ATTR: [] });
}

// Test for injection attacks
export function testForInjection(text: string): boolean {
  const dangerousPatterns = [
    /<script/i,
    /javascript:/i,
    /on\w+\s*=/i,
    /eval\(/i,
    /expression\(/i,
    /vbscript:/i,
    /data:text\/html/i,
  ];
  
  return dangerousPatterns.some(pattern => pattern.test(text));
}
```

### Step 3: Update Chatbot Component
**File:** `src/Components/Chatbot.js`
```javascript
import { safeParseMarkdown, testForInjection } from '../utils/markdownParser';

const Chatbot = ({ setChatResults }) => {
  const [chatMessages, setChatMessages] = useState([]);
  const [error, setError] = useState(null);

  // Replace parseMarkdown function call
  const handleAsk = async (queryText = null) => {
    const messageText = queryText || question.trim();
    
    // Validate input before sending
    if (testForInjection(messageText)) {
      setError('Message contains invalid content');
      return;
    }
    
    if (!messageText || messageText.length > 5000) return;

    // ... rest of implementation

    // Later: Use safe rendering
    setChatMessages(prev => prev.map(m =>
      m.id === assistantId 
        ? { ...m, text: accumulated, html: safeParseMarkdown(accumulated) }
        : m
    ));
  };

  return (
    <div>
      {chatMessages.map(msg => (
        <div key={msg.id}>
          {msg.role === 'user' ? (
            <div>{msg.text}</div>
          ) : (
            // ✅ Safe HTML rendering with DOMPurify
            <div 
              dangerouslySetInnerHTML={{ 
                __html: safeParseMarkdown(msg.text) 
              }} 
            />
          )}
        </div>
      ))}
    </div>
  );
};
```

---

## CRITICAL FIX #3: Batch State Updates

### Before (5+ Renders)
```javascript
setGraphData(newGraphData);
setFilteredData(newFilteredData);
setSearchResults(results);
setAvailableLabels(labels);
setSelectedLabelFilter('ALL');
```

### After (1 Render with React 18 Batching)
```javascript
import { startTransition } from 'react';

startTransition(() => {
  setGraphData(newGraphData);
  setFilteredData(newFilteredData);
  setSearchResults(results);
  setAvailableLabels(labels);
  setSelectedLabelFilter('ALL');
});
```

### Alternative: Refactor to Single State
```javascript
// ✅ Consolidated state reduces complexity
const [graphState, setGraphState] = useState({
  data: { nodes: [], links: [] },
  filtered: { nodes: [], links: [] },
  search: {
    query: '',
    results: null,
    labels: [],
    selectedLabel: 'ALL'
  },
  ui: {
    loading: false,
    error: null,
    layout: 'force-directed'
  }
});

// Single update
setGraphState(prev => ({
  ...prev,
  data: newGraphData,
  filtered: newFilteredData,
  search: {
    ...prev.search,
    results,
    labels,
    selectedLabel: 'ALL'
  }
}));
```

---

## CRITICAL FIX #4: Memory Leak Cleanup

### Before (Memory Leak)
```javascript
React.useEffect(() => {
  const handler = (e) => { /* ... */ };
  window.addEventListener('dt-highlight-nodes', handler);
  // ❌ NO CLEANUP - listener remains forever
}, []);

React.useEffect(() => {
  setTimeout(() => setHighlightedNodeNames(new Set()), 15000);
  // ❌ Timer never cleared
}, []);
```

### After (Proper Cleanup)
```javascript
React.useEffect(() => {
  const handler = (e) => {
    const names = e.detail?.names;
    if (Array.isArray(names) && names.length > 0) {
      const nameSet = new Set(names.map(n => (n || '').toLowerCase()));
      setHighlightedNodeNames(nameSet);
    }
  };

  window.addEventListener('dt-highlight-nodes', handler);
  
  // ✅ CLEANUP FUNCTION
  return () => {
    window.removeEventListener('dt-highlight-nodes', handler);
  };
}, []);

// Timer cleanup
React.useEffect(() => {
  const timerId = setTimeout(() => {
    setHighlightedNodeNames(new Set());
  }, 15000);
  
  // ✅ CLEANUP FUNCTION
  return () => {
    clearTimeout(timerId);
  };
}, []);
```

### Systematic Search for Cleanup Issues
```bash
# Find useEffect without cleanup
grep -n "useEffect.*=>.*{$" src/Components/*.js | \
while read line; do
  file=$(echo "$line" | cut -d: -f1)
  linenum=$(echo "$line" | cut -d: -f2)
  
  # Check if return statement exists within next 20 lines
  tail -n +$linenum "$file" | head -20 | grep -q "return () =>"
  if [ $? -ne 0 ]; then
    echo "⚠️ Missing cleanup at $file:$linenum"
  fi
done
```

### Create Cleanup Hook
**File:** `src/hooks/useEffectWithCleanup.ts`
```typescript
import { useEffect, useRef } from 'react';

export function useEventListener(
  eventName: string,
  handler: (event: any) => void,
  element: Window | Document | HTMLElement = window,
  dependencies: any[] = []
) {
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    const isSupported = element && element.addEventListener;
    if (!isSupported) return;

    const eventListener = (event: any) => handlerRef.current(event);
    element.addEventListener(eventName, eventListener);

    // ✅ Automatic cleanup
    return () => {
      element.removeEventListener(eventName, eventListener);
    };
  }, [eventName, element, ...dependencies]);
}

// Usage
useEventListener('dt-highlight-nodes', (e) => {
  const names = e.detail?.names;
  if (Array.isArray(names)) {
    setHighlightedNodeNames(new Set(names));
  }
});
```

---

## CRITICAL FIX #5: Remove Hardcoded Credentials

### Step 1: Update config.js
```javascript
// ✅ NEW: config.js
const config = {
  // API Configuration
  apiUrl: process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000',
  apiTimeout: parseInt(process.env.REACT_APP_API_TIMEOUT || '30000'),
  
  // Neo4j Configuration
  neo4jUrl: process.env.REACT_APP_NEO4J_URL || 'bolt://localhost:7687',
  neo4jUser: process.env.REACT_APP_NEO4J_USER || 'neo4j',
  neo4jPassword: process.env.REACT_APP_NEO4J_PASSWORD || 'password', // Still bad!
  
  // Logging
  logLevel: process.env.REACT_APP_LOG_LEVEL || 'error',
  
  // Feature flags
  enableDebug: process.env.REACT_APP_DEBUG === 'true',
};

// Validation
if (process.env.NODE_ENV === 'production') {
  if (!process.env.REACT_APP_BACKEND_URL) {
    throw new Error('REACT_APP_BACKEND_URL not set in production');
  }
  if (!process.env.REACT_APP_NEO4J_PASSWORD) {
    throw new Error('REACT_APP_NEO4J_PASSWORD not set in production');
  }
}

export default config;
```

### Step 2: Create .env Files
**.env.local (Never commit)**
```env
REACT_APP_BACKEND_URL=http://localhost:8000
REACT_APP_NEO4J_URL=bolt://localhost:7687
REACT_APP_NEO4J_USER=neo4j
REACT_APP_NEO4J_PASSWORD=YOUR_SECURE_PASSWORD_HERE
REACT_APP_LOG_LEVEL=debug
REACT_APP_DEBUG=true
```

**.env.example (Commit this)**
```env
REACT_APP_BACKEND_URL=http://localhost:8000
REACT_APP_NEO4J_URL=bolt://localhost:7687
REACT_APP_NEO4J_USER=neo4j
# REACT_APP_NEO4J_PASSWORD is required but not tracked
REACT_APP_API_TIMEOUT=30000
REACT_APP_LOG_LEVEL=error
REACT_APP_DEBUG=false
```

### Step 3: Update .gitignore
```bash
# Environment variables
.env
.env.local
.env.*.local

# Never commit credentials
**/credentials.json
**/secrets.js
**/.credentials
```

### Step 4: Update GraphHEB_og.js
**Before:**
```javascript
const driver = neo4j.driver(
  'bolt://localhost:7687',
  neo4j.auth.basic('neo4j', 'password'),
);
```

**After:**
```javascript
import config from '../config';

const driver = neo4j.driver(
  config.neo4jUrl,
  neo4j.auth.basic(config.neo4jUser, config.neo4jPassword),
  { disableLosslessIntegers: true }
);
```

### Step 5: Rotate Credentials
```bash
# 1. Change Neo4j password
# Log into Neo4j browser or use cypher-shell
CALL dbms.changePassword('NEW_SECURE_PASSWORD');

# 2. Update environment variables
# Set REACT_APP_NEO4J_PASSWORD to new password

# 3. Update backend environment
# Set NEO4J_PASSWORD in backend .env

# 4. Audit git history
git log --all -p -- "*/GraphHEB_og.js" | grep -i password
# Assume compromised and rotate!
```

---

## HIGH FIX #1: Centralize API Configuration

### Create API Client Factory
**File:** `src/services/apiClient.ts`
```typescript
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import config from '../config';

class APIClient {
  private instance: AxiosInstance;
  private requestQueue: any[] = [];
  private isOnline = true;

  constructor() {
    this.instance = axios.create({
      baseURL: config.apiUrl,
      timeout: config.apiTimeout,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor for auth/logging
    this.instance.interceptors.request.use(
      (config) => {
        // Add auth token if available
        const token = localStorage.getItem('auth_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor for error handling
    this.instance.interceptors.response.use(
      (response) => response,
      async (error) => {
        // Handle 401 - redirect to login
        if (error.response?.status === 401) {
          localStorage.removeItem('auth_token');
          window.location.href = '/login';
        }
        
        // Handle network errors
        if (!error.response) {
          this.isOnline = false;
        }
        
        return Promise.reject(error);
      }
    );

    // Monitor online/offline status
    window.addEventListener('online', () => { this.isOnline = true; });
    window.addEventListener('offline', () => { this.isOnline = false; });
  }

  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.get<T>(url, config).then(r => r.data);
  }

  post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.post<T>(url, data, config).then(r => r.data);
  }

  put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.put<T>(url, data, config).then(r => r.data);
  }

  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.instance.delete<T>(url, config).then(r => r.data);
  }
}

export default new APIClient();
```

### Usage in Components
**Before:**
```javascript
axios.get("http://localhost:8000/graphvis").then(...)
axios.post('http://localhost:8000/graphfilter', { search: term })
```

**After:**
```javascript
import apiClient from '../services/apiClient';

apiClient.get('/graphvis').then(...)
apiClient.post('/graphfilter', { search: term })
```

---

## Testing Checklist

### Performance Testing
- [ ] Render time < 500ms for 1000 nodes
- [ ] Search response < 300ms
- [ ] Memory usage stable over 30 minutes
- [ ] No console warnings or errors

### Security Testing
- [ ] Test XSS payloads in chat: `<script>alert('xss')</script>`
- [ ] Test prompt injection: `"...ignore previous instructions..."`
- [ ] Verify credentials not in source code
- [ ] Check for hardcoded API URLs

### Accessibility Testing
- [ ] Navigate with Tab key only
- [ ] Screen reader announces all UI elements
- [ ] Color contrast ratio ≥ 4.5:1
- [ ] Focus visible on all interactive elements

---

## Deployment Checklist

- [ ] Run `npm run build`
- [ ] Verify no console logs in production bundle
- [ ] Check environment variables are set
- [ ] Run security audit: `npm audit`
- [ ] Performance Lighthouse score ≥ 90
- [ ] Test on real backend/Neo4j instances
- [ ] Database credentials rotated
- [ ] Error monitoring (Sentry) configured

