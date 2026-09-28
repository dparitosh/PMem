"""Validated PostgreSQL JDBC configuration for the optional Spark data plane."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


class PostgresJdbcConfigurationError(RuntimeError):
    pass


def enabled() -> bool:
    return os.getenv("DEPO_SPARK_POSTGRES_ENABLED", "false").strip().lower() == "true"


def configuration() -> dict[str, str]:
    dsn = (os.getenv("DEPO_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    driver_jar = Path(os.getenv("DEPO_SPARK_POSTGRES_DRIVER_JAR", "").strip())
    if not dsn:
        raise PostgresJdbcConfigurationError("DEPO_DATABASE_URL is required for Spark PostgreSQL JDBC")
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname or not parsed.path.strip("/"):
        raise PostgresJdbcConfigurationError("DEPO_DATABASE_URL must be a PostgreSQL URL with host and database")
    if parsed.fragment:
        raise PostgresJdbcConfigurationError("DEPO_DATABASE_URL must not contain a URL fragment")
    if not parsed.username:
        raise PostgresJdbcConfigurationError("DEPO_DATABASE_URL must include the application user for Spark PostgreSQL JDBC")
    if not driver_jar.is_absolute() or not driver_jar.is_file() or driver_jar.suffix.lower() != ".jar":
        raise PostgresJdbcConfigurationError("DEPO_SPARK_POSTGRES_DRIVER_JAR must be an existing absolute .jar path")
    if any(key.lower() in {"user", "password"} for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise PostgresJdbcConfigurationError("Put PostgreSQL credentials in URL userinfo, not query parameters")
    try:
        port = parsed.port or 5432
    except ValueError as exc:
        raise PostgresJdbcConfigurationError("DEPO_DATABASE_URL contains an invalid PostgreSQL port") from exc
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    authority = f"{host}:{port}"
    query = f"?{parsed.query}" if parsed.query else ""
    return {
        "url": f"jdbc:postgresql://{authority}/{parsed.path.strip('/')}{query}",
        "user": unquote(parsed.username),
        "password": unquote(parsed.password or ""),
        "driver": "org.postgresql.Driver",
        "driver_jar": str(driver_jar.resolve()),
    }


def read_probe(spark) -> int:
    """Execute a bounded read-only JDBC probe without exposing credentials."""
    config = configuration()
    frame = (
        spark.read.format("jdbc")
        .option("url", config["url"])
        .option("driver", config["driver"])
        .option("user", config["user"])
        .option("password", config["password"])
        .option("query", "SELECT 1 AS connectivity_check")
        .load()
    )
    row = frame.first()
    return int(row["connectivity_check"])
