import pytest

from backend.Services.ap242_domain_model import AP242_DOMAIN_MODEL_NAMESPACE, AP242_DOMAIN_MODEL_XSD_URL
from backend.ingestion_service.ap242_mbd import ap242_mbd


AP242_PART21 = b"""ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-100','Pump Housing','Demo housing',());
#2 = SHAPE_REPRESENTATION('Body shape',(#5),#9);
#3 = ADVANCED_FACE('',(),#6,.T.);
#4 = CARTESIAN_POINT('origin',(0.0,0.0,0.0));
#5 = GEOMETRIC_TOLERANCE('GT1','Position tolerance','controls hole',#3,#4);
#6 = DIMENSIONAL_SIZE('D1','Hole diameter','nominal',25.0,#3);
#7 = DATUM_FEATURE('A','Primary datum','mounting face',#3);
#8 = ANNOTATION_TEXT_OCCURRENCE('NOTE1','Machined surface','Ra 1.6',#3);
#9 = GEOMETRIC_REPRESENTATION_CONTEXT(3);
ENDSEC;
END-ISO-10303-21;
"""


def test_extract_ap242_mbd_keeps_traceable_product_geometry_and_pmi():
    result = ap242_mbd.extract(filename="pump.stp", content=AP242_PART21)

    assert result["standard"] == "ap242"
    assert result["source_representation"] == "part21-step"
    assert result["coverage"]["products"] == 1
    assert result["coverage"]["geometry"] >= 1
    assert result["coverage"]["geometric_tolerances"] == 1
    assert result["coverage"]["dimensions"] == 1
    assert result["coverage"]["datums"] == 1
    assert result["coverage"]["annotations"] == 1
    assert any(item["domain_candidate"] == "GeometricTolerance" for item in result["domain_candidates"])
    assert result["conformance"]["status"] == "not_validated"
    assert result["export"]["part21_step"] is True


def test_part21_is_not_misrepresented_as_part28_exportable():
    with pytest.raises(ValueError, match="conformance mapping"):
        ap242_mbd.export_part28(filename="pump.stp", content=AP242_PART21)


def test_existing_ap242_part28_is_reexported_losslessly():
    source = f'''<?xml version="1.0" encoding="UTF-8"?>
<Uos xmlns="{AP242_DOMAIN_MODEL_NAMESPACE}"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="{AP242_DOMAIN_MODEL_NAMESPACE} {AP242_DOMAIN_MODEL_XSD_URL}">
  <Header><Name>AP242 smoke</Name></Header>
</Uos>'''.encode("utf-8")

    result = ap242_mbd.extract(filename="part.stpx", content=source)

    assert result["source_representation"] == "part28-xml"
    assert result["export"]["part28_xml"] is True
    assert ap242_mbd.export_part28(filename="part.stpx", content=source) == source
