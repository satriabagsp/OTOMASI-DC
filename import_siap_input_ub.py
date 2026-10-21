"""Impor aman folder SIAP INPUT UB ke tabel sumber OTOMASI_DC.

Bawaan adalah dry-run. Gunakan --execute untuk menulis dan --round-values bila
nilai rupiah desimal memang boleh dibulatkan seperti opsi pada GUI.
File Excel sumber tidak pernah diubah.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from core import Mapping, TARGETS, assignment_id, preview_actions
from pusat import CentralAPI, CentralError, load_config


ROOT = Path(__file__).resolve().parent
DEFAULT_FOLDER = ROOT / "SIAP INPUT UB"
CONFIG_FILE = ROOT / "config_pusat.json"
OUTPUT = ROOT / "hasil"
CHECKED = {"1", "true", "ya", "y", "x", "v", "✓", "✔"}
LEGACY_PRODUCTION = "metrik_biaya_produksin (mejadi)"
DATABASE_PRODUCTION = "metrik_biaya_produksin (menjadi)"
IMPORT_PREFIX = "SIAP INPUT UB/"
FILE_MAPPINGS = [Mapping(label, code, value, remark) for label, code, value, remark in TARGETS]
TARGET_VALUE_COLUMNS = [value for _, _, value, _ in TARGETS]
TARGET_REMARK_COLUMNS = [remark for _, _, _, remark in TARGETS]
REQUIRED = {
    "kategori", "level_2_full_code", "nama_usaha", "link_fasih_sm",
    "tahun_operasi", "KBLI (menjadi)", *TARGET_VALUE_COLUMNS, *TARGET_REMARK_COLUMNS,
}


@dataclass
class Candidate:
    file: str
    excel_row: int
    assignment_id: str
    name: str
    category: str
    region: str
    record: dict

    @property
    def source_file(self):
        return IMPORT_PREFIX + self.file

    @property
    def source_key(self):
        return self.source_file, self.excel_row

    @property
    def business_key(self):
        return self.assignment_id, self.name.casefold(), self.category, self.region


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    text = str(value).strip()
    return text if text else None


def normalize_columns(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Pilih nama kolom tanpa spasi pinggir; utamakan header yang sudah tepat."""
    groups = defaultdict(list)
    for column in data.columns:
        groups[str(column).strip()].append(column)
    normalized = {}
    warnings = []
    for name, originals in groups.items():
        exact = next((column for column in originals if str(column) == name), originals[0])
        normalized[name] = data[exact]
        if len(originals) > 1:
            warnings.append(f"header ganda {name!r}; dipakai kolom {str(exact)!r}")
    return pd.DataFrame(normalized), warnings


def make_candidate(row, path: Path, excel_row: int, database_columns: set[str],
                   load_batch: str, round_values: bool) -> Candidate:
    missing = REQUIRED - set(row.index)
    if missing:
        raise ValueError("kolom wajib tidak ditemukan: " + ", ".join(sorted(missing)))
    name = str(row["nama_usaha"]).strip()
    if not name:
        raise ValueError("nama usaha kosong")
    aid = assignment_id(row["link_fasih_sm"])
    category = str(row["kategori"]).strip().upper()
    region = str(row["level_2_full_code"]).strip()
    if not category or not region:
        raise ValueError("kategori atau wilayah kosong")
    if str(row.get("KBLI (menjadi)", "")).strip():
        raise ValueError("perubahan KBLI belum didukung aplikasi")
    year = str(row.get("tahun_operasi", "")).strip()
    if not year.isdigit() or int(year) >= 2026:
        raise ValueError(f"tahun operasi {year!r} belum didukung aplikasi")

    actions = preview_actions(row, FILE_MAPPINGS, round_values)
    prepared = row.to_dict()
    for mapping, _, value, change in actions:
        if change:
            prepared[mapping.nilai] = value

    record = {}
    for column, value in prepared.items():
        destination = DATABASE_PRODUCTION if column == LEGACY_PRODUCTION else column
        if destination in database_columns and destination not in {
            "id", "source_file", "source_row", "load_batch", "loaded_at",
            "assignment_id", "automation_status", "automation_stage",
            "automation_message", "automation_attempts", "automation_bot_id",
            "automation_started_at", "automation_updated_at", "automation_completed_at",
        }:
            record[destination] = clean_value(value)
    record.update({
        "source_file": IMPORT_PREFIX + path.name,
        "source_row": excel_row,
        "load_batch": load_batch,
        "assignment_id": aid,
        "Siap Input": 1,
        "Sudah Diinput": 0,
        "automation_status": "SIAP_DIINPUT",
    })
    return Candidate(path.name, excel_row, aid, name, category, region, record)


