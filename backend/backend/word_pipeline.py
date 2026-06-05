"""
Word Document to Neo4j Pipeline
Converts Word documents to images, extracts content with LLM, creates LangChain documents, stores in Neo4j
Supports both AZURE and OLLAMA LLMs with vision capabilities
"""
import os
import base64
import logging
from typing import List, Optional, Tuple
from pathlib import Path
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image
import io
from langchain.docstore.document import Document
from langchain_neo4j import Neo4jVector
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter
from datetime import datetime
from dotenv import load_dotenv
from .core.llm import embeddings, llm, unstructured_llm, LLM_AVAILABLE
import subprocess

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
        "WORD_PAGE_WIDTH": int(os.getenv("WORD_PAGE_WIDTH", "800")),
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

# ========== Word Document Processing ==========
def docx_to_images(docx_path: str, output_dir: str = "temp_images") -> List[str]:
    """
    Convert Word document to images using LibreOffice/OpenOffice
    Falls back to text extraction if conversion fails
    
    Args:
        docx_path: Path to Word file
        output_dir: Directory to save temporary images
        
    Returns:
        List of image file paths
        
    Raises:
        FileNotFoundError: If document file doesn't exist
        Exception: If conversion fails
    """
    try:
        if not os.path.exists(docx_path):
            raise FileNotFoundError(f"Word document not found: {docx_path}")
        
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"📄 Converting Word document to images: {docx_path}")
        
        image_paths = []
        
        # Try using LibreOffice/OpenOffice for conversion
        try:
            import subprocess
            temp_pdf = os.path.join(output_dir, "temp_document.pdf")
            
            # Convert DOCX to PDF using LibreOffice
            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", output_dir,
                docx_path
            ]
            
            logger.info("  Converting DOCX to PDF via LibreOffice...")
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            
            if result.returncode == 0:
                # Now convert PDF to images
                import fitz
                pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
                
                if os.path.exists(pdf_path):
                    doc = fitz.open(pdf_path)
                    
                    for page_num in range(len(doc)):
                        try:
                            page = doc.load_page(page_num)
                            mat = fitz.Matrix(2.0, 2.0)
                            pix = page.get_pixmap(matrix=mat)
                            
                            image_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
                            pix.save(image_path)
                            image_paths.append(image_path)
                            logger.info(f"  ✓ Converted page {page_num + 1}/{len(doc)}")
                        except Exception as e:
                            logger.error(f"  ✗ Failed to convert page {page_num + 1}: {e}")
                            raise
                    
                    doc.close()
                    
                    # Clean up temporary PDF
                    try:
                        os.remove(pdf_path)
                    except (OSError, FileNotFoundError) as e:
                        logger.warning(f"Could not remove temporary PDF {pdf_path}: {e}")
            else:
                logger.warning("  LibreOffice conversion failed, falling back to text extraction...")
                image_paths = _extract_text_as_images(docx_path, output_dir)
        
        except Exception as e:
            logger.warning(f"  Image conversion failed: {e}, falling back to text extraction...")
            image_paths = _extract_text_as_images(docx_path, output_dir)
        
        if not image_paths:
            raise Exception("No images could be generated from Word document")
        
        logger.info(f"✅ Created {len(image_paths)} images from Word document")
        return image_paths
        
    except Exception as e:
        logger.error(f"❌ Error converting Word document to images: {e}")
        raise

def _extract_text_as_images(docx_path: str, output_dir: str) -> List[str]:
    """
    Fallback: Extract text from Word document and convert to images
    
    Args:
        docx_path: Path to Word file
        output_dir: Directory to save images
        
    Returns:
        List of image file paths
    """
    try:
        logger.info("  Extracting text from Word document...")
        
        # Extract text from docx
        doc = DocxDocument(docx_path)
        text_content = ""
        
        for para in doc.paragraphs:
            if para.text.strip():
                text_content += para.text + "\n"
        
        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text_content += cell.text + " | "
                text_content += "\n"
        
        if not text_content.strip():
            raise Exception("No text content found in Word document")
        
        # Split text into pages (roughly 100 lines per image/page)
        lines = text_content.split("\n")
        page_size = 100
        pages = [lines[i:i + page_size] for i in range(0, len(lines), page_size)]
        
        image_paths = []
        
        # Create images from text using PIL
        from PIL import Image, ImageDraw, ImageFont
        
        for page_num, page_lines in enumerate(pages, 1):
            try:
                # Create image with text
                img = Image.new('RGB', (CONFIG["WORD_PAGE_WIDTH"], 1200), color='white')
                draw = ImageDraw.Draw(img)
                
                # Try to use a default font
                try:
                    font = ImageFont.truetype("arial.ttf", 12)
                except (OSError, IOError) as e:
                    logger.warning(f"Could not load truetype font, using default: {e}")
                    font = ImageFont.load_default()
                
                y_offset = 20
                for line in page_lines:
                    draw.text((20, y_offset), line[:100], fill='black', font=font)
                    y_offset += 20
                    if y_offset > 1100:
                        break
                
                # Crop to actual content size
                img = img.crop((0, 0, CONFIG["WORD_PAGE_WIDTH"], y_offset + 20))
                
                image_path = os.path.join(output_dir, f"page_{page_num}.png")
                img.save(image_path)
                image_paths.append(image_path)
                
                logger.info(f"  ✓ Created text image for page {page_num}")
            except Exception as e:
                logger.error(f"  ✗ Failed to create text image for page {page_num}: {e}")
                raise
        
        return image_paths
    
    except Exception as e:
        logger.error(f"❌ Error extracting text as images: {e}")
        raise

