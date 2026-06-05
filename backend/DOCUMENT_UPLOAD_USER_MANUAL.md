# Document Upload API — User Manual

## Overview

The **Document Upload API** provides a unified interface for uploading and processing technical documents in multiple formats:
- **PDF** (`.pdf`) — Portable Document Format
- **Word** (`.docx`, `.doc`) — Microsoft Word Documents
- **PowerPoint** (`.pptx`, `.ppt`) — Microsoft PowerPoint Presentations

The system automatically detects file format and processes documents using LLM-powered vision capabilities to extract complete, structured content. All processed documents are stored as embeddings in the Neo4j knowledge graph for semantic search and retrieval.

---

## 🚨 Important Prerequisites

### LLM Model Must Have Vision Capability

The document processing pipeline **requires** an LLM model with vision/image understanding capabilities. This is **mandatory** for extracting content from document pages/slides.

#### Supported LLM Models:

| LLM Provider | Model | Vision Capability | Status |
|--------------|-------|-------------------|--------|
| **Azure OpenAI** | GPT-4V (Turbo) | ✅ Yes | Recommended |
| **Azure OpenAI** | GPT-4o | ✅ Yes | Recommended |
| **OpenAI** | GPT-4 Turbo | ✅ Yes | Supported |
| **OpenAI** | GPT-4o | ✅ Yes | Supported |
| **Anthropic** | Claude 3 Vision | ✅ Yes | Supported |
| **Anthropic** | Claude 3.5 Sonnet | ✅ Yes | Supported |
| **Ollama** | llava | ✅ Yes | Supported (local) |
| **Ollama** | llama2 | ❌ No | **NOT supported** |
| **Ollama** | mistral | ❌ No | **NOT supported** |

#### Configuration:

Ensure your `.env` file has the correct LLM configuration:

```bash
# For Azure OpenAI (GPT-4V Vision)
USE_LLM=azure
USE_EMBEDDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4-vision  # or gpt-4-turbo
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

Or for Ollama with vision model:

```bash
USE_LLM=ollama
USE_EMBEDDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL_NAME=llava:7b  # Vision-capable model
EMBED_MODEL_NAME=nomic-embed-text:latest
```

#### Verifying Vision Capability:

To test if your LLM has vision capability:

```bash
curl -X GET http://localhost:8000/api/documents/health
```

Look for the note in the response confirming vision capability requirement.

---

## 🎯 Separate Document LLM Configuration (Optional)

### Why Use a Separate Document LLM?

By default, the document processing pipeline uses the main LLM configured in `USE_LLM`. However, you can optionally configure a **separate vision-capable LLM** specifically for document processing using the `UNSTRUCTURED_LLM` configuration. This is useful when:

- Your main LLM (used for chat/reasoning) lacks vision capability
- You want to use different models for different purposes (e.g., GPT-4 for tools, GPT-4V for vision)
- You need APIM (API Management) gateway routing for compliance/governance
- You want to optimize costs by using cheaper vision models for documents

### Configuration Priority

When `USE_UNSTRUCTURED_LLM=true`, the system tries to initialize an LLM in this order:

1. **APIM Gateway** (if `UNSTRUCTURED_APIM_ENDPOINT` provided) — **Recommended**
2. **Direct Azure OpenAI** (if `UNSTRUCTURED_AZURE_OPENAI_ENDPOINT` provided)
3. **Ollama Local** (if `UNSTRUCTURED_LLM_TYPE=ollama`)
4. **Fallback to Main LLM** (if `USE_UNSTRUCTURED_LLM=false`)

### Option 1: Use APIM Gateway (Recommended)

Azure API Management (APIM) provides a unified gateway for routing requests with governance, rate limiting, and compliance features:

```bash
# .env
USE_UNSTRUCTURED_LLM=true
UNSTRUCTURED_LLM_TYPE=azure

# APIM Gateway (unified endpoint)
UNSTRUCTURED_APIM_ENDPOINT=https://your-apim.azure-api.net/gpt4-vision
UNSTRUCTURED_APIM_SUBSCRIPTION_KEY=your-subscription-key
UNSTRUCTURED_APIM_API_VERSION=2024-02-15-preview
```

**Benefits:**
- ✅ Unified gateway for multiple LLM backends
- ✅ Rate limiting and quota management
- ✅ Request/response transformation
- ✅ Compliance and governance policies
- ✅ Cost management and analytics

### Option 2: Use Direct Azure OpenAI

Direct connection to Azure OpenAI (without APIM):

```bash
# .env
USE_UNSTRUCTURED_LLM=true
UNSTRUCTURED_LLM_TYPE=azure

