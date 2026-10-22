import openpyxl, glob

for f in glob.glob('data/*.xlsx'):
    try:
        wb = openpyxl.load_workbook(f, data_only=False)
        print('FILE:', f)
        print('  Sheet names:', wb.sheetnames)
        for s in wb.sheetnames:
            ws = wb[s]
            print(f'   Sheet "{s}": max_row={ws.max_row}, max_col={ws.max_column}')
            for r in range(1, min(7, ws.max_row + 1)):
                row_vals = [str(ws.cell(row=r, column=c).value) for c in range(1, min(5, ws.max_column + 1))]
                print(f'     r{r}:', row_vals)
    except Exception as e:
        print('Error:', f, e)
