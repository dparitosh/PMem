"""
Simple PDF to Neo4j Pipeline
Converts PDF pages to images, extracts content with LLM, creates LangChain documents, stores in Neo4j
"""
import os
import base64
from typing import List
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image
from langchain.docstore.document import Document
from langchain_neo4j import Neo4jVector
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter
from datetime import datetime
from .core.llm import embeddings, llm_azure

llm = llm_azure
def pdf_to_neo4j_pipeline(
    pdf_path: str,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    output_dir: str = "temp_images"
) -> Neo4jVector:
    """
    Complete pipeline: PDF → Images → LLM extraction → LangChain docs → Neo4j
    
    Args:
        pdf_path: Path to PDF file
        neo4j_uri: Neo4j database URI
        neo4j_username: Neo4j username
        neo4j_password: Neo4j password
        output_dir: Directory to save temporary images
    
    Returns:
        Neo4jVector: Vector store with all documents
    """
    
    # Step 1: Convert PDF to images
    print("📄 Converting PDF to images...")
    images = pdf_to_images(pdf_path, output_dir)
    print(f"✅ Created {len(images)} images")
    
    # Step 2: Extract content from images using LLM
    print("🤖 Extracting content with GPT-4 Vision...")
    page_documents = images_to_documents(images)
    print(f"✅ Extracted content from {len(page_documents)} pages")
    
    # Step 2.5: Combine all pages into a single document
    print("📝 Combining pages into single document...")
    combined_document = combine_pages_to_single_document(page_documents, pdf_path)
    print("✅ Created single combined document")
    
    # Step 2.6: Split into chunks for embedding (512 token limit)
    print("✂️ Splitting document into chunks for embedding...")
    chunked_documents = split_document_for_embedding(combined_document)
    print(f"✅ Created {len(chunked_documents)} chunks for embedding")
    
    # Step 3: Store in Neo4j
    print("🗄️ Storing in Neo4j...")
    vector_store = documents_to_neo4j(
        chunked_documents, neo4j_uri, neo4j_username, neo4j_password
    )
    print("✅ Stored in Neo4j successfully")
    
    # Cleanup temporary images
    cleanup_images(images)
    
    return vector_store


def pdf_to_images(pdf_path: str, output_dir: str = "temp_images") -> List[str]:
    """Convert PDF pages to images using PyMuPDF"""
    
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)
    
    # Open PDF with fitz
    doc = fitz.open(pdf_path)
    
    image_paths = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Convert page to image (PNG)
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
        pix = page.get_pixmap(matrix=mat)
        
        # Save as PNG
        image_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
        pix.save(image_path)
        image_paths.append(image_path)
    
    doc.close()
    return image_paths


