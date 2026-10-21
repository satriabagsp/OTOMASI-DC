"""Alur FASIH dengan Playwright sinkron; dipanggil dari thread pekerja GUI."""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from core import preview_actions
from katalog_rincian import KATALOG, L

TIMEOUT = 30000


class NeedsSourceData(RuntimeError):
    """FASIH requires facts absent from the selected source row."""


def one(locator, label):
    n = locator.count()
    if n != 1:
        raise RuntimeError(f'{label} ditemukan {n} kali, harus tepat satu.')
    return locator


def input_value(page, code):
    box = field(page, code)
    value = one(box.locator('input:visible:not([type="radio"]):not([type="checkbox"]), textarea:visible'), f'Input {code}')
    return value.input_value().strip()


def field(page, code):
    exact, prefix = json.dumps(code), json.dumps(code + '#')
    result = page.locator(f':is([id={exact}], [id^={prefix}]):visible')
    result.first.wait_for(state='visible', timeout=TIMEOUT)
    return one(result, f'Rincian {code}')


def open_block(page, name):
    sidebar = page.locator('div.fasih-form-sidebar > div[title]')
    l = page.locator('div.fasih-form-sidebar > div[title="SE2026 - L BLOK II"]:visible')
    ub = page.locator('div.fasih-form-sidebar > div[title="BLOK I"]:visible')
    mandiri = page.locator('div.fasih-form-sidebar > div[title="BLOK II"]:visible')
    page.locator('div.fasih-form-sidebar > div[title="SE2026 - L BLOK II"]:visible, div.fasih-form-sidebar > div[title="BLOK I"]:visible, div.fasih-form-sidebar > div[title="BLOK II"]:visible').first.wait_for(timeout=TIMEOUT)
    if l.count() == 1 and ub.count() == 0:
        l.click()
        # Pastikan nama muncul; gunakan title asli agar spasi akhir tetap cocok.
        page.wait_for_function('name => [...document.querySelectorAll("div.fasih-form-sidebar > div[title]")].some(e => e.title.trim() === name)', arg=name.strip(), timeout=TIMEOUT)
        titles = sidebar.evaluate_all('(els) => els.map(e => e.title)')
        matches = [t for t in titles if t.strip() == name.strip()]
        if len(matches) != 1:
            raise RuntimeError(f'Nama usaha {name!r} ditemukan {len(matches)} kali.')
        one(page.locator(f'div.fasih-form-sidebar > div[title={json.dumps(matches[0], ensure_ascii=False)}]'), 'Nama usaha').click()
        return 'L'
    if ub.count() == 1 and l.count() == 0:
        ub.click()
        current = input_value(page, 'nama_usaha')
        if current != name.strip():
            raise RuntimeError(f'Nama usaha berbeda: sumber={name!r}, FASIH={current!r}')
        return 'UB'
    if mandiri.count() == 1 and l.count() == 0 and ub.count() == 0:
        mandiri.click()
        page.wait_for_function('name => [...document.querySelectorAll("div.fasih-form-sidebar > div[title]")].some(e => e.title.trim() === name)', arg=name.strip(), timeout=TIMEOUT)
        matches = [title for title in sidebar.evaluate_all('(els) => els.map(e => e.title)') if title.strip() == name.strip()]
        if len(matches) != 1:
            raise RuntimeError(f'Nama usaha {name!r} ditemukan {len(matches)} kali pada kuesioner Mandiri.')
        one(page.locator(f'div.fasih-form-sidebar > div[title={json.dumps(matches[0], ensure_ascii=False)}]'), 'Nama usaha Mandiri').click()
        return 'MANDIRI'
    raise RuntimeError(f'Jenis kuesioner tidak pasti: L={l.count()}, UB={ub.count()}.')


def open_target_block(page, name, kind, block):
    if block == L:
        open_block(page, name)
    else:
        if kind != 'L':
            raise RuntimeError(f'Blok {block} belum didukung pada kuesioner UB.')
        locator = page.locator(f'div.fasih-form-sidebar > div[title={json.dumps(block, ensure_ascii=False)}]:visible')
        one(locator, f'Blok {block}').click()


