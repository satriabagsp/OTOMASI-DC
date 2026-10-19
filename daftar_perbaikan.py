"""Penyimpanan lokal daftar pemetaan; tidak menyimpan data atau kredensial."""
import json
import os
import tempfile
from pathlib import Path
from katalog_rincian import KATALOG


def load_lists(path):
    path = Path(path)
    if not path.exists():
        return {'versi': 1, 'terpilih': '', 'daftar': {}}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('versi') != 1 or not isinstance(data.get('daftar'), dict):
        raise ValueError('Format daftar perbaikan tidak dikenali; file tidak diubah.')
    if not isinstance(data.get('terpilih', ''), str):
        raise ValueError('Pilihan daftar perbaikan tidak valid; file tidak diubah.')
    for name, rows in data['daftar'].items():
        if not isinstance(name, str) or not isinstance(rows, list) or not rows:
            raise ValueError('Daftar perbaikan rusak; file tidak diubah.')
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('pakai'), bool):
                raise ValueError('Pemetaan tersimpan tidak valid; file tidak diubah.')
            if not all(isinstance(row.get(k), str) for k in ('blok', 'kode', 'nilai', 'remark')):
                raise ValueError('Pemetaan tersimpan tidak valid; file tidak diubah.')
            if (row['blok'], row['kode']) not in KATALOG:
                raise ValueError(f"Rincian tersimpan tidak ada di katalog: {row['kode']}")
    if data.get('terpilih') and data['terpilih'] not in data['daftar']:
        raise ValueError('Daftar terpilih tidak ditemukan; file tidak diubah.')
    return data


def save_lists(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    # Tulis di berkas sementara pada folder yang sama, lalu ganti secara atomik.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.daftar_', suffix='.tmp', delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(content)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
