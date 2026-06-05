from langchain_neo4j import Neo4jVector
from .core.llm import embeddings
from neo4j import GraphDatabase
from typing import Dict, List
from langchain_core.documents import Document
from pathlib import Path
from dotenv import load_dotenv
import tiktoken
import time
import random
import logging
import os
from tqdm import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load encoder for sfr-embedding-mistral (same as gpt-4 or cl100k_base)
encoding = tiktoken.get_encoding("cl100k_base")

def _first_env(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip()
    return None


env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# --- Config ---
NEO4J_URL = _first_env("NEO4J_URI", "NEO4J_URL")
NEO4J_USERNAME = _first_env("NEO4J_USER", "NEO4J_USERNAME")
NEO4J_PASSWORD = _first_env("NEO4J_PASS", "NEO4J_PASSWORD")
INDEX_NAME = os.getenv("NEO4J_EMBEDDING_INDEX", "graph_embeddings")
EMBEDDING_PROPERTY = "embedding"
BATCH_SIZE = 15  # Process 10 embeddings at a time
MAX_RETRIES = 6
BASE_WAIT_TIME = 2  # Base wait time in seconds

missing = [
    key
    for key, value in {
        "NEO4J_URI": NEO4J_URL,
        "NEO4J_USER": NEO4J_USERNAME,
        "NEO4J_PASS": NEO4J_PASSWORD,
    }.items()
    if not value
]

if missing:
    raise ValueError(
        f"Missing Neo4j configuration in backend/.env: {', '.join(missing)}"
    )

# Convert all node properties (except embedding) to a string
def serialize_all_properties(props: dict) -> str:
    return ", ".join(f"{k}: {v}" for k, v in props.items() if k != EMBEDDING_PROPERTY)
    # def clean(value):
    #     if value is None:
    #         return ""
    #     if isinstance(value, list):
    #         return ", ".join(map(str, value))
    #     return str(value).strip()
 
    # parts = []
    # for key, value in props.items():
    #     if key == "embedding":
    #         continue
    #     readable_key = key.replace("_", " ").lower()
    #     sentence = f"The {readable_key} is {clean(value)}."
    #     parts.append(sentence)
    # return " ".join(parts)

# Create a function to serialize relationship properties including relationship type
def serialize_relationship_properties(rel_type: str, props: dict) -> str:
    def clean(value):
        if value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return str(value).strip()
    
    parts = [f"This is a {rel_type.lower()} relationship."]
    
    for key, value in props.items():
        if key == "embedding":
            continue
        readable_key = key.replace("_", " ").lower()
        sentence = f"The {readable_key} is {clean(value)}."
        parts.append(sentence)
    
    return " ".join(parts)

def batch_embed_queries(texts: List[str], retry_count=0):
    """
    Embed multiple texts with retry logic for rate limiting
    """
    if retry_count >= MAX_RETRIES:
        logger.error(f"Maximum retries ({MAX_RETRIES}) exceeded. Giving up on this batch.")
        return None
    
    try:
        # Process embeddings in a batch
        return [embeddings.embed_query(text) for text in texts]
    except Exception as e:
        # Handle all exceptions including rate limit errors
        wait_time = BASE_WAIT_TIME * (2 ** retry_count) + random.uniform(0, 1)
        logger.warning(f"Error occurred: {str(e)}. Retrying in {wait_time:.2f} seconds. (Attempt {retry_count + 1}/{MAX_RETRIES})")
        time.sleep(wait_time)
        return batch_embed_queries(texts, retry_count + 1)

def gather_graph_entities_without_embeddings():
    """
    Collect both nodes and relationships without embeddings.
    Returns two lists of documents ready for embedding.
    """
    driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    node_documents = []
    relationship_documents = []
    
    # Gather nodes without embeddings
    with driver.session() as session:
        query = f"""
        MATCH (n)
        WHERE n.{EMBEDDING_PROPERTY} IS NULL
        RETURN id(n) AS id, properties(n) AS props, labels(n) AS labels
        """
        result = session.run(query)
        records = list(result)
        
        logger.info(f"Found {len(records)} nodes without embeddings")

        for record in records:
            node_id = record["id"]
            props = record["props"]
            labels = record["labels"]
            text = serialize_all_properties(props).strip()
            
            # Include node labels in the document
            if labels:
                label_text = f"This is a {', '.join(labels)} node. "
                text = label_text + text
                
            if text:
                doc = Document(
                    page_content=text, 
                    metadata={
                        "entity_type": "node",
                        "node_id": node_id,
                        "labels": labels
                    }
                )
                node_documents.append(doc)
    
    # Gather relationships without embeddings
    # with driver.session() as session:
    #     query = f"""
    #     MATCH ()-[r]-()
    #     WHERE r.{EMBEDDING_PROPERTY} IS NOT NULL
    #     RETURN id(r) AS id, type(r) AS rel_type, properties(r) AS props, 
    #            id(startNode(r)) AS start_id, id(endNode(r)) AS end_id
    #     """
    #     result = session.run(query)
    #     records = list(result)
        
    #     logger.info(f"Found {len(records)} relationships without embeddings")

    #     for record in records:
    #         rel_id = record["id"]
    #         rel_type = record["rel_type"]
    #         props = record["props"]
    #         start_id = record["start_id"]
    #         end_id = record["end_id"]
            
    #         text = serialize_relationship_properties(rel_type, props).strip()
            
    #         if text:
    #             doc = Document(
    #                 page_content=text, 
    #                 metadata={
    #                     "entity_type": "relationship",
    #                     "relationship_id": rel_id,
    #                     "relationship_type": rel_type,
    #                     "start_node_id": start_id,
    #                     "end_node_id": end_id
    #                 }
    #             )
    #             relationship_documents.append(doc)
    
    return node_documents #relationship_documents

def process_entity_embeddings(documents):
    """
    Process embeddings for a list of documents (can be nodes or relationships).
    Saves embeddings back to the database.
    """
    if not documents:
        return
        
    driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    # Process in batches
    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i:i+BATCH_SIZE]
        texts = [doc.page_content for doc in batch]
        
        logger.info(f"Processing batch {i//BATCH_SIZE + 1}/{(len(documents) + BATCH_SIZE - 1)//BATCH_SIZE}")
        
        # Get embeddings for the batch
        batch_embeddings = batch_embed_queries(texts)
        
        if not batch_embeddings:
            logger.error(f"Failed to get embeddings for batch {i//BATCH_SIZE + 1}. Skipping.")
            continue
            
        # Save embeddings back to database entities
        with driver.session() as session:
            for doc, embedding in zip(batch, batch_embeddings):
                entity_type = doc.metadata["entity_type"]
                
                if entity_type == "node":
                    session.run(
                        f"""
                        MATCH (n) WHERE id(n) = $id
                        SET n.{EMBEDDING_PROPERTY} = $embedding
                        """,
                        id=doc.metadata["node_id"],
                        embedding=embedding
                    )
                elif entity_type == "relationship":
                    session.run(
                        f"""
                        MATCH ()-[r]-() WHERE id(r) = $id
                        SET r.{EMBEDDING_PROPERTY} = $embedding
                        """,
                        id=doc.metadata["relationship_id"],
                        embedding=embedding
                    )
        
        logger.info(f"✅ Batch {i//BATCH_SIZE + 1} processed and saved to database")
        
        # Add a small delay between batches to avoid rate limits
        if i + BATCH_SIZE < len(documents):
            time.sleep(1.0)