def close_note_dialog(page, dialog):
    """Tutup dialog catatan tanpa gagal bila FASIH menutupnya sendiri.

    Setelah Simpan atau ketika catatan lama dibuka, FASIH kadang merender ulang
    halaman. Tombol Dismiss dapat lepas dari DOM di tengah klik; itu sudah
    merupakan tanda dialog sedang ditutup, bukan kegagalan pengisian.
    """
    page.wait_for_timeout(350)
    if dialog.count() == 0 or not dialog.is_visible():
        page.wait_for_timeout(250)
        return
    close = dialog.get_by_role('button', name='Dismiss', exact=True)
    one(close, 'Tutup catatan')
    try:
        close.click(timeout=5000)
    except PlaywrightError:
        # React/FASIH dapat membuang dialog ketika halaman sedang memuat ulang.
        # Lanjut hanya bila dialog benar-benar sudah hilang.
        try:
            dialog.wait_for(state='hidden', timeout=5000)
        except PlaywrightError as exc:
            raise RuntimeError('Dialog catatan masih terbuka setelah halaman stabil.') from exc
    else:
        try:
            dialog.wait_for(state='hidden', timeout=5000)
        except PlaywrightError:
            if dialog.count() and dialog.is_visible():
                raise RuntimeError('Dialog catatan tidak tertutup setelah tombol Dismiss dipilih.')
    # Beri FASIH kesempatan menyelesaikan render sebelum catatan berikutnya dibuka.
    page.wait_for_timeout(250)


def add_note(page, code, remark):
    box = field(page, code)
    one(box.locator('button[title="Catatan"]:visible'), f'Tombol Catatan {code}').click()
    dialog = page.locator('[id^="dialog-"][id$="-content"]:visible')
    dialog.wait_for(timeout=TIMEOUT)
    one(dialog, 'Dialog catatan')
    text = dialog.inner_text()
    pattern = r'(?<![\w])' + re.escape(remark) + r'(?![\w])'
    if re.search(pattern, text):
        close_note_dialog(page, dialog)
        return 'sudah_ada'
    editor = one(dialog.locator('textarea:visible'), f'Editor catatan {code}')
    if editor.input_value().strip():
        raise RuntimeError(f'Editor catatan {code} berisi teks; tidak ditimpa otomatis.')
    editor.fill(remark)
    one(dialog.get_by_role('button', name='Simpan', exact=True), f'Simpan catatan {code}').click()
    # Catatan mungkin tetap terbuka setelah disimpan.
    close_note_dialog(page, dialog)
    return 'berhasil'


