"""
Refactored PDF to Neo4j Pipeline
Converts PDF pages to images, extracts content with LLM, creates LangChain documents, stores in Neo4j
Supports both AZURE and OLLAMA LLMs with vision capabilities
"""
import os
import base64
import logging
from typing import List, Optional, Tuple
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image
from langchain.docstore.document import Document
from langchain_neo4j import Neo4jVector
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter
from datetime import datetime
from dotenv import load_dotenv
from .core.llm import embeddings, llm, unstructured_llm, LLM_AVAILABLE

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# ========== Configuration from .env ==========
def _get_env_config() -> dict:
    """Load all configuration from environment variables with defaults"""
    return {
        "NEO4J_URI": os.getenv("NEO4J_URI"),
        "NEO4J_USER": os.getenv("NEO4J_USER"),
        "NEO4J_PASS": os.getenv("NEO4J_PASS"),
        "NEO4J_DATABASE": os.getenv("NEO4J_DATABASE", "windchilltest"),
        "NEO4J_DOCUMENT_INDEX": os.getenv("NEO4J_DOCUMENT_INDEX", "datasheet_index"),
        "NEO4J_DOCUMENT_NODE_LABEL": os.getenv("NEO4J_DOCUMENT_NODE_LABEL", "DocumentChunk"),
        "PDF_ZOOM_LEVEL": float(os.getenv("PDF_ZOOM_LEVEL", "2.0")),
        "DOCUMENT_CHUNK_SIZE": int(os.getenv("DOCUMENT_CHUNK_SIZE", "400")),
        "DOCUMENT_CHUNK_OVERLAP": int(os.getenv("DOCUMENT_CHUNK_OVERLAP", "50")),
        "DOCUMENT_TEMP_DIR": os.getenv("DOCUMENT_TEMP_DIR", "temp_documents"),
    }

CONFIG = _get_env_config()

# ========== Validation Functions ==========
def validate_neo4j_credentials() -> Tuple[bool, Optional[str]]:
    """Validate Neo4j credentials are available"""
    required = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASS"]
    missing = [k for k in required if not CONFIG.get(k)]
    if missing:
        error_msg = f"Missing Neo4j credentials: {', '.join(missing)}"
        logger.error(error_msg)
        return False, error_msg
    return True, None

def validate_llm_available() -> Tuple[bool, Optional[str]]:
    """Validate LLM is available and has vision capability"""
    if not LLM_AVAILABLE:
        error_msg = "LLM not available. Ensure AZURE or OLLAMA is properly configured and has vision capability (GPT-4V, Claude, etc.)"
        logger.error(error_msg)
        return False, error_msg
    return True, None

# ========== PDF Processing ==========
def pdf_to_images(pdf_path: str, output_dir: str = "temp_images") -> List[str]:
    """
    Convert PDF pages to images using PyMuPDF
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save temporary images
        
    Returns:
        List of image file paths
        
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        Exception: If conversion fails
    """
    try:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"📄 Converting PDF to images: {pdf_path}")
        
        # Open PDF with fitz
        doc = fitz.open(pdf_path)
        image_paths = []
        
        for page_num in range(len(doc)):
            try:
                page = doc.load_page(page_num)
                
                # Convert page to image (PNG) with configurable zoom
                mat = fitz.Matrix(CONFIG["PDF_ZOOM_LEVEL"], CONFIG["PDF_ZOOM_LEVEL"])
                pix = page.get_pixmap(matrix=mat)
                
                # Save as PNG
                image_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
                pix.save(image_path)
                image_paths.append(image_path)
                
                logger.info(f"  ✓ Converted page {page_num + 1}/{len(doc)}")
            except Exception as e:
                logger.error(f"  ✗ Failed to convert page {page_num + 1}: {e}")
                raise
        
        doc.close()
        logger.info(f"✅ Created {len(image_paths)} images from PDF")
        return image_paths
        
    except Exception as e:
        logger.error(f"❌ Error converting PDF to images: {e}")
        raise

