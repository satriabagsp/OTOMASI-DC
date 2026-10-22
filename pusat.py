"""Klien API untuk jurnal bersama OTOMASI_DC."""
from __future__ import annotations

import json
import os
import re
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests


DEFAULT_BASE_URL = "http://103.54.218.181:8555/api/v1/gateway"
DEFAULT_DATABASE = "OTOMASI_DC"
DEFAULT_TABLE = "hasil_otomasi_dc"
DEFAULT_SOURCE_TABLE = "data_split_usaha_20261016"
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KATEGORI = re.compile(r"^[A-Za-z0-9]+$")
WILAYAH = re.compile(r"^\d+$")


class CentralError(RuntimeError):
    """Kesalahan koneksi atau respons API pusat yang aman ditampilkan."""


@dataclass(frozen=True)
class CentralConfig:
    base_url: str
    token: str
    database: str = DEFAULT_DATABASE
    table: str = DEFAULT_TABLE
    source_table: str = DEFAULT_SOURCE_TABLE
    bot_id: str = ""

    def __post_init__(self):
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("URL API pusat harus diawali http:// atau https://.")
        if (not IDENTIFIER.fullmatch(self.database) or not IDENTIFIER.fullmatch(self.table)
                or not IDENTIFIER.fullmatch(self.source_table)):
            raise ValueError("Nama database atau tabel pusat tidak valid.")
        if not self.token.strip():
            raise ValueError("Token API pusat belum diisi.")
        if not self.bot_id.strip():
            raise ValueError("Identitas PC/bot belum diisi.")

    @property
    def query_url(self):
        return self.base_url.rstrip("/") + "/query"

    @property
    def insert_url(self):
        return self.base_url.rstrip("/") + "/insert"


def default_bot_id():
    return socket.gethostname().strip() or "PC-TANPA-NAMA"


def load_config(path: Path):
    """Muat konfigurasi lokal; environment variable memiliki prioritas."""
    path = Path(path)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Konfigurasi database pusat tidak dapat dibaca: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Konfigurasi database pusat harus berupa objek JSON.")

    token = os.environ.get("OTOMASI_DC_API_TOKEN", data.get("token", ""))
    if not str(token).strip():
        return None
    return CentralConfig(
        base_url=str(os.environ.get("OTOMASI_DC_API_URL", data.get("base_url", DEFAULT_BASE_URL))).strip(),
        token=str(token).strip(),
        database=str(os.environ.get("OTOMASI_DC_DATABASE", data.get("database", DEFAULT_DATABASE))).strip(),
        table=str(os.environ.get("OTOMASI_DC_TABLE", data.get("table", DEFAULT_TABLE))).strip(),
        source_table=str(os.environ.get(
            "OTOMASI_DC_SOURCE_TABLE", data.get("source_table", DEFAULT_SOURCE_TABLE)
        )).strip(),
        bot_id=str(os.environ.get("OTOMASI_DC_BOT_ID", data.get("bot_id", default_bot_id()))).strip(),
    )


