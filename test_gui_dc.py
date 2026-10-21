import tempfile
import unittest
from pathlib import Path

import pandas as pd
from core import Journal, Mapping, check_duplicate_assignments, make_queue, old_ids, preview_actions, validate_mappings
from daftar_perbaikan import load_lists, save_lists
from katalog_rincian import L, P


def row(aid, remark='#DC_00', value='', ready='1'):
    return {'kategori':'G', 'level_2_full_code':'3201', 'nama_usaha':'USAHA CONTOH',
            'link_fasih_sm':f'https://fasih-sm.bps.go.id/app/assignment/11111111-1111-1111-1111-111111111111/{aid}',
            'Siap Input':ready, 'Sudah Diinput':'', 'nilai':value, 'remark':remark}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.mapping = [Mapping('Gaji', 'gaji', 'nilai', 'remark')]
        self.ids = [f'{i:08x}-0000-0000-0000-000000000000' for i in range(1, 7)]
        self.data = pd.DataFrame([row(i) for i in self.ids])
        self.data['_baris_sumber'] = self.data.index + 2

    def test_dc00_and_other_remarks(self):
        self.assertFalse(preview_actions(self.data.iloc[0], self.mapping)[0][3])
        data = row(self.ids[0], '#0', '99999')
        self.assertFalse(preview_actions(data, self.mapping)[0][3])
        data = row(self.ids[0], '#DC_03', '')
        with self.assertRaisesRegex(ValueError, 'membutuhkan nilai'):
            preview_actions(data, self.mapping)
        data['nilai'] = '12000'
        self.assertTrue(preview_actions(data, self.mapping)[0][3])
        data['nilai'] = '12.000'
        with self.assertRaisesRegex(ValueError, 'ambigu'):
            preview_actions(data, self.mapping)

    def test_fraction_requires_explicit_rounding(self):
        data = row(self.ids[0], '#DC_03', '2494322493.05')
        with self.assertRaisesRegex(ValueError, 'centang pilihan pembulatan'):
            preview_actions(data, self.mapping)
        self.assertEqual(preview_actions(data, self.mapping, True)[0][2], '2494322493')
        data['nilai'] = '35769491136.6897'
        self.assertEqual(preview_actions(data, self.mapping, True)[0][2], '35769491137')
        data['nilai'] = '1000.5'
        self.assertEqual(preview_actions(data, self.mapping, True)[0][2], '1001')
        data['nilai'] = '1,000'
        with self.assertRaisesRegex(ValueError, 'pemisah ribuan'):
            preview_actions(data, self.mapping, True)

    def test_dynamic_text_value_only_and_note_only(self):
        text_mapping = [Mapping('Nama komersial', 'nama_komersial', 'nilai', '', L)]
        data = row(self.ids[0], value='TOKO BARU 01')
        validate_mappings(data.keys(), text_mapping)
        self.assertEqual(preview_actions(data, text_mapping)[0][2:], ('TOKO BARU 01', True))
        note_mapping = [Mapping('Status badan usaha', 'badan_usaha', '', 'remark', L)]
        data['remark'] = '#DC_03'
        validate_mappings(data.keys(), note_mapping)
        self.assertEqual(preview_actions(data, note_mapping)[0][1:], ('#DC_03', '', False))
        with self.assertRaisesRegex(ValueError, 'hanya didukung untuk remark'):
            validate_mappings(data.keys(), [Mapping('Status badan usaha', 'badan_usaha', 'nilai', 'remark', L)])
        with self.assertRaisesRegex(ValueError, 'belum didukung'):
            validate_mappings(data.keys(), [Mapping('Jenis Prelist', 'jenis_prelist', 'nilai', '', P)])

    def test_saved_list_round_trip_and_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'daftar.json'
            saved = load_lists(path)
            saved['terpilih'] = 'Perbaikan G'
            saved['daftar']['Perbaikan G'] = [{'pakai':True, 'blok':L, 'kode':'gaji', 'nilai':'upah', 'remark':'catatan'}]
            save_lists(path, saved)
            self.assertEqual(load_lists(path), saved)
            broken = {'versi':1, 'terpilih':'x', 'daftar':{'x':[{'pakai':True, 'blok':L, 'kode':'tidak_ada', 'nilai':'', 'remark':'x'}]}}
            save_lists(path, broken)
            with self.assertRaisesRegex(ValueError, 'tidak ada di katalog'):
                load_lists(path)

    def test_errors_beyond_limit_do_not_block_preview(self):
        self.data.loc[5, ['remark', 'nilai']] = ['#DC_03', '2.5']
        self.assertEqual(len(make_queue(self.data, self.mapping, 'G', '3201', set(), {}, limit=1)), 1)
        with self.assertRaisesRegex(ValueError, 'desimal'):
            make_queue(self.data, self.mapping, 'G', '3201', set(), {}, limit=6)
        self.assertEqual(len(make_queue(self.data, self.mapping, 'G', '3201', set(), {}, limit=6, round_values=True)), 6)

    def test_split_does_not_shift_after_success(self):
        top = make_queue(self.data, self.mapping, 'G', '3201', set(), {}, split='atas', limit=100)
        bottom = make_queue(self.data, self.mapping, 'G', '3201', {self.ids[0]}, {}, split='bawah', limit=100)
        self.assertEqual([x['assignment_id'] for x in top], self.ids[:3])
        self.assertEqual([x['assignment_id'] for x in bottom], self.ids[3:])

    def test_reverse_and_completed(self):
        rows = make_queue(self.data, self.mapping, 'G', '3201', {self.ids[-1]}, {}, reverse=True, limit=2)
        self.assertEqual([x['assignment_id'] for x in rows], [self.ids[-2], self.ids[-3]])

    def test_duplicate_even_when_other_row_not_ready(self):
        copy = self.data.iloc[[0]].copy()
        copy['Siap Input'] = ''
        data = pd.concat([self.data, copy], ignore_index=True)
        with self.assertRaisesRegex(ValueError, 'beberapa baris'):
            check_duplicate_assignments(data, 'G', '3201', set(), {})

    def test_journal_claim_is_exclusive_and_retry_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            first, second = Journal(path / 'status.sqlite3'), Journal(path / 'status.sqlite3')
            aid = self.ids[0]
            self.assertTrue(first.claim(aid, 'USAHA', 'input.xlsx', 2))
            self.assertFalse(second.claim(aid, 'USAHA', 'input.xlsx', 2))
            first.finish(aid, 'error', 'contoh galat')
            self.assertFalse(second.claim(aid, 'USAHA', 'input.xlsx', 2))
            first.allow_retry(aid)
            self.assertTrue(second.claim(aid, 'USAHA', 'input.xlsx', 2))
            second.finish(aid, 'berhasil', 'OK')
            with self.assertRaises(ValueError):
                first.allow_retry(aid)
            first.export(path)
            self.assertTrue((path / 'rekap_error_gui.xlsx').exists())

    def test_notebook_logs(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            pd.DataFrame([{'assignment_id':self.ids[0], 'status':'berhasil'}]).to_csv(path / 'G_3201_selesai_atas.csv', index=False)
            pd.DataFrame([{'assignment_id':self.ids[1]}]).to_excel(path / 'G_3201_error_usaha_2026_bawah.xlsx', index=False)
            self.assertEqual(old_ids(path, 'G', '3201', True), {self.ids[0], self.ids[1]})
            self.assertEqual(old_ids(path, 'G', '3201', False), {self.ids[0]})

    def test_retry_errors_only_and_clean_export_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            first, second = Journal(path / 'status.sqlite3'), Journal(path / 'status.sqlite3')
            for aid in self.ids[:3]:
                self.assertTrue(first.claim(aid, 'USAHA', 'input.xlsx', 2))
            first.finish(self.ids[0], 'error', 'galat lama')
            first.finish(self.ids[1], 'berhasil', 'sudah sukses')
            first.export(path)
            self.assertEqual(len(pd.read_excel(path / 'rekap_error_gui.xlsx')), 1)
            self.assertEqual(first.statuses(include_errors=False), {self.ids[1]: 'berhasil', self.ids[2]: 'berjalan'})
            queued = make_queue(self.data, self.mapping, 'G', '3201', set(), first.statuses(include_errors=False), limit=6)
            self.assertEqual([r['assignment_id'] for r in queued], [self.ids[0], *self.ids[3:]])
            self.assertFalse(second.claim(self.ids[0], 'USAHA', 'input.xlsx', 2))
            self.assertTrue(first.claim(self.ids[0], 'USAHA', 'input.xlsx', 2, retry_errors=True))
            self.assertFalse(second.claim(self.ids[0], 'USAHA', 'input.xlsx', 2, retry_errors=True))
            self.assertFalse(second.claim(self.ids[1], 'USAHA', 'input.xlsx', 2, retry_errors=True))
            self.assertFalse(second.claim(self.ids[2], 'USAHA', 'input.xlsx', 2, retry_errors=True))
            first.finish(self.ids[0], 'berhasil', 'sukses ulang')
            first.export(path)
            self.assertTrue(pd.read_excel(path / 'rekap_error_gui.xlsx').empty)
            self.assertTrue(pd.read_csv(path / 'error_gui.csv').empty)
            self.assertIn(self.ids[0], pd.read_csv(path / 'selesai_gui.csv')['assignment_id'].tolist())


if __name__ == '__main__':
    unittest.main()