def images_to_documents(image_paths: List[str]) -> List[Document]:
    """Extract content from images using imported LLM and create LangChain documents"""
    
    documents = []
    
    extraction_prompt = """
You are an expert document analyst specializing in comprehensive content extraction from PDF images. Your task is to extract ALL textual content from the provided PDF page image(s) while maintaining perfect structural integrity, context, and formatting for downstream RAG (Retrieval-Augmented Generation) applications.

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
  - Continue nesting as needed
- Preserve original indentation and spacing patterns
- Maintain parent-child relationships between sections

#### 3. FORMATTING PRESERVATION
- **Tables**: Convert to proper markdown table format with headers and alignment
- **Lists**: Maintain bullet points (•, -, *) and numbered lists (1., 2., etc.)
- **Text Styling**: Indicate **bold**, *italic*, and `code/monospace` text
- **Special Characters**: Preserve mathematical symbols, Greek letters, units, etc.
- **Line Breaks**: Maintain paragraph breaks and section separations
- **Columns**: If multi-column layout, clearly separate and label columns

#### 4. CONTEXTUAL INFORMATION
- Add [IMAGE], [FIGURE], [CHART], [DIAGRAM] placeholders where visual elements appear
- Include descriptive captions for any figures, charts, or diagrams
- Note relationships between text and visual elements
- Preserve cross-references and citations exactly as shown

#### 5. METADATA CAPTURE
- Document title, authors, publication info (if visible)
- Page numbers and section numbers
- Headers and footers content
- Date stamps, revision numbers, or version info

### OUTPUT FORMAT STRUCTURE:

```markdown
# Document Title (if visible)

## Metadata
- **Page Number**: [X]
- **Section**: [Section name if applicable]
- **Document Type**: [Technical manual, research paper, etc.]

## Content

[Extract all content here maintaining hierarchy and formatting]

### Tables
[Convert all tables to markdown format]

### Figures and Visual Elements
[List all visual elements with descriptions]

## Cross-References and Citations
[List any references, citations, or footnotes]

## Technical Specifications
[Any technical data, specifications, measurements, etc.]
```

### QUALITY ASSURANCE CHECKLIST:
Before submitting, verify:
- [ ] Every visible text element has been captured
- [ ] Hierarchical structure matches the original document
- [ ] Tables are properly formatted and complete
- [ ] Mathematical formulas and symbols are accurate
- [ ] Technical terminology is preserved exactly
- [ ] No content has been paraphrased or summarized
- [ ] Visual elements are appropriately noted
- [ ] Cross-references and page links are maintained

### SPECIAL HANDLING FOR TECHNICAL DOCUMENTS:
- **Code blocks**: Use ```language``` for any code snippets
- **Formulas**: Use LaTeX notation for mathematical expressions
- **Units**: Preserve all units of measurement exactly
- **Model numbers**: Capture all part numbers, model codes, and identifiers
- **Specifications**: Extract all technical specifications in structured format

### RAG OPTIMIZATION GUIDELINES:
- Create clear, searchable section headers
- Maintain semantic relationships between concepts
- Ensure technical terms are properly contextualized
- Structure content for easy chunking and retrieval
- Preserve all domain-specific terminology and jargon

### ERROR HANDLING:
- If text is unclear or partially obscured, note: [UNCLEAR: best_guess]
- If content is cut off at page edges, note: [PARTIAL: visible_content...]
- If images/charts cannot be fully described, note: [COMPLEX_VISUAL: brief_description]

Now proceed to extract the content from the provided PDF image(s) following these comprehensive guidelines.

Be thorough and extract every piece of visible information.
"""
    
    for i, image_path in enumerate(image_paths, 1):
        print(f"  Processing page {i}/{len(image_paths)}")
        
        # Encode image
        with open(image_path, 'rb') as f:
            encoded_image = base64.b64encode(f.read()).decode('ascii')
        
        # Create messages for LLM
        messages = [
            SystemMessage(content="Extract structured data from datasheet images."),
            HumanMessage(content=[
                {"type": "text", "text": extraction_prompt},
                {"type": "image", "image": encoded_image}
            ])
        ]
        
        # Extract content with imported LLM
        response = llm.invoke(messages)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Create LangChain document
        doc = Document(
            page_content=content,
            metadata={
                "source": os.path.basename(image_path),
                "page_number": i,
                "total_pages": len(image_paths),
                "processing_method": "gpt4_vision",
                "processed_at": datetime.now().isoformat(),
                "document_type": "datasheet"
            }
        )
        
        documents.append(doc)
    
    return documents


def combine_pages_to_single_document(page_documents: List[Document], pdf_path: str) -> Document:
    """Combine all page documents into a single document for the entire PDF/datasheet"""
    
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
        "document_type": "datasheet",
        "processing_method": "gpt4_vision_combined",
        "processed_at": datetime.now().isoformat(),
        "file_path": pdf_path
    }
    
    # Create single combined document
    combined_document = Document(
        page_content=combined_content.strip(),
        metadata=combined_metadata
    )
    
    return combined_document