def fingerprint(candidate: Candidate):
    columns = [
        DATABASE_PRODUCTION if value == LEGACY_PRODUCTION else value
        for value in TARGET_VALUE_COLUMNS
    ] + TARGET_REMARK_COLUMNS
    return tuple((column, candidate.record.get(column)) for column in columns)


def deduplicate(candidates: list[Candidate]):
    groups = defaultdict(list)
    for candidate in candidates:
        groups[candidate.assignment_id].append(candidate)
    kept, held = [], []
    for _, rows in groups.items():
        if len(rows) == 1:
            kept.append(rows[0])
            continue
        same_business = len({row.business_key for row in rows}) == 1
        same_values = len({fingerprint(row) for row in rows}) == 1
        if same_business and same_values:
            ordered = sorted(rows, key=lambda row: (row.file, row.excel_row))
            kept.append(ordered[0])
            for row in ordered[1:]:
                held.append((row, "duplikat identik; dipakai satu baris saja"))
        else:
            for row in rows:
                held.append((row, "assignment muncul pada beberapa baris yang tidak identik"))
    return kept, held


def chunks(values, size):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def database_rows(api: CentralAPI, candidates: list[Candidate]):
    table = api._quote(api.config.source_table)
    result = []
    source_files = sorted({candidate.source_file for candidate in candidates})
    if source_files:
        literals = ",".join(api._literal(value) for value in source_files)
        result.extend(api._query(
            f"SELECT id,source_file,source_row,assignment_id,nama_usaha,kategori,level_2_full_code,"
            f"{api._quote('Sudah Diinput')} AS sudah_diinput,automation_status "
            f"FROM {table} WHERE source_file IN ({literals})"
        ))
    ids = sorted({candidate.assignment_id for candidate in candidates})
    for batch in chunks(ids, 150):
        literals = ",".join(api._literal(value) for value in batch)
        result.extend(api._query(
            f"SELECT id,source_file,source_row,assignment_id,nama_usaha,kategori,level_2_full_code,"
            f"{api._quote('Sudah Diinput')} AS sudah_diinput,automation_status "
            f"FROM {table} WHERE assignment_id IN ({literals})"
        ))
    unique = {}
    for row in result:
        unique[int(row["id"])] = row
    return list(unique.values())


def is_checked(value):
    return str(value or "").strip().casefold() in CHECKED


def classify(candidates: list[Candidate], existing: list[dict]):
    by_source = defaultdict(list)
    by_assignment = defaultdict(list)
    by_business = defaultdict(list)
    for row in existing:
        source_key = (str(row.get("source_file") or ""), int(row.get("source_row") or 0))
        by_source[source_key].append(row)
        aid = str(row.get("assignment_id") or "").strip().lower()
        by_assignment[aid].append(row)
        business_key = (
            aid,
            str(row.get("nama_usaha") or "").strip().casefold(),
            str(row.get("kategori") or "").strip().upper(),
            str(row.get("level_2_full_code") or "").strip(),
        )
        by_business[business_key].append(row)

    inserts, updates, held = [], [], []
    for candidate in candidates:
        matches = by_source.get(candidate.source_key, [])
        if not matches:
            matches = by_business.get(candidate.business_key, [])
        if not matches and by_assignment.get(candidate.assignment_id):
            held.append((candidate, "assignment sudah ada dengan identitas usaha/wilayah berbeda"))
            continue
        if len(matches) > 1:
            held.append((candidate, "lebih dari satu baris database cocok; pembaruan ambigu"))
            continue
        if not matches:
            inserts.append(candidate)
            continue
        current = matches[0]
        status = str(current.get("automation_status") or "BELUM_DIANTREKAN").strip().upper()
        if is_checked(current.get("sudah_diinput")) or status in {
            "BERJALAN", "BERHASIL", "ERROR", "PERLU_DATA", "PERLU_DIPERIKSA",
        }:
            held.append((candidate, f"baris database sudah memiliki status {status}"))
            continue
        updates.append((candidate, int(current["id"])))
    return inserts, updates, held


