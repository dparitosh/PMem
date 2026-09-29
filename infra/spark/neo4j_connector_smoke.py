"""Read-only verification for the official Neo4j Connector for Apache Spark."""
import os

from pyspark.sql import SparkSession


auth_mode = os.getenv("NEO4J_AUTH_MODE", "token").strip().lower()
required = ("NEO4J_URI",) if auth_mode == "none" else ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASS")
missing = [key for key in required if not os.getenv(key)]
if missing:
    raise RuntimeError(f"Missing Neo4j configuration: {', '.join(missing)}")

builder = (
    SparkSession.builder.appName("depo-neo4j-spark-smoke")
    .config("neo4j.url", os.environ["NEO4J_URI"])
    .config("neo4j.authentication.type", "none" if auth_mode == "none" else "basic")
    .config("neo4j.database", os.getenv("NEO4J_DATABASE", "neo4j"))
)
if auth_mode != "none":
    builder = builder.config("neo4j.authentication.basic.username", os.environ["NEO4J_USER"])
    builder = builder.config("neo4j.authentication.basic.password", os.environ["NEO4J_PASS"])
spark = builder.getOrCreate()
try:
    rows = (
        spark.read.format("org.neo4j.spark.DataSource")
        .option("query", "RETURN 1 AS connector_smoke")
        .load()
        .collect()
    )
    if len(rows) != 1 or rows[0]["connector_smoke"] != 1:
        raise RuntimeError("Neo4j connector returned an unexpected smoke result")
    print("Neo4j Spark connector smoke passed")
finally:
    spark.stop()
