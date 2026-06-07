"""AP242 Domain Model reference metadata.

The AP242 XML Domain Model is published through ISO/TS 10303-4442.
Keep these values centralized so STEP/STPX import, OWL generation, and
registry/reporting code do not drift across editions.
"""

AP242_DOMAIN_MODEL_STANDARD = "ISO/TS 10303-4442:2025"
AP242_DOMAIN_MODEL_EDITION = "5"
AP242_DOMAIN_MODEL_NAMESPACE = (
    "https://standards.iso.org/iso/ts/10303/-4442/ed-5/tech/xml-schema/domain_model"
)
AP242_DOMAIN_MODEL_XSD_URL = f"{AP242_DOMAIN_MODEL_NAMESPACE}/DomainModel.xsd"
AP242_DOMAIN_MODEL_XSD_VERSION = "N11493;2024-12-03"
AP242_DOMAIN_MODEL_PART15_COMPLIANCE = "10303-15:2024"
AP242_DOMAIN_MODEL_SCHEMA_TOKEN = "AP242_DOMAIN_MODEL_ED5"

AP242_MBD_BOM_STANDARD = "ISO/TS 10303-3001"
AP242_MBD_BOM_SCHEMA_NAME = "managed_model_based_3d_engineering_bom"
AP242_MBD_BOM_NAMESPACE = (
    "http://standards.iso.org/iso/ts/10303/-3001/-ed-2/tech/xml-schema/bo_model"
)
AP242_MBD_BOM_XSD_VERSION = "2016-03-30"


def is_ap242_domain_model_namespace(namespace: str | None) -> bool:
    value = (namespace or "").strip().rstrip("/")
    return value == AP242_DOMAIN_MODEL_NAMESPACE


def describe_ap242_domain_model() -> dict:
    return {
        "standard": AP242_DOMAIN_MODEL_STANDARD,
        "edition": AP242_DOMAIN_MODEL_EDITION,
        "namespace": AP242_DOMAIN_MODEL_NAMESPACE,
        "xsd_url": AP242_DOMAIN_MODEL_XSD_URL,
        "xsd_version": AP242_DOMAIN_MODEL_XSD_VERSION,
        "part15_compliance": AP242_DOMAIN_MODEL_PART15_COMPLIANCE,
    }


def describe_ap242_mbd_bom() -> dict:
    return {
        "standard": AP242_MBD_BOM_STANDARD,
        "schema_name": AP242_MBD_BOM_SCHEMA_NAME,
        "namespace": AP242_MBD_BOM_NAMESPACE,
        "xsd_version": AP242_MBD_BOM_XSD_VERSION,
        "express_filename": "bom.exp",
        "xsd_filename": "bom.xsd",
    }
