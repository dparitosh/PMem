#!/usr/bin/env python3
"""Test XMI parser with SugarPlantMBSE.xmi"""

from pathlib import Path
from backend.backend.Services.xmi_parser import XMIParser
import json

# Path to test file
xmi_file = Path(r"c:\Users\895428\Depo\SPLM_Folder\XMI\SugarPlantMBSE.xmi")

if not xmi_file.exists():
    print(f"❌ File not found: {xmi_file}")
    exit(1)

print(f"📄 Testing XMI file: {xmi_file}")
print(f"   File size: {xmi_file.stat().st_size / 1024:.1f} KB")

try:
    parser = XMIParser()
    result = parser.parse(xmi_file)
    
    print(f"\n✅ Parsing completed")
    print(f"   Nodes found: {len(result['nodes'])}")
    print(f"   Relationships found: {len(result['relationships'])}")
    
    # Show node types breakdown
    node_types = {}
    for node in result['nodes']:
        label = node.get('label', 'Unknown')
        node_types[label] = node_types.get(label, 0) + 1
    
    print(f"\n📊 Node Types Breakdown:")
    for ntype, count in sorted(node_types.items(), key=lambda x: x[1], reverse=True):
        print(f"   {ntype}: {count}")
    
    # Show first few nodes
    if result['nodes']:
        print(f"\n📋 First 5 nodes:")
        for i, node in enumerate(result['nodes'][:5], 1):
            print(f"   {i}. {node.get('label', 'Unknown')}: {node.get('properties', {}).get('name', 'N/A')}")
    
    # Show relationship types
    if result['relationships']:
        rel_types = {}
        for rel in result['relationships']:
            rtype = rel.get('type', 'Unknown')
            rel_types[rtype] = rel_types.get(rtype, 0) + 1
        
        print(f"\n🔗 Relationship Types:")
        for rtype, count in sorted(rel_types.items(), key=lambda x: x[1], reverse=True):
            print(f"   {rtype}: {count}")
    
    # Save detailed output
    output_file = Path("xmi_parse_result.json")
    with open(output_file, 'w') as f:
        json.dump({
            'node_count': len(result['nodes']),
            'relationship_count': len(result['relationships']),
            'node_types': node_types,
            'sample_nodes': result['nodes'][:5],
            'sample_relationships': result['relationships'][:5] if result['relationships'] else []
        }, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: {output_file}")
    
except Exception as e:
    print(f"❌ Error parsing XMI: {e}")
    import traceback
    traceback.print_exc()
