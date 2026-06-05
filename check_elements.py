#!/usr/bin/env python3
"""Check elements with names in XMI"""

from pathlib import Path
from lxml import etree

xmi_file = Path(r'c:\Users\895428\Depo\SPLM_Folder\XMI\SugarPlantMBSE.xmi')
tree = etree.parse(str(xmi_file))
root = tree.getroot()

# XMI namespace
xmi_ns = '{http://www.omg.org/spec/XMI/20131001}'

# Look for all elements with names
print('📊 Elements with names (first 30):')
found = []
for elem in root.iter():
    name = elem.get('name')
    if name:
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        xmi_type = elem.get(f'{xmi_ns}type', '')
        elem_id = elem.get(f'{xmi_ns}id', '')
        found.append((name, tag, xmi_type))
        if len(found) >= 30:
            break

for i, (name, tag, xmi_type) in enumerate(found, 1):
    print(f'   {i:2}. {name:40} | tag={tag:20} | type={xmi_type}')

# Count total by tag
print('\n📊 Total count by tag name:')
tag_counts = {}
for elem in root.iter():
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    tag_counts[tag] = tag_counts.get(tag, 0) + 1

for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
    print(f'   {tag:30} : {count:5}')