# Direct Azure OpenAI (no APIM)
UNSTRUCTURED_AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
UNSTRUCTURED_AZURE_OPENAI_API_KEY=your-api-key
UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT=gpt-4-vision
UNSTRUCTURED_AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

### Option 3: Use Local Ollama Vision Model

Run vision model locally using Ollama:

```bash
# .env
USE_UNSTRUCTURED_LLM=true
UNSTRUCTURED_LLM_TYPE=ollama

# Ollama Configuration
UNSTRUCTURED_OLLAMA_BASE_URL=http://localhost:11434
UNSTRUCTURED_LLM_MODEL_NAME=llava:7b
```

Install Ollama and pull vision model:
```bash
ollama pull llava:7b
```

### Option 4: Use Main LLM (Default)

No separate configuration needed — uses the main LLM:

```bash
# .env
USE_UNSTRUCTURED_LLM=false
# Document processing will use USE_LLM configuration
```

---

## 📋 Supported Document Formats

### PDF (`.pdf`)

- **Processing**: Pages converted to high-resolution images (2x zoom)
- **Extraction**: Complete page content, text, tables, diagrams
- **Use Case**: Datasheets, technical specifications, manuals, reports

### Word Document (`.docx`, `.doc`)

- **Processing**: Document converted to PDF (via LibreOffice), then to images
- **Fallback**: Text extraction with image rendering if conversion unavailable
- **Extraction**: Headings, body text, tables, lists, formatting
- **Use Case**: Design documents, requirements, procedures, guidelines

### PowerPoint (`.pptx`, `.ppt`)

- **Processing**: Slides converted to images (via LibreOffice or python-pptx)
- **Extraction**: Slide text, bullet points, speaker notes, chart descriptions
- **Use Case**: Technical presentations, process flows, architecture diagrams, training materials

---

## 🔧 Configuration

### Environment Variables

All document processing configuration is managed via `.env` file in the `backend/` directory:

```bash
# ========== NEO4J DATABASE ==========
NEO4J_URI=neo4j+ssc://your-neo4j-instance
NEO4J_USER=your-username
NEO4J_PASS=your-password
NEO4J_DATABASE=windchilltest

# ========== MAIN LLM (Chat, Reasoning, Tool Calling) ==========
USE_LLM=ollama                    # or "azure"
USE_EMBEDDER=ollama               # or "azure"
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL_NAME=llama3:latest
EMBED_MODEL_NAME=nomic-embed-text:latest

# ========== UNSTRUCTURED LLM (Document Processing - Optional) ==========
USE_UNSTRUCTURED_LLM=false        # Set to true for separate LLM
UNSTRUCTURED_LLM_TYPE=azure       # or "ollama"

# APIM Gateway (Recommended for APIM routing)
UNSTRUCTURED_APIM_ENDPOINT=
UNSTRUCTURED_APIM_SUBSCRIPTION_KEY=
UNSTRUCTURED_APIM_API_VERSION=2024-02-15-preview

# Direct Azure OpenAI (if APIM not used)
UNSTRUCTURED_AZURE_OPENAI_ENDPOINT=
UNSTRUCTURED_AZURE_OPENAI_API_KEY=
UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT=gpt-4-vision
UNSTRUCTURED_AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Ollama for Documents (local vision model)
UNSTRUCTURED_OLLAMA_BASE_URL=http://localhost:11434
UNSTRUCTURED_LLM_MODEL_NAME=llava:7b

# ========== DOCUMENT PIPELINE ==========
NEO4J_DOCUMENT_INDEX=datasheet_index
NEO4J_DOCUMENT_NODE_LABEL=DocumentChunk
DOCUMENT_CHUNK_SIZE=400           # Characters per chunk
DOCUMENT_CHUNK_OVERLAP=50         # Overlap between chunks
DOCUMENT_TEMP_DIR=temp_documents  # Temporary file storage

# Format-Specific Configuration
PDF_ZOOM_LEVEL=2.0              # Image zoom for PDF pages (1.0-3.0)
WORD_PAGE_WIDTH=800             # Image width for Word documents
PPT_SLIDE_DPI=150               # Image DPI for PowerPoint slides

# ========== UPLOAD CONSTRAINTS ==========
MAX_FILE_SIZE_MB=50              # Maximum file size
MAX_FILES_PER_UPLOAD=10          # Maximum files per batch
```

