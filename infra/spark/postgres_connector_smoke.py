"""Read-only Spark JDBC connectivity smoke test for customer PostgreSQL."""
from backend.data_pipeline_service.postgres_jdbc import read_probe

from pyspark.sql import SparkSession


spark = SparkSession.builder.appName("depo-postgres-jdbc-smoke").getOrCreate()
try:
    if read_probe(spark) != 1:
        raise RuntimeError("PostgreSQL JDBC probe returned an unexpected value")
    print("DEPO Spark PostgreSQL JDBC smoke test passed.")
finally:
    spark.stop()