def kirim(page, log, nama_usaha=''):
    fixed = set()
    while True:
        one(page.get_by_role('button', name='Kirim', exact=True), 'Kirim utama').click()
        summary = page.locator('[id^="dialog-"][id$="-content"]:visible').filter(has_text=re.compile(r'GALAT|PERINGATAN|CATATAN|KOSONG|Masih Ada yang Belum Dijawab', re.I))
        summary.wait_for(timeout=TIMEOUT)
        if 'Masih Ada yang Belum Dijawab' in summary.inner_text():
            count = re.search(r'(\d+) pertanyaan wajib belum dijawab', summary.inner_text(), re.I)
            summary.get_by_role('button', name='Tinjau Jawaban', exact=True).click()
            missing = page.get_by_text('Wajib diisi', exact=True)
            details = missing.evaluate_all('els => els.map(e => e.closest("[id]")?.innerText?.slice(0, 160) || e.parentElement?.innerText?.slice(0, 160) || "")')
            review = page.get_by_role('dialog', name='Tinjau Jawaban')
            if review.count() == 1:
                detail_text = ' | '.join(review.inner_text().splitlines()[2:])[:600]
            else:
                detail_text = ' | '.join(dict.fromkeys(s.replace('\n', ' ') for s in details if 'Wajib diisi' in s))[:600]
            raise NeedsSourceData(f'{count.group(1) if count else "Beberapa"} pertanyaan wajib belum dijawab. {detail_text}'.strip())
        card = one(summary.get_by_role('button', name=re.compile(r'^GALAT\b', re.I)), 'Kartu GALAT')
        match = re.search(r'GALAT\s*(\d+)', card.inner_text(), re.I)
        if not match:
            raise RuntimeError('Jumlah GALAT tidak dapat dibaca.')
        if int(match.group(1)) == 0:
            break
        card.click()
        dialog = page.get_by_role('dialog', name='Galat')
        dialog.wait_for(timeout=TIMEOUT)
        detail = dialog.inner_text()
        target = dialog.locator('[title="Tampilkan Anomali Usaha dan Keluarga"]')
        if int(match.group(1)) != 1:
            raise RuntimeError('GALAT validasi: ' + ' | '.join(detail.splitlines()))
        if target.count() == 1 and 'Wajib diisi' in detail and 'anomali' not in fixed:
            one(dialog.get_by_role('button', name='Lihat', exact=True), 'Lihat GALAT').click()
            box = page.locator('#cek_anomali_button')
            box.wait_for(timeout=TIMEOUT)
            switch = one(box.locator('input[role="switch"]'), 'Sakelar anomali')
            if switch.get_attribute('aria-checked') != 'false':
                raise RuntimeError('Status sakelar tidak sesuai; periksa manual.')
            one(box.locator('input[role="switch"] + div'), 'Kendali anomali').click()
            page.locator('#cek_anomali_button input[role="switch"][aria-checked="true"]').wait_for(state='attached', timeout=10000)
            fixed.add('anomali')
            log('Sakelar anomali diaktifkan; periksa ulang GALAT.')
            continue
        if ('Status badan usaha adalah CV maka nama usaha harus diakhiri dengan ,CV' in detail
                and 'Perubahan Nama usaha/perusahaan' in detail and 'nama_cv' not in fixed and nama_usaha):
            one(dialog.get_by_role('button', name='Lihat', exact=True), 'Lihat GALAT').click()
            box = field(page, 'nama_usaha_edit')
            editor = one(box.locator('input:visible, textarea:visible'), 'Perubahan nama usaha')
            current = editor.input_value().strip()
            if current and current.casefold() != nama_usaha.strip().casefold():
                raise RuntimeError(f'Nama pada rincian perbaikan berbeda dari sumber: {current!r}.')
            corrected = nama_usaha.rstrip(' ,') + ',CV'
            editor.fill(corrected)
            if editor.input_value().strip() != corrected:
                raise RuntimeError('Perbaikan akhiran CV tidak tersimpan di isian.')
            fixed.add('nama_cv')
            log(f'Nama usaha diperbaiki sesuai GALAT CV: {corrected}.')
            continue
        raise RuntimeError('GALAT validasi: ' + ' | '.join(detail.splitlines()))
    one(summary.get_by_role('button', name='Kirim', exact=True), 'Kirim ringkasan').click()
    dialog = page.locator('[id^="dialog-"][id$="-content"]:visible').filter(has_text=re.compile(r'Konfirmasi Kirim', re.I))
    dialog.wait_for(timeout=TIMEOUT)
    one(dialog.get_by_role('button', name='Konfirmasi', exact=True), 'Konfirmasi Kirim').click()
    success = page.get_by_role('alertdialog', name='Assignment Berhasil Disubmit')
    success.wait_for(timeout=TIMEOUT)
    one(success.get_by_role('button', name='Kembali ke Review', exact=True), 'Kembali ke Review').click()
    page.wait_for_url(re.compile(r'/assignment/[^/?#]+/[^/?#]+/?(?:\?.*)?$'), timeout=TIMEOUT)


def approve_assignment(page):
    """Approve dari halaman review dan pastikan tombol Revoke muncul kembali."""
    approve = page.locator('button:has(svg.tabler-icon-check):visible')
    revoke = page.locator('button:has(svg.tabler-icon-rotate-clockwise):visible')
    page.locator('button:has(svg.tabler-icon-check):visible, button:has(svg.tabler-icon-rotate-clockwise):visible').first.wait_for(timeout=TIMEOUT)
    if approve.count() == 1 and revoke.count() == 0:
        approve.click()
        dialog = page.locator('[role="alertdialog"], [role="dialog"]').filter(has_text=re.compile(r'Approve Assignment', re.I))
        dialog.wait_for(timeout=TIMEOUT)
        one(dialog.get_by_role('button', name='Konfirmasi', exact=True), 'Konfirmasi approve').click()
        dialog.wait_for(state='hidden', timeout=TIMEOUT)
    elif not (approve.count() == 0 and revoke.count() == 1):
        raise RuntimeError('Status approve tidak dapat dipastikan.')
    revoke.first.wait_for(timeout=TIMEOUT)
    one(revoke, 'Revoke setelah approve')