**Key Points:**
- All values are optional except `NEO4J_*` (if using Neo4j)
- Use `.env.example` as a template
- LLM must have vision capability (GPT-4V, Claude Vision, llava, etc.)
- Unstructured LLM defaults to main LLM if `USE_UNSTRUCTURED_LLM=false`

### Dependencies Installation

```bash
# Install required packages
cd backend/
pip install python-docx==1.1.2 python-pptx==0.6.23

# Or use requirements.txt (already updated)
pip install -r requirements.txt
```

### Optional: LibreOffice Installation

For best quality document conversion, install LibreOffice:

```bash
# Ubuntu/Debian
sudo apt-get install libreoffice

# macOS
brew install libreoffice

# Windows
# Download from https://www.libreoffice.org/download/
```

If LibreOffice is not installed, the system falls back to python-docx and python-pptx with acceptable quality.

---

## 🚀 Quick Start

### 1. Start the Backend Server

```bash
cd backend/
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Verify Document API is Running

```bash
curl -X GET http://localhost:8000/api/documents/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "Document Upload API",
  "supported_formats": ["pdf", "word", "powerpoint"],
  "max_file_size_mb": 50,
  "max_files_per_upload": 10,
  "note": "LLM model must have vision capability (GPT-4V, Claude, etc.)",
  "timestamp": "2024-12-20T10:30:45.123456"
}
```

### 3. Check Supported Formats

```bash
curl -X GET http://localhost:8000/api/documents/supported-formats
```

---

## 📤 Uploading Documents

### Option 1: Upload Multiple Documents (Batch)

Upload mixed format documents in a single request:

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "files=@datasheet.pdf" \
  -F "files=@manual.docx" \
  -F "files=@presentation.pptx"
```

**Response**:
```json
{
  "status": "success",
  "message": "Successfully processed 3 out of 3 files",
  "summary": {
    "total_files": 3,
    "valid_files": 3,
    "invalid_files": 0,
    "successfully_processed": 3,
    "failed_processing": 0,
    "file_types": {
      "pdf": 1,
      "word": 1,
      "powerpoint": 1
    }
  },
  "results": [
    {
      "file": "/temp/datasheet.pdf",
      "file_name": "datasheet.pdf",
      "format": "pdf",
      "status": "success",
      "message": "PDF processed successfully",
      "started_at": "2024-12-20T10:30:45.123456",
      "completed_at": "2024-12-20T10:31:12.654321"
    },
    ...
  ],
  "timestamp": "2024-12-20T10:31:15.234567"
}
```

### Option 2: Upload Single Document

Upload one document at a time:

```bash
curl -X POST http://localhost:8000/api/documents/upload-single \
  -F "file=@datasheet.pdf" \
  -F "index_name=technical_docs"
```

### Option 3: Python Client

```python
import requests
from pathlib import Path

# Single file
files = {'file': open('datasheet.pdf', 'rb')}
response = requests.post(
    'http://localhost:8000/api/documents/upload-single',
    files=files
)
print(response.json())

# Multiple files (batch)
file_list = [
    ('files', open('datasheet.pdf', 'rb')),
    ('files', open('manual.docx', 'rb')),
    ('files', open('presentation.pptx', 'rb'))
]
response = requests.post(
    'http://localhost:8000/api/documents/upload',
    files=file_list
)
print(response.json())
```

### Option 4: JavaScript/Node.js Client

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

// Batch upload
const uploadBatch = async () => {
  const form = new FormData();
  
  // Add multiple files
  form.append('files', fs.createReadStream('datasheet.pdf'));
  form.append('files', fs.createReadStream('manual.docx'));
  form.append('files', fs.createReadStream('presentation.pptx'));
  
  try {
    const response = await axios.post(
      'http://localhost:8000/api/documents/upload',
      form,
      { headers: form.getHeaders() }
    );
    
    console.log('Upload successful:', response.data);
    console.log(`Processed ${response.data.summary.successfully_processed} files`);
  } catch (error) {
    console.error('Upload failed:', error.response.data);
  }
};

