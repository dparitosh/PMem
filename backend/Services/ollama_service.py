"""
Ollama LLM Service
Provides local LLM integration for conversational guidance and recommendations
"""

import logging
import requests
import os
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


class OllamaService:
    """Service for Ollama local LLM"""
    
    DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    DEFAULT_MODEL = os.getenv("LLM_MODEL_NAME", "mistral")
    DEFAULT_API_KEY = os.getenv("OLLAMA_API_KEY", "")
    
    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, api_key: str = DEFAULT_API_KEY):
        """Initialize Ollama service"""
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = model or self.DEFAULT_MODEL
        self.api_key = api_key or self.DEFAULT_API_KEY
        self._available_models = None

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    def _native_base_url(self) -> str:
        """Normalize configured endpoint to Ollama-native base URL.

        If the configured base URL points to a chat path (e.g. /api/chat),
        trim it so native /api/tags and /api/generate can be appended.
        """
        parsed = urlparse(self.base_url)
        path = parsed.path.rstrip("/")
        for suffix in ("/api/chat", "/chat", "/api/generate"):
            if path.endswith(suffix):
                path = path[: -len(suffix)]
                break
        if not path:
            path = ""
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")

    def _chat_style_query(self, full_prompt: str, temperature: float) -> Optional[str]:
        """Fallback for APIM/chat-style Ollama gateways."""
        try:
            response = requests.post(
                self.base_url,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "stream": False,
                    "temperature": temperature,
                },
                headers=self._headers(),
                timeout=150,
            )
            if response.status_code != 200:
                logger.error(f"Ollama chat-style query failed: {response.status_code}")
                return None
            result = response.json()
            choices = result.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content")
                if content:
                    return str(content).strip()
            if result.get("response"):
                return str(result.get("response")).strip()
            return None
        except Exception as e:
            logger.error(f"Ollama chat-style query error: {e}")
            return None
    
    def health_check(self) -> bool:
        """Check if Ollama is running and accessible
        
        Note: Azure APIM only exposes /api/generate endpoint, not /api/tags.
        We test by attempting a minimal generate request instead.
        Azure endpoints can be slow, so we use extended timeouts.
        """
        try:
            native_base = self._native_base_url()
            
            # Try /api/tags first (standard Ollama) with short timeout
            try:
                response = requests.get(
                    f"{native_base}/api/tags",
                    headers=self._headers(),
                    timeout=3,
                )
                if response.status_code == 200:
                    return True
            except (requests.Timeout, requests.ConnectionError):
                pass  # Azure doesn't support /api/tags, fall through
            except Exception:
                pass
            
            # Fallback: Test /api/generate (works for Azure APIM)
            # Azure can be very slow, use extended timeout (200s)
            try:
                response = requests.post(
                    f"{native_base}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": "test",
                        "stream": False,
                    },
                    headers=self._headers(),
                    timeout=200,  # Azure APIM can be very slow (200s max)
                )
                return response.status_code == 200
            except requests.Timeout:
                # Timeout on Azure is often transient, log it but don't fail
                logger.warning("Ollama health check timed out (Azure endpoint may be slow)")
                return False
            
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False
    
    def list_models(self) -> list:
        """Get list of available models"""
        try:
            native_base = self._native_base_url()
            response = requests.get(
                f"{native_base}/api/tags",
                headers=self._headers(),
                timeout=5,
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
            
            native_base = self._native_base_url()

            # Call Ollama native generate API first
            response = requests.post(
                f"{native_base}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                    "temperature": temperature,
                },
                headers=self._headers(),
                timeout=120,  # Azure APIM can be very slow; allow up to 2 minutes
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()

            # Fallback to chat-style endpoint if URL points to a chat path
            if self.base_url.endswith("/api/chat") or self.base_url.endswith("/chat"):
                fallback_response = self._chat_style_query(full_prompt, temperature)
                if fallback_response:
                    return fallback_response

            logger.error(f"Ollama query failed: HTTP {response.status_code} — {response.text[:200]}")
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
                      model: str = OllamaService.DEFAULT_MODEL,
                      api_key: str = OllamaService.DEFAULT_API_KEY) -> OllamaService:
    """Get or create Ollama service singleton"""
    global _ollama_service
    # Read model from environment at call time to respect runtime .env changes
    env_model = os.getenv('LLM_MODEL_NAME', model)
    env_api_key = os.getenv('OLLAMA_API_KEY', api_key)
    env_base = os.getenv('OLLAMA_BASE_URL', base_url)

    if _ollama_service is None or _ollama_service.model != env_model or _ollama_service.base_url != env_base or _ollama_service.api_key != env_api_key:
        _ollama_service = OllamaService(env_base, env_model, env_api_key)
    return _ollama_service
