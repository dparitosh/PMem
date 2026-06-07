import os
import logging
from urllib.parse import urlparse, urlunparse
from pathlib import Path
# from langchain_openai import AzureOpenAI
from langchain_openai import AzureOpenAIEmbeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings


from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def _first_env(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip()
    return None


env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# --- Configuration ---
AZURE_OPENAI_ENDPOINT = _first_env("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = _first_env("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = _first_env("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = _first_env("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT = _first_env("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT")
AZURE_OPENAI_EMBEDDINGS_ENDPOINT = _first_env("AZURE_OPENAI_EMBEDDINGS_ENDPOINT")
AZURE_OPENAI_EMBEDDINGS_VERSION = _first_env("AZURE_OPENAI_EMBEDDINGS_VERSION")


# ========== UNSTRUCTURED LLM CONFIGURATION (for document processing with vision) ==========
USE_UNSTRUCTURED_LLM = (_first_env("USE_UNSTRUCTURED_LLM") or "false").lower() == "true"
UNSTRUCTURED_LLM_TYPE = (_first_env("UNSTRUCTURED_LLM_TYPE") or "azure").lower()

# APIM Gateway for document processing
UNSTRUCTURED_APIM_ENDPOINT = _first_env("UNSTRUCTURED_APIM_ENDPOINT")
UNSTRUCTURED_APIM_SUBSCRIPTION_KEY = _first_env("UNSTRUCTURED_APIM_SUBSCRIPTION_KEY")
UNSTRUCTURED_APIM_API_VERSION = _first_env("UNSTRUCTURED_APIM_API_VERSION") or "2024-02-15-preview"

# Azure config for unstructured (fallback if APIM not available)
UNSTRUCTURED_AZURE_OPENAI_ENDPOINT = _first_env("UNSTRUCTURED_AZURE_OPENAI_ENDPOINT")
UNSTRUCTURED_AZURE_OPENAI_API_KEY = _first_env("UNSTRUCTURED_AZURE_OPENAI_API_KEY")
UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT = _first_env("UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT") or "gpt-4-vision"
UNSTRUCTURED_AZURE_OPENAI_API_VERSION = _first_env("UNSTRUCTURED_AZURE_OPENAI_API_VERSION") or "2024-02-15-preview"

# Ollama config for unstructured
UNSTRUCTURED_OLLAMA_BASE_URL = _first_env("UNSTRUCTURED_OLLAMA_BASE_URL") or "http://localhost:11434"
UNSTRUCTURED_OLLAMA_API_KEY = _first_env("UNSTRUCTURED_OLLAMA_API_KEY") or ""
UNSTRUCTURED_LLM_MODEL_NAME = _first_env("UNSTRUCTURED_LLM_MODEL_NAME") or "llava:7b"


# ========== LLM CONFIGURATION ==========
# Set to "azure" or "ollama"
USE_LLM = (_first_env("USE_LLM") or "ollama").lower()
USE_EMBEDDER = (_first_env("USE_EMBEDDER") or USE_LLM).lower()

OLLAMA_BASE_URL = _first_env("OLLAMA_BASE_URL") or "http://localhost:11434"
OLLAMA_API_KEY = _first_env("OLLAMA_API_KEY") or ""
LLM_MODEL_NAME = _first_env("LLM_MODEL_NAME") or "llama3:latest"
EMBED_MODEL_NAME = _first_env("EMBED_MODEL_NAME", "LLM_MODEL_NAME") or "nomic-embed-text:latest"


def _normalize_ollama_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    path = parsed.path.rstrip("/")
    for suffix in ("/api/generate", "/api/chat", "/chat"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


class UnavailableLLM:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def invoke(self, *args, **kwargs):
        raise RuntimeError(self._reason)

    def bind_tools(self, *args, **kwargs):
        return self


class UnavailableEmbeddings:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def embed_query(self, *args, **kwargs):
        raise RuntimeError(self._reason)

    def embed_documents(self, *args, **kwargs):
        raise RuntimeError(self._reason)


def _init_azure_llm() -> AzureChatOpenAI:
    missing = [
        key
        for key, value in {
            "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
            "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
            "AZURE_OPENAI_DEPLOYMENT": AZURE_OPENAI_DEPLOYMENT,
            "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing Azure OpenAI settings: {', '.join(missing)}")

    return AzureChatOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_deployment=AZURE_OPENAI_DEPLOYMENT,
        temperature=0,
        model_kwargs={
            "user": "user-1234",
        },
    )


def _init_azure_embeddings() -> AzureOpenAIEmbeddings:
    missing = [
        key
        for key, value in {
            "AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT": AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT,
            "AZURE_OPENAI_EMBEDDINGS_ENDPOINT": AZURE_OPENAI_EMBEDDINGS_ENDPOINT,
            "AZURE_OPENAI_EMBEDDINGS_VERSION": AZURE_OPENAI_EMBEDDINGS_VERSION,
            "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing Azure embeddings settings: {', '.join(missing)}")

    return AzureOpenAIEmbeddings(
        model=AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT,
        api_version=AZURE_OPENAI_EMBEDDINGS_VERSION,
        api_key=AZURE_OPENAI_API_KEY,
        azure_endpoint=AZURE_OPENAI_EMBEDDINGS_ENDPOINT,
    )


def _init_ollama_llm() -> ChatOllama:
    if not OLLAMA_BASE_URL or not LLM_MODEL_NAME:
        raise ValueError("Missing OLLAMA_BASE_URL or LLM_MODEL_NAME")
    kwargs = dict(model=LLM_MODEL_NAME, base_url=_normalize_ollama_base_url(OLLAMA_BASE_URL))
    if OLLAMA_API_KEY:
        kwargs["client_kwargs"] = {"headers": {"api-key": OLLAMA_API_KEY}}
    return ChatOllama(**kwargs)


def _init_ollama_embeddings() -> OllamaEmbeddings:
    if not OLLAMA_BASE_URL or not EMBED_MODEL_NAME:
        raise ValueError("Missing OLLAMA_BASE_URL or EMBED_MODEL_NAME")
    kwargs = dict(model=EMBED_MODEL_NAME, base_url=_normalize_ollama_base_url(OLLAMA_BASE_URL))
    if OLLAMA_API_KEY:
        kwargs["client_kwargs"] = {"headers": {"api-key": OLLAMA_API_KEY}}
    return OllamaEmbeddings(**kwargs)


# ========== UNSTRUCTURED LLM INITIALIZATION (for document processing) ==========
def _init_unstructured_apim_llm() -> AzureChatOpenAI:
    """Initialize Azure OpenAI LLM through APIM gateway (API Management)"""
    missing = [
        key
        for key, value in {
            "UNSTRUCTURED_APIM_ENDPOINT": UNSTRUCTURED_APIM_ENDPOINT,
            "UNSTRUCTURED_APIM_SUBSCRIPTION_KEY": UNSTRUCTURED_APIM_SUBSCRIPTION_KEY,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing APIM settings for unstructured LLM: {', '.join(missing)}")

    return AzureChatOpenAI(
        azure_endpoint=UNSTRUCTURED_APIM_ENDPOINT,
        api_key=UNSTRUCTURED_APIM_SUBSCRIPTION_KEY,
        api_version=UNSTRUCTURED_APIM_API_VERSION,
        azure_deployment=UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT,
        temperature=0,
        model_kwargs={"user": "document-processor"},
    )


def _init_unstructured_azure_llm() -> AzureChatOpenAI:
    """Initialize Azure OpenAI LLM for unstructured document processing (vision-capable)"""
    missing = [
        key
        for key, value in {
            "UNSTRUCTURED_AZURE_OPENAI_ENDPOINT": UNSTRUCTURED_AZURE_OPENAI_ENDPOINT,
            "UNSTRUCTURED_AZURE_OPENAI_API_KEY": UNSTRUCTURED_AZURE_OPENAI_API_KEY,
            "UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT": UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT,
            "UNSTRUCTURED_AZURE_OPENAI_API_VERSION": UNSTRUCTURED_AZURE_OPENAI_API_VERSION,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing unstructured Azure OpenAI settings: {', '.join(missing)}")

    return AzureChatOpenAI(
        azure_endpoint=UNSTRUCTURED_AZURE_OPENAI_ENDPOINT,
        api_key=UNSTRUCTURED_AZURE_OPENAI_API_KEY,
        api_version=UNSTRUCTURED_AZURE_OPENAI_API_VERSION,
        azure_deployment=UNSTRUCTURED_AZURE_OPENAI_DEPLOYMENT,
        temperature=0,
        model_kwargs={"user": "document-processor"},
    )


def _init_unstructured_ollama_llm() -> ChatOllama:
    """Initialize Ollama LLM for unstructured document processing (vision-capable like llava)"""
    if not UNSTRUCTURED_OLLAMA_BASE_URL or not UNSTRUCTURED_LLM_MODEL_NAME:
        raise ValueError("Missing UNSTRUCTURED_OLLAMA_BASE_URL or UNSTRUCTURED_LLM_MODEL_NAME")
    kwargs = dict(model=UNSTRUCTURED_LLM_MODEL_NAME, base_url=UNSTRUCTURED_OLLAMA_BASE_URL)
    if UNSTRUCTURED_OLLAMA_API_KEY:
        kwargs["client_kwargs"] = {"headers": {"api-key": UNSTRUCTURED_OLLAMA_API_KEY}}
    return ChatOllama(**kwargs)


# --- Initialize models with safe fallbacks ---
llm_azure_error = None
embeddings_azure_error = None
llm_ollama_error = None
embeddings_ollama_error = None

try:
    llm_azure = _init_azure_llm()
except Exception as exc:
    llm_azure_error = exc
    llm_azure = UnavailableLLM(f"Azure LLM unavailable: {exc}")

try:
    embeddings_azure = _init_azure_embeddings()
except Exception as exc:
    embeddings_azure_error = exc
    embeddings_azure = UnavailableEmbeddings(f"Azure embeddings unavailable: {exc}")

try:
    llm_ollama = _init_ollama_llm()
except Exception as exc:
    llm_ollama_error = exc
    llm_ollama = UnavailableLLM(f"Ollama LLM unavailable: {exc}")

try:
    embeddings_ollama = _init_ollama_embeddings()
except Exception as exc:
    embeddings_ollama_error = exc
    embeddings_ollama = UnavailableEmbeddings(f"Ollama embeddings unavailable: {exc}")


# --- Initialize unstructured LLM (document processing with vision) ---
unstructured_llm_error = None
unstructured_llm = None

if USE_UNSTRUCTURED_LLM:
    try:
        # Try APIM first if available
        if UNSTRUCTURED_APIM_ENDPOINT and UNSTRUCTURED_APIM_SUBSCRIPTION_KEY:
            unstructured_llm = _init_unstructured_apim_llm()
        elif UNSTRUCTURED_LLM_TYPE == "azure":
            unstructured_llm = _init_unstructured_azure_llm()
        elif UNSTRUCTURED_LLM_TYPE == "ollama":
            unstructured_llm = _init_unstructured_ollama_llm()
        else:
            raise ValueError(f"Unknown UNSTRUCTURED_LLM_TYPE: {UNSTRUCTURED_LLM_TYPE}")
    except Exception as exc:
        unstructured_llm_error = exc
        unstructured_llm = UnavailableLLM(f"Unstructured LLM unavailable: {exc}")
else:
    # Use main LLM as fallback for unstructured - will be set after llm is initialized
    unstructured_llm = None
    unstructured_llm_error = None


LLM_AVAILABLE = True
EMBEDDER_AVAILABLE = True
llm_error = None
embeddings_error = None

if USE_LLM == "azure":
    llm = llm_azure
    if llm_azure_error:
        LLM_AVAILABLE = False
        llm_error = llm_azure_error
elif USE_LLM == "ollama":
    llm = llm_ollama
    if llm_ollama_error:
        LLM_AVAILABLE = False
        llm_error = llm_ollama_error
else:
    LLM_AVAILABLE = False
    llm_error = ValueError("USE_LLM must be 'azure' or 'ollama'")
    llm = UnavailableLLM(str(llm_error))

# Now set unstructured_llm fallback after llm is defined
if not USE_UNSTRUCTURED_LLM and unstructured_llm is None:
    unstructured_llm = llm
    unstructured_llm_error = llm_error

if USE_EMBEDDER == "azure":
    embeddings = embeddings_azure
    if embeddings_azure_error:
        EMBEDDER_AVAILABLE = False
        embeddings_error = embeddings_azure_error
elif USE_EMBEDDER == "ollama":
    embeddings = embeddings_ollama
    if embeddings_ollama_error:
        EMBEDDER_AVAILABLE = False
        embeddings_error = embeddings_ollama_error
else:
    EMBEDDER_AVAILABLE = False
    embeddings_error = ValueError("USE_EMBEDDER must be 'azure' or 'ollama'")
    embeddings = UnavailableEmbeddings(str(embeddings_error))

if not LLM_AVAILABLE or not EMBEDDER_AVAILABLE:
    logger.warning("LLM/EMBEDDER MODEL NOT AVAILABLE")
    if llm_error:
        logger.error(f"LLM init error: {llm_error}")
    if embeddings_error:
        logger.error(f"Embedder init error: {embeddings_error}")
else:
    logger.info(f"Using {USE_LLM.upper()} LLM and {USE_EMBEDDER.upper()} embedder")

if USE_UNSTRUCTURED_LLM:
    if unstructured_llm_error:
        logger.error(f"⚠️ Unstructured LLM error: {unstructured_llm_error}")
    else:
        if UNSTRUCTURED_APIM_ENDPOINT:
            logger.info(f"Using APIM gateway for document processing (unstructured)")
        else:
            logger.info(f"Using {UNSTRUCTURED_LLM_TYPE.upper()} for document processing (unstructured)")



# print(llm.invoke("What is ollama?"))
# print("__")
# embedding = embeddings.embed_query("What is my name?")
# print(len(embedding))