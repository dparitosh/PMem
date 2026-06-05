"""
Ollama LLM Service
Provides local LLM integration for conversational guidance and recommendations
"""

import logging
import requests
import json
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class OllamaService:
    """Service for Ollama local LLM"""
    
    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "mistral"  # Or: llama2, neural-chat, etc.
    
    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL):
        """Initialize Ollama service"""
        self.base_url = base_url
        self.model = model
        self._available_models = None
    
    def health_check(self) -> bool:
        """Check if Ollama is running and accessible"""
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=3
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False
    
    def list_models(self) -> list:
        """Get list of available models"""
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                self._available_models = [m['name'] for m in data.get('models', [])]
                return self._available_models
            return []
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    def query(self, prompt: str, context: Optional[str] = None, temperature: float = 0.7) -> Optional[str]:
        """
        Query the LLM with optional context
        
        Args:
            prompt: User question
            context: Additional context from knowledge graph
            temperature: Creativity level (0-1)
        
        Returns:
            LLM response or None if error
        """
        try:
            # Build full prompt with context
            if context:
                full_prompt = f"""You are a manufacturing engineering assistant with access to product knowledge.

CONTEXT FROM KNOWLEDGE GRAPH:
{context}

USER QUESTION:
{prompt}

Provide a helpful, structured response based on the context."""
            else:
                full_prompt = prompt
            
            # Call Ollama API
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                    "temperature": temperature,
                    "timeout": 120
                },
                timeout=150
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                logger.error(f"Ollama query failed: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Ollama request timed out")
            return None
        except Exception as e:
            logger.error(f"Ollama query error: {e}")
            return None
    
    def generate_guidance(self, file_type: str, schema_info: Optional[Dict[str, Any]] = None) -> str:
        """Generate guidance message for user during import"""
        try:
            if schema_info:
                context = f"""
Schema Information:
- Entity Count: {schema_info.get('entity_count', 0)}
- DERIVE Attributes: {schema_info.get('derived_attributes', 0)}
- INVERSE Relationships: {schema_info.get('inverse_attributes', 0)}
- UNIQUE Constraints: {schema_info.get('unique_constraints', 0)}
- Schema References: {schema_info.get('reference_count', 0)}
"""
            else:
                context = None
            
            prompt = f"""Generate a brief, encouraging 2-3 sentence message for a user who just uploaded a {file_type} file 
for a manufacturing product ontology system. Highlight what will be possible once import completes."""
            
            response = self.query(prompt, context=context, temperature=0.5)
            return response or f"📤 {file_type} file uploaded successfully. Processing..."
            
        except Exception as e:
            logger.error(f"Failed to generate guidance: {e}")
            return f"📤 {file_type} file uploaded. Processing..."
    
    def generate_completion_message(self, schema_info: Dict[str, Any]) -> str:
        """Generate completion message with schema summary"""
        try:
            prompt = f"""Generate an enthusiastic but professional 3-4 sentence message confirming successful import.
Include: 
- Number of entities ({schema_info.get('entity_count', 0)})
- Key features (DERIVE: {schema_info.get('derived_attributes', 0)}, INVERSE: {schema_info.get('inverse_attributes', 0)})
- What user can now do (search, recommendations, change impact analysis)

Keep it friendly and actionable."""
            
            response = self.query(prompt, temperature=0.5)
            return response or "✓ Import completed successfully!"
            
        except Exception as e:
            logger.error(f"Failed to generate completion message: {e}")
            return "✓ Import completed successfully!"
    
    def answer_question(self, question: str, graph_context: Optional[str] = None, 
                        schema_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Answer a user question using LLM with graph context
        
        Returns: {
            'answer': str,
            'reasoning': str,
            'confidence': 0-1,
            'sources': list
        }
        """
        try:
            # Build context
            context = ""
            sources = []
            
            if schema_info:
                context += f"\n\nSCHEMA: {schema_info.get('entity_count', 0)} entities, "
                context += f"{schema_info.get('derived_attributes', 0)} computed properties"
                sources.append("schema-metadata")
            
            if graph_context:
                context += f"\n\nGRAPH DATA:\n{graph_context}"
                sources.append("neo4j-query")
            
            # Get response
            response = self.query(question, context=context, temperature=0.7)
            
            return {
                'answer': response or "Unable to answer question",
                'reasoning': f"Based on {', '.join(sources) if sources else 'general knowledge'}",
                'confidence': 0.8 if response else 0.3,
                'sources': sources,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to answer question: {e}")
            return {
                'answer': f"Error: {str(e)}",
                'reasoning': "error",
                'confidence': 0.0,
                'sources': [],
                'timestamp': datetime.now().isoformat()
            }


# Singleton instance
_ollama_service = None


def get_ollama_service(base_url: str = OllamaService.DEFAULT_BASE_URL, 
                      model: str = OllamaService.DEFAULT_MODEL) -> OllamaService:
    """Get or create Ollama service singleton"""
    global _ollama_service
    if _ollama_service is None:
        _ollama_service = OllamaService(base_url, model)
    return _ollama_service
