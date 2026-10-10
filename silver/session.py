"""Spark sessions with Iceberg, matching AWS Glue 5.1 (Spark 3.5.6, Iceberg 1.10.0)."""

from pyspark.sql import SparkSession

ICEBERG_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.10.0"
EXTENSIONS = "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
CATALOG = "local"


def local_spark(
    app: str,
    warehouse: str = "data/warehouse",
    cores: str = "*",
    memory: str = "4g",
    ui: bool = True,
) -> SparkSession:
    """Spark on this machine. Iceberg tables live in a folder here (Glue Catalog on AWS)."""
    return (
        SparkSession.builder.master(f"local[{cores}]")
        .appName(app)
        .config("spark.driver.memory", memory)
        .config("spark.ui.enabled", str(ui).lower())
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.jars.packages", ICEBERG_PACKAGE)
        .config("spark.sql.extensions", EXTENSIONS)
        .config(f"spark.sql.catalog.{CATALOG}", "org.apache.iceberg.spark.SparkCatalog")
        .config(f"spark.sql.catalog.{CATALOG}.type", "hadoop")
        .config(f"spark.sql.catalog.{CATALOG}.warehouse", warehouse)
        .getOrCreate()
    )
