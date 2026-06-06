"""
Centralized Neo4j Database Configuration & Connection Management
================================================================

This module provides:
- Unified environment configuration with fallbacks
- Singleton Neo4j driver instance management
- Connection pooling and lifecycle management
- Support for both Aura (neo4j+s://) and on-premises (bolt://) deployments
- SSL/TLS configuration
- Connection timeout management

Usage:
    from backend.core.db_config import get_driver, get_config, Neo4jConfig
    
    driver = get_driver()
    config = get_config()
    
    # For context managers:
    from backend.core.db_config import Neo4jConnection
    with Neo4jConnection() as session:
        result = session.run("MATCH (n) RETURN count(n) as count")
"""

import os
import logging
import time
from typing import Optional, Dict, Any
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass
from enum import Enum
import atexit

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver, Session
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class Neo4jDeploymentType(Enum):
    """Neo4j deployment type"""
    AURA = "aura"  # neo4j+s://
    ON_PREMISES = "on_premises"  # bolt://
    ENTERPRISE = "enterprise"  # bolt+s://


@dataclass
class Neo4jConfig:
    """Neo4j connection configuration"""
    uri: str
    username: str
    password: str
    database: str = "neo4j"
    deployment_type: Neo4jDeploymentType = Neo4jDeploymentType.AURA
    
    # Connection pool settings
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: float = 60.0
    connection_timeout: float = 30.0
    socket_keep_alive: bool = True
    socket_connection_timeout: float = 15.0
    
    # Query settings
    query_timeout: int = 30  # seconds
    
    # SSL/TLS
    encrypted: bool = True
    trust_system_ca_signed_certificates: bool = True
    trust_custom_ca_signed_certificates: Optional[str] = None
    
    # Metadata
    user_agent: str = "depo-ontology/1.0.0"
    
    def __repr__(self) -> str:
        """Representation without exposing password"""
        return (
            f"Neo4jConfig(uri={self.uri}, username={self.username}, "
            f"database={self.database}, deployment={self.deployment_type.value})"
        )


class Neo4jConfigError(Exception):
    """Neo4j configuration error"""
    pass


def _get_env(*keys: str) -> Optional[str]:
    """Get first available environment variable from keys list"""
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip()
    return None


def _has_placeholder_neo4j_uri() -> bool:
    """Return True when the active process env still has a template Neo4j URI."""
    uri = _get_env("NEO4J_URI", "NEO4J_URL", "Neo4j_url")
    return bool(uri and "your-neo4j-instance" in uri)


def _detect_deployment_type(uri: str) -> Neo4jDeploymentType:
    """Detect deployment type from URI scheme"""
    if uri.startswith("neo4j+s://"):
        return Neo4jDeploymentType.AURA
    elif uri.startswith("bolt+s://"):
        return Neo4jDeploymentType.ENTERPRISE
    elif uri.startswith("bolt://"):
        return Neo4jDeploymentType.ON_PREMISES
    else:
        # Default to Aura for neo4j+s if scheme not recognized
        return Neo4jDeploymentType.AURA


def _load_environment() -> None:
    """Load environment variables from centralized .env file (SINGLE SOURCE OF TRUTH)"""
    # CENTRALIZED: Load from requirements/.env in project root FIRST
    # This ensures all scripts (root and backend) use the SAME configuration
    # db_config.py is at: Depo_onto/backend/core/db_config.py
    # Need to go up 4 levels to project root, then into requirements/
    possible_paths = [
        Path(__file__).parent.parent.parent / "requirements" / ".env",  # Project root: requirements/.env (PRIMARY)
        Path(__file__).parent.parent / ".env",  # Fallback: backend/.env
        Path.cwd() / ".env",  # Fallback: Current working directory
        Path.cwd() / "requirements" / ".env",  # Fallback: requirements/ from cwd
    ]
    
    for env_path in possible_paths:
        if env_path.exists():
            load_dotenv(env_path, override=_has_placeholder_neo4j_uri())
            logger.debug(f"Loaded environment from {env_path}")
            return
    
    logger.warning(
        "No .env file found in standard locations. "
        "Using environment variables or defaults. "
        "Recommended: Set environment variables or create requirements/.env"
    )


