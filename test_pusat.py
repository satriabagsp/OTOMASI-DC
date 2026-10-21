"""Tes koneksi pusat memakai respons tiruan; tidak menghubungi server kantor."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from pusat import CentralAPI, CentralConfig, load_config, save_config


class CentralTests(unittest.TestCase):
    def config(self):
        return CentralConfig(
            base_url='http://example.test/api/v1/gateway', token='token-uji',
            database='OTOMASI_DC', table='hasil_otomasi_dc', bot_id='PC-UJI')

    def response(self, data):
        response = MagicMock()
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

    def test_completed_ids_memakai_filter_dan_merapikan_id(self):
        post = MagicMock(return_value=self.response({
            'results': [{'assignment_id': ' ABC '}, {'assignment_id': 'def'}, {'lain': 'x'}]
        }))
        api = CentralAPI(self.config(), post=post)
        self.assertEqual(api.completed_ids('g', '3201'), {'abc', 'def'})
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['database'], 'OTOMASI_DC')
        self.assertIn("status = 'berhasil'", payload['sql'])
        self.assertIn("kategori = 'G'", payload['sql'])
        self.assertIn("wilayah = '3201'", payload['sql'])

    def test_record_append_tidak_mengirim_path_id_dan_waktu(self):
        post = MagicMock(return_value=self.response({'message': 'ok'}))
        api = CentralAPI(self.config(), post=post)
        api.record(
            assignment_id='ABC', kategori='g', wilayah='3201',
            nama_file=r'C:\Data\G.xlsx', nama_sheet='Sheet1', status='error',
            tahap='isi_rincian', kode_rincian='gaji', pesan='Galat uji',
        )
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['if_exists'], 'append')
        record = payload['records'][0]
        self.assertEqual(record['assignment_id'], 'abc')
        self.assertEqual(record['nama_file'], 'G.xlsx')
        self.assertNotIn('id', record)
        self.assertNotIn('waktu', record)

    def test_source_rows_membaca_batch_siap_input(self):
        post = MagicMock(return_value=self.response({'results': [{'id': 7, 'kategori': 'G'}]}))
        api = CentralAPI(self.config(), post=post)
        self.assertEqual(api.source_rows('g', '3201', 25), [{'id': 7, 'kategori': 'G'}])
        sql = post.call_args.kwargs['json']['sql']
        self.assertIn("`Siap Input`=1", sql)
        self.assertIn("COALESCE(`Sudah Diinput`,0)=0", sql)
        self.assertIn("ORDER BY id ASC LIMIT 25", sql)

    def test_claim_source_diverifikasi_dengan_bot_id(self):
        responses = [
            self.response({'message': 'ok'}),
            self.response({'results': [{'automation_status': 'BERJALAN', 'automation_bot_id': 'PC-UJI'}]}),
        ]
        post = MagicMock(side_effect=responses)
        api = CentralAPI(self.config(), post=post)
        self.assertTrue(api.claim_source(17))
        self.assertTrue(post.call_args_list[0].args[0].endswith('/update'))
        self.assertIn('WHERE id=17', post.call_args_list[0].kwargs['json']['sql'])

    def test_complete_source_berhasil_menandai_sudah_diinput(self):
        responses = [
            self.response({'message': 'ok'}),
            self.response({'results': [{'automation_status': 'BERHASIL', 'sudah': 1}]}),
        ]
        post = MagicMock(side_effect=responses)
        api = CentralAPI(self.config(), post=post)
        api.complete_source(17, 'BERHASIL', 'selesai', 'Selesai')
        sql = post.call_args_list[0].kwargs['json']['sql']
        self.assertIn("`Sudah Diinput`=1", sql)
        self.assertIn("automation_bot_id='PC-UJI'", sql)

    def test_config_lokal_disimpan_dan_bisa_dibaca(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            save_config(path, self.config())
            loaded = load_config(path)
            self.assertEqual(loaded, self.config())
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['token'], 'token-uji')

    def test_tanpa_token_berarti_database_pusat_nonaktif(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(load_config(Path(folder) / 'tidak-ada.json'))


if __name__ == '__main__':
    unittest.main()
