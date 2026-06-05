from backend.services.unified_data_import import FileParser, FileType

if __name__ == "__main__":
    # Use an actual XMI/MDXML file for proof
    file_path = r"C:\Users\895428\Depo\SPLM_Folder\XMI\SugarPlantMBSE.xmi"
    with open(file_path, "rb") as f:
        file_content = f.read()
    rows, stats = FileParser.parse(file_content, FileType.XMI)
    print("Parsed Rows:")
    for row in rows:
        print(row)
    print("\nStats:")
    print(stats)