def images_to_documents(image_paths: List[str], document_name: str = "Word Document") -> List[Document]:
    """
    Extract content from images using LLM with vision capability
    
    Args:
        image_paths: List of image file paths
        document_name: Name of the source document
        
    Returns:
        List of LangChain Document objects
    """
    try:
        logger.info(f"🤖 Extracting content from {len(image_paths)} images with LLM vision...")
        
        documents = []
        extraction_prompt = """
You are an expert document analyst. Extract ALL textual content from this Word document image while maintaining structure, formatting, and hierarchy.

### EXTRACTION REQUIREMENTS:
- Extract **every word, number, and symbol** visible
- Maintain hierarchical structure with markdown (# ## ### ####)
- Format tables in markdown
- Preserve lists, bullet points, and numbering
- Indicate **bold**, *italic*, and `code` text
- Include all metadata, headers, footers, and page numbers

### OUTPUT:
Provide clean, structured markdown with all content preserved and properly formatted.
"""
        
        for i, image_path in enumerate(image_paths, 1):
            try:
                logger.info(f"  Processing page {i}/{len(image_paths)}")
                
                # Encode image
                with open(image_path, 'rb') as f:
                    encoded_image = base64.b64encode(f.read()).decode('ascii')
                
                # Create messages for LLM
                messages = [
                    SystemMessage(content="Extract structured data from Word document images. You have vision capabilities."),
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
                        "document_type": "word",
                        "format": "docx",
                        "document_name": document_name
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

def combine_and_split_documents(page_documents: List[Document], docx_path: str, chunk_size: int = None, chunk_overlap: int = None) -> List[Document]:
    """
    Combine pages and split into chunks for embedding
    
    Args:
        page_documents: List of page documents
        docx_path: Original document path
        chunk_size: Target characters per chunk
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of chunked documents
    """
    try:
        chunk_size = chunk_size or CONFIG["DOCUMENT_CHUNK_SIZE"]
        chunk_overlap = chunk_overlap or CONFIG["DOCUMENT_CHUNK_OVERLAP"]
        
        logger.info("📝 Combining and chunking document...")
        
        # Combine all page content
        combined_content = ""
        for i, doc in enumerate(page_documents, 1):
            combined_content += f"\n\n--- PAGE {i} ---\n\n"
            combined_content += doc.page_content
        
        # Create combined document
        doc_name = os.path.splitext(os.path.basename(docx_path))[0]
        combined_metadata = {
            "source": doc_name,
            "document_name": doc_name,
            "total_pages": len(page_documents),
            "document_type": "word",
            "processing_method": "llm_vision_combined",
            "processed_at": datetime.now().isoformat(),
            "file_path": docx_path,
            "format": "docx"
        }
        
        combined_document = Document(
            page_content=combined_content.strip(),
            metadata=combined_metadata
        )
        
        # Split into chunks
        logger.info(f"✂️ Splitting into chunks (size={chunk_size}, overlap={chunk_overlap})...")
        
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
        
        chunks = text_splitter.split_documents([combined_document])
        
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
        logger.error(f"❌ Error combining and splitting documents: {e}")
        raise

def documents_to_neo4j(
    documents: List[Document],
    neo4j_uri: str = None,
    neo4j_username: str = None,
    neo4j_password: str = None,
    index_name: str = None,
    database: str = None
) -> Neo4jVector:
    """Store documents in Neo4j vector database"""
    try:
        neo4j_uri = neo4j_uri or CONFIG["NEO4J_URI"]
        neo4j_username = neo4j_username or CONFIG["NEO4J_USER"]
        neo4j_password = neo4j_password or CONFIG["NEO4J_PASS"]
        index_name = index_name or CONFIG["NEO4J_DOCUMENT_INDEX"]
        database = database or CONFIG["NEO4J_DATABASE"]
        
        logger.info(f"🗄️ Storing {len(documents)} documents in Neo4j...")
        
        if not all([neo4j_uri, neo4j_username, neo4j_password]):
            raise ValueError("Missing Neo4j credentials")
        
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
        logger.error(f"❌ Error storing documents: {e}")
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
        
        logger.info("✅ Cleanup complete")
    except Exception as e:
        logger.warning(f"⚠️ Cleanup error: {e}")

def word_to_neo4j_pipeline(
    docx_path: str,
    output_dir: str = None,
    index_name: str = None
) -> Neo4jVector:
    """
    Complete pipeline: Word → Images → LLM extraction → LangChain docs → Neo4j
    
    Args:
        docx_path: Path to Word document
        output_dir: Directory to save temporary images
        index_name: Neo4j index name
    
    Returns:
        Neo4jVector: Vector store with all documents
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
        
        # Step 1: Convert Word to images
        images = docx_to_images(docx_path, output_dir)
        
        # Step 2: Extract content from images
        doc_name = os.path.splitext(os.path.basename(docx_path))[0]
        page_documents = images_to_documents(images, doc_name)
        
        # Step 3: Combine and split
        chunked_documents = combine_and_split_documents(page_documents, docx_path)
        
        # Step 4: Store in Neo4j
        vector_store = documents_to_neo4j(chunked_documents, index_name=index_name)
        
        # Cleanup
        cleanup_images(images)
        
        logger.info("✅ Word document pipeline completed successfully")
        return vector_store
        
    except Exception as e:
        logger.error(f"❌ Word pipeline failed: {e}")
        raise