def sql_value(api: CentralAPI, value):
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return api._literal(value)


def update_existing(api: CentralAPI, candidate: Candidate, source_id: int):
    writable = {
        DATABASE_PRODUCTION,
        *[value for value in TARGET_VALUE_COLUMNS if value != LEGACY_PRODUCTION],
        *TARGET_REMARK_COLUMNS,
        "Siap Input", "Sudah Diinput", "automation_status",
    }
    assignments = []
    for column in sorted(writable):
        if column in candidate.record:
            assignments.append(f"{api._quote(column)}={sql_value(api, candidate.record[column])}")
    assignments.extend((
        "automation_stage=NULL", "automation_message=NULL", "automation_updated_at=NOW()"
    ))
    table = api._quote(api.config.source_table)
    api._update(
        f"UPDATE {table} SET {', '.join(assignments)} WHERE id={int(source_id)} "
        f"AND COALESCE({api._quote('Sudah Diinput')},0)=0 "
        "AND COALESCE(automation_status,'BELUM_DIANTREKAN') IN ('BELUM_DIANTREKAN','SIAP_DIINPUT')"
    )


def insert_new(api: CentralAPI, candidates: list[Candidate], batch_size: int):
    for batch in chunks(candidates, batch_size):
        api._request(api.config.insert_url, {
            "database": api.config.database,
            "table_name": api.config.source_table,
            "if_exists": "append",
            "records": [candidate.record for candidate in batch],
        })


def verify_written(api: CentralAPI, inserts: list[Candidate], updates: list[tuple[Candidate, int]]):
    """Pastikan semua baris yang ditulis benar-benar berstatus siap input."""
    table = api._quote(api.config.source_table)
    expected = set()
    found = set()

    by_file = defaultdict(list)
    for candidate in inserts:
        key = ("source", candidate.source_file, candidate.excel_row)
        expected.add(key)
        by_file[candidate.source_file].append(candidate.excel_row)
    for source_file, source_rows in by_file.items():
        for batch in chunks(sorted(set(source_rows)), 150):
            row_literals = ",".join(str(int(value)) for value in batch)
            rows = api._query(
                f"SELECT source_file,source_row,{api._quote('Siap Input')} AS siap_input,"
                f"{api._quote('Sudah Diinput')} AS sudah_diinput,automation_status "
                f"FROM {table} WHERE source_file={api._literal(source_file)} "
                f"AND source_row IN ({row_literals})"
            )
            for row in rows:
                if (is_checked(row.get("siap_input")) and
                        not is_checked(row.get("sudah_diinput")) and
                        str(row.get("automation_status") or "").upper() == "SIAP_DIINPUT"):
                    found.add(("source", str(row.get("source_file")), int(row.get("source_row"))))

    update_ids = [source_id for _, source_id in updates]
    for source_id in update_ids:
        expected.add(("id", int(source_id)))
    for batch in chunks(update_ids, 150):
        if not batch:
            continue
        id_literals = ",".join(str(int(value)) for value in batch)
        rows = api._query(
            f"SELECT id,{api._quote('Siap Input')} AS siap_input,"
            f"{api._quote('Sudah Diinput')} AS sudah_diinput,automation_status "
            f"FROM {table} WHERE id IN ({id_literals})"
        )
        for row in rows:
            if (is_checked(row.get("siap_input")) and
                    not is_checked(row.get("sudah_diinput")) and
                    str(row.get("automation_status") or "").upper() == "SIAP_DIINPUT"):
                found.add(("id", int(row["id"])))

    missing = expected - found
    if missing:
        raise CentralError(
            f"verifikasi pascatulis gagal: {len(missing)} dari {len(expected)} baris "
            "belum ditemukan dengan status SIAP_DIINPUT"
        )
    return len(found)


def save_report(rows, summary, mode):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = OUTPUT / f"impor_ub_{mode}_{stamp}.csv"
    summary_path = OUTPUT / f"impor_ub_{mode}_{stamp}.json"
    pd.DataFrame(rows, columns=[
        "file", "baris_excel", "kategori", "wilayah", "assignment_id", "aksi", "alasan"
    ]).to_csv(report_path, index=False, encoding="utf-8-sig")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path, summary_path


