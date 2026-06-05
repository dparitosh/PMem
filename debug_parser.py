#!/usr/bin/env python3
"""Debug XMI parser extraction"""

from pathlib import Path
from lxml import etree

xmi_file = Path(r'c:\Users\895428\Depo\SPLM_Folder\XMI\SugarPlantMBSE.xmi')
tree = etree.parse(str(xmi_file))
root = tree.getroot()

# Check what Pass 1 would find
print("🔍 Checking Pass 1 XPath matching...")

# The problematic XPath from the parser
elements_pass1 = root.xpath(".//*[@*[local-name()='type']]")
print(f"   Elements found by XPath './/*[@*[local-name()='type']]': {len(elements_pass1)}")

# Let's count which ones have xmi:type specifically
xmi_type_ns = '{http://www.omg.org/spec/XMI/20131001}'
uml_ns = '{http://www.omg.org/spec/UML/20131001}'

count_with_xmi_type = 0
count_packagedelements = 0
count_with_proper_type = 0

for elem in elements_pass1:
    xmi_type = elem.get(f'{xmi_type_ns}type')
    if xmi_type:
        count_with_xmi_type += 1
    
    tag = elem.tag
    if '}' in tag:
        tag = tag.split('}')[-1]
    
    if tag == 'packagedElement':
        count_packagedelements += 1
        if xmi_type and 'uml:' in xmi_type:
            count_with_proper_type += 1

print(f"   - With xmi:type attribute: {count_with_xmi_type}")
print(f"   - packagedElements: {count_packagedelements}")
print(f"   - packagedElements with proper xmi:type: {count_with_proper_type}")

# Check packagedElements directly
print(f"\n📦 packagedElements directly:")
# Find packagedElements without namespace in xpath
packagedelements = [e for e in root.iter() if e.tag.endswith('}packagedElement') or e.tag == 'packagedElement']
print(f"   Total packagedElements: {len(packagedelements)}")

named_with_type = 0
named_without_type = 0
unnamed_with_type = 0
unnamed_without_type = 0

for elem in packagedelements:
    name = elem.get('name', '')
    xmi_type = elem.get(f'{xmi_type_ns}type', '')
    
    if name:
        if xmi_type:
            named_with_type += 1
        else:
            named_without_type += 1
    else:
        if xmi_type:
            unnamed_with_type += 1
        else:
            unnamed_without_type += 1

print(f"   - Named with xmi:type: {named_with_type}")
print(f"   - Named without xmi:type: {named_without_type}")
print(f"   - Unnamed with xmi:type: {unnamed_with_type}")
print(f"   - Unnamed without xmi:type: {unnamed_without_type}")

# Show some example packagedElements with and without names/types
print(f"\n📋 Sample packagedElements:")
for i, elem in enumerate(packagedelements[:10]):
    name = elem.get('name', '[no name]')
    xmi_type = elem.get(f'{xmi_type_ns}type', '[no type]')
    print(f"   {i+1}. name={name[:40]} type={xmi_type}")
