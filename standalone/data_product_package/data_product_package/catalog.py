from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_xlsx_catalog(path: str) -> Dict[str, Any]:
    """Read the simple catalog layout used by dataproduct1.xlsx.

    This intentionally supports the workbook's first sheet without requiring
    openpyxl. It is not a general-purpose spreadsheet engine.
    """
    workbook_path = Path(path).resolve()
    with zipfile.ZipFile(workbook_path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root:
                shared.append("".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t"))
        sheet_name = "xl/worksheets/sheet1.xml"
        root = ET.fromstring(archive.read(sheet_name))

    rows: List[List[str]] = []
    for row in root.iter():
        if _local_name(row.tag) != "row":
            continue
        cells: Dict[int, str] = {}
        for cell in row:
            if _local_name(cell.tag) != "c":
                continue
            ref = cell.attrib.get("r", "A1")
            letters = re.match(r"([A-Z]+)", ref)
            if not letters:
                continue
            index = 0
            for char in letters.group(1):
                index = index * 26 + ord(char) - 64
            index -= 1
            value = next((node.text or "" for node in cell if _local_name(node.tag) == "v"), "")
            if cell.attrib.get("t") == "s" and value:
                value = shared[int(value)]
            cells[index] = value
        if cells:
            rows.append([cells.get(index, "") for index in range(max(cells) + 1)])

    if not rows:
        raise ValueError(f"Workbook contains no rows: {workbook_path}")
    headers = rows[0]
    records = [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in rows[1:]]
    return {"source": str(workbook_path), "sheet": "Important Product Tables", "headers": headers, "records": records}