uploadBatch();
```

---

## 🔍 Understanding Processing Results

### Success Response

When documents are processed successfully:

```json
{
  "status": "success",
  "message": "Successfully processed 3 out of 3 files",
  "summary": {
    "total_files": 3,
    "valid_files": 3,
    "successfully_processed": 3,
    "failed_processing": 0,
    "file_types": {
      "pdf": 1,
      "word": 1,
      "powerpoint": 1
    }
  },
  "results": [
    {
      "file": "/temp/datasheet.pdf",
      "format": "pdf",
      "status": "success",
      "message": "PDF processed successfully"
    },
    ...
  ]
}
```

### Partial Success Response

When some files fail processing:

```json
{
  "status": "partial",
  "message": "Successfully processed 2 out of 3 files",
  "summary": {
    "total_files": 3,
    "successfully_processed": 2,
    "failed_processing": 1
  },
  "validation_errors": [
    {
      "file": "invalid_file.txt",
      "error": "Unsupported file format: .txt"
    }
  ],
  "processing_results": [
    {
      "file_name": "datasheet.pdf",
      "status": "success",
      "message": "PDF processed successfully"
    },
    {
      "file_name": "corrupted.docx",
      "status": "error",
      "error": "Failed to convert Word document to images: [error details]"
    }
  ]
}
```

### Processing Stages

Each document goes through these stages:

1. **Validation** — Check file format, size, existence
2. **Format Detection** — Automatically identify PDF, Word, or PowerPoint
3. **Conversion** — Convert to images (PDF pages, Word/PPT slides)
4. **Extraction** — Use LLM vision to extract text and structure
5. **Chunking** — Split into 400-character chunks with 50-character overlap
6. **Embedding** — Create vector embeddings and store in Neo4j
7. **Cleanup** — Remove temporary image files

---

## 🐛 Troubleshooting

### Problem: "LLM not available" Error

**Cause**: LLM configuration is incorrect or model doesn't have vision capability.

**Solution**:
1. Verify `.env` file has correct LLM settings
2. Check that model has vision capability (see Prerequisites)
3. Test LLM connection: `python -c "from core.llm import llm; print(llm.invoke('test')"`
4. Ensure Azure OpenAI endpoint or Ollama service is running

### Problem: "File too large" Error

**Cause**: File exceeds `MAX_FILE_SIZE_MB` limit (default 50 MB).

**Solution**:
1. Split large files into smaller chunks
2. Or increase `MAX_FILE_SIZE_MB` in `.env` (not recommended for production)
3. Check file size: `ls -lh filename.pdf`

### Problem: "Too many files" Error

**Cause**: Uploading more than `MAX_FILES_PER_UPLOAD` files at once (default 10).

**Solution**:
1. Upload in multiple batches
2. Or increase `MAX_FILES_PER_UPLOAD` in `.env`

### Problem: "LibreOffice not found" Warning

**Cause**: LibreOffice is not installed (optional but recommended).

**Solution**:
- Install LibreOffice (see Configuration section)
- Or system will fall back to python-pptx/python-docx (acceptable quality)

### Problem: "Failed to convert Word/PowerPoint" Error

**Cause**: Corruption or unsupported format in document.

**Solution**:
1. Try re-saving the document in Office 365
2. Verify file is not corrupted: `file filename.docx`
3. Check file header matches extension
4. Try with a simpler document first

### Problem: Neo4j Connection Error

**Cause**: Neo4j credentials or connection URL is incorrect.

**Solution**:
1. Verify `.env` has correct Neo4j settings
2. Test connection: `neo4j-shell -u neo4j -p password`
3. Check Neo4j service is running
4. Verify network connectivity to Neo4j instance

### Problem: "No text extracted" or Empty Results

**Cause**: Document contains only images or scanned content.

**Solution**:
1. Ensure LLM model supports OCR (Optical Character Recognition)
2. Verify image quality is sufficient (use `PDF_ZOOM_LEVEL=3.0` for better resolution)
3. Consider running OCR preprocessing on scanned documents

### Problem: "Unstructured LLM unavailable" Error

**Cause**: Document LLM configuration is incorrect when `USE_UNSTRUCTURED_LLM=true`.

**Solution** (check in priority order):

1. **If using APIM Gateway:**
   - Verify `UNSTRUCTURED_APIM_ENDPOINT` is valid
   - Verify `UNSTRUCTURED_APIM_SUBSCRIPTION_KEY` is correct
   - Test APIM connection: `curl -H "Ocp-Apim-Subscription-Key: your-key" https://your-apim-endpoint`