@lru_cache(maxsize=1)
def get_config() -> Neo4jConfig:
    """
    Get Neo4j configuration from environment variables with fallbacks.
    
    Environment Variable Precedence:
    - URI: NEO4J_URI > NEO4J_URL > Neo4j_url
    - Username: NEO4J_USER > NEO4J_USERNAME > Neo4j_user
    - Password: NEO4J_PASS > NEO4J_PASSWORD > Neo4j_password
    - Database: NEO4J_DATABASE > Neo4j_database
    
    Returns:
        Neo4jConfig: Configuration object
        
    Raises:
        Neo4jConfigError: If required configuration is missing
    """
    # Ensure environment is loaded
    _load_environment()
    
    # Get configuration values with fallbacks
    uri = _get_env("NEO4J_URI", "NEO4J_URL", "Neo4j_url")
    username = _get_env("NEO4J_USER", "NEO4J_USERNAME", "Neo4j_user")
    password = _get_env("NEO4J_PASS", "NEO4J_PASSWORD", "Neo4j_password")
    database = _get_env("NEO4J_DATABASE", "Neo4j_database") or "neo4j"
    
    # Validate required fields
    missing = []
    if not uri:
        missing.append("NEO4J_URI (or NEO4J_URL)")
    if not username:
        missing.append("NEO4J_USER (or NEO4J_USERNAME)")
    if not password:
        missing.append("NEO4J_PASS (or NEO4J_PASSWORD)")
    
    if missing:
        error_msg = f"Missing required Neo4j configuration: {', '.join(missing)}"
        logger.error(error_msg)
        raise Neo4jConfigError(error_msg)
    
    # Detect deployment type from URI
    deployment_type = _detect_deployment_type(uri)
    
    # Optional: Custom SSL configuration
    custom_ca = os.getenv("NEO4J_CUSTOM_CA_PATH")
    
    default_encrypted = deployment_type != Neo4jDeploymentType.ON_PREMISES
    encrypted_env = os.getenv("NEO4J_ENCRYPTED")

    config = Neo4jConfig(
        uri=uri,
        username=username,
        password=password,
        database=database,
        deployment_type=deployment_type,
        # Connection pool settings
        max_connection_pool_size=int(os.getenv("NEO4J_MAX_POOL_SIZE", "50")),
        connection_acquisition_timeout=float(
            os.getenv("NEO4J_CONNECTION_ACQUISITION_TIMEOUT", "60")
        ),
        connection_timeout=float(
            os.getenv("NEO4J_CONNECTION_TIMEOUT", "30")
        ),
        socket_keep_alive=os.getenv("NEO4J_SOCKET_KEEP_ALIVE", "true").lower() == "true",
        socket_connection_timeout=float(
            os.getenv("NEO4J_SOCKET_CONNECTION_TIMEOUT", "15")
        ),
        # Query settings
        query_timeout=int(os.getenv("NEO4J_QUERY_TIMEOUT", "30")),
        # SSL settings
        encrypted=(
            encrypted_env.lower() == "true"
            if encrypted_env is not None
            else default_encrypted
        ),
        trust_system_ca_signed_certificates=os.getenv(
            "NEO4J_TRUST_SYSTEM_CA", "true"
        ).lower() == "true",
        trust_custom_ca_signed_certificates=custom_ca,
    )
    
    logger.info(f"Neo4j configuration loaded: {config}")
    return config


