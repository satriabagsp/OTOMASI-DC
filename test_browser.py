"""Tes Playwright pada halaman tiruan; tidak menghubungi FASIH."""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from playwright.sync_api import sync_playwright
from core import Mapping
from katalog_rincian import L, P
from fasih import Fasih, NeedsSourceData, add_note, kirim, ready_field, same_review_assignment

HTML = r'''<!doctype html><html><body>
<button id="send" onclick="summary()">Kirim</button><div id="panel"></div>
<div id="gaji#1"><button title="Catatan" onclick="note()">Catatan</button></div>
<script>
let anomaly=false, other=false, submit=false;
const panel=document.querySelector('#panel');
function summary(){
 panel.innerHTML=`<div role="dialog" aria-label="Kirim" id="dialog-demo-content">
 <button onclick="details()">GALAT ${anomaly?0:1} Perlu diperbaiki</button>
 <button>PERINGATAN 0</button><button>CATATAN 0</button><button>KOSONG 0</button>
 <button onclick="confirmSend()">Kirim</button></div>`;
}
function details(){
 panel.innerHTML=`<div role="dialog" aria-label="Galat" id="dialog-demo-content">Galat
 <div title="${other?'Rincian lain':'Tampilkan Anomali Usaha dan Keluarga'}">${other?'Rincian lain':'Tampilkan Anomali Usaha dan Keluarga'}</div>
 <ul><li>Wajib diisi</li></ul><button onclick="see()">Lihat</button></div>`;
}
function see(){
 panel.innerHTML=`<div id="cek_anomali_button"><input type="checkbox" role="switch" aria-checked="false" hidden>
 <div onclick="turnOn()">Aktifkan</div></div>`;
}
function turnOn(){anomaly=true; document.querySelector('#cek_anomali_button input').setAttribute('aria-checked','true');}
function confirmSend(){panel.innerHTML=`<div role="dialog" id="dialog-demo-content">Konfirmasi Kirim<button onclick="success()">Konfirmasi</button></div>`;}
function success(){submit=true;panel.innerHTML=`<div role="alertdialog" aria-label="Assignment Berhasil Disubmit"><button onclick="review()">Kembali ke Review</button></div>`;}
function review(){panel.innerHTML='';history.pushState({},'', '/app/assignment/a/b');}
function note(){panel.innerHTML=`<div role="dialog" id="dialog-demo-content">#DC_001<textarea></textarea><button onclick="saveNote()">Simpan</button><button aria-label="Dismiss" onclick="panel.innerHTML=''">Close</button></div>`;}
function saveNote(){document.body.dataset.saved=document.querySelector('textarea').value;panel.innerHTML='';}
</script></body></html>'''

PROCESS_HTML = r'''<!doctype html><html><body><div id="toolbar"></div>
<div class="fasih-form-sidebar"><div title="BLOK I">BLOK I</div></div>
<div id="nama_usaha"><input value="USAHA CONTOH"></div>
<div id="tahun_operasi"><input value="2001"></div>
<div id="gaji"><input value="500"><button title="Catatan" onclick="note()">Catatan</button></div>
<div id="panel"></div>
<script>
const toolbar=document.querySelector('#toolbar'), panel=document.querySelector('#panel');
let submitted=false, approved=false;
function review(){toolbar.innerHTML=`<button onclick="edit()"><svg class="tabler-icon-edit"></svg></button>`;}
function edit(){history.pushState({},'', '/app/assignment/a/b/edit');toolbar.innerHTML=`<button onclick="summary()">Kirim</button>`;}
function note(){panel.innerHTML=`<div role="dialog" id="dialog-demo-content"><textarea></textarea><button onclick="saveNote()">Simpan</button><button aria-label="Dismiss" onclick="panel.innerHTML=''">Close</button></div>`;}
function saveNote(){document.body.dataset.note=document.querySelector('textarea').value;panel.innerHTML='';}
function summary(){panel.innerHTML=`<div role="dialog" id="dialog-demo-content"><button>GALAT 0 Perlu diperbaiki</button><button>PERINGATAN 0</button><button>CATATAN 0</button><button>KOSONG 0</button><button onclick="confirmSend()">Kirim</button></div>`;}
function confirmSend(){panel.innerHTML=`<div role="dialog" id="dialog-demo-content">Konfirmasi Kirim<button onclick="success()">Konfirmasi</button></div>`;}
function success(){submitted=true;panel.innerHTML=`<div role="alertdialog" aria-label="Assignment Berhasil Disubmit"><button onclick="back()">Kembali ke Review</button></div>`;}
function back(){history.pushState({},'', '/app/assignment/a/b');panel.innerHTML='';toolbar.innerHTML=`<button onclick="approveDialog()"><svg class="tabler-icon-check"></svg></button>`;}
function approveDialog(){panel.innerHTML=`<div role="dialog">Approve Assignment<button onclick="approve()">Konfirmasi</button></div>`;}
function approve(){approved=true;panel.innerHTML='';toolbar.innerHTML=`<button><svg class="tabler-icon-rotate-clockwise"></svg></button>`;}
review();
</script></body></html>'''

