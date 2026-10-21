"""Tes lokal importer UB; tidak membaca atau menulis database pusat."""
import unittest
from pathlib import Path

import pandas as pd

from core import TARGETS
from import_siap_input_ub import (
    DATABASE_PRODUCTION,
    Candidate,
    classify,
    deduplicate,
    make_candidate,
)


def source_row():
    row = {
        "kategori": "G",
        "level_2_full_code": "3201",
        "nama_usaha": "Usaha Uji",
        "link_fasih_sm": (
            "https://fasih-sm.bps.go.id/app/assignment/"
            "11111111-1111-1111-1111-111111111111/"
            "22222222-2222-2222-2222-222222222222"
        ),
        "tahun_operasi": "2025",
        "KBLI (menjadi)": "",
    }
    for _, _, value, remark in TARGETS:
        row[value] = ""
        row[remark] = "#0"
    row["metrik_biaya_produksin (mejadi)"] = "10.5"
    row["metrik_biaya_produksin (Remark)"] = "#3"
    return pd.Series(row)


class ImportTests(unittest.TestCase):
    def test_candidate_membulatkan_dan_memakai_nama_kolom_database(self):
        columns = set(source_row().index)
        columns.remove("metrik_biaya_produksin (mejadi)")
        columns.add(DATABASE_PRODUCTION)
        candidate = make_candidate(
            source_row(), Path("G.xlsx"), 2, columns, "UJI", round_values=True
        )
        self.assertEqual(candidate.record[DATABASE_PRODUCTION], "11")
        self.assertEqual(candidate.record["automation_status"], "SIAP_DIINPUT")

    def test_duplikat_identik_hanya_menyimpan_satu(self):
        record = {DATABASE_PRODUCTION: "11"}
        first = Candidate("H.xlsx", 2, "abc", "Usaha", "H", "3201", record)
        second = Candidate("H.xlsx", 3, "abc", "Usaha", "H", "3201", record.copy())
        kept, held = deduplicate([first, second])
        self.assertEqual((len(kept), len(held)), (1, 1))

    def test_status_sudah_berjalan_tidak_ditimpakan(self):
        candidate = Candidate("G.xlsx", 2, "abc", "Usaha", "G", "3201", {})
        existing = [{
            "id": 5,
            "source_file": candidate.source_file,
            "source_row": 2,
            "assignment_id": "abc",
            "nama_usaha": "Usaha",
            "kategori": "G",
            "level_2_full_code": "3201",
            "sudah_diinput": 0,
            "automation_status": "BERJALAN",
        }]
        inserts, updates, held = classify([candidate], existing)
        self.assertEqual((len(inserts), len(updates), len(held)), (0, 0, 1))


if __name__ == "__main__":
    unittest.main()