2. **If using Direct Azure OpenAI:**
   - Verify `UNSTRUCTURED_AZURE_OPENAI_ENDPOINT` (full URL with trailing slash)
   - Verify `UNSTRUCTURED_AZURE_OPENAI_API_KEY` is correct
   - Verify `UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT` matches your deployment name
   - Test connection: `python -c "from core.llm import unstructured_llm; print(unstructured_llm.invoke('test'))"`

3. **If using Ollama:**
   - Verify Ollama service is running: `curl http://localhost:11434/api/tags`
   - Verify model is installed: `ollama list | grep llava`
   - If missing, install: `ollama pull llava:7b`
   - Verify `UNSTRUCTURED_OLLAMA_BASE_URL` is correct

4. **Fallback to main LLM:**
   - Set `USE_UNSTRUCTURED_LLM=false` to use the main LLM instead
   - Verify main LLM has vision capability

### Problem: "APIM subscription key invalid" or "401 Unauthorized"

**Cause**: APIM authentication credentials are incorrect or expired.

**Solution**:
1. Regenerate APIM subscription key in Azure Portal
2. Verify key hasn't been rotated or revoked
3. Check key expiration in APIM settings
4. Test key manually: `curl -H "Ocp-Apim-Subscription-Key: your-key" https://your-apim.azure-api.net/health`

---

## 📊 Monitoring and Logging

### View Processing Logs

Logs are written to stdout and can be monitored in real-time:

```bash
# Watch logs as they arrive
tail -f backend.log | grep "document"

# Filter by status
grep "✅\|✗\|❌" backend.log

# See only errors
grep "Error\|error\|ERROR" backend.log
```

### Log Levels

- 🟢 **INFO** — Successful operations, checkpoints
- 🟡 **WARNING** — Non-critical issues, fallbacks activated
- 🔴 **ERROR** — Processing failures, validation errors

### Example Log Output

```
INFO:document_processor:Processing batch of 3 documents...
INFO:document_processor:✓ Valid: datasheet.pdf (pdf)
INFO:document_processor:✓ Valid: manual.docx (word)
INFO:document_processor:✓ Valid: presentation.pptx (powerpoint)
INFO:pdf_pipeline:📄 Converting PDF to images: datasheet.pdf
INFO:pdf_pipeline:  ✓ Converted page 1/12
INFO:pdf_pipeline:  ✓ Converted page 2/12
...
INFO:pdf_pipeline:🤖 Extracting content from 12 images with LLM vision...
INFO:pdf_pipeline:  Processing page 1/12
INFO:pdf_pipeline:  ✓ Extracted page 1
...
INFO:pdf_pipeline:🗄️ Storing 45 documents in Neo4j...
INFO:pdf_pipeline:✅ PDF pipeline completed successfully
```

---

## 🔐 Security & Best Practices

### API Security

1. **CORS Settings** — Configure allowed origins in production:
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://yourdomain.com"],  # Specific origins only
       allow_methods=["POST", "GET"],
       allow_headers=["*"],
   )
   ```

2. **File Size Limits** — Enforce reasonable limits:
   ```bash
   MAX_FILE_SIZE_MB=50      # Prevent memory exhaustion
   MAX_FILES_PER_UPLOAD=10  # Rate limiting
   ```

3. **Temporary File Cleanup** — Automatic cleanup of temporary files after processing

4. **LLM Usage** — Monitor API calls and costs (Azure/OpenAI)

### Performance Optimization

1. **Chunk Size** — Default 400 characters; adjust based on LLM token limits:
   ```bash
   DOCUMENT_CHUNK_SIZE=400      # ~100 tokens
   DOCUMENT_CHUNK_OVERLAP=50    # Context preservation
   ```

2. **Zoom Level** — Higher zoom = better quality but slower:
   ```bash
   PDF_ZOOM_LEVEL=2.0           # Recommended: 2.0-3.0
   ```

3. **Parallel Processing** — For large batches, implement queue system (future enhancement)

---

## 📡 API Reference

### Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/documents/upload` | Upload multiple mixed-format documents |
| POST | `/api/documents/upload-single` | Upload single document |
| GET | `/api/documents/supported-formats` | Get supported formats info |
| GET | `/api/documents/health` | Health check |

