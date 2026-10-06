"""
Ollama LLM Service
Provides local LLM integration for conversational guidance and recommendations
"""

import logging
import requests
import os
from typing import Optional, Dict, Any
from datetime import datetime
from backend.core.ollama_auth import ollama_base_url, ollama_generation_route, ollama_timeout

logger = logging.getLogger(__name__)


class OllamaService:
    """Service for Ollama local LLM"""
    
    DEFAULT_BASE_URL = "http://127.0.0.1:11434"
    DEFAULT_MODEL = os.getenv("LLM_MODEL_NAME") or os.getenv('OLLAMA_MODEL') or 'llama3:latest'
    DEFAULT_API_KEY = os.getenv("OLLAMA_API_KEY", "")
    
    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, api_key: str = DEFAULT_API_KEY):
        """Initialize Ollama service"""
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = model or self.DEFAULT_MODEL
        self.api_key = api_key if api_key is not None else self.DEFAULT_API_KEY
        self._available_models = None
        self._session = requests.Session()
        self._session.trust_env = False

    def _headers(self) -> Dict[str, str]:
        from backend.core.ollama_auth import ollama_headers
        return ollama_headers(self.base_url, self.api_key)

    def _native_base_url(self) -> str:
        """Use the shared, validated native API-root resolver."""
        return ollama_base_url(self.base_url)

    def _chat_style_query(self, full_prompt: str, temperature: float) -> Optional[str]:
        return self._request_query(full_prompt, temperature, 'chat')

    def _request_query(self, full_prompt: str, temperature: float, operation: str) -> Optional[str]:
        body = {'model': self.model, 'stream': False, 'options': {'temperature': temperature}}
        if operation == 'generate':
            body['prompt'] = full_prompt
        else:
            body['messages'] = [{'role': 'user', 'content': full_prompt}]
        response = self._session.post(
            self._native_base_url() + '/api/' + operation,
            json=body, headers=self._headers(), timeout=ollama_timeout())
        response.raise_for_status()
        result = response.json()
        content = result.get('response') if operation == 'generate' else result.get('message', {}).get('content')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Ollama returned no answer')
        return content.strip()

    def health_check(self) -> bool:
        """Check that the configured model appears in a valid model list."""
        models = self.list_models()
        return self.model in models or (':' not in self.model and self.model + ':latest' in models)

    def list_models(self) -> list:
        """Get list of available models"""
        try:
            native_base = self._native_base_url()
            response = self._session.get(
                f"{native_base}/api/tags",
                headers=self._headers(),
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                models = data.get('models')
                if not isinstance(models, list) or any(not isinstance(m, dict) or not isinstance(m.get('name') or m.get('model'), str) for m in models):
                    raise ValueError('Invalid Ollama model list')
                self._available_models = [m.get('name') or m.get('model') for m in models]
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
            
            _, operation = ollama_generation_route(self.base_url)
            return self._request_query(full_prompt, temperature, operation)

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
            
            if not response:
                raise RuntimeError('Ollama generation failed')
            return {
                'answer': response,
                'reasoning': f"Based on {', '.join(sources) if sources else 'general knowledge'}",
                'confidence': 0.8 if response else 0.3,
                'sources': sources,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to answer question: {e}")
            raise RuntimeError('Ollama generation failed') from e



# Singleton instance
_ollama_service = None


def get_ollama_service(base_url: str = OllamaService.DEFAULT_BASE_URL,
                      model: str = OllamaService.DEFAULT_MODEL,
                      api_key: str = OllamaService.DEFAULT_API_KEY) -> OllamaService:
    """Get or create Ollama service singleton"""
    global _ollama_service
    # Read model from environment at call time to respect runtime .env changes
    env_model = os.getenv('LLM_MODEL_NAME') or os.getenv('OLLAMA_MODEL') or model
    env_api_key = os.getenv('OLLAMA_API_KEY', api_key)
    env_base = (os.getenv('OLLAMA_API_URL', '').strip() or os.getenv('OLLAMA_BASE_URL', '').strip() or base_url)
    ollama_base_url() if os.getenv('OLLAMA_API_URL') or os.getenv('OLLAMA_BASE_URL') else ollama_base_url(env_base)

    if _ollama_service is None or _ollama_service.model != env_model or _ollama_service.base_url != env_base or _ollama_service.api_key != env_api_key:
        _ollama_service = OllamaService(env_base, env_model, env_api_key)
    return _ollama_service
