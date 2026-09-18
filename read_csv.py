"""
Program Python untuk membaca file CSV.
Mendukung dua pendekatan: csv module (standar library) dan pandas.
"""

import csv
import sys
from pathlib import Path


def baca_csv_standar(filepath: str, delimiter: str = ',', encoding: str = 'utf-8') -> list[dict]:
    """
    Membaca CSV menggunakan modul standar `csv`.
    Mengembalikan list of dict (setiap baris = satu dict).
    """
    data = []
    with open(filepath, mode='r', newline='', encoding=encoding) as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            data.append(row)
    return data


def baca_csv_pandas(filepath: str, delimiter: str = ',', encoding: str = 'utf-8'):
    """
    Membaca CSV menggunakan pandas (perlu: pip install pandas).
    Mengembalikan DataFrame.
    """
    try:
        import pandas as pd
    except ImportError:
        print("pandas belum terinstall. Jalankan: pip install pandas")
        return None

    df = pd.read_csv(filepath, delimiter=delimiter, encoding=encoding)
    return df


def main():
    # Contoh penggunaan
    if len(sys.argv) < 2:
        print("Usage: python read_csv.py <path_ke_file.csv> [--pandas]")
        sys.exit(1)

    filepath = sys.argv[1]
    use_pandas = '--pandas' in sys.argv

    if not Path(filepath).exists():
        print(f"File tidak ditemukan: {filepath}")
        sys.exit(1)

    print(f"Membaca: {filepath}\n")

    if use_pandas:
        df = baca_csv_pandas(filepath)
        if df is not None:
            print(f"Shape: {df.shape}")
            print(f"Kolom: {list(df.columns)}")
            print("\n5 baris pertama:")
            print(df.head())
            print("\nInfo:")
            print(df.info())
    else:
        data = baca_csv_standar(filepath)
        print(f"Jumlah baris: {len(data)}")
        if data:
            print(f"Kolom: {list(data[0].keys())}")
            print("\n5 baris pertama:")
            for i, row in enumerate(data[:5]):
                print(f"  Baris {i+1}: {row}")


if __name__ == '__main__':
    main()