### Request Parameters

#### `/api/documents/upload`
- `files` (File, required): Multiple document files
- `index_name` (String, optional): Neo4j index name (default: `datasheet_index`)

#### `/api/documents/upload-single`
- `file` (File, required): Single document file
- `index_name` (String, optional): Neo4j index name

### Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success (all or partial processing) |
| 400 | Bad request (validation error) |
| 500 | Server error (processing failed) |

---

## 📖 Examples

### Configuration Example 1: Main LLM Only (Default)

Use the main LLM for document processing (simplest setup):

```bash
# .env
USE_UNSTRUCTURED_LLM=false
USE_LLM=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL_NAME=llama3:latest  # Must have vision capability
```

**Pros**: Simpler configuration, single LLM
**Cons**: Main LLM must have vision capability

### Configuration Example 2: Separate LLM via APIM Gateway (Recommended)

Use APIM for unified document processing with governance:

```bash
# .env
USE_UNSTRUCTURED_LLM=true
UNSTRUCTURED_LLM_TYPE=azure
UNSTRUCTURED_APIM_ENDPOINT=https://my-apim.azure-api.net/gpt4v
UNSTRUCTURED_APIM_SUBSCRIPTION_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
UNSTRUCTURED_APIM_API_VERSION=2024-02-15-preview

# Main LLM can be different (no vision required)
USE_LLM=ollama
LLM_MODEL_NAME=llama3:latest  # Reasoning-focused
EMBED_MODEL_NAME=nomic-embed-text:latest
```

**Pros**: APIM governance, different models for different purposes
**Cons**: Requires APIM setup

### Configuration Example 3: Separate Azure OpenAI LLM

Use direct Azure OpenAI for documents, different LLM for main tasks:

```bash
# .env
USE_UNSTRUCTURED_LLM=true
UNSTRUCTURED_LLM_TYPE=azure
UNSTRUCTURED_AZURE_OPENAI_ENDPOINT=https://my-vision.openai.azure.com/
UNSTRUCTURED_AZURE_OPENAI_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT=gpt-4-vision

# Main LLM with different Azure instance
USE_LLM=azure
AZURE_OPENAI_ENDPOINT=https://my-main.openai.azure.com/
AZURE_OPENAI_API_KEY=yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
AZURE_OPENAI_DEPLOYMENT=gpt-4-turbo  # Tool calling, no vision
```

**Pros**: Optimize each LLM for its purpose, better cost management
**Cons**: Multiple Azure subscriptions needed

### Configuration Example 4: Local Ollama Vision Model

Use local Ollama vision model for documents:

```bash
# .env
USE_UNSTRUCTURED_LLM=true
UNSTRUCTURED_LLM_TYPE=ollama
UNSTRUCTURED_OLLAMA_BASE_URL=http://localhost:11434
UNSTRUCTURED_LLM_MODEL_NAME=llava:7b  # Local vision model

# Main LLM can run elsewhere
USE_LLM=ollama
OLLAMA_BASE_URL=http://remote-ollama:11434
LLM_MODEL_NAME=mistral:latest  # Non-vision model
```

**Pros**: Local vision processing, no API costs
**Cons**: Requires local compute resources

---

### Upload Example 1: Upload Engineering Datasheet PDF

```bash
curl -X POST http://localhost:8000/api/documents/upload-single \
  -F "file=@SKF_bearing_datasheet.pdf"
```

**Result**: All pages extracted, tables converted to markdown, specifications indexed

### Upload Example 2: Upload Design Requirements Document

```bash
curl -X POST http://localhost:8000/api/documents/upload-single \
  -F "file=@design_requirements.docx" \
  -F "index_name=requirements"
```

**Result**: Sections preserved, lists indexed, formatting maintained

### Upload Example 3: Batch Upload Mixed Documents

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "files=@datasheet.pdf" \
  -F "files=@procedure.docx" \
  -F "files=@training.pptx" \
  -F "index_name=technical_library"
```

**Result**: All documents processed and stored with single index

### Upload Example 4: Integrate with Python Application

```python
import requests
import json
from pathlib import Path