class Neo4jDriverPool:
    """
    Singleton Neo4j driver pool manager.
    
    Provides:
    - Lazy initialization of driver
    - Connection pooling
    - Automatic reconnection on failure
    - Proper resource cleanup
    """
    
    _instance: Optional["Neo4jDriverPool"] = None
    _driver: Optional[Driver] = None
    _config: Optional[Neo4jConfig] = None
    _last_connection_error_time: float = 0.0
    _RECONNECTION_COOLDOWN: float = 60.0  # seconds
    
    def __new__(cls) -> "Neo4jDriverPool":
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_driver(self) -> Driver:
        """
        Get or create the Neo4j driver instance.
        
        Uses exponential backoff with cooldown to prevent hammering
        a paused or unavailable database.
        
        Returns:
            neo4j.Driver: Connected driver instance
            
        Raises:
            Neo4jConfigError: If configuration is invalid
            Exception: If driver creation fails (after cooldown)
        """
        # Return existing driver if available
        if self._driver is not None:
            return self._driver
        
        # Allow override of cooldown via env for easier debugging
        try:
            self._RECONNECTION_COOLDOWN = float(os.getenv("NEO4J_RECONNECTION_COOLDOWN", str(self._RECONNECTION_COOLDOWN)))
        except Exception:
            pass

        # Check cooldown to prevent repeated connection attempts
        current_time = time.time()
        if self._last_connection_error_time:
            elapsed = current_time - self._last_connection_error_time
            if elapsed < self._RECONNECTION_COOLDOWN:
                remaining = self._RECONNECTION_COOLDOWN - elapsed
                error_msg = (
                    f"Neo4j driver unavailable. "
                    f"Retry in {int(remaining)}s. "
                    f"AuraDB may be paused — check console.neo4j.io"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
        
        try:
            # Get configuration
            config = get_config()
            self._config = config

            # Helper: check DNS resolution for the host portion of the URI
            def _is_host_resolvable(uri: str, timeout: float = 3.0) -> bool:
                try:
                    host = urlparse(uri).hostname or uri
                    # Temporarily set default timeout for resolution
                    old = socket.getdefaulttimeout()
                    socket.setdefaulttimeout(timeout)
                    try:
                        socket.getaddrinfo(host, None)
                        return True
                    finally:
                        socket.setdefaulttimeout(old)
                except Exception:
                    return False
            
            # ✅ FIXED: Build driver kwargs based on deployment type
            # neo4j+s:// and bolt+s:// handle encryption automatically
            # Don't pass encryption settings for these schemes
            # Note: socket_keep_alive and socket_connection_timeout are not valid Neo4j driver params
            driver_kwargs = {
                'max_connection_pool_size': config.max_connection_pool_size,
                'connection_acquisition_timeout': config.connection_acquisition_timeout,
                'connection_timeout': config.connection_timeout,
                'user_agent': config.user_agent,
            }
            
            # Only add encryption settings for schemes that support them
            # neo4j+s:// and bolt+s:// handle encryption automatically
            if config.deployment_type != Neo4jDeploymentType.AURA:
                # For on-premises (bolt:// or bolt+s://), add encryption settings
                if config.encrypted or config.deployment_type == Neo4jDeploymentType.ENTERPRISE:
                    driver_kwargs['encrypted'] = config.encrypted
                    driver_kwargs['trust_system_ca_signed_certificates'] = config.trust_system_ca_signed_certificates
                    if config.trust_custom_ca_signed_certificates:
                        driver_kwargs['custom_trust'] = config.trust_custom_ca_signed_certificates
            
            # Create driver with appropriate settings
            # Defensive: ensure unsupported keys are not passed to the neo4j driver.
            # Some environments historically exported socket_* keys which are not
            # accepted by newer neo4j Python drivers and will raise ConfigurationError.
            unsupported_keys = {"socket_keep_alive", "socket_connection_timeout"}
            for k in list(driver_kwargs.keys()):
                if k in unsupported_keys:
                    logger.warning("Removing unsupported Neo4j driver kwarg: %s", k)
                    driver_kwargs.pop(k, None)

            # If the variables are present in the environment / config, log a note
            # to help operators clean up their .env files.
            # Only warn if the operator actually set the corresponding NEO4J_* env var
            env_name_map = {
                "socket_keep_alive": "NEO4J_SOCKET_KEEP_ALIVE",
                "socket_connection_timeout": "NEO4J_SOCKET_CONNECTION_TIMEOUT",
            }
            for k, env_var in env_name_map.items():
                if os.getenv(env_var) is not None:
                    logger.warning(
                        "NEO4J env var %s is set but will be ignored by the driver."
                        " Consider removing %s from backend/.env",
                        env_var,
                        env_var,
                    )

            # Create the driver. Some neo4j Python driver versions are strict about
            # kwarg names and will raise ConfigurationError for unknown keys.
            # Be defensive: if we ever hit that, drop the unexpected keys and retry.
            try:
                self._driver = GraphDatabase.driver(
                    config.uri,
                    auth=(config.username, config.password),
                    database=config.database,
                    **driver_kwargs,
                )
            except Exception as create_exc:
                try:
                    from neo4j.exceptions import ConfigurationError
                except Exception:
                    ConfigurationError = None

                if ConfigurationError is not None and isinstance(create_exc, ConfigurationError):
                    msg = str(create_exc)
                    if "Unexpected config keys:" in msg:
                        unexpected = msg.split("Unexpected config keys:", 1)[1]
                        unexpected_keys = [k.strip() for k in unexpected.split(",") if k.strip()]
                        if unexpected_keys:
                            for k in unexpected_keys:
                                if k in driver_kwargs:
                                    logger.warning("Dropping unsupported Neo4j driver kwarg and retrying: %s", k)
                                    driver_kwargs.pop(k, None)
                            self._driver = GraphDatabase.driver(
                                config.uri,
                                auth=(config.username, config.password),
                                database=config.database,
                                **driver_kwargs,
                            )
                        else:
                            raise
                    else:
                        raise
                else:
                    raise
            
            # Test connection
            with self._driver.session(database=config.database) as session:
                session.run("RETURN 1")
            
            logger.info(
                f"Neo4j driver created successfully "
                f"(Deployment: {config.deployment_type.value})"
            )
            
            # Reset error tracking
            self._last_connection_error_time = 0.0
            
            return self._driver
            
        except Exception as exc:
            self._driver = None
            self._last_connection_error_time = current_time
            # Additional diagnostics for routing information failures
            msg = str(exc)
            # Detect routing or DNS resolution failures and provide DNS diagnostics
            if (
                "Unable to retrieve routing information" in msg
                or "routing" in msg.lower()
                or "cannot resolve address" in msg.lower()
                or "getaddrinfo" in msg.lower()
                or "resolve" in msg.lower()
            ):
                try:
                    host = urlparse(get_config().uri).hostname
                except Exception:
                    host = None

                if host:
                    resolvable = _is_host_resolvable(host)
                    logger.error(
                        "Routing information error for host %s (resolvable=%s)."
                        " Ensure DNS and network connectivity to the Aura endpoint.",
                        host,
                        resolvable,
                    )
                else:
                    logger.error("Routing information error and host could not be determined.")

            error_msg = (
                f"Failed to create Neo4j driver. "
                f"Check NEO4J_URI, NEO4J_USER, NEO4J_PASS in backend/.env. "
                f"Error: {exc}"
            )
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from exc
    
    def close(self) -> None:
        """Close the driver connection"""
        if self._driver is not None:
            try:
                self._driver.close()
                # Avoid calling the logging subsystem during interpreter shutdown
                # (logging handlers may be closed and cause "Logging error" messages).
                try:
                    import sys as _sys
                    _sys.stderr.write("Neo4j driver closed\n")
                except Exception:
                    pass
            except Exception as exc:
                try:
                    import sys as _sys
                    _sys.stderr.write(f"Error closing driver: {exc}\n")
                except Exception:
                    pass
            finally:
                self._driver = None
    
    def reset(self) -> None:
        """Reset the driver (close and clear cache)"""
        self.close()
        # Clear the lru_cache for get_config
        get_config.cache_clear()
        self._config = None


# Global singleton instance
_pool = Neo4jDriverPool()


def get_driver() -> Driver:
    """
    Get the Neo4j driver instance (convenience function).
    
    Returns:
        neo4j.Driver: Connected driver instance
        
    Usage:
        driver = get_driver()
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n)")
    """
    return _pool.get_driver()


def close_driver() -> None:
    """Close and cleanup the Neo4j driver"""
    _pool.close()


def reset_driver() -> None:
    """Reset the Neo4j driver (for testing or reconfiguration)"""
    _pool.reset()


# Ensure driver is closed cleanly on process exit to avoid relying on destructor
atexit.register(close_driver)


class Neo4jConnection:
    """Context manager for Neo4j sessions"""
    
    def __init__(self, database: Optional[str] = None):
        """
        Initialize connection manager.
        
        Args:
            database: Optional database name override
        """
        self.database = database
        self.session: Optional[Session] = None
    
    def __enter__(self) -> Session:
        """Enter context - create session"""
        driver = get_driver()
        self.session = driver.session(database=self.database or "neo4j")
        return self.session
    
    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        """Exit context - close session"""
        if self.session:
            try:
                self.session.close()
            except Exception as exc:
                logger.error(f"Error closing session: {exc}")


def get_connection_info() -> Dict[str, Any]:
    """
    Get current Neo4j connection information for debugging.
    
    Returns:
        Dictionary with connection details (password redacted)
    """
    try:
        config = get_config()
        return {
            "uri": config.uri,
            "username": config.username,
            "password": "***REDACTED***",
            "database": config.database,
            "deployment_type": config.deployment_type.value,
            "pool_size": config.max_connection_pool_size,
            "connected": _pool._driver is not None,
        }
    except Exception as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    """Test module"""
    logging.basicConfig(level=logging.INFO)
    
    try:
        logger.info("Checking Neo4j Configuration...")
        config = get_config()
        logger.info("Configuration loaded: URI=%s, User=%s, Database=%s, Deployment=%s",
                    config.uri, config.username, config.database, config.deployment_type.value)

        logger.info("Testing connection...")
        driver = get_driver()
        logger.info("Driver created successfully")

        with driver.session(database=config.database) as session:
            result = session.run("RETURN 1 as test")
            logger.info("Connection test successful: %s", result.single())

        logger.info("All checks passed")

    except Exception as exc:
        logger.exception("Error while testing Neo4j configuration: %s", exc)
        exit(1)
