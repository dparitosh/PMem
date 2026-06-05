"""
PowerPoint to Neo4j Pipeline
Converts PowerPoint presentations to images, extracts content with LLM, creates LangChain documents, stores in Neo4j
Supports both AZURE and OLLAMA LLMs with vision capabilities
"""
import os
import base64
import logging
from typing import List, Optional, Tuple
from pathlib import Path
from pptx import Presentation
from PIL import Image, ImageDraw, ImageFont
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
        "PPT_SLIDE_DPI": int(os.getenv("PPT_SLIDE_DPI", "150")),
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

# ========== PowerPoint Processing ==========
def pptx_to_images(pptx_path: str, output_dir: str = "temp_images") -> List[str]:
    """
    Convert PowerPoint presentation to images using LibreOffice or python-pptx
    
    Args:
        pptx_path: Path to PowerPoint file
        output_dir: Directory to save temporary images
        
    Returns:
        List of image file paths
        
    Raises:
        FileNotFoundError: If file doesn't exist
        Exception: If conversion fails
    """
    try:
        if not os.path.exists(pptx_path):
            raise FileNotFoundError(f"PowerPoint file not found: {pptx_path}")
        
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"📊 Converting PowerPoint to images: {pptx_path}")
        
        image_paths = []
        
        # Try using LibreOffice first (better quality)
        try:
            temp_pdf = os.path.join(output_dir, "temp_presentation.pdf")
            
            # Convert PPTX to PDF using LibreOffice
            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", output_dir,
                pptx_path
            ]
            
            logger.info("  Converting PPTX to PDF via LibreOffice...")
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            
            if result.returncode == 0:
                # Convert PDF to images
                import fitz
                pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
                
                if os.path.exists(pdf_path):
                    doc = fitz.open(pdf_path)
                    
                    for page_num in range(len(doc)):
                        try:
                            page = doc.load_page(page_num)
                            mat = fitz.Matrix(2.0, 2.0)
                            pix = page.get_pixmap(matrix=mat)
                            
                            image_path = os.path.join(output_dir, f"slide_{page_num + 1}.png")
                            pix.save(image_path)
                            image_paths.append(image_path)
                            logger.info(f"  ✓ Converted slide {page_num + 1}/{len(doc)}")
                        except Exception as e:
                            logger.error(f"  ✗ Failed to convert slide {page_num + 1}: {e}")
                            raise
                    
                    doc.close()
                    
                    # Clean up temporary PDF
                    try:
                        os.remove(pdf_path)
                    except (OSError, FileNotFoundError) as e:
                        logger.warning(f"Could not remove temporary PDF {pdf_path}: {e}")
            else:
                logger.warning("  LibreOffice conversion failed, using python-pptx fallback...")
                image_paths = _extract_slides_as_images(pptx_path, output_dir)
        
        except Exception as e:
            logger.warning(f"  Image conversion failed: {e}, using python-pptx fallback...")
            image_paths = _extract_slides_as_images(pptx_path, output_dir)
        
        if not image_paths:
            raise Exception("No images could be generated from PowerPoint")
        
        logger.info(f"✅ Created {len(image_paths)} images from PowerPoint")
        return image_paths
        
    except Exception as e:
        logger.error(f"❌ Error converting PowerPoint to images: {e}")
        raise

def _extract_slides_as_images(pptx_path: str, output_dir: str) -> List[str]:
    """
    Fallback: Extract slide content and convert to images using python-pptx
    
    Args:
        pptx_path: Path to PowerPoint file
        output_dir: Directory to save images
        
    Returns:
        List of image file paths
    """
    try:
        logger.info("  Extracting slides as images via python-pptx...")
        
        presentation = Presentation(pptx_path)
        image_paths = []
        
        for slide_num, slide in enumerate(presentation.slides, 1):
            try:
                # Extract text from slide
                slide_text = f"--- SLIDE {slide_num} ---\n\n"
                
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_text += shape.text + "\n"
                
                # Create image from slide text
                img = Image.new('RGB', (1024, 768), color='white')
                draw = ImageDraw.Draw(img)
                
                # Try to use a default font
                try:
                    font = ImageFont.truetype("arial.ttf", 14)
                    title_font = ImageFont.truetype("arial.ttf", 18)
                except (OSError, IOError) as e:
                    logger.warning(f"Could not load truetype font, using default: {e}")
                    font = ImageFont.load_default()
                    title_font = font
                
                # Draw title
                draw.text((20, 20), f"Slide {slide_num}", fill='black', font=title_font)
                
                # Draw content
                y_offset = 60
                for line in slide_text.split("\n"):
                    if y_offset > 750:
                        break
                    
                    if line.strip():
                        # Wrap long lines
                        for subline in [line[i:i+80] for i in range(0, len(line), 80)]:
                            if y_offset > 750:
                                break
                            draw.text((30, y_offset), subline, fill='black', font=font)
                            y_offset += 18
                
                image_path = os.path.join(output_dir, f"slide_{slide_num}.png")
                img.save(image_path)
                image_paths.append(image_path)
                
                logger.info(f"  ✓ Created image for slide {slide_num}/{len(presentation.slides)}")
                
            except Exception as e:
                logger.error(f"  ✗ Failed to process slide {slide_num}: {e}")
                raise
        
        return image_paths
    
    except Exception as e:
        logger.error(f"❌ Error extracting slides: {e}")
        raise

