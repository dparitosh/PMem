"""Verify registered draft and apply the versioned analytics-view migration."""
import json
from dotenv import load_dotenv


def main():
    load_dotenv(".env.local")
    from backend.mesh_store import PostgresRegistry
    from backend.oslc_service.ontology_shapes import catalog_shape
    registry = PostgresRegistry("ontology_catalog")
    with registry._connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT ontology_id, lifecycle_status, classes, object_properties, datatype_properties FROM depo_ontology_analytics WHERE ontology_name = %s", ("PLMXML schema-set draft",))
        rows = cursor.fetchall()
    results = []
    for identifier, status, classes, objects, datatypes in rows:
        shape = catalog_shape(identifier, "http://127.0.0.1:8015")
        results.append({"ontology_id": identifier, "lifecycle": status,
                        "sql_classes": int(classes), "sql_object_properties": int(objects),
                        "sql_datatype_properties": int(datatypes),
                        "oslc_shape_classes": len(shape["describes"]),
                        "oslc_shape_properties": len(shape["properties"])})
    print(json.dumps(results))


if __name__ == "__main__":
    main()