def main():
    parser = argparse.ArgumentParser(description="Impor aman folder SIAP INPUT UB ke database pusat.")
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--execute", action="store_true", help="Tulis ke database. Tanpa opsi ini hanya dry-run.")
    parser.add_argument("--round-values", action="store_true", help="Bulatkan nilai rupiah desimal, 0,5 naik.")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--load-batch", default="SIAP_INPUT_UB_20261021")
    args = parser.parse_args()
    if not args.folder.is_dir():
        raise SystemExit(f"Folder tidak ditemukan: {args.folder}")
    if not 1 <= args.batch_size <= 500:
        raise SystemExit("--batch-size harus antara 1 dan 500.")
    config = load_config(CONFIG_FILE)
    if not config:
        raise SystemExit("config_pusat.json belum berisi token database pusat.")
    api = CentralAPI(config, timeout=(10, 90))
    database_columns = set(api.source_columns())

    candidates = []
    report_rows = []
    warnings = []
    files = sorted(args.folder.glob("*.xlsx"))
    if not files:
        raise SystemExit("Tidak ada file XLSX pada folder sumber.")
    for path in files:
        data, column_warnings = normalize_columns(pd.read_excel(
            path, sheet_name=0, dtype=str, keep_default_na=False
        ))
        warnings.extend(f"{path.name}: {message}" for message in column_warnings)
        for index, row in data.iterrows():
            excel_row = int(index) + 2
            try:
                candidates.append(make_candidate(
                    row, path, excel_row, database_columns, args.load_batch, args.round_values
                ))
            except Exception as exc:
                report_rows.append((
                    path.name, excel_row, str(row.get("kategori", "")).strip().upper(),
                    str(row.get("level_2_full_code", "")).strip(), "", "DITAHAN", str(exc),
                ))

    candidates, duplicate_held = deduplicate(candidates)
    for candidate, reason in duplicate_held:
        report_rows.append((candidate.file, candidate.excel_row, candidate.category,
                            candidate.region, candidate.assignment_id, "DITAHAN", reason))

    existing = database_rows(api, candidates)
    inserts, updates, database_held = classify(candidates, existing)
    for candidate, reason in database_held:
        report_rows.append((candidate.file, candidate.excel_row, candidate.category,
                            candidate.region, candidate.assignment_id, "DITAHAN", reason))
    for candidate in inserts:
        report_rows.append((candidate.file, candidate.excel_row, candidate.category,
                            candidate.region, candidate.assignment_id, "INSERT", "baris baru"))
    for candidate, source_id in updates:
        report_rows.append((candidate.file, candidate.excel_row, candidate.category,
                            candidate.region, candidate.assignment_id, "UPDATE", f"id database {source_id}"))

    mode = "execute" if args.execute else "dry_run"
    held_reasons = Counter(row[6] for row in report_rows if row[5] == "DITAHAN")
    summary = {
        "mode": mode,
        "database": config.database,
        "table": config.source_table,
        "folder": str(args.folder.resolve()),
        "files": len(files),
        "source_rows": sum(1 for _ in report_rows),
        "round_values": args.round_values,
        "insert": len(inserts),
        "update": len(updates),
        "held": sum(1 for row in report_rows if row[5] == "DITAHAN"),
        "held_reasons": dict(sorted(held_reasons.items())),
        "warnings": warnings,
    }
    report_path, summary_path = save_report(report_rows, summary, mode)
    summary["report_csv"] = str(report_path)
    summary["summary_json"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        print("DRY-RUN: database belum diubah. Tambahkan --execute setelah laporan diperiksa.")
        return

    for candidate, source_id in updates:
        update_existing(api, candidate, source_id)
    insert_new(api, inserts, args.batch_size)
    verified = verify_written(api, inserts, updates)
    summary["verified_ready"] = verified
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"SELESAI: {len(updates)} baris diperbarui, {len(inserts)} baris ditambahkan, "
        f"dan {verified} baris terverifikasi SIAP_DIINPUT."
    )


if __name__ == "__main__":
    try:
        main()
    except (CentralError, OSError, ValueError) as exc:
        raise SystemExit(f"GAGAL: {exc}") from exc
