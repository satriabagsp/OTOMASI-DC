"""Tes antrean GUI tanpa membuka FASIH atau mengubah data pengguna."""
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import App, RINCIAN_PILIHAN, compatible_column, preview_fetch_limit
from core import Journal, TARGETS
from katalog_rincian import L
import pandas as pd


class ColumnCompatibilityTests(unittest.TestCase):
    def test_pratinjau_database_tidak_mengambil_200_baris_saat_batas_satu(self):
        self.assertEqual(preview_fetch_limit(1), 5)
        self.assertEqual(preview_fetch_limit(10), 30)
        self.assertEqual(preview_fetch_limit(2000), 5000)
        with self.assertRaisesRegex(ValueError, 'antara 1 dan 5000'):
            preview_fetch_limit(0)

    def test_typo_lama_dipetakan_ke_nama_kolom_database(self):
        columns = ['metrik_biaya_produksin (menjadi)']
        self.assertEqual(
            compatible_column('metrik_biaya_produksin (mejadi)', columns),
            'metrik_biaya_produksin (menjadi)',
        )

    def test_nama_database_dipetakan_kembali_ke_file_lama(self):
        columns = ['metrik_biaya_produksin (mejadi)']
        self.assertEqual(
            compatible_column('metrik_biaya_produksin (menjadi)', columns),
            'metrik_biaya_produksin (mejadi)',
        )


