"""Small deterministic Spark smoke job for the optional DEPO execution plane."""
from __future__ import annotations

import json
import os
from pyspark.sql import SparkSession


def main() -> None:
    warehouse = os.getenv("DEPO_SPARK_OUTPUT_ROOT", "D:/DEPO/data/spark")
    spark = (
        SparkSession.builder.appName("depo-spark-smoke")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.warehouse.dir", warehouse)
        .getOrCreate()
    )
    try:
        rows = [("AP242", "Product"), ("QIF", "QualityMeasurement"), ("ReqIF", "Requirement"), ("PLMXML", "ProductStructure")]
        frame = spark.createDataFrame(rows, ["source_standard", "canonical_concept"])
        count = frame.count()
        standards = [row.source_standard for row in frame.select("source_standard").orderBy("source_standard").collect()]
        if count != len(rows) or standards != sorted(row[0] for row in rows):
            raise RuntimeError("Spark smoke result did not match the expected records")
        print(json.dumps({"status": "ok", "records": count, "standards": standards}, sort_keys=True))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
