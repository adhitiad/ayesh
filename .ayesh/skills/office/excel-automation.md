---
name: excel-automation
description: "Otomasi Excel dengan xlwings - eksekusi VBA, update dashboard, jalankan macro. Trigger: /excel-automation, /otomasi-excel, /macro-excel, /xlwings"
category: office
tags: [excel, automation, macro, vba]
---

# Excel Automation

Otomasi Excel menggunakan **xlwings** - interaksi live dengan Excel, eksekusi VBA macro, update dashboard real-time.

## Langkah

### Update Dashboard Live
```
"Update dashboard Excel dengan data baru ini"
```

### Jalankan VBA Macro
```
"Jalankan macro 'CalculateSales' dengan parameter 100"
```

### Generate Kode
1. Gunakan `tulis_kode` untuk buat script xlwings
2. Jalankan via `jalankan_python`
3. Pastikan Excel sudah terinstall di mesin

## xlwings vs openpyxl

| Fitur | xlwings | openpyxl |
|-------|---------|----------|
| Perlu Excel | Ya | Tidak |
| Live interaction | Ya | Tidak |
| Eksekusi VBA | Ya | Tidak |
| Speed (file besar) | Cepat | Lambat |
| Server deploy | Terbatas | Mudah |

## Dasar xlwings

```python
import xlwings as xw

# Buka workbook
wb = xw.Book('file.xlsx')

# Aktif
wb = xw.books.active

# Sheet baru
sheet = wb.sheets['Sheet1']
```

### Baca/Tulis Range

```python
# Sel tunggal
sheet['A1'].value = 'Halo'
nilai = sheet['A1'].value

# Range
sheet['A1:C3'].value = [[1,2,3], [4,5,6], [7,8,9]]
data = sheet['A1:C3'].value

# Named range
sheet['MyRange'].value = 'Data'

# Expand range
sheet['A1'].expand().value
sheet['A1'].expand('table').value
```

### Formatting

```python
# Font
sheet['A1'].font.bold = True
sheet['A1'].font.size = 14
sheet['A1'].font.color = (255, 0, 0)

# Background
sheet['A1'].color = (255, 255, 0)

# Number format
sheet['B1'].number_format = '#,##0.00'

# Column width
sheet['A:A'].column_width = 20

# Autofit
sheet['A:D'].autofit()
```

### Charts

```python
chart = sheet.charts.add(left=100, top=100, width=400, height=250)
chart.set_source_data(sheet['A1:B10'])
chart.chart_type = 'column_clustered'
chart.name = 'Grafik Sales'
```

### VBA Integration

```python
# Jalankan macro
wb.macro('MacroName')()

# Dengan parameter
wb.macro('MyMacro')('arg1', 'arg2')

# Dapatkan return value
result = wb.macro('CalculateTotal')(100, 200)
```

### UDF (User Defined Functions)

```python
import xlwings as xw

@xw.func
def my_sum(x, y):
    """Tambah dua angka"""
    return x + y

@xw.func
@xw.arg('data', ndim=2)
def my_array_func(data):
    """Proses array data"""
    import numpy as np
    return np.sum(data)
```

### Performance Optimization

```python
app = xw.App(visible=False)
try:
    app.screen_updating = False
    app.calculation = 'manual'
    
    wb = app.books.open('file.xlsx')
    sheet = wb.sheets['Data']
    sheet['A1'].value = data
    
    app.calculation = 'automatic'
    wb.save()
finally:
    wb.close()
    app.quit()
```

## Contoh: Dashboard Update

```python
import xlwings as xw
from datetime import datetime

wb = xw.books.active
dashboard = wb.sheets['Dashboard']
data_sheet = wb.sheets['Data']

# Update data
data_sheet['A1'].value = new_data

# Update KPIs
dashboard['B2'].value = new_data['Sales'].sum()
dashboard['A1'].value = f'Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}'

# Refresh charts
for chart in dashboard.charts:
    chart.api.Refresh()
```

## Contoh: Batch Processing

```python
from pathlib import Path

def proses_folder(folder_path, output_path):
    app = xw.App(visible=False)
    app.screen_updating = False
    
    try:
        summary = xw.Book()
        sheet = summary.sheets[0]
        sheet['A1'].value = ['File', 'Total Sales', 'Total Units']
        
        row = 2
        for file in Path(folder_path).glob('*.xlsx'):
            wb = app.books.open(str(file))
            data = wb.sheets['Sales']
            
            sheet[f'A{row}'].value = file.name
            sheet[f'B{row}'].value = data['B:B'].api.SpecialCells(11).Value
            
            wb.close()
            row += 1
        
        summary.save(output_path)
    finally:
        app.quit()
```

## Instalasi

```bash
pip install xlwings

# Untuk add-in
xlwings addin install
```

## Limitasi
- Memerlukan Excel terinstall
- Tidak suitable untuk server-side
- Fitur VBA memerlukan trust settings
- macOS support terbatas