def update_graph_embeddings():
    """
    Main function to update embeddings for both nodes and relationships
    using a single vector index.
    """
    logger.info("Starting embedding update process")
    
    # Get all entities without embeddings
    # node_documents, relationship_documents = gather_graph_entities_without_embeddings()
    node_documents = gather_graph_entities_without_embeddings()
    # Combine all documents for processing
    all_documents = node_documents #+ relationship_documents
    
    if not all_documents:
        logger.info("✅ No entities found needing embeddings.")
        return
        
    # logger.info(f"Found total of {len(all_documents)} entities to process ({len(node_documents)} nodes, {len(relationship_documents)} relationships)")
    logger.info(f"Found total of {len(all_documents)} entities to process ({len(node_documents)} nodes)")
    # Process all documents
    # process_entity_embeddings(all_documents)
    
    # Add all processed documents to the vector index
    try:
        Neo4jVector.from_documents(
            documents=all_documents,
            embedding=embeddings,
            url=NEO4J_URL,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            index_name=INDEX_NAME,
            create_index_if_not_exists=True,
        )
        logger.info(f"✅ Indexed {len(all_documents)} entities in vector index.")
    except Exception as e:
        logger.error(f"Error creating vector index: {str(e)}")
        
    logger.info("Embedding update process completed")