def images_to_documents(image_paths: List[str]) -> List[Document]:
    """
    Extract content from images using LLM with vision capability
    
    Args:
        image_paths: List of image file paths
        
    Returns:
        List of LangChain Document objects
        
    Raises:
        Exception: If LLM extraction fails
    """
    try:
        logger.info(f"🤖 Extracting content from {len(image_paths)} images with LLM vision...")
        
        documents = []
        
        extraction_prompt = """
You are an expert document analyst specializing in comprehensive content extraction from document images. Your task is to extract ALL textual content from the provided document page image(s) while maintaining perfect structural integrity, context, and formatting for downstream RAG (Retrieval-Augmented Generation) applications.

### EXTRACTION REQUIREMENTS:

#### 1. CONTENT COMPLETENESS
- Extract **every single word, number, symbol, and character** visible in the image
- Include ALL headers, subheaders, body text, captions, footnotes, and annotations
- Capture table data, bullet points, numbered lists, and any structured content
- Include page numbers, watermarks, and marginal notes if present
- Do NOT omit or summarize any content - extract everything verbatim

#### 2. STRUCTURAL HIERARCHY PRESERVATION
- Maintain the exact hierarchical structure using markdown formatting:
  - # for main titles/headings (H1)
  - ## for major sections (H2)
  - ### for subsections (H3)
  - #### for sub-subsections (H4)
- Preserve original indentation and spacing patterns

#### 3. FORMATTING PRESERVATION
- **Tables**: Convert to proper markdown table format with headers and alignment
- **Lists**: Maintain bullet points and numbered lists
- **Text Styling**: Indicate **bold**, *italic*, and `code/monospace` text
- **Special Characters**: Preserve mathematical symbols, Greek letters, units, etc.
- **Line Breaks**: Maintain paragraph breaks and section separations
- **Columns**: If multi-column layout, clearly separate columns

#### 4. CONTEXTUAL INFORMATION
- Add [IMAGE], [FIGURE], [CHART], [DIAGRAM] placeholders where visual elements appear
- Include descriptive captions for any figures, charts, or diagrams
- Preserve cross-references and citations exactly as shown

#### 5. METADATA CAPTURE
- Document title, authors, publication info (if visible)
- Page numbers and section numbers
- Headers and footers content
- Date stamps, revision numbers, or version info

### OUTPUT FORMAT:

```markdown
## Content

[Extract all content here maintaining hierarchy and formatting]

### Tables
[Convert all tables to markdown format]

### Figures and Visual Elements
[List all visual elements with descriptions]
```

### QUALITY ASSURANCE:
Before submitting, verify:
- [ ] Every visible text element has been captured
- [ ] Hierarchical structure matches the original document
- [ ] Tables are properly formatted and complete
- [ ] Mathematical formulas and symbols are accurate
- [ ] Technical terminology is preserved exactly
- [ ] No content has been paraphrased or summarized

Now proceed to extract the content from the provided document image following these guidelines.
Be thorough and extract every piece of visible information.
"""
        
        for i, image_path in enumerate(image_paths, 1):
            try:
                logger.info(f"  Processing page {i}/{len(image_paths)}")
                
                # Encode image
                with open(image_path, 'rb') as f:
                    encoded_image = base64.b64encode(f.read()).decode('ascii')
                
                # Create messages for LLM
                messages = [
                    SystemMessage(content="Extract structured data from document images. You have vision capabilities."),
                    HumanMessage(content=[
                        {"type": "text", "text": extraction_prompt},
                        {"type": "image", "image": encoded_image}
                    ])
                ]
                
                # Extract content with unstructured LLM (vision-capable)
                response = unstructured_llm.invoke(messages)
                content = response.content if hasattr(response, 'content') else str(response)
                
                # Create LangChain document
                doc = Document(
                    page_content=content,
                    metadata={
                        "source": os.path.basename(image_path),
                        "page_number": i,
                        "total_pages": len(image_paths),
                        "processing_method": "llm_vision",
                        "processed_at": datetime.now().isoformat(),
                        "document_type": "pdf",
                        "format": "pdf"
                    }
                )
                
                documents.append(doc)
                logger.info(f"  ✓ Extracted page {i}")
                
            except Exception as e:
                logger.error(f"  ✗ Failed to extract page {i}: {e}")
                raise
        
        logger.info(f"✅ Extracted content from {len(documents)} pages")
        return documents
        
    except Exception as e:
        logger.error(f"❌ Error extracting content from images: {e}")
        raise

