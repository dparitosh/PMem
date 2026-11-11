"""AP242 representation identification shared by parser consumers."""


def is_ap242(file_schema: str | None, namespace: str | None, content: bytes) -> bool:
    # Parser metadata identifies the representation; comments and labels do not.
    marker = (file_schema or "").lower() + " " + (namespace or "").lower()
    if any(value in marker for value in ("ap242", "managed_model_based_3d_engineering", "10303/-4442")):
        return True
    # Earlier AP242 BO exchanges identify the vocabulary as bo_model and the
    # actual container by xsi:type. Never identify AP242 from a comment/label.
    if str(namespace or '').rstrip('/').endswith('/tech/xml-schema/bo_model'):
        import defusedxml.ElementTree as ET
        try:
            root=ET.fromstring(content)
            return any(str(element.attrib.get('{http://www.w3.org/2001/XMLSchema-instance}type','')).split(':')[-1]=='AP242DataContainer' for element in root.iter())
        except (ET.ParseError, ValueError):
            return False
    return False