class WorkerTests(unittest.TestCase):
    def test_mode_database_mengunci_dan_menandai_baris_berhasil(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            journal = Journal(output / 'status.sqlite3')
            central = MagicMock()
            central.claim_source.return_value = True
            worker = SimpleNamespace(commands=queue.Queue(), messages=queue.Queue(),
                                     stop_event=threading.Event(), journal=journal, central=central)
            rows = [dict(assignment_id='satu', nama_usaha='Usaha', _baris_sumber=44, _source_id=123)]
            worker.commands.put(('browser', None))
            worker.commands.put(('run', (rows, [], 'DB:data_split_usaha_20261016', 'DATABASE',
                                          'G', '3201', False, False, False, 'database')))
            worker.commands.put(('close', None))
            browser = MagicMock()
            with patch('app.OUTPUT', output), patch('fasih.Fasih', return_value=browser):
                App.worker(worker)
            central.claim_source.assert_called_once_with(123, retry_errors=False)
            central.complete_source.assert_called_once_with(
                123, 'BERHASIL', 'selesai', 'Submit dan approve terverifikasi.')
            self.assertEqual(journal.statuses(), {'satu': 'berhasil'})

    def test_hasil_iterasi_dikirim_ke_database_pusat(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            journal = Journal(output / 'status.sqlite3')
            central = MagicMock()
            worker = SimpleNamespace(commands=queue.Queue(), messages=queue.Queue(),
                                     stop_event=threading.Event(), journal=journal, central=central)
            rows = [dict(assignment_id='satu', nama_usaha='Usaha', _baris_sumber=2)]
            worker.commands.put(('browser', None))
            worker.commands.put(('run', (rows, [], r'C:\Data\G.xlsx', 'Sheet1',
                                          'G', '3201', False, False, False)))
            worker.commands.put(('close', None))
            browser = MagicMock()
            with patch('app.OUTPUT', output), patch('app.old_ids', return_value=set()), \
                 patch('fasih.Fasih', return_value=browser):
                App.worker(worker)
            central.record.assert_called_once()
            sent = central.record.call_args.kwargs
            self.assertEqual((sent['status'], sent['tahap']), ('berhasil', 'selesai'))
            self.assertEqual((sent['nama_file'], sent['nama_sheet']), (r'C:\Data\G.xlsx', 'Sheet1'))

    def test_gagal_setelah_perubahan_ditandai_perlu_diperiksa(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            journal = Journal(output / 'status.sqlite3')
            central = MagicMock()
            worker = SimpleNamespace(commands=queue.Queue(), messages=queue.Queue(),
                                     stop_event=threading.Event(), journal=journal, central=central)
            rows = [dict(assignment_id='satu', nama_usaha='Usaha', _baris_sumber=2)]
            worker.commands.put(('browser', None))
            worker.commands.put(('run', (rows, [], 'G.xlsx', 'Sheet1',
                                          'G', '3201', False, False, False)))
            worker.commands.put(('close', None))
            browser = MagicMock()
            browser.process.side_effect = RuntimeError('Timeout approve')
            browser.may_have_changed = True
            browser.last_stage = 'approve'
            browser.last_code = None
            with patch('app.OUTPUT', output), patch('app.old_ids', return_value=set()), \
                 patch('fasih.Fasih', return_value=browser):
                App.worker(worker)
            self.assertEqual(journal.statuses(), {'satu': 'perlu_diperiksa'})
            sent = central.record.call_args.kwargs
            self.assertEqual((sent['status'], sent['tahap']), ('perlu_diperiksa', 'approve'))
            self.assertEqual(pd.read_csv(output / 'perlu_diperiksa_gui.csv')['assignment_id'].tolist(), ['satu'])

    def test_missing_required_data_is_reported_separately(self):
        from fasih import NeedsSourceData
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            journal = Journal(output / 'status.sqlite3')
            worker = SimpleNamespace(commands=queue.Queue(), messages=queue.Queue(),
                                     stop_event=threading.Event(), journal=journal)
            rows = [dict(assignment_id='satu', nama_usaha='Usaha', _baris_sumber=2)]
            worker.commands.put(('browser', None))
            worker.commands.put(('run', (rows, [], 'contoh.xlsx', 'Sheet1', 'G', '3201', False, False, False)))
            worker.commands.put(('close', None))
            browser = MagicMock()
            browser.process.side_effect = NeedsSourceData('Kecamatan wajib diisi')
            with patch('app.OUTPUT', output), patch('app.old_ids', return_value=set()), patch('fasih.Fasih', return_value=browser):
                App.worker(worker)
            self.assertEqual(journal.statuses(), {'satu': 'perlu_data'})
            self.assertTrue(pd.read_csv(output / 'error_gui.csv').empty)
            self.assertEqual(pd.read_csv(output / 'perlu_data_gui.csv')['assignment_id'].tolist(), ['satu'])

    def test_ulangi_error_sukses_dan_gagal_diekspor_sesuai_hasil(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            journal = Journal(output / 'status.sqlite3')
            rows = [dict(assignment_id='pertama', nama_usaha='Satu', _baris_sumber=2),
                    dict(assignment_id='kedua', nama_usaha='Dua', _baris_sumber=3)]
            for row in rows:
                journal.claim(row['assignment_id'], row['nama_usaha'], 'contoh.xlsx', row['_baris_sumber'])
                journal.finish(row['assignment_id'], 'error', 'error lama')
            worker = SimpleNamespace(commands=queue.Queue(), messages=queue.Queue(),
                                     stop_event=threading.Event(), journal=journal)
            worker.commands.put(('browser', None))
            worker.commands.put(('run', (rows, [], 'contoh.xlsx', 'Sheet1', 'G', '3201', False, False, True)))
            worker.commands.put(('close', None))
            browser = MagicMock()
            browser.process.side_effect = [None, RuntimeError('error baru')]
            with patch('app.OUTPUT', output), patch('app.old_ids', return_value=set()), patch('fasih.Fasih', return_value=browser):
                App.worker(worker)
            self.assertEqual(journal.statuses(), {'pertama': 'berhasil', 'kedua': 'error'})
            errors = pd.read_excel(output / 'rekap_error_gui.xlsx')
            self.assertEqual(errors['assignment_id'].tolist(), ['kedua'])
            self.assertEqual(errors['pesan'].tolist(), ['error baru'])

    def test_error_dicatat_dan_iterasi_berikutnya_dijalankan(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            journal = Journal(output / 'status.sqlite3')
            worker = SimpleNamespace(commands=queue.Queue(), messages=queue.Queue(),
                                     stop_event=threading.Event(), journal=journal)
            rows = [dict(assignment_id='pertama', nama_usaha='Usaha pertama', _baris_sumber=2),
                    dict(assignment_id='kedua', nama_usaha='Usaha kedua', _baris_sumber=3)]
            worker.commands.put(('browser', None))
            worker.commands.put(('run', (rows, [], 'contoh.xlsx', 'Sheet1', 'G', '3201', True, False, False)))
            worker.commands.put(('close', None))
            browser = MagicMock()
            browser.process.side_effect = [RuntimeError('Galat uji'), None]
            with patch('app.OUTPUT', output), patch('app.old_ids', return_value=set()), patch('fasih.Fasih', return_value=browser):
                App.worker(worker)
            self.assertEqual(browser.process.call_count, 2)
            self.assertEqual(journal.statuses(), {'pertama': 'error', 'kedua': 'berhasil'})
            self.assertTrue((output / 'rekap_error_gui.xlsx').exists())
            messages = [worker.messages.get_nowait() for _ in range(worker.messages.qsize())]
            logs = '\n'.join(text for _, text in messages)
            self.assertIn('[1/2] Usaha pertama', logs)
            self.assertIn('[2/2] Usaha kedua', logs)
            self.assertIn('berhasil 1, perlu data 0, error 1, dilewati 0', logs)
            self.assertIn('Lanjut ke baris berikutnya', logs)

    def test_gagal_mencatat_error_menghentikan_antrean(self):
        worker = SimpleNamespace(commands=queue.Queue(), messages=queue.Queue(),
                                 stop_event=threading.Event(), journal=MagicMock())
        worker.journal.claim.return_value = True
        worker.journal.finish.side_effect = OSError('Database tidak dapat ditulis')
        rows = [dict(assignment_id='pertama', nama_usaha='Usaha pertama', _baris_sumber=2),
                dict(assignment_id='kedua', nama_usaha='Usaha kedua', _baris_sumber=3)]
        worker.commands.put(('browser', None))
        worker.commands.put(('run', (rows, [], 'contoh.xlsx', 'Sheet1', 'G', '3201', True, False, False)))
        worker.commands.put(('close', None))
        browser = MagicMock()
        browser.process.side_effect = RuntimeError('Galat uji')
        with patch('app.old_ids', return_value=set()), patch('fasih.Fasih', return_value=browser):
            App.worker(worker)
        self.assertEqual(browser.process.call_count, 1)
        messages = [worker.messages.get_nowait() for _ in range(worker.messages.qsize())]
        self.assertTrue(any(kind == 'error' and 'Database tidak dapat ditulis' in text for kind, text in messages))

    def test_gui_default_and_saved_mapping_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pilihan.json'
            cols = {col: ['#DC_00' if col.endswith('(Remark)') else ''] for _, _, value, remark in TARGETS for col in (value, remark)}
            cols.update({'nama_baru':['TOKO BARU'], '_baris_sumber':[2]})
            source = pd.DataFrame(cols)
            with patch('app.DAFTAR_FILE', path), patch('app.Journal'), patch('app.read_source', return_value=source), \
                 patch('app.simpledialog.askstring', return_value='Daftar uji'), patch('app.messagebox.showerror') as errors:
                first = App()
                try:
                    first.withdraw()
                    first.path.set('contoh.xlsx')
                    first.sheet.set('Sheet1')
                    first.load_sheet()
                    self.assertEqual(len(first.get_mappings()), 7)
                    first.add_mapping()
                    extra = first.mapping_vars[-1]
                    extra['target'].set(RINCIAN_PILIHAN[(L, 'nama_komersial')])
                    extra['pakai'].set(True)
                    extra['nilai'].set('nama_baru')
                    first.save_list()
                    self.assertTrue(path.exists())
                    self.assertFalse(errors.called)
                finally:
                    first.commands.put(('close', None))
                    first.thread.join(timeout=2)
                    first.destroy()
                second = App()
                try:
                    second.withdraw()
                    second.path.set('contoh.xlsx')
                    second.sheet.set('Sheet1')
                    second.load_sheet()
                    selected = second.get_mappings()
                    self.assertEqual(second.daftar_nama.get(), 'Daftar uji')
                    self.assertEqual(len(selected), 8)
                    self.assertEqual((selected[-1].kode, selected[-1].nilai), ('nama_komersial', 'nama_baru'))
                    self.assertFalse(errors.called)
                finally:
                    second.commands.put(('close', None))
                    second.thread.join(timeout=2)
                    second.destroy()


if __name__ == '__main__':
    unittest.main()