def combine_pages_to_single_document(page_documents: List[Document], pdf_path: str) -> Document:
    """
    Combine all page documents into a single document for the entire PDF
    
    Args:
        page_documents: List of page documents
        pdf_path: Original PDF file path
        
    Returns:
        Combined Document object
    """
    try:
        logger.info("📝 Combining pages into single document...")
        
        # Combine all page content
        combined_content = ""
        total_pages = len(page_documents)
        
        for i, doc in enumerate(page_documents, 1):
            combined_content += f"\n\n--- PAGE {i} ---\n\n"
            combined_content += doc.page_content
        
        # Create metadata for the entire document
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        combined_metadata = {
            "source": pdf_name,
            "document_name": pdf_name,
            "total_pages": total_pages,
            "document_type": "pdf",
            "processing_method": "llm_vision_combined",
            "processed_at": datetime.now().isoformat(),
            "file_path": pdf_path,
            "format": "pdf"
        }
        
        # Create single combined document
        combined_document = Document(
            page_content=combined_content.strip(),
            metadata=combined_metadata
        )
        
        logger.info("✅ Created combined document")
        return combined_document
        
    except Exception as e:
        logger.error(f"❌ Error combining pages: {e}")
        raise

def split_document_for_embedding(document: Document, chunk_size: int = None, chunk_overlap: int = None) -> List[Document]:
    """
    Split document into chunks suitable for embedding
    
    Args:
        document: Document to split
        chunk_size: Target characters per chunk (from config if None)
        chunk_overlap: Overlap between chunks (from config if None)
        
    Returns:
        List of chunked documents
    """
    try:
        chunk_size = chunk_size or CONFIG["DOCUMENT_CHUNK_SIZE"]
        chunk_overlap = chunk_overlap or CONFIG["DOCUMENT_CHUNK_OVERLAP"]
        
        logger.info(f"✂️ Splitting document into chunks (size={chunk_size}, overlap={chunk_overlap})...")
        
        # Initialize text splitter optimized for documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=[
                "\n\n--- PAGE ",
                "\n\n## ",
                "\n\n### ",
                "\n\n",
                "\n",
                ". ",
                " ",
                ""
            ]
        )
        
        # Split the document
        chunks = text_splitter.split_documents([document])
        
        # Enhance metadata for each chunk
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                "chunk_id": i + 1,
                "total_chunks": len(chunks),
                "chunk_method": "recursive_character",
            })
        
        logger.info(f"✅ Created {len(chunks)} chunks")
        return chunks
        
    except Exception as e:
        logger.error(f"❌ Error splitting document: {e}")
        raise

def documents_to_neo4j(
    documents: List[Document],
    neo4j_uri: str = None,
    neo4j_username: str = None,
    neo4j_password: str = None,
    index_name: str = None,
    database: str = None
) -> Neo4jVector:
    """
    Store documents in Neo4j vector database
    
    Args:
        documents: List of documents to store
        neo4j_uri: Neo4j URI (from config if None)
        neo4j_username: Neo4j username (from config if None)
        neo4j_password: Neo4j password (from config if None)
        index_name: Index name (from config if None)
        database: Database name (from config if None)
        
    Returns:
        Neo4jVector store instance
        
    Raises:
        ValueError: If required credentials are missing
        Exception: If Neo4j connection fails
    """
    try:
        neo4j_uri = neo4j_uri or CONFIG["NEO4J_URI"]
        neo4j_username = neo4j_username or CONFIG["NEO4J_USER"]
        neo4j_password = neo4j_password or CONFIG["NEO4J_PASS"]
        index_name = index_name or CONFIG["NEO4J_DOCUMENT_INDEX"]
        database = database or CONFIG["NEO4J_DATABASE"]
        
        logger.info(f"🗄️ Storing {len(documents)} documents in Neo4j...")
        
        if not all([neo4j_uri, neo4j_username, neo4j_password]):
            raise ValueError("Missing Neo4j credentials: URI, username, or password")
        
        # Create Neo4j vector store
        vector_store = Neo4jVector.from_documents(
            documents=documents,
            embedding=embeddings,
            url=neo4j_uri,
            username=neo4j_username,
            password=neo4j_password,
            database=database,
            index_name=index_name,
            node_label=CONFIG["NEO4J_DOCUMENT_NODE_LABEL"],
            text_node_property="content"
        )
        
        logger.info("✅ Documents stored in Neo4j successfully")
        return vector_store
        
    except Exception as e:
        logger.error(f"❌ Error storing documents in Neo4j: {e}")
        raise

