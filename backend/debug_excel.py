import xlrd
import os

excel_file = r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared\Business\SpinnerAttributeData_ALL.xls"

if os.path.exists(excel_file):
    wb = xlrd.open_workbook(excel_file)
    print(f"Sheets: {wb.sheet_names()[:5]}")
    
    for sheet_name in wb.sheet_names()[:2]:
        ws = wb.sheet_by_name(sheet_name)
        print(f"\n[{sheet_name}]")
        print(f"  Max Row: {ws.nrows}, Max Col: {ws.ncols}")
        
        # Print header row
        headers = []
        for col in range(min(10, ws.ncols)):
            val = ws.cell_value(0, col)
            headers.append(str(val) if val else f"Col{col}")
        print(f"  Headers: {headers}")
        
        # Print first data row
        data = []
        for col in range(min(10, ws.ncols)):
            val = ws.cell_value(1, col)
            data.append(str(val)[:20] if val else "")
        print(f"  Row 2: {data}")
        
        # Count non-empty rows
        non_empty_rows = sum(1 for r in range(ws.nrows) if any(ws.cell_value(r, c) for c in range(ws.ncols)))
        print(f"  Non-empty rows: {non_empty_rows}")
else:
    print(f"File not found: {excel_file}")
