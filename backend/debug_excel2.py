import os

excel_file = r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared\Business\SpinnerAttributeData_ALL.xls"

if os.path.exists(excel_file):
    with open(excel_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read(500)
        print("First 500 chars:")
        print(content)
        print(f"\nFile size: {os.path.getsize(excel_file)} bytes")
        
        # Check if it looks like CSV
        lines = content.split('\n')
        print(f"\nFirst line: {lines[0][:100]}")
        if '\t' in lines[0]:
            print("Contains tabs - likely TAB-separated")
        if ',' in lines[0]:
            print("Contains commas - likely CSV")
else:
    print(f"File not found: {excel_file}")
