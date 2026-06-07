import csv
from pathlib import Path

# Sample files to analyze
folders = {
    "Business": r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared\Business",
    "Objects": r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared\Objects",
    "Relationships": r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared\Relationships",
}

for folder_name, folder_path in folders.items():
    print(f"\n{'='*80}")
    print(f"FOLDER: {folder_name}")
    print(f"{'='*80}")
    
    folder = Path(folder_path)
    if not folder.exists():
        print(f"  ❌ Folder not found: {folder_path}")
        continue
    
    files = list(folder.glob("*.xls"))
    print(f"  📁 Total files: {len(files)}")
    
    if not files:
        continue
    
    # Analyze first file in each folder
    sample_file = sorted(files)[0]
    print(f"  📄 Sample: {sample_file.name}")
    
    try:
        with open(sample_file, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f, delimiter='\t')
            rows = list(reader)
            
            if rows:
                headers = rows[0]
                print(f"  📊 Columns ({len(headers)}): {headers[:5]}")
                print(f"  📝 Data rows: {len(rows) - 1}")
                
                # Show first 2 data rows
                if len(rows) > 1:
                    print(f"  🔹 Row 1: {rows[1][:3]}")
                if len(rows) > 2:
                    print(f"  🔹 Row 2: {rows[2][:3]}")
    except Exception as e:
        print(f"  ❌ Error reading file: {e}")

print(f"\n{'='*80}")
print("ANALYSIS SUMMARY")
print(f"{'='*80}")
print("""
BUSINESS folder:  Contains Business Objects with attributes
- Likely columns: Name, Type, Description, attributes...
- Goal: Extract BO definitions as entities

OBJECTS folder:   Contains object metadata/attributes
- Likely columns: Attribute Name, Type, Registry Name...
- Goal: Extract attribute definitions

RELATIONSHIPS folder: Contains relationship definitions
- Likely columns: Name, Source, Target, Type...
- Goal: Extract relationship definitions between objects
""")