class DocumentUploadClient:
    def __init__(self, api_url="http://localhost:8000"):
        self.api_url = api_url
    
    def upload_document(self, file_path, index_name=None):
        """Upload single document"""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {}
            if index_name:
                data['index_name'] = index_name
            
            response = requests.post(
                f"{self.api_url}/api/documents/upload-single",
                files=files,
                data=data
            )
        
        return response.json()
    
    def upload_batch(self, file_paths, index_name=None):
        """Upload multiple documents"""
        files = [('files', open(fp, 'rb')) for fp in file_paths]
        data = {}
        if index_name:
            data['index_name'] = index_name
        
        response = requests.post(
            f"{self.api_url}/api/documents/upload",
            files=files,
            data=data
        )
        
        return response.json()

# Usage
client = DocumentUploadClient()

# Upload single
result = client.upload_document('datasheet.pdf')
print(f"Status: {result['status']}")
print(f"Message: {result['message']}")

# Upload batch
files = ['doc1.pdf', 'doc2.docx', 'doc3.pptx']
result = client.upload_batch(files, index_name='technical_docs')
print(json.dumps(result['summary'], indent=2))
```

---

## 🎯 Next Steps

After uploading documents:

1. **Search** — Use Neo4j similarity search on document embeddings
2. **Integrate** — Use extracted content in RAG applications
3. **Monitor** — Track Neo4j vector index growth
4. **Optimize** — Adjust chunk size and overlap based on results
5. **Scale** — Implement async processing for high-volume uploads

---

## 📞 Support & FAQ

### Q: Can I upload protected/password-protected documents?
**A**: Not currently. Please unprotect documents before uploading.

### Q: What happens to temporary image files?
**A**: Automatically cleaned up after processing completes.

### Q: Can I change the Neo4j index after upload?
**A**: No, index is fixed at upload time. Create new uploads with different index names.

### Q: Is there a limit on document complexity?
**A**: No hard limit, but very large documents (1000+ pages) may take several minutes.

### Q: Can I retrieve uploaded documents later?
**A**: Yes, they're stored as embeddings in Neo4j. Use similarity search queries.

### Q: What document metadata is preserved?
**A**: File name, format, upload timestamp, chunk info, and source links.

### Q: Should I use a separate document LLM or the main LLM?
**A**: Use `USE_UNSTRUCTURED_LLM=true` if:
- Your main LLM doesn't have vision capability
- You want different models for reasoning vs. vision (cost/performance optimization)
- You need APIM gateway routing for compliance
- Otherwise, use the main LLM (simpler configuration)

### Q: What's the difference between APIM and direct Azure OpenAI?
**A**: 
- **APIM**: Unified gateway with governance, rate limiting, request transformation (recommended for enterprises)
- **Direct**: Direct connection to Azure OpenAI, lower latency, simpler setup

### Q: Can I use a cheaper vision model for documents?
**A**: Yes! Use `UNSTRUCTURED_LLM_TYPE=ollama` with `llava:7b` or similar local models to reduce API costs.

### Q: What happens if both main and unstructured LLM fail?
**A**: Document processing will fail with clear error messages. Check logs for specific configuration issues.

### Q: Can I switch LLM providers mid-deployment?
**A**: Yes, just update `.env` and restart the service. New uploads will use the new LLM configuration.

### Q: Is there additional cost for using APIM?
**A**: Yes, APIM has separate pricing tiers. See Azure API Management pricing for details.

---

## ⚠️ Limitations & Known Issues

1. **OCR Not Included** — Scanned documents require separate OCR preprocessing
2. **Complex Tables** — Very complex multi-level tables may need manual review
3. **Protected PDFs** — Password-protected PDFs must be unlocked first
4. **Handwriting** — Handwritten text not extracted (not supported by LLM vision models)
5. **Deprecated Formats** — `.doc` and `.ppt` (legacy Office) have reduced feature support

---

## 📝 Version History

### v1.1 (Latest)
- ✅ Separate document LLM configuration (`UNSTRUCTURED_LLM`)
- ✅ APIM gateway support for document processing
- ✅ Multiple LLM fallback options (APIM → Azure → Ollama → Main)
- ✅ Enhanced troubleshooting and configuration examples
- ✅ Configuration priority system

### v1.0
- ✅ PDF support with vision extraction
- ✅ Word document support
- ✅ PowerPoint presentation support
- ✅ Batch upload capability
- ✅ Environment-based configuration
- ✅ Automatic format detection
- ✅ Graceful error handling

---

## 📄 License & Attribution

This document upload system is part of the Traceability & Impact Analysis Platform.

For more information, see the main [README.md](../README.md).
