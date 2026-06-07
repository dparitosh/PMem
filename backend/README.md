# Digital Traceability Backend

A FastAPI-based backend service for digital traceability applications, providing graph database operations, AI-powered chat functionality, and data ingestion pipelines for Neo4j.

## Overview

This backend serves as the core API layer for a digital traceability system built with:
- **FastAPI**: High-performance web framework for building APIs
- **Neo4j**: Graph database for storing and querying complex relationships
- **LangChain & LangGraph**: AI orchestration for chat and data processing
- **Azure OpenAI**: LLM services for text processing and embeddings

## Project Structure

```
backend/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── azure.txt              # Azure configuration (credentials)
├── spinner_datatype.csv   # Sample data file
├── data_pipeline.py       # CSV data ingestion pipeline
├── simple_pdf_pipeline.py # PDF processing pipeline
├── create_embeddings.py   # Embedding generation utilities
├── main_og.py            # Original main file (deprecated)
├── agent/                 # AI agent components
│   ├── __init__.py
│   ├── chat.py           # LangGraph-based chat agent
│   ├── memory.py         # Session memory management
│   └── sessions.py       # Session handling
├── chains/                # LangChain chains for specific operations
│   ├── __init__.py
│   ├── cypher.py         # Cypher query generation
│   ├── cypher_og.py      # Original cypher implementation
│   └── vector.py         # Vector search operations
├── core/                  # Core utilities and configurations
│   ├── __init__.py
│   ├── graph.py          # Neo4j connection and graph operations
│   ├── llm.py            # LLM and embedding configurations
│   ├── CustomAOI_helper.py # Custom AOI utilities
│   └── DeveloperApp.py   # Development utilities
├── models/                # Pydantic models
│   └── schema.py         # API request/response schemas
├── Services/              # Business logic services
│   ├── __init__.py
│   ├── graph_embeddings.py # Graph embedding services
│   └── Ingestion.py      # Data ingestion services
└── Data/                  # Data storage directory
```

## Key Components

### Core Module (`core/`)

- **`graph.py`**: Manages Neo4j database connections and provides graph operations
- **`llm.py`**: Configures Azure OpenAI models for text generation and embeddings
- **`CustomAOI_helper.py`**: Utilities for custom Area of Interest (AOI) operations
- **`DeveloperApp.py`**: Development and testing utilities

### Agent Module (`agent/`)

- **`chat.py`**: Implements a LangGraph-based conversational agent with multiple tools:
  - General chat for PLM and graph database questions
  - Project/product information retrieval
  - Vector search for datasheet facts and definitions
  - Cypher query generation and execution
- **`memory.py`**: Manages conversation memory and session state
- **`sessions.py`**: Handles user session management

### Chains Module (`chains/`)

- **`cypher.py`**: Generates and executes Cypher queries for graph operations
- **`vector.py`**: Handles vector-based search and retrieval operations
- **`cypher_og.py`**: Original Cypher implementation (legacy)

### Services Module (`Services/`)

- **`graph_embeddings.py`**: Services for creating and managing graph embeddings
- **`Ingestion.py`**: Data ingestion and processing services

## Data Pipelines

### CSV Data Pipeline (`data_pipeline.py`)

Processes CSV files to create Neo4j graph structures:

1. **Data Reading**: Reads CSV files with proper encoding handling
2. **Node Creation**: Creates nodes with labels derived from data types
3. **Relationship Creation**: Establishes parent-child relationships
4. **Property Mapping**: Maps CSV columns to node properties
5. **Attribute Handling**: Processes dynamic attributes columns

**Usage**:
```python
python data_pipeline.py
```

### PDF Processing Pipeline (`simple_pdf_pipeline.py`)

Converts PDF documents to Neo4j vector store:

1. **PDF to Images**: Converts PDF pages to high-quality images using PyMuPDF
2. **LLM Extraction**: Uses GPT-4 Vision to extract text content from images
3. **Document Creation**: Creates LangChain documents with metadata
4. **Text Splitting**: Splits documents into manageable chunks
5. **Vector Storage**: Stores embeddings in Neo4j vector index

**Usage**:
```python
from simple_pdf_pipeline import pdf_to_neo4j_pipeline

vector_store = pdf_to_neo4j_pipeline(
    pdf_path="document.pdf",
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="password"
)
```

## API Endpoints

### Core Endpoints

- `GET /schema` - Returns graph schema (node labels, relationships, properties)
- `GET /graphvis` - Returns entire graph data for visualization
- `POST /graphfilter` - Filters graph nodes based on text search
- `POST /chat` - AI-powered chat with graph context
- `GET /graphtraverse/{node_id}` - Traverses graph from specific node

### Data Ingestion Endpoints

- `POST /api/ingest-csv` - Ingest CSV data
- `POST /api/ingest-pdf` - Ingest PDF documents
- Various endpoints for managing node definitions, relationships, indexes, and constraints

## Setup and Installation

### Prerequisites

- Python 3.8+
- Neo4j 5.0+
- Azure OpenAI account (for LLM features)

### Installation

1. **Clone and navigate to backend directory**:
   ```bash
   cd backend
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   Create a `.env` file with:
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASS=your_password
   NEO4J_DATABASE=neo4j

   AZURE_OPENAI_API_KEY=your_azure_key
   AZURE_OPENAI_ENDPOINT=your_azure_endpoint
   AZURE_OPENAI_DEPLOYMENT=your_deployment_name
   ```

4. **Start Neo4j database** (if running locally)

5. **Run the application**:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

### Docker Setup (Optional)

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Usage

### Basic API Usage

```python
import requests

# Get graph schema
response = requests.get("http://localhost:8000/schema")
schema = response.json()

# Chat with the AI agent
response = requests.post("http://localhost:8000/chat", json={
    "session_id": "user123",
    "message": "What products are available?"
})
result = response.json()
```

### Data Ingestion

```python
# CSV Ingestion
files = {"file": open("data.csv", "rb")}
data = {"node_definitions": "...", "relationship_definitions": "..."}

response = requests.post("http://localhost:8000/api/ingest-csv",
                        files=files, data=data)

# PDF Ingestion
files = {"file": open("document.pdf", "rb")}
response = requests.post("http://localhost:8000/api/ingest-pdf", files=files)
```

## Configuration

### Neo4j Configuration

The application connects to Neo4j using environment variables. Ensure your Neo4j instance is running and accessible.

### LLM Configuration

Azure OpenAI is used for:
- Text generation and chat responses
- Document content extraction from images
- Embedding generation for vector search

Configure the Azure credentials in the `.env` file.

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
isort .
```

### API Documentation

When running the server, visit `http://localhost:8000/docs` for interactive API documentation powered by Swagger UI.

## Troubleshooting

### Common Issues

1. **Neo4j Connection Failed**: Check URI, credentials, and ensure Neo4j is running
2. **Azure OpenAI Errors**: Verify API key and endpoint configuration
3. **Memory Issues**: For large datasets, increase system memory or implement pagination
4. **CORS Errors**: Ensure frontend is configured to allow backend origin

### Logs

Check application logs for detailed error information. Enable debug logging by setting:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

1. Follow the existing code structure
2. Add tests for new features
3. Update documentation for API changes
4. Use type hints and docstrings

## License

[Add license information here]