def images_to_documents(image_paths: List[str], document_name: str = "PowerPoint Presentation") -> List[Document]:
    """
    Extract content from slide images using LLM with vision capability
    
    Args:
        image_paths: List of image file paths
        document_name: Name of the source presentation
        
    Returns:
        List of LangChain Document objects
    """
    try:
        logger.info(f"🤖 Extracting content from {len(image_paths)} slides with LLM vision...")
        
        documents = []
        extraction_prompt = """
You are an expert presentation analyst. Extract ALL textual and visual content from this PowerPoint slide image.

### EXTRACTION REQUIREMENTS:
- Extract **every word, number, bullet point, and symbol** visible
- Maintain hierarchical structure with markdown (# ## ### ####)
- Format tables and data in markdown
- Preserve all lists and bullet structures
- Indicate **bold**, *italic*, and any text styling
- Describe charts, diagrams, images with [CHART], [DIAGRAM], [IMAGE] tags
- Include all annotations and speaker notes visible
- Preserve slide numbers and transitions if visible

### OUTPUT:
Provide clean, structured markdown with all slide content and descriptions.
"""
        
        for i, image_path in enumerate(image_paths, 1):
            try:
                logger.info(f"  Processing slide {i}/{len(image_paths)}")
                
                # Encode image
                with open(image_path, 'rb') as f:
                    encoded_image = base64.b64encode(f.read()).decode('ascii')
                
                # Create messages for LLM
                messages = [
                    SystemMessage(content="Extract structured data from PowerPoint slide images. You have vision capabilities."),
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
                        "slide_number": i,
                        "total_slides": len(image_paths),
                        "processing_method": "llm_vision",
                        "processed_at": datetime.now().isoformat(),
                        "document_type": "powerpoint",
                        "format": "pptx",
                        "document_name": document_name
                    }
                )
                
                documents.append(doc)
                logger.info(f"  ✓ Extracted slide {i}")
                
            except Exception as e:
                logger.error(f"  ✗ Failed to extract slide {i}: {e}")
                raise
        
        logger.info(f"✅ Extracted content from {len(documents)} slides")
        return documents
        
    except Exception as e:
        logger.error(f"❌ Error extracting content from slides: {e}")
        raise

def combine_and_split_documents(page_documents: List[Document], pptx_path: str, chunk_size: int = None, chunk_overlap: int = None) -> List[Document]:
    """
    Combine slides and split into chunks for embedding
    
    Args:
        page_documents: List of slide documents
        pptx_path: Original presentation path
        chunk_size: Target characters per chunk
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of chunked documents
    """
    try:
        chunk_size = chunk_size or CONFIG["DOCUMENT_CHUNK_SIZE"]
        chunk_overlap = chunk_overlap or CONFIG["DOCUMENT_CHUNK_OVERLAP"]
        
        logger.info("📝 Combining and chunking presentation...")
        
        # Combine all slide content
        combined_content = ""
        for i, doc in enumerate(page_documents, 1):
            combined_content += f"\n\n--- SLIDE {i} ---\n\n"
            combined_content += doc.page_content
        
        # Create combined document
        doc_name = os.path.splitext(os.path.basename(pptx_path))[0]
        combined_metadata = {
            "source": doc_name,
            "document_name": doc_name,
            "total_slides": len(page_documents),
            "document_type": "powerpoint",
            "processing_method": "llm_vision_combined",
            "processed_at": datetime.now().isoformat(),
            "file_path": pptx_path,
            "format": "pptx"
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
                "\n\n--- SLIDE ",
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

def pptx_to_neo4j_pipeline(
    pptx_path: str,
    output_dir: str = None,
    index_name: str = None
) -> Neo4jVector:
    """
    Complete pipeline: PowerPoint → Images → LLM extraction → LangChain docs → Neo4j
    
    Args:
        pptx_path: Path to PowerPoint file
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
        
        # Step 1: Convert PowerPoint to images
        images = pptx_to_images(pptx_path, output_dir)
        
        # Step 2: Extract content from images
        doc_name = os.path.splitext(os.path.basename(pptx_path))[0]
        page_documents = images_to_documents(images, doc_name)
        
        # Step 3: Combine and split
        chunked_documents = combine_and_split_documents(page_documents, pptx_path)
        
        # Step 4: Store in Neo4j
        vector_store = documents_to_neo4j(chunked_documents, index_name=index_name)
        
        # Cleanup
        cleanup_images(images)
        
        logger.info("✅ PowerPoint pipeline completed successfully")
        return vector_store
        
    except Exception as e:
        logger.error(f"❌ PowerPoint pipeline failed: {e}")
        raise