def save_config(path: Path, config: CentralConfig):
    """Simpan konfigurasi secara atomik di komputer pengguna."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({
        "base_url": config.base_url,
        "database": config.database,
        "table": config.table,
        "source_table": config.source_table,
        "bot_id": config.bot_id,
        "token": config.token,
    }, ensure_ascii=False, indent=2)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".config_pusat_", suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(content)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


class CentralAPI:
    def __init__(self, config: CentralConfig, post=requests.post, timeout=(4, 12)):
        self.config = config
        self.post = post
        self.timeout = timeout

    @property
    def headers(self):
        return {"Content-Type": "application/json", "X-Admin-Token": self.config.token}

    def _request(self, url, payload):
        try:
            response = self.post(url, headers=self.headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            raise CentralError(f"API pusat tidak dapat dihubungi: {exc}") from exc
        except (ValueError, TypeError) as exc:
            raise CentralError("Respons API pusat bukan JSON yang valid.") from exc
        if not isinstance(result, dict):
            raise CentralError("Format respons API pusat tidak dikenali.")
        return result

    @staticmethod
    def _quote(name):
        return "`" + str(name).replace("`", "``") + "`"

    @staticmethod
    def _literal(value):
        return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"

    @property
    def update_url(self):
        return self.config.base_url.rstrip("/") + "/update"

    def _query(self, sql):
        result = self._request(self.config.query_url, {
            "database": self.config.database,
            "sql": sql,
        })
        rows = result.get("results")
        if not isinstance(rows, list):
            raise CentralError("Respons query pusat tidak memiliki daftar results.")
        return rows

    def _update(self, sql):
        return self._request(self.update_url, {
            "database": self.config.database,
            "sql": sql,
        })

    def source_columns(self):
        """Ambil nama kolom tabel sumber tanpa memuat seluruh tabel."""
        table = self._quote(self.config.source_table)
        rows = self._query(f"SELECT * FROM {table} LIMIT 1")
        if rows:
            return list(rows[0])
        fields = self._query(f"SHOW COLUMNS FROM {table}")
        return [str(row.get("Field", "")) for row in fields if row.get("Field")]

    def source_rows(self, kategori, wilayah, limit, *, reverse=False,
                    split="semua", retry_errors=False):
        """Ambil batch kecil yang siap diproses dari tabel sumber."""
        kategori = str(kategori).strip().upper()
        wilayah = str(wilayah).strip()
        if not KATEGORI.fullmatch(kategori) or not WILAYAH.fullmatch(wilayah):
            raise ValueError("Kategori atau kode wilayah tidak valid untuk database pusat.")
        if split not in {"semua", "atas", "bawah"}:
            raise ValueError("Pembagian antrean database tidak valid.")
        limit = int(limit)
        if limit < 1 or limit > 5000:
            raise ValueError("Jumlah pengambilan database harus antara 1 dan 5000.")
        table = self._quote(self.config.source_table)
        allowed = ["BELUM_DIANTREKAN", "SIAP_DIINPUT"]
        if retry_errors:
            allowed.extend(("ERROR", "PERLU_DATA"))
        statuses = ",".join(self._literal(value) for value in allowed)
        descending = bool(reverse) ^ (split == "bawah")
        order = "DESC" if descending else "ASC"
        sql = (
            f"SELECT * FROM {table} "
            f"WHERE kategori={self._literal(kategori)} "
            f"AND level_2_full_code={self._literal(wilayah)} "
            f"AND {self._quote('Siap Input')}=1 "
            f"AND COALESCE({self._quote('Sudah Diinput')},0)=0 "
            f"AND COALESCE(automation_status,'BELUM_DIANTREKAN') IN ({statuses}) "
            f"ORDER BY id {order} LIMIT {limit}"
        )
        return self._query(sql)

    def duplicate_source_ids(self, assignment_ids, *, chunk_size=100):
        """Cari assignment siap input yang muncul pada lebih dari satu baris.

        ID diperiksa per kelompok kecil. Daftar ``IN`` yang berisi ribuan ID
        membuat gateway pusat melewati batas waktu, terutama saat pratinjau
        mengambil kandidat cadangan untuk melewati baris yang tidak layak.
        """
        values = sorted({str(value).strip().lower() for value in assignment_ids if str(value).strip()})
        if not values:
            return set()
        if any(not re.fullmatch(r"[0-9a-f-]{36}", value) for value in values):
            raise ValueError("Assignment ID untuk pemeriksaan duplikat tidak valid.")
        chunk_size = int(chunk_size)
        if chunk_size < 1 or chunk_size > 250:
            raise ValueError("Ukuran pemeriksaan duplikat harus antara 1 dan 250.")
        table = self._quote(self.config.source_table)
        duplicates = set()
        for start in range(0, len(values), chunk_size):
            chunk = values[start:start + chunk_size]
            literals = ",".join(self._literal(value) for value in chunk)
            rows = self._query(
                f"SELECT assignment_id, COUNT(*) AS jumlah FROM {table} "
                f"WHERE assignment_id IN ({literals}) "
                f"AND {self._quote('Siap Input')}=1 "
                f"AND COALESCE({self._quote('Sudah Diinput')},0)=0 "
                "GROUP BY assignment_id HAVING COUNT(*) > 1"
            )
            duplicates.update(
                str(row["assignment_id"]).strip().lower()
                for row in rows if row.get("assignment_id")
            )
        return duplicates

    def claim_source(self, source_id, *, retry_errors=False):
        """Kunci satu baris secara bersyarat, lalu verifikasi pemilik kuncinya."""
        source_id = int(source_id)
        allowed = ["BELUM_DIANTREKAN", "SIAP_DIINPUT"]
        if retry_errors:
            allowed.extend(("ERROR", "PERLU_DATA"))
        statuses = ",".join(self._literal(value) for value in allowed)
        table = self._quote(self.config.source_table)
        bot = self._literal(self.config.bot_id)
        self._update(
            f"UPDATE {table} SET automation_status='BERJALAN', automation_bot_id={bot}, "
            "automation_stage='mulai', automation_message=NULL, "
            "automation_started_at=NOW(), automation_updated_at=NOW(), "
            "automation_attempts=COALESCE(automation_attempts,0)+1 "
            f"WHERE id={source_id} AND {self._quote('Siap Input')}=1 "
            f"AND COALESCE({self._quote('Sudah Diinput')},0)=0 "
            f"AND COALESCE(automation_status,'BELUM_DIANTREKAN') IN ({statuses})"
        )
        rows = self._query(
            f"SELECT automation_status, automation_bot_id FROM {table} WHERE id={source_id} LIMIT 1"
        )
        return bool(rows and rows[0].get("automation_status") == "BERJALAN"
                    and str(rows[0].get("automation_bot_id", "")) == self.config.bot_id)

    def release_checked_source(self, assignment_id):
        """Buka kembali hanya baris tertunda milik bot ini setelah diperiksa pengguna."""
        aid = str(assignment_id).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", aid):
            raise ValueError("Assignment ID tidak valid.")
        table = self._quote(self.config.source_table)
        rows = self._query(
            f"SELECT id, automation_status, automation_bot_id, "
            f"{self._quote('Siap Input')} AS siap, {self._quote('Sudah Diinput')} AS sudah "
            f"FROM {table} WHERE assignment_id={self._literal(aid)} LIMIT 2"
        )
        if len(rows) != 1:
            raise CentralError("Assignment harus ditemukan tepat satu kali di tabel sumber.")
        row = rows[0]
        if str(row.get("siap", "")).strip() not in {"1", "True", "true"} or str(row.get("sudah", "")).strip() not in {"0", "False", "false", "None"}:
            raise CentralError("Baris sumber tidak dalam keadaan siap untuk dicoba ulang.")
        status = row.get("automation_status")
        if status == "SIAP_DIINPUT":
            return
        if status != "PERLU_DIPERIKSA" or row.get("automation_bot_id") != self.config.bot_id:
            raise CentralError("Status baris sumber atau pemilik bot tidak sesuai untuk izin ulang.")
        source_id = int(row["id"])
        sql = (
            f"UPDATE {table} SET automation_status='SIAP_DIINPUT', "
            "automation_stage='diizinkan_ulang', automation_message='Diperiksa dan diizinkan ulang oleh pengguna', "
            "automation_updated_at=NOW() "
            f"WHERE id={source_id} AND assignment_id={self._literal(aid)} "
            "AND automation_status='PERLU_DIPERIKSA' "
            f"AND automation_bot_id={self._literal(self.config.bot_id)} "
            f"AND {self._quote('Siap Input')}=1 AND COALESCE({self._quote('Sudah Diinput')},0)=0"
        )
        try:
            self._update(sql)
        except CentralError:
            # Gateway kadang mengembalikan 500 setelah UPDATE sebenarnya tersimpan.
            pass
        current = self._query(
            f"SELECT automation_status FROM {table} WHERE id={source_id} LIMIT 1"
        )
        if not current or current[0].get("automation_status") != "SIAP_DIINPUT":
            raise CentralError("Izin ulang belum tersimpan di tabel sumber.")

    def complete_source(self, source_id, status, stage, message):
        """Simpan hasil otomasi ke baris sumber yang sedang dikunci bot ini."""
        statuses = {"BERHASIL", "ERROR", "PERLU_DATA", "PERLU_DIPERIKSA"}
        if status not in statuses:
            raise ValueError(f"Status sumber tidak valid: {status}")
        source_id = int(source_id)
        table = self._quote(self.config.source_table)
        sent = f", {self._quote('Sudah Diinput')}=1" if status == "BERHASIL" else ""
        completed = ", automation_completed_at=NOW()" if status == "BERHASIL" else ""
        # Playwright dapat memberi call log beberapa halaman. Simpan rincian utuh di
        # jurnal lokal, tetapi kirim ringkasan satu baris ke gateway pusat.
        short_message = " ".join(str(message).split())[:480]
        sql = (
            f"UPDATE {table} SET automation_status={self._literal(status)}, "
            f"automation_stage={self._literal(str(stage)[:80])}, "
            f"automation_message={self._literal(short_message)}, "
            f"automation_updated_at=NOW(){completed}{sent} "
            f"WHERE id={source_id} AND automation_status='BERJALAN' "
            f"AND automation_bot_id={self._literal(self.config.bot_id)}"
        )
        try:
            self._update(sql)
        except CentralError:
            # Respons 500 tidak membuktikan UPDATE gagal; baca dahulu agar tidak
            # mengulang operasi yang sebenarnya telah tersimpan.
            current = self._query(
                f"SELECT automation_status FROM {table} WHERE id={source_id} LIMIT 1"
            )
            if not current or current[0].get("automation_status") != status:
                # Gateway tertentu gagal pada pesan panjang/karakter call log.
                # Coba ringkasan yang lebih kecil dengan syarat kunci yang sama.
                fallback = (
                    f"UPDATE {table} SET automation_status={self._literal(status)}, "
                    f"automation_stage={self._literal(str(stage)[:80])}, "
                    f"automation_message={self._literal(short_message[:160])}, "
                    f"automation_updated_at=NOW(){completed}{sent} "
                    f"WHERE id={source_id} AND automation_status='BERJALAN' "
                    f"AND automation_bot_id={self._literal(self.config.bot_id)}"
                )
                self._update(fallback)
        rows = self._query(
            f"SELECT automation_status, {self._quote('Sudah Diinput')} AS sudah "
            f"FROM {table} WHERE id={source_id} LIMIT 1"
        )
        if not rows or rows[0].get("automation_status") != status:
            raise CentralError("Status baris sumber tidak berhasil diverifikasi setelah pembaruan.")
        if status == "BERHASIL" and str(rows[0].get("sudah", "")).strip() not in {"1", "True", "true"}:
            raise CentralError("Kolom Sudah Diinput belum tersimpan setelah proses berhasil.")

    def completed_ids(self, kategori: str, wilayah: str):
        kategori = str(kategori).strip().upper()
        wilayah = str(wilayah).strip()
        if not KATEGORI.fullmatch(kategori) or not WILAYAH.fullmatch(wilayah):
            raise ValueError("Kategori atau kode wilayah tidak valid untuk database pusat.")
        sql = (f"SELECT DISTINCT assignment_id FROM {self.config.table} "
               f"WHERE status = 'berhasil' AND kategori = '{kategori}' AND wilayah = '{wilayah}'")
        result = self._request(self.config.query_url, {"database": self.config.database, "sql": sql})
        rows = result.get("results")
        if not isinstance(rows, list):
            raise CentralError("Respons query pusat tidak memiliki daftar results.")
        ids = set()
        for row in rows:
            if isinstance(row, dict) and row.get("assignment_id") is not None:
                value = str(row["assignment_id"]).strip().lower()
                if value:
                    ids.add(value)
        return ids

    def record(self, *, assignment_id, kategori, wilayah, nama_file, nama_sheet,
               status, tahap, kode_rincian=None, pesan=None):
        if status not in {"berhasil", "error", "perlu_data", "perlu_diperiksa"}:
            raise ValueError(f"Status pusat tidak valid: {status}")
        record = {
            "assignment_id": str(assignment_id).strip().lower(),
            "kategori": str(kategori).strip().upper(),
            "wilayah": str(wilayah).strip(),
            "nama_file": Path(str(nama_file)).name,
            "nama_sheet": str(nama_sheet).strip() or None,
            "status": status,
            "tahap": str(tahap).strip()[:50] or None,
            "kode_rincian": str(kode_rincian).strip()[:100] if kode_rincian else None,
            "pesan": str(pesan).strip()[:30000] if pesan else None,
            "bot_id": self.config.bot_id,
        }
        self._request(self.config.insert_url, {
            "database": self.config.database,
            "table_name": self.config.table,
            "if_exists": "append",
            "records": [record],
        })