REMARK_REVIEW_HTML = r'''<!doctype html><html><body><div id="toolbar"></div>
<div class="fasih-form-sidebar"><div title="BLOK I">BLOK I</div></div>
<div id="nama_usaha"><input value="USAHA CONTOH"></div>
<div id="tahun_operasi"><input value="2001"></div>
<div id="gaji"><input value="500"><button title="Catatan" onclick="note()">Catatan</button></div>
<div id="panel"></div>
<script>
const toolbar=document.querySelector('#toolbar'), panel=document.querySelector('#panel');
let revoked=false, edited=false, submitted=false, approved=false;
function approvedReview(){toolbar.innerHTML=`<button onclick="revokeDialog()"><svg class="tabler-icon-rotate-clockwise"></svg></button>`;}
function revokeDialog(){panel.innerHTML=`<div role="dialog">Revoke Assignment<button onclick="revoke()">Konfirmasi</button></div>`;}
function revoke(){revoked=true;panel.innerHTML='';toolbar.innerHTML=`<button onclick="edit()"><svg class="tabler-icon-edit"></svg></button><button onclick="approveDialog()"><svg class="tabler-icon-check"></svg></button>`;}
function edit(){edited=true;history.pushState({},'', '/app/assignment/a/b/edit');}
function note(){panel.innerHTML=`<div role="dialog" id="dialog-note-content"><textarea></textarea><button onclick="saveNote()">Simpan</button><button aria-label="Dismiss" onclick="panel.innerHTML=''">Close</button></div>`;}
function saveNote(){document.body.dataset.note=document.querySelector('textarea').value;panel.innerHTML='';}
function approveDialog(){panel.innerHTML=`<div role="dialog">Approve Assignment<button onclick="approve()">Konfirmasi</button></div>`;}
function approve(){approved=true;panel.innerHTML='';approvedReview();}
approvedReview();
</script></body></html>'''


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        cls.browser = cls.p.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=HTML))
        self.page.goto('https://example.test/app/assignment/a/b/edit')

    def tearDown(self):
        self.page.close()

    def test_sakelar_then_submit(self):
        kirim(self.page, lambda _: None)
        self.assertTrue(self.page.evaluate('anomaly'))
        self.assertTrue(self.page.evaluate('submit'))
        self.assertTrue(self.page.url.endswith('/app/assignment/a/b'))

    def test_review_dapat_berganti_kegiatan_tetapi_assignment_tetap_sama(self):
        original = 'https://example.test/app/assignment/kegiatan-lama/assignment-1'
        self.assertTrue(same_review_assignment(
            original, 'https://example.test/app/assignment/kegiatan-baru/assignment-1'))
        self.assertFalse(same_review_assignment(
            original, 'https://example.test/app/assignment/kegiatan-baru/assignment-2'))

    def test_other_galat_not_submitted(self):
        self.page.evaluate('other=true')
        with self.assertRaisesRegex(RuntimeError, 'GALAT validasi'):
            kirim(self.page, lambda _: None)
        self.assertFalse(self.page.evaluate('submit'))
        self.assertFalse(self.page.evaluate('anomaly'))

    def test_required_questions_dialog_is_not_treated_as_zero_galat(self):
        self.page.unroute_all()
        html = '''<!doctype html><html><body><button onclick="show()">Kirim</button><div id="panel"></div>
        <script>function show(){document.querySelector('#panel').innerHTML=`<div role="dialog" id="dialog-required-content">Kirim Masih Ada yang Belum Dijawab 2 pertanyaan wajib belum dijawab<button onclick="review()">Tinjau Jawaban</button></div>`}
        function review(){document.querySelector('#panel').innerHTML=`<div id="kecamatan">3. Kecamatan <span>Wajib diisi</span></div><div id="kelurahan">4. Kelurahan <span>Wajib diisi</span></div>`}</script></body></html>'''
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        self.page.goto('https://example.test/app/assignment/a/b/edit')
        with self.assertRaisesRegex(RuntimeError, 'Kecamatan.*Kelurahan'):
            kirim(self.page, lambda _: None)

    def test_exact_cv_validation_can_be_fixed_and_submitted(self):
        self.page.unroute_all()
        html = '''<!doctype html><html><body><button onclick="show()">Kirim</button><div id="panel"></div>
        <script>let sent=false, valid=false; function show(){valid=document.querySelector('#nama_usaha_edit input')?.value.endsWith(',CV'); document.querySelector('#panel').innerHTML=`<div role="dialog" id="dialog-cv-content">Kirim <button onclick="details()">GALAT ${valid?0:1} Perlu diperbaiki</button><button>PERINGATAN 0</button><button>CATATAN 0</button><button>KOSONG 0</button><button onclick="confirmSend()">Kirim</button></div>`}
        function details(){document.querySelector('#panel').innerHTML=`<div role="dialog" aria-label="Galat" id="dialog-cv-content">Galat Perubahan Nama usaha/perusahaan Status badan usaha adalah CV maka nama usaha harus diakhiri dengan ,CV<button onclick="see()">Lihat</button></div>`}
        function see(){document.querySelector('#panel').innerHTML=`<div id="nama_usaha_edit"><input value="SPBU WARU JAYA"></div>`}
        function confirmSend(){document.querySelector('#panel').innerHTML=`<div role="dialog" id="dialog-cv-content">Konfirmasi Kirim<button onclick="success()">Konfirmasi</button></div>`}
        function success(){sent=true;document.querySelector('#panel').innerHTML=`<div role="alertdialog" aria-label="Assignment Berhasil Disubmit"><button onclick="review()">Kembali ke Review</button></div>`}
        function review(){history.pushState({},'', '/app/assignment/a/b');document.querySelector('#panel').innerHTML=''}</script></body></html>'''
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        self.page.goto('https://example.test/app/assignment/a/b/edit')
        kirim(self.page, lambda _: None, 'SPBU WARU JAYA')
        self.assertTrue(self.page.evaluate('sent && valid'))

    def test_note_is_exact_not_substring(self):
        self.assertEqual(add_note(self.page, 'gaji', '#DC_00'), 'berhasil')
        self.assertEqual(self.page.locator('body').get_attribute('data-saved'), '#DC_00')

    def test_catatan_yang_menutup_sendiri_tidak_dianggap_gagal(self):
        self.page.unroute_all()
        html = r'''<!doctype html><html><body>
        <div id="gaji"><button title="Catatan" onclick="note()">Catatan</button></div>
        <div id="panel"></div><script>
        const panel = document.querySelector('#panel');
        function note() {
          panel.innerHTML = `<div role="dialog" id="dialog-note-content">#0
            <button aria-label="Dismiss">Tutup</button></div>`;
          setTimeout(() => panel.innerHTML = '', 80);
        }
        </script></body></html>'''
        self.page.route('https://example.test/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=html))
        self.page.goto('https://example.test/app/assignment/a/b')
        self.assertEqual(add_note(self.page, 'gaji', '#0'), 'sudah_ada')

    def test_rincian_sudah_tampil_tidak_mengklik_sidebar_lagi(self):
        self.page.unroute_all()
        html = r'''<!doctype html><html><body>
        <div class="fasih-form-sidebar"><div title="SE2026 - L BLOK II"
          onclick="document.querySelector('#biaya_produksi').hidden = true">Blok L</div></div>
        <div id="biaya_produksi"><button title="Catatan">Catatan</button></div>
        </body></html>'''
        self.page.route('https://example.test/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=html))
        self.page.goto('https://example.test/app/assignment/a/b')
        ready_field(self.page, 'USAHA CONTOH', 'L', L, 'biaya_produksi')
        self.assertTrue(self.page.locator('#biaya_produksi').is_visible())

    def test_full_review_edit_submit_approve(self):
        self.page.unroute_all()
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=PROCESS_HTML))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'remark':'#DC_00', 'nilai':''}
        fasih.process(row, [Mapping('Gaji', 'gaji', 'nilai', 'remark')], lambda _: None)
        self.assertTrue(self.page.evaluate('submitted && approved'))
        self.assertEqual(self.page.locator('body').get_attribute('data-note'), '#DC_00')

    def test_dc00_dan_0_ditulis_dari_review_tanpa_edit_atau_kirim(self):
        self.page.unroute_all()
        self.page.route('https://example.test/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=REMARK_REVIEW_HTML))
        for remark in ('#0', '#DC_00'):
            with self.subTest(remark=remark):
                self.page.goto('https://example.test/app/assignment/a/b')
                fasih = Fasih(Path('unused'))
                fasih.page = self.page
                row = {'link_fasih_sm':'https://example.test/app/assignment/a/b',
                       'nama_usaha':'USAHA CONTOH', 'remark':remark, 'nilai':'99999'}
                logs = []
                fasih.process(row, [Mapping('Gaji', 'gaji', 'nilai', 'remark')], logs.append)
                self.assertTrue(self.page.evaluate('revoked && approved'))
                self.assertFalse(self.page.evaluate('edited || submitted'))
                self.assertEqual(self.page.locator('body').get_attribute('data-note'), remark)
                self.assertTrue(any('Edit dan Kirim dilewati' in text for text in logs))

    def test_remark_saja_melanjutkan_assignment_yang_sudah_direvoke(self):
        self.page.unroute_all()
        html = REMARK_REVIEW_HTML.rsplit('approvedReview();', 1)
        html = 'revoke();'.join(html)
        self.page.route('https://example.test/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=html))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm': 'https://example.test/app/assignment/a/b',
               'nama_usaha': 'USAHA CONTOH', 'remark': '#DC_00', 'nilai': ''}
        fasih.process(row, [Mapping('Gaji', 'gaji', 'nilai', 'remark')], lambda _: None)
        self.assertTrue(self.page.evaluate('revoked && approved'))
        self.assertFalse(self.page.evaluate('edited || submitted'))
        self.assertEqual(self.page.locator('body').get_attribute('data-note'), '#DC_00')

    def test_change_value_for_non_dc00(self):
        self.page.unroute_all()
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=PROCESS_HTML))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'remark':'#DC_03', 'nilai':'2500'}
        fasih.process(row, [Mapping('Gaji', 'gaji', 'nilai', 'remark')], lambda _: None)
        self.assertEqual(self.page.locator('#gaji input').input_value(), '2500')
        self.assertEqual(self.page.locator('body').get_attribute('data-note'), '#DC_03')

    def test_rounded_value_is_the_one_sent(self):
        self.page.unroute_all()
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=PROCESS_HTML))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'remark':'#DC_03', 'nilai':'2500.65'}
        fasih.process(row, [Mapping('Gaji', 'gaji', 'nilai', 'remark')], lambda _: None, round_values=True)
        self.assertEqual(self.page.locator('#gaji input').input_value(), '2501')

    def test_dynamic_text_and_note_only(self):
        self.page.unroute_all()
        html = PROCESS_HTML.replace('<div id="gaji">', '<div id="nama_komersial"><input value="LAMA"></div><div id="badan_usaha"><button title="Catatan" onclick="note()">Catatan</button></div><div id="gaji">')
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'nilai':'TOKO BARU 01', 'remark':'#DC_03'}
        mappings = [Mapping('Nama komersial', 'nama_komersial', 'nilai', '', L), Mapping('Badan usaha', 'badan_usaha', '', 'remark', L)]
        fasih.process(row, mappings, lambda _: None)
        self.assertEqual(self.page.locator('#nama_komersial input').input_value(), 'TOKO BARU 01')
        self.assertEqual(self.page.locator('body').get_attribute('data-note'), '#DC_03')
        self.assertTrue(self.page.evaluate('submitted && approved'))

    def test_other_block_in_ub_stops_before_revoke(self):
        self.page.unroute_all()
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=PROCESS_HTML))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'nilai':'JALAN BARU'}
        with self.assertRaisesRegex(RuntimeError, 'belum didukung pada kuesioner UB'):
            fasih.process(row, [Mapping('Jalan', 'jalan_domisili', 'nilai', '', P)], lambda _: None)
        self.assertFalse(self.page.url.endswith('/edit'))

    def test_targets_from_two_blocks(self):
        self.page.unroute_all()
        sidebar = '<div class="fasih-form-sidebar"><div title="SE2026 - L BLOK II">BLOK II</div><div title="USAHA CONTOH">USAHA CONTOH</div><div title="SE2026 - P">SE2026 - P</div></div>'
        html = PROCESS_HTML.replace('<div class="fasih-form-sidebar"><div title="BLOK I">BLOK I</div></div>', sidebar)
        html = html.replace('<div id="gaji">', '<div id="jalan_domisili"><input value="LAMA"></div><div id="gaji">')
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'jalan':'JALAN BARU', 'remark':'#DC_00'}
        mappings = [Mapping('Jalan', 'jalan_domisili', 'jalan', '', P), Mapping('Gaji', 'gaji', '', 'remark', L)]
        fasih.process(row, mappings, lambda _: None)
        self.assertEqual(self.page.locator('#jalan_domisili input').input_value(), 'JALAN BARU')
        self.assertEqual(self.page.locator('body').get_attribute('data-note'), '#DC_00')
        self.assertTrue(self.page.evaluate('submitted && approved'))

    def test_profile_options_match_notebook(self):
        playwright = MagicMock()
        context = playwright.chromium.launch_persistent_context.return_value
        context.pages = [MagicMock()]
        with patch('fasih.sync_playwright') as factory:
            factory.return_value.start.return_value = playwright
            fasih = Fasih(Path('contoh_profil'))
            fasih.open()
            kwargs = playwright.chromium.launch_persistent_context.call_args.kwargs
            self.assertEqual(kwargs['args'], ['--disable-blink-features=AutomationControlled'])
            self.assertIn('Chrome/143.0.0.0', kwargs['user_agent'])
            self.assertFalse(kwargs['headless'])
            self.assertEqual(playwright.chromium.launch_persistent_context.call_args.args[0], str(Path('contoh_profil')))
            fasih.close()

    def test_2026_stops_before_edit(self):
        self.page.unroute_all()
        html = PROCESS_HTML.replace('value="2001"', 'value="2026"')
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'remark':'#DC_00', 'nilai':''}
        with self.assertRaisesRegex(RuntimeError, '2026'):
            fasih.process(row, [Mapping('Gaji', 'gaji', 'nilai', 'remark')], lambda _: None)
        self.assertFalse(self.page.url.endswith('/edit'))
        self.assertFalse(self.page.evaluate('submitted'))

    def test_mandiri_business_block_uses_same_financial_codes(self):
        self.page.unroute_all()
        html = PROCESS_HTML.replace('<div title="BLOK I">BLOK I</div>', '<div title="BLOK II">BLOK II</div><div title="USAHA CONTOH">USAHA CONTOH</div>')
        self.page.route('https://example.test/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        fasih = Fasih(Path('unused'))
        fasih.page = self.page
        row = {'link_fasih_sm':'https://example.test/app/assignment/a/b', 'nama_usaha':'USAHA CONTOH', 'remark':'#DC_00', 'nilai':''}
        fasih.process(row, [Mapping('Gaji', 'gaji', 'nilai', 'remark')], lambda _: None)
        self.assertTrue(self.page.evaluate('submitted && approved'))


if __name__ == '__main__':
    unittest.main()
