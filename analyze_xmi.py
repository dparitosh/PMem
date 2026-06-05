#!/usr/bin/env python3
"""Analyze XMI file structure"""

from pathlib import Path
from lxml import etree

xmi_file = Path(r'c:\Users\895428\Depo\SPLM_Folder\XMI\SugarPlantMBSE.xmi')
try:
    tree = etree.parse(str(xmi_file))
    root = tree.getroot()
    
    # Look for packagedElements
    uml_ns = '{http://www.omg.org/spec/UML/20131001}'
    sysml_ns = '{http://www.omg.org/spec/SysML/20181001/SysML}'
    xmi_ns = '{http://www.omg.org/spec/XMI/20131001}'
    
    print('📋 Sample packagedElements (first 10 with names):')
    count = 0
    for elem in root.iter(f'{uml_ns}packagedElement'):
        name = elem.get('name', '')
        if name and count < 10:
            # Get the tag name (after namespace)
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            xmi_type = elem.get(f'{xmi_ns}type', 'N/A')
            print(f'   {count+1}. name="{name}", tag={tag}, xmi:type={xmi_type}')
            count += 1
    
    # Check attributes of first named element
    print('\n📍 Example element attributes:')
    for elem in root.iter(f'{uml_ns}packagedElement'):
        name = elem.get('name', '')
        if name:
            print(f'   Element: {name}')
            for k, v in sorted(elem.attrib.items())[:15]:
                # Simplify key names
                if '}' in k:
                    k = k.split('}')[-1]
                print(f'      {k}: {v}')
            
            # Check for stereotype applications
            print(f'\n   Child elements:')
            for child in list(elem)[:5]:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                child_name = child.get('name', '')
                print(f'      - {child_tag} (name: {child_name})')
            break
    
    # Look for elements with Requirement stereotype
    print(f'\n🔍 Looking for Requirement-like elements:')
    found = 0
    for elem in root.iter(f'{uml_ns}packagedElement'):
        name = elem.get('name', '')
        if any(x in str(elem.tag).lower() or (name and 'req' in name.lower()) for x in ['requirement']):
            print(f'   {name}')
            found += 1
            if found >= 5:
                break
    
    if found == 0:
        print('   No Requirement elements found with that search')
        
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