# Run it
if __name__ == "__main__":
    update_graph_embeddings()


# from langchain_neo4j import Neo4jVector
# from core.llm import embeddings
# from neo4j import GraphDatabase
# from typing import Dict
# from langchain_core.documents import Document
# import tiktoken

# # Load encoder for sfr-embedding-mistral (same as gpt-4 or cl100k_base)
# encoding = tiktoken.get_encoding("cl100k_base")

# # --- Config ---
# NEO4J_URL = "bolt://10.161.116.244:7687"
# NEO4J_USERNAME = "neo4j"
# NEO4J_PASSWORD = "infineon"
# INDEX_NAME = "node_embeddings"
# EMBEDDING_PROPERTY = "embedding"


# # Convert all node properties (except embedding) to a string
# def serialize_all_properties(properties: Dict) -> str:
#     return ", ".join(f"{k}: {v}" for k, v in properties.items() if k != EMBEDDING_PROPERTY)

# # def serialize_all_properties(props: dict) -> str:
# #     def clean(value):
# #         if value is None:
# #             return ""
# #         if isinstance(value, list):
# #             return ", ".join(map(str, value))
# #         return str(value).strip()
 
# #     parts = []
# #     for key, value in props.items():
# #         if key == "embedding":
# #             continue
# #         readable_key = key.replace("_", " ").lower()
# #         sentence = f"The {readable_key} is {clean(value)}."
# #         parts.append(sentence)
# #     return " ".join(parts)

# def update_embeddings_for_new_nodes():
#     driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
#     documents = []
#     # metadatas = []

#     with driver.session() as session:
#         query = f"""
#         MATCH (n)
#         WHERE n.{EMBEDDING_PROPERTY} IS NULL
#         RETURN id(n) AS id, properties(n) AS props
#         """
#         result = session.run(query)

#         for record in result:
#             node_id = record["id"]
#             props = record["props"]
#             labels = record["labels"]
            
#             text = serialize_all_properties(props).strip()
#             # Include node labels in the document
#             if labels:
#                 label_text = f"This is a {', '.join(labels)} node. "
#                 text = label_text + text
#             # print(f"lenght the prop text:{len(encoding.encode(text))}")

#             if text:
#                 doc = Document(page_content=text, metadata={"node_id": node_id})
#                 documents.append(doc)
#                 # print(f"the page content is: {doc.page_content}")
#                 # metadatas.append({"node_id": node_id})

#     # if not documents:
#     #     print("✅ No new nodes found needing embeddings.")
#     #     return

#     # Add to vector index
#     # Neo4jVector.from_documents(
#     #     documents=documents,
#     #     embedding=embeddings,
#     #     url=NEO4J_URL,
#     #     username=NEO4J_USERNAME,
#     #     password=NEO4J_PASSWORD,
#     #     index_name=INDEX_NAME,
#     #     create_index_if_not_exists=True,
#     # )

#     print(f"✅ Embedded and indexed {len(documents)} new nodes.")

#     # Save embeddings back to nodes
#     with driver.session() as session:
#         for doc in documents:
#             print(f"doc is: {doc}")
#             # embeddings.embed_documents(doc)
#             embedding = embeddings.embed_query(doc.page_content)
#             # session.run(
#             #     f"""
#             #     MATCH (n) WHERE id(n) = $id
#             #     SET n.{EMBEDDING_PROPERTY} = $embedding
#             #     """,
#             #     id=doc.metadata["node_id"],
#             #     embedding=embedding
#             # )

#     print("✅ Embeddings saved back to nodes.")

# # Run it
# if __name__ == "__main__":
#     update_embeddings_for_new_nodes()