class Fasih:
    def __init__(self, profile: Path):
        self.profile = profile
        self.playwright = None
        self.context = None
        self.page = None
        self.work_page = None
        self.last_stage = ''
        self.last_code = None
        self.may_have_changed = False

    def open(self):
        if self.context:
            return
        self.playwright = sync_playwright().start()
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                str(self.profile), headless=False,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/143.0.0.0 Safari/537.36',
                args=['--disable-blink-features=AutomationControlled'],
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.goto('https://fasih-sm.bps.go.id/', wait_until='domcontentloaded', timeout=TIMEOUT)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        self.context = self.playwright = self.page = None
        self.work_page = None

    def process(self, row, mappings, log, round_values=False):
        self.last_stage = 'buka_assignment'
        self.last_code = None
        self.may_have_changed = False
        if not self.page:
            raise RuntimeError('Buka browser dan login manual terlebih dahulu.')
        target_url = str(row['link_fasih_sm']).strip()
        if self.context and (not self.work_page or self.work_page.is_closed()):
            self.work_page = self.context.new_page()
        page = self.work_page if self.context else self.page
        for attempt in range(3):
            try:
                page.goto(target_url, wait_until='domcontentloaded', timeout=TIMEOUT)
                action = page.locator('button:has(svg.tabler-icon-rotate-clockwise):visible, button:has(svg.tabler-icon-edit):visible')
                action.first.wait_for(timeout=TIMEOUT)
                if page.url.split('?', 1)[0].rstrip('/') != target_url.rstrip('/'):
                    raise RuntimeError(f'Halaman berubah dari assignment tujuan: {page.url}')
                break
            except PlaywrightError as exc:
                try:
                    login_visible = 'sso.bps.go.id' in page.url or page.get_by_text('Lanjutkan dengan SSO Eksternal').count() > 0
                except PlaywrightError:
                    login_visible = False
                if login_visible:
                    raise RuntimeError('Sesi login FASIH belum siap. Selesaikan login di browser GUI lalu ulangi.') from exc
                if attempt == 2 or not self.context:
                    raise
                log('Navigasi assignment terpotong; membuka ulang tab kerja sebelum ada perubahan.')
                page.close()
                self.work_page = self.context.new_page()
                page = self.work_page
        # Cek nama dan tahun pada halaman review sebelum melakukan revoke.
        self.last_stage = 'validasi_assignment'
        kind = open_block(page, str(row['nama_usaha']).strip())
        year = input_value(page, 'tahun_operasi')
        if not year.isdigit() or int(year) >= 2026:
            raise RuntimeError(f'Tahun operasi {year!r} tidak didukung; isian bulanan perlu penanganan manual.')
        log(f'Nama cocok, kuesioner {kind}, tahun operasi {year}.')
        # Validasi semua perintah sebelum status atau isian diubah.
        actions = preview_actions(row, mappings, round_values)
        if kind in ('UB', 'MANDIRI') and any(m.blok != L for m, _, _, _ in actions):
            raise RuntimeError(f'Blok selain usaha belum didukung pada kuesioner {kind}.')
        if str(row.get('KBLI (menjadi)', '')).strip():
            raise RuntimeError('Perubahan KBLI belum didukung; perlu penanganan manual.')
        note_only = bool(actions) and all(
            not change and remark.upper() in {'#0', '#DC_00'}
            for _, remark, _, change in actions
        )
        if note_only:
            # Tombol catatan tersedia dari halaman review; periksa semuanya sebelum revoke.
            for m, _, _, _ in actions:
                self.last_stage = 'validasi_rincian'
                self.last_code = m.kode
                open_target_block(page, str(row['nama_usaha']).strip(), kind, m.blok)
                box = field(page, m.kode)
                one(box.locator('button[title="Catatan"]:visible'), f'Catatan {m.kode}')
        revoke = page.locator('button:has(svg.tabler-icon-rotate-clockwise):visible')
        edit = page.locator('button:has(svg.tabler-icon-edit):visible')
        review_note_flow = note_only and revoke.count() == 1
        if revoke.count() == 1:
            self.last_stage = 'revoke'
            revoke.click()
            dialog = page.locator('[role="alertdialog"], [role="dialog"]').filter(has_text=re.compile(r'Revoke Assignment', re.I))
            dialog.wait_for(timeout=TIMEOUT)
            one(dialog.get_by_role('button', name='Konfirmasi', exact=True), 'Konfirmasi revoke').click()
            dialog.wait_for(state='hidden', timeout=TIMEOUT)
            self.may_have_changed = True
            log('Assignment di-revoke; jika proses gagal, status perlu diperiksa manual.')
        elif revoke.count() != 0 or edit.count() != 1:
            raise RuntimeError('Status review tidak dapat dipastikan.')
        if review_note_flow:
            self.last_stage = 'isi_rincian_review'
            for m, remark, _, _ in actions:
                self.last_code = m.kode
                open_target_block(page, str(row['nama_usaha']).strip(), kind, m.blok)
                self.may_have_changed = True
                status = add_note(page, m.kode, remark)
                log(f'{m.label}: catatan {status} dari halaman review.')
            self.last_stage = 'approve'
            self.last_code = None
            approve_assignment(page)
            self.last_stage = 'selesai'
            log('Mode remark saja: Edit dan Kirim dilewati; approve terverifikasi.')
            return
        self.last_stage = 'buka_edit'
        edit.first.wait_for(timeout=TIMEOUT)
        one(edit, 'Edit assignment').click()
        page.wait_for_url(re.compile(r'/edit(?:\?.*)?$'), timeout=TIMEOUT)
        open_block(page, str(row['nama_usaha']).strip())
        if input_value(page, 'tahun_operasi') != year:
            raise RuntimeError('Tahun operasi berubah saat membuka edit.')
        # Periksa semua target sebelum menulis apapun ke rincian.
        for m, remark, value, change in actions:
            self.last_stage = 'validasi_rincian'
            self.last_code = m.kode
            open_target_block(page, str(row['nama_usaha']).strip(), kind, m.blok)
            box = field(page, m.kode)
            if remark:
                one(box.locator('button[title="Catatan"]:visible'), f'Catatan {m.kode}')
            if change:
                target_input = one(box.locator('input:visible:not([type="radio"]):not([type="checkbox"]), textarea:visible'), f'Input {m.kode}')
                if not target_input.is_editable():
                    raise RuntimeError(f'Input {m.kode} tidak dapat diedit pada assignment ini.')
        for m, remark, value, change in actions:
            self.last_stage = 'isi_rincian'
            self.last_code = m.kode
            open_target_block(page, str(row['nama_usaha']).strip(), kind, m.blok)
            if change:
                box = field(page, m.kode)
                number_input = one(box.locator('input:visible:not([type="radio"]):not([type="checkbox"]), textarea:visible'), f'Input {m.kode}')
                self.may_have_changed = True
                number_input.fill(value)
                displayed = number_input.input_value().strip()
                # FASIH dapat menampilkan pemisah ribuan, tetapi nilainya harus tetap sama.
                jenis = KATALOG[(m.blok, m.kode)][1]
                normalized = re.sub(r'[.,\s]', '', displayed)
                matches = displayed == value if jenis == 'teks' else normalized.isascii() and normalized.isdigit() and int(normalized) == int(value)
                if not matches:
                    raise RuntimeError(f'Nilai {m.kode} setelah diisi tidak cocok; periksa manual.')
                log(f'{m.label}: nilai diubah.')
            if remark:
                self.may_have_changed = True
                status = add_note(page, m.kode, remark)
                log(f'{m.label}: catatan {status}.')
        self.last_stage = 'kirim'
        self.last_code = None
        kirim(page, log, str(row['nama_usaha']).strip())
        self.may_have_changed = True
        if page.url.split('?', 1)[0].rstrip('/') != target_url.rstrip('/'):
            raise RuntimeError(f'Setelah Kirim, halaman review tidak sesuai assignment tujuan: {page.url}')
        self.last_stage = 'approve'
        approve_assignment(page)
        self.last_stage = 'selesai'
        self.last_code = None
        log('Approve terverifikasi.')