def cleanup_images(image_paths: List[str]):
    """Remove temporary image files"""
    try:
        logger.info("🧹 Cleaning up temporary images...")
        
        for image_path in image_paths:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as e:
                logger.warning(f"  Could not remove {image_path}: {e}")
        
        # Remove directory if empty
        if image_paths:
            try:
                parent_dir = os.path.dirname(image_paths[0])
                if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    logger.info(f"  Removed empty directory: {parent_dir}")
            except Exception as e:
                logger.warning(f"  Could not remove directory: {e}")
        
        logger.info("✅ Cleanup complete")
    except Exception as e:
        logger.warning(f"⚠️ Cleanup error: {e}")

def pdf_to_neo4j_pipeline(
    pdf_path: str,
    output_dir: str = None,
    index_name: str = None
) -> Neo4jVector:
    """
    Complete pipeline: PDF → Images → LLM extraction → LangChain docs → Neo4j
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save temporary images
        index_name: Neo4j index name
    
    Returns:
        Neo4jVector: Vector store with all documents
        
    Raises:
        Exception: If any step in the pipeline fails
    """
    output_dir = output_dir or CONFIG["DOCUMENT_TEMP_DIR"]
    index_name = index_name or CONFIG["NEO4J_DOCUMENT_INDEX"]
    
    try:
        # Validate prerequisites
        creds_valid, creds_error = validate_neo4j_credentials()
        if not creds_valid:
            raise ValueError(creds_error)
        
        llm_valid, llm_error = validate_llm_available()
        if not llm_valid:
            raise RuntimeError(llm_error)
        
        # Step 1: Convert PDF to images
        images = pdf_to_images(pdf_path, output_dir)
        
        # Step 2: Extract content from images using LLM
        page_documents = images_to_documents(images)
        
        # Step 2.5: Combine all pages into a single document
        combined_document = combine_pages_to_single_document(page_documents, pdf_path)
        
        # Step 2.6: Split into chunks for embedding
        chunked_documents = split_document_for_embedding(combined_document)
        
        # Step 3: Store in Neo4j
        vector_store = documents_to_neo4j(chunked_documents, index_name=index_name)
        
        # Cleanup temporary images
        cleanup_images(images)
        
        logger.info("✅ PDF pipeline completed successfully")
        return vector_store
        
    except Exception as e:
        logger.error(f"❌ PDF pipeline failed: {e}")
        # Attempt cleanup even on failure
        try:
            cleanup_images([])
        except (OSError, FileNotFoundError) as cleanup_err:
            logger.warning(f"Cleanup failed: {cleanup_err}")
        raise

def search_documents(vector_store: Neo4jVector, query: str, k: int = 5) -> List[Document]:
    """
    Search documents in the vector store
    
    Args:
        vector_store: Neo4jVector store instance
        query: Search query
        k: Number of results
        
    Returns:
        List of matching documents
    """
    try:
        logger.info(f"🔍 Searching for: '{query}'")
        
        results = vector_store.similarity_search(query, k=k)
        
        logger.info(f"✅ Found {len(results)} results")
        for i, doc in enumerate(results, 1):
            logger.info(f"  {i}. {doc.metadata.get('document_name', 'Unknown')} - {doc.page_content[:100]}...")
        
        return results
    except Exception as e:
        logger.error(f"❌ Search error: {e}")
        raise

# Usage example
if __name__ == "__main__":
    try:
        PDF_PATH = input("Enter PDF file path: ").strip()
        
        if not os.path.exists(PDF_PATH):
            print(f"❌ File not found: {PDF_PATH}")
            exit(1)
        
        # Run the pipeline
        vector_store = pdf_to_neo4j_pipeline(pdf_path=PDF_PATH)
        
        # Test search
        search_query = input("Enter search query (optional, press Enter to skip): ").strip()
        if search_query:
            search_documents(vector_store, search_query)
        
        print("✅ PDF processing completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        exit(1)
