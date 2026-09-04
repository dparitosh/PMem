"""Small deterministic Spark smoke job for the optional DEPO execution plane."""
from __future__ import annotations

import json
import os
from pyspark.sql import SparkSession


def main() -> None:
    warehouse = os.getenv("DEPO_SPARK_OUTPUT_ROOT", "D:/DEPO/data/spark")
    spark = (
        SparkSession.builder.appName("depo-spark-smoke")
        .config("spark.sql.warehouse.dir", warehouse)
        .getOrCreate()
    )
    rows = [("AP242", "Product"), ("QIF", "QualityMeasurement"), ("ReqIF", "Requirement")]
    frame = spark.createDataFrame(rows, ["source_standard", "canonical_concept"])
    result = {
        "status": "ok",
        "records": frame.count(),
        "standards": [row.source_standard for row in frame.select("source_standard").orderBy("source_standard").collect()],
    }
    print(json.dumps(result, sort_keys=True))
    spark.stop()


if __name__ == "__main__":
    main()