def split_document_for_embedding(document: Document, chunk_size: int = 400, chunk_overlap: int = 50) -> List[Document]:
    """
    Split document into chunks suitable for 512-token embedding limit
    
    Args:
        document: Combined document to split
        chunk_size: Target characters per chunk (roughly 100 chars = 25 tokens)
        chunk_overlap: Overlap between chunks to preserve context
    
    Returns:
        List of chunked documents with preserved metadata
    """
    
    # Initialize text splitter optimized for datasheets
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=[
            "\n\n--- PAGE ",  # Preserve page boundaries
            "\n\n## ",       # Preserve section boundaries
            "\n\n### ",      # Preserve subsection boundaries
            "\n\n",          # Paragraph boundaries
            "\n",            # Line boundaries
            ". ",            # Sentence boundaries
            " ",             # Word boundaries
            ""               # Character boundaries
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
            "max_tokens": "512"
        })
        
        # Add context indicators
        if "--- PAGE " in chunk.page_content:
            # Extract page numbers this chunk contains
            import re
            page_numbers = re.findall(r"--- PAGE (\d+) ---", chunk.page_content)
            if page_numbers:
                chunk.metadata["contains_pages"] = page_numbers
    
    return chunks


def documents_to_neo4j(
    documents: List[Document],
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    index_name: str = "datasheet_index"
) -> Neo4jVector:
    """Store documents in Neo4j vector database"""
    
    # Create Neo4j vector store using imported embeddings
    vector_store = Neo4jVector.from_documents(
        documents=documents,
        embedding=embeddings,
        url=neo4j_uri,
        username=neo4j_username,
        password=neo4j_password,
        database = "windchilltest",
        index_name=index_name,
        node_label="DatasheetChunk",
        text_node_property="content"
    )
    
    return vector_store


def cleanup_images(image_paths: List[str]):
    """Remove temporary image files"""
    for image_path in image_paths:
        try:
            os.remove(image_path)
        except:
            pass
    
    # Remove directory if empty
    try:
        parent_dir = os.path.dirname(image_paths[0])
        os.rmdir(parent_dir)
    except:
        pass


def search_documents(vector_store: Neo4jVector, query: str, k: int = 5):
    """Search documents in the vector store"""
    results = vector_store.similarity_search(query, k=k)
    
    print(f"🔍 Found {len(results)} results for: '{query}'")
    for i, doc in enumerate(results, 1):
        chunk_info = f"Chunk {doc.metadata.get('chunk_id', '?')}/{doc.metadata.get('total_chunks', '?')}"
        pages_info = doc.metadata.get('contains_pages', ['Unknown'])
        pages_str = ', '.join(pages_info) if isinstance(pages_info, list) else str(pages_info)
        
        print(f"\n{i}. {doc.metadata.get('document_name', 'Unknown')} - {chunk_info}")
        print(f"   Contains pages: {pages_str}")
        print(f"   Source: {doc.metadata.get('source', 'Unknown')}")
        print(f"   Content preview: {doc.page_content[:200]}...")
    
    return results



# Usage example
if __name__ == "__main__":
    # Configuration
    PDF_PATH = "C:/App/DEPO_3DX_KG/Digital_thread/backend/Data/InductionMotor_TechnicalSpecification.pdf"
    NEO4J_URI = "neo4j://127.0.0.1:7687"
    NEO4J_USERNAME = "neo4j"
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
    
    try:
        # Run the pipeline
        vector_store = pdf_to_neo4j_pipeline(
            pdf_path=PDF_PATH,
            neo4j_uri=NEO4J_URI,
            neo4j_username=NEO4J_USERNAME,
            neo4j_password=NEO4J_PASSWORD
        )
        
        # Test search
        search_documents(vector_store, "TC33xEXT")
        search_documents(vector_store, "thermal characteristics")
        
    except Exception as e:
        print(f"❌ Error: {e}")
