"""Pembacaan sumber dan antrean GUI DC; tidak menghubungi FASIH."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from katalog_rincian import KATALOG, L

CHECKED = {'1', 'true', 'ya', 'y', 'x', 'v', '✓', '✔'}
TARGETS = [
    ('Upah/gaji', 'gaji', 'metrik_upah_gaji (menjadi)', 'metrik_upah_gaji (Remark)'),
    ('Biaya produksi', 'biaya_produksi', 'metrik_biaya_produksin (mejadi)', 'metrik_biaya_produksin (Remark)'),
    ('Biaya pembelian', 'biaya_pembelian', 'metrik_biaya_pembelian (menjadi)', 'metrik_biaya_pembelian (Remark)'),
    ('Biaya operasional', 'operasional', 'metrik_biaya_operasional (menjadi)', 'metrik_biaya_operasional (Remark)'),
    ('Biaya non-operasional', 'non_operasional', 'metrik_biaya_non_operasional (menjadi)', 'metrik_biaya_non_operasional (Remark)'),
    ('Pendapatan barang/jasa', 'nilai_pendapatan', 'metrik_pendapatan_barang_jasa (menjadi)', 'metrik_pendapatan_barang_jasa (Remark)'),
    ('Pendapatan lainnya', 'pendapatan_lain', 'metrik_pendapatan_lainnya (menjadi)', 'metrik_pendapatan_lainnya (Remark)'),
]


@dataclass(frozen=True)
class Mapping:
    label: str
    kode: str
    nilai: str
    remark: str
    blok: str = L


def read_source(path: Path, sheet: str | None = None) -> pd.DataFrame:
    if path.suffix.lower() == '.csv':
        data = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif path.suffix.lower() == '.xlsx':
        data = pd.read_excel(path, sheet_name=sheet or 0, dtype=str, keep_default_na=False)
    else:
        raise ValueError('Pilih file .xlsx atau .csv.')
    data.columns = data.columns.astype(str).str.strip()
    if data.columns.duplicated().any():
        raise ValueError('Nama kolom sumber duplikat; perbaiki nama kolom terlebih dahulu.')
    data['_baris_sumber'] = data.index + 2
    return data.fillna('')


def assignment_id(url: str) -> str:
    u = urlparse(str(url).strip())
    if u.scheme != 'https' or u.hostname != 'fasih-sm.bps.go.id' or u.query or u.fragment:
        raise ValueError('Tautan harus berupa URL assignment HTTPS FASIH tanpa parameter.')
    parts = u.path.strip('/').split('/')
    if len(parts) != 4 or parts[:2] != ['app', 'assignment']:
        raise ValueError('Format tautan assignment tidak sesuai.')
    if not all(re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', p) for p in parts[2:]):
        raise ValueError('ID pada tautan assignment tidak sesuai.')
    return parts[3].lower()


def validate_mappings(columns, mappings):
    if not mappings:
        raise ValueError('Pilih minimal satu rincian.')
    if len({(m.blok, m.kode) for m in mappings}) != len(mappings):
        raise ValueError('Rincian FASIH tidak boleh dipilih lebih dari sekali.')
    for m in mappings:
        target = KATALOG.get((m.blok, m.kode))
        if target is None:
            raise ValueError(f'Rincian tidak ada di katalog: {m.blok} / {m.kode}')
        jenis = target[1]
        if jenis == 'informasi':
            raise ValueError(f'{m.label} belum didukung untuk perbaikan otomatis.')
        if not m.nilai and not m.remark:
            raise ValueError(f'Pilih kolom nilai dan/atau remark untuk {m.label}.')
        if m.remark and m.remark not in columns:
            raise ValueError(f'Kolom remark untuk {m.label} tidak ditemukan.')
        if m.nilai and m.nilai not in columns:
            raise ValueError(f'Kolom nilai untuk {m.label} tidak ditemukan.')
        if m.nilai and jenis == 'catatan':
            raise ValueError(f'{m.label} saat ini hanya didukung untuk remark; jangan pilih kolom nilai.')
        if m.remark and m.blok == 'CATATAN':
            raise ValueError(f'{m.label} adalah catatan umum, bukan tombol remark rincian.')


def rupiah_integer(value, round_values=False):
    # Titik adalah desimal, bukan pemisah ribuan; jangan menebak format CSV.
    if not re.fullmatch(r'\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', value) or len(value) > 100:
        raise ValueError('nilai harus angka tanpa pemisah ribuan (gunakan titik untuk desimal).')
    if re.fullmatch(r'[1-9]\d{0,2}\.\d{3}', value):
        raise ValueError('format angka ambigu: titik dapat berarti desimal atau pemisah ribuan; perbaiki sumber.')
    try:
        number = Decimal(value)
        if not number.is_finite() or number.adjusted() > 24 or number.adjusted() < -100:
            raise ValueError('nilai di luar batas yang didukung.')
        rounded = number.to_integral_value(rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError('nilai angka tidak valid.') from exc
    if number != rounded and not round_values:
        raise ValueError('nilai memiliki desimal; centang pilihan pembulatan jika disetujui.')
    return format(rounded, 'f')


def preview_actions(row, mappings, round_values=False):
    result = []
    for m in mappings:
        remark = str(row[m.remark]).strip() if m.remark else ''
        value = str(row[m.nilai]).strip() if m.nilai else ''
        if m.remark and not remark:
            raise ValueError(f'Remark {m.label} kosong.')
        change = bool(m.nilai) and remark.upper() != '#DC_00'
        if change and not value:
            raise ValueError(f'{m.label}: {remark} membutuhkan nilai perbaikan.')
        if change:
            try:
                jenis = KATALOG[(m.blok, m.kode)][1]
                if jenis == 'rupiah':
                    value = rupiah_integer(value, round_values)
                elif jenis == 'angka':
                    if not re.fullmatch(r'[0-9]+', value):
                        raise ValueError('nilai harus bilangan bulat tanpa pemisah.')
                elif jenis != 'teks':
                    raise ValueError('pengubahan nilai untuk rincian ini belum didukung.')
            except ValueError as exc:
                raise ValueError(f'{m.label}: {exc}') from exc
        result.append((m, remark, value, change))
    return result


class Journal:
    """Klaim atomik per assignment; status proses terputus tidak dicoba ulang diam-diam."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30)) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS pekerjaan (
                assignment_id TEXT PRIMARY KEY, nama_usaha TEXT NOT NULL,
                sumber TEXT NOT NULL, baris TEXT NOT NULL, status TEXT NOT NULL,
                pesan TEXT NOT NULL, waktu TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            db.execute('''CREATE TABLE IF NOT EXISTS riwayat (
                assignment_id TEXT NOT NULL, status TEXT NOT NULL, pesan TEXT NOT NULL,
                waktu TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

    def statuses(self, include_errors=True):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            statuses = dict(db.execute("SELECT assignment_id, status FROM pekerjaan WHERE status != 'siap_diulang'"))
        return statuses if include_errors else {aid: status for aid, status in statuses.items() if status not in ('error', 'perlu_data')}

    def claim(self, aid, name, source, row, retry_errors=False):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT status FROM pekerjaan WHERE assignment_id=?', (aid,)).fetchone()
            if old and old[0] != 'siap_diulang' and not (retry_errors and old[0] in ('error', 'perlu_data')):
                return False
            db.execute('''INSERT INTO pekerjaan (assignment_id,nama_usaha,sumber,baris,status,pesan) VALUES (?,?,?,?,?,?)
                          ON CONFLICT(assignment_id) DO UPDATE SET nama_usaha=excluded.nama_usaha,
                          sumber=excluded.sumber,baris=excluded.baris,status=excluded.status,pesan='',waktu=CURRENT_TIMESTAMP''',
                       (aid, name, source, str(row), 'berjalan', ''))
            db.execute('INSERT INTO riwayat (assignment_id,status,pesan) VALUES (?,?,?)', (aid, 'berjalan', ''))
        return True

    def finish(self, aid, status, message):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute('UPDATE pekerjaan SET status=?, pesan=?, waktu=CURRENT_TIMESTAMP WHERE assignment_id=?',
                       (status, str(message)[:30000], aid))
            db.execute('INSERT INTO riwayat (assignment_id,status,pesan) VALUES (?,?,?)', (aid, status, str(message)[:30000]))

    def allow_retry(self, aid):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT status FROM pekerjaan WHERE assignment_id=?', (aid,)).fetchone()
            if not old or old[0] not in ('error', 'berjalan', 'perlu_data'):
                raise ValueError('ID tidak ditemukan sebagai error, perlu data, atau proses yang terputus.')
            db.execute("UPDATE pekerjaan SET status='siap_diulang', pesan='Diizinkan ulang oleh pengguna', waktu=CURRENT_TIMESTAMP WHERE assignment_id=?", (aid,))
            db.execute('INSERT INTO riwayat (assignment_id,status,pesan) VALUES (?,?,?)', (aid, 'siap_diulang', 'Diizinkan ulang oleh pengguna'))

    def export(self, output: Path):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            data = pd.read_sql_query('SELECT * FROM pekerjaan ORDER BY waktu, assignment_id', db)
        # Berkas hanya milik GUI ini; tidak menimpa rekap notebook.
        for status, filename in [('berhasil', 'selesai_gui.csv'), ('error', 'error_gui.csv'), ('berjalan', 'perlu_diperiksa_gui.csv'), ('perlu_data', 'perlu_data_gui.csv')]:
            data[data['status'] == status].to_csv(output / filename, index=False, encoding='utf-8-sig')
        data[data['status'] == 'error'].to_excel(output / 'rekap_error_gui.xlsx', index=False)


def old_ids(folder: Path, kategori: str, wilayah: str, skip_errors: bool):
    ids = set()
    if not re.fullmatch(r'[A-Za-z0-9]+', kategori) or not re.fullmatch(r'\d+', wilayah):
        raise ValueError('Kategori atau kode wilayah tidak valid.')
    for path in folder.glob(f'{kategori}_{wilayah}_selesai_*.csv'):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        if not {'assignment_id', 'status'} <= set(df.columns):
            raise ValueError(f'Log selesai tidak lengkap: {path.name}')
        ids.update(df.loc[df.status.isin(['berhasil', 'sudah_ada']), 'assignment_id'].astype(str).str.strip().str.lower())
    if skip_errors:
        for path in folder.glob(f'{kategori}_{wilayah}_error_usaha_2026_*.xlsx'):
            df = pd.read_excel(path, dtype=str, keep_default_na=False)
            if 'assignment_id' not in df:
                raise ValueError(f'Kolom assignment_id tidak ditemukan: {path.name}')
            ids.update(df.assignment_id.astype(str).str.strip().str.lower())
    return ids


def check_duplicate_assignments(data, kategori, wilayah, done_ids, statuses):
    scoped = data.loc[data.kategori.astype(str).str.strip().str.upper().eq(kategori.upper()) &
                      data.level_2_full_code.astype(str).str.strip().eq(wilayah)].copy()
    records = []
    for _, row in scoped.iterrows():
        try:
            aid = assignment_id(row['link_fasih_sm'])
        except ValueError:
            continue  # Baris siap yang tidak valid akan ditolak oleh make_queue.
        ready = str(row['Siap Input']).strip().casefold() in CHECKED
        sent = str(row['Sudah Diinput']).strip().casefold() in CHECKED
        records.append((aid, ready and not sent))
    counts = {}
    eligible = set()
    for aid, active in records:
        counts[aid] = counts.get(aid, 0) + 1
        if active and aid not in done_ids and aid not in statuses:
            eligible.add(aid)
    duplicates = sorted(aid for aid in eligible if counts[aid] > 1)
    if duplicates:
        raise ValueError('Satu assignment terdapat pada beberapa baris sumber; perlu penanganan gabungan: ' + ', '.join(duplicates[:5]))


def make_queue(data, mappings, kategori, wilayah, done_ids, statuses, reverse=False, split='semua', limit=1, round_values=False):
    required = {'kategori','level_2_full_code','nama_usaha','link_fasih_sm','Siap Input','Sudah Diinput'}
    missing = required - set(data.columns)
    if missing:
        raise ValueError('Kolom wajib tidak ditemukan: ' + ', '.join(sorted(missing)))
    validate_mappings(data.columns, mappings)
    if split not in ('semua', 'atas', 'bawah') or limit < 1:
        raise ValueError('Pembagian atau batas proses tidak valid.')
    ready = data['Siap Input'].astype(str).str.strip().str.casefold().isin(CHECKED)
    sent = data['Sudah Diinput'].astype(str).str.strip().str.casefold().isin(CHECKED)
    rows = data.loc[ready & ~sent & data.kategori.astype(str).str.strip().str.upper().eq(kategori.upper()) &
                    data.level_2_full_code.astype(str).str.strip().eq(wilayah)].copy()
    # Batas dibentuk sebelum menghapus log selesai/error, agar tidak bergeser setelah satu proses selesai.
    if split != 'semua':
        mid = (len(rows) + 1) // 2
        rows = rows.iloc[:mid] if split == 'atas' else rows.iloc[mid:]
    if reverse:
        rows = rows.iloc[::-1]
    candidates, problems = [], []
    for _, row in rows.iterrows():
        if len(candidates) + len(problems) >= limit:
            break
        try:
            aid = assignment_id(row['link_fasih_sm'])
            if aid in done_ids or aid in statuses:
                continue
            if not str(row['nama_usaha']).strip():
                raise ValueError('Nama usaha kosong.')
            preview_actions(row, mappings, round_values)
            record = row.to_dict()
            record['assignment_id'] = aid
            candidates.append(record)
        except ValueError as exc:
            problems.append(f"Baris {row['_baris_sumber']}: {exc}")
    # Lebih dari satu usaha per assignment perlu alur gabungan; hentikan daripada menandai sebagian selesai.
    counts = pd.Series([r['assignment_id'] for r in candidates], dtype=str).value_counts()
    duplicate = set(counts[counts > 1].index)
    if duplicate:
        raise ValueError('Ada beberapa baris untuk assignment yang sama; perlu penanganan gabungan: ' + ', '.join(sorted(duplicate)[:5]))
    if problems:
        raise ValueError('Perbaiki data sebelum menjalankan:\n' + '\n'.join(problems[:15]))
    return candidates[:limit]
