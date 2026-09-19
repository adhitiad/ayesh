---
name: xlsx-manipulation
description: "Buat, edit, manipulasi spreadsheet Excel dengan openpyxl. Trigger: /xlsx-manipulation, /spreadsheet, /buat-excel, /edit-excel, /format-excel"
category: office
tags: [xlsx, excel, manipulation, openpyxl]
---

# XLSX Manipulation

Buat, edit, dan manipulasi spreadsheet Excel (.xlsx) menggunakan **openpyxl** - tanpa perlu Excel terinstall.

## Langkah

### Buat Spreadsheet Baru
```
"Buat spreadsheet budget dengan format rapi"
```

### Menggunakan office_tool
```
office_tool("create_xlsx", '{"output": "budget.xlsx", "headers": ["Kategori", "Jan", "Feb", "Mar"], "data": [["Gaji", 5000, 5000, 5000], ["Sewa", -1500, -1500, -1500]]}')
```

### Edit yang Sudah Ada
```
"Tambah kolom total di spreadsheet ini"
```

### Format & Chart
```
"Tambah conditional formatting dan chart ke spreadsheet ini"
```

### Generate Kode
1. Gunakan `tulis_kode` untuk buat script openpyxl
2. Jalankan via `jalankan_python`
3. Output: file .xlsx

## Dasar openpyxl

```python
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Fill, Border, Alignment, PatternFill
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.utils import get_column_letter

# Buat baru
wb = Workbook()
ws = wb.active

# Buka yang ada
wb = load_workbook('existing.xlsx')
ws = wb.active
```

### Baca/Tulis Sel

```python
# Tulis
ws['A1'] = 'Header'
ws['B1'] = 42
ws.cell(row=1, column=3, value='Data')
ws['A1:C1'] = [['Col1', 'Col2', 'Col3']]
ws.append(['Baris', 'Data', 'Disini'])

# Baca
nilai = ws['A1'].value
for row in ws['A1:C3']:
    for cell in row:
        print(cell.value)
```

### Formulas

```python
ws['D1'] = '=SUM(A1:C1)'
ws['D2'] = '=AVERAGE(A2:C2)'
ws['E1'] = '=IF(D1>100,"High","Low")'

# Named ranges
from openpyxl.workbook.defined_name import DefinedName
ref = "Sheet!$A$1:$C$10"
defn = DefinedName("SalesData", attr_text=ref)
wb.defined_names.add(defn)
ws['F1'] = '=SUM(SalesData)'
```

### Formatting

```python
# Font
ws['A1'].font = Font(name='Arial', size=14, bold=True, color='FF0000')

# Background
ws['A1'].fill = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')

# Border
from openpyxl.styles import Side
thin_border = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)
ws['A1'].border = thin_border

# Alignment
ws['A1'].alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

# Number format
ws['B2'].number_format = '#,##0.00'  # Currency
ws['C2'].number_format = '0.00%'     # Percentage
ws['D2'].number_format = 'YYYY-MM-DD' # Date
```

### Conditional Formatting

```python
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule
from openpyxl.styles import PatternFill

# Color scale (heatmap)
color_scale = ColorScaleRule(
    start_type='min', start_color='FF0000',
    end_type='max', end_color='00FF00'
)
ws.conditional_formatting.add('A1:A10', color_scale)

# Cell value rule
red_fill = PatternFill(start_color='FFCCCC', end_color='FFCCCC', fill_type='solid')
rule = CellIsRule(operator='greaterThan', formula=['100'], fill=red_fill)
ws.conditional_formatting.add('B1:B10', rule)
```

### Charts

```python
# Bar Chart
data = Reference(ws, min_col=2, min_row=1, max_col=3, max_row=5)
categories = Reference(ws, min_col=1, min_row=2, max_row=5)

chart = BarChart()
chart.type = "col"
chart.title = "Sales by Region"
chart.add_data(data, titles_from_data=True)
chart.set_categories(categories)
ws.add_chart(chart, "E1")

# Line Chart
line = LineChart()
line.title = "Trend Analysis"
line.add_data(data, titles_from_data=True)
ws.add_chart(line, "E15")

# Pie Chart
pie = PieChart()
pie.add_data(data, titles_from_data=True)
pie.set_categories(categories)
ws.add_chart(pie, "M1")
```

### Data Validation

```python
from openpyxl.worksheet.datavalidation import DataValidation

# Dropdown
dv = DataValidation(type="list", formula1='"Opsi1,Opsi2,Opsi3"', allow_blank=True)
dv.error = "Pilih dari daftar"
ws.add_data_validation(dv)
dv.add('A1:A100')

# Number range
dv_num = DataValidation(type="whole", operator="between", formula1="1", formula2="100")
ws.add_data_validation(dv_num)
dv_num.add('B1:B100')
```

### Sheet Operations

```python
# Sheet baru
ws2 = wb.create_sheet("Data")
ws3 = wb.create_sheet("Summary", 0)  # di posisi 0

# Rename
ws.title = "Laporan Utama"

# Delete
del wb["Sheet2"]

# Copy
source = wb["Template"]
target = wb.copy_worksheet(source)
```

### Row/Column Operations

```python
# Column width
ws.column_dimensions['A'].width = 20

# Row height
ws.row_dimensions[1].height = 30

# Hide column
ws.column_dimensions['C'].hidden = True

# Freeze panes
ws.freeze_panes = 'B2'

# Auto-filter
ws.auto_filter.ref = "A1:D100"
```

## Contoh: Budget Tracker

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

wb = Workbook()
ws = wb.active
ws.title = "Budget 2026"

# Headers
months = ['Kategori', 'Jan', 'Feb', 'Mar', 'Q1 Total']
ws.append(months)

# Data
budget_data = [
    ['Gaji', 5000, 5000, 5000],
    ['Sewa', -1500, -1500, -1500],
    ['Listrik', -200, -180, -220],
    ['Makan', -400, -450, -380],
    ['Transport', -150, -160, -140],
]

for row in budget_data:
    ws.append(row + [f'=SUM(B{ws.max_row + 1}:D{ws.max_row + 1})'])

# Total
ws.append(['TOTAL', 
    f'=SUM(B2:B{ws.max_row})',
    f'=SUM(C2:C{ws.max_row})',
    f'=SUM(D2:D{ws.max_row})',
    f'=SUM(E2:E{ws.max_row})'
])

# Format
header_fill = PatternFill('solid', fgColor='366092')
header_font = Font(bold=True, color='FFFFFF')

for cell in ws[1]:
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal='center')

for row in ws.iter_rows(min_row=2, min_col=2, max_col=5):
    for cell in row:
        cell.number_format = '#,##0.00'

wb.save('budget_2026.xlsx')
```

## Best Practices
1. Gunakan templates untuk format complex
2. Batch operations, jangan cell-by-cell
3. Named ranges untuk formula clearer
4. Data validation untuk cegah input error
5. Save incrementally untuk file besar

## Limitasi
- Tidak bisa eksekusi VBA
- Pivot tables complex tidak fully support
- Sparkline support terbatas
- External data connections tidak didukung
- Beberapa chart types advanced tidak tersedia
