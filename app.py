"""GUI lokal untuk memilih sumber dan menjalankan otomasi DC FASIH."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import pandas as pd
from core import Journal, Mapping, TARGETS, check_duplicate_assignments, make_queue, old_ids, preview_actions, read_source, validate_mappings
from daftar_perbaikan import load_lists, save_lists
from katalog_rincian import KATALOG, L, RINCIAN
from pusat import (CentralAPI, CentralConfig, DEFAULT_BASE_URL, DEFAULT_DATABASE,
                   DEFAULT_SOURCE_TABLE, DEFAULT_TABLE, default_bot_id,
                   load_config, save_config)

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'hasil'
PROFILE = ROOT.parent / 'fasih_profile_gui'
DAFTAR_FILE = ROOT / 'daftar_perbaikan.json'
CENTRAL_CONFIG_FILE = ROOT / 'config_pusat.json'
DATABASE_BATCH_TOTAL = 25
PILIHAN_RINCIAN = {f'{label} ({kode})  |  {blok} · {jenis}': (blok, kode) for blok, kode, label, jenis in RINCIAN}
RINCIAN_PILIHAN = {value: label for label, value in PILIHAN_RINCIAN.items()}
COLUMN_ALIASES = {
    'metrik_biaya_produksin (mejadi)': 'metrik_biaya_produksin (menjadi)',
    'metrik_biaya_produksin (menjadi)': 'metrik_biaya_produksin (mejadi)',
}


def compatible_column(name, columns):
    """Cari nama kolom yang sama atau alias typo lama/baru."""
    if name in columns:
        return name
    alias = COLUMN_ALIASES.get(name, '')
    return alias if alias in columns else ''


def _browser_stage(browser):
    value = getattr(browser, 'last_stage', '')
    return value if isinstance(value, str) and value else 'proses_assignment'


def _browser_code(browser):
    value = getattr(browser, 'last_code', None)
    return value if isinstance(value, str) and value else None


def _record_central(owner, row, source, sheet, kategori, wilayah, status, tahap, kode, pesan):
    central = getattr(owner, 'central', None)
    if not central:
        return
    try:
        central.record(
            assignment_id=row['assignment_id'], kategori=kategori, wilayah=wilayah,
            nama_file=source, nama_sheet=sheet, status=status, tahap=tahap,
            kode_rincian=kode, pesan=pesan,
        )
        owner.messages.put(('log', f'Database pusat: status {status} tersimpan.'))
    except Exception as exc:
        owner.messages.put(('log', f'PERINGATAN sinkronisasi database pusat gagal: {exc}\nStatus lokal tetap tersimpan.'))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Otomasi DC USAHA - FASIH')
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f'{min(1900, screen_width - 20)}x{min(1020, screen_height - 50)}+0+0')
        self.minsize(1200, 720)
        self.messages = queue.Queue()
        self.commands = queue.Queue()
        self.stop_event = threading.Event()
        self.data = None
        self.rows = []
        self.mappings = []
        self.source_mode = tk.StringVar(value='file')
        self.path = tk.StringVar()
        self.sheet = tk.StringVar()
        self.kategori = tk.StringVar(value='G')
        self.wilayah = tk.StringVar(value='3201')
        self.batch_number = tk.StringVar(value='')
        self.batch_total = tk.StringVar(value=str(DATABASE_BATCH_TOTAL))
        self.limit = tk.StringVar(value='1')
        self.pembagian = tk.StringVar(value='semua')
        self.reverse = tk.BooleanVar(value=False)
        self.skip_errors = tk.BooleanVar(value=True)
        self.retry_errors = tk.BooleanVar(value=False)
        self.only_dc00 = tk.BooleanVar(value=False)
        # Nilai sumber adalah rupiah. Bawaan pembulatan dibuat aktif agar angka
        # desimal tidak pernah terkirim sebagai teks bertitik/koma ke FASIH.
        self.round_values = tk.BooleanVar(value=True)
        self.browser_ready = False
        self.busy = False
        self.journal = Journal(OUTPUT / 'status_gui.sqlite3')
        self.mapping_vars = []
        self.default_mapping = True
        self.daftar_nama = tk.StringVar(value='Bawaan')
        self.central = None
        self.central_config_error = ''
        try:
            central_config = load_config(CENTRAL_CONFIG_FILE)
            self.central = CentralAPI(central_config) if central_config else None
        except Exception as exc:
            self.central_config_error = str(exc)
        if self.central:
            self.source_mode.set('database')
        self.styles()
        self.build()
        self.reset_mapping()
        self.restore_lists()
        if self.central_config_error:
            self.log(f'PERINGATAN database pusat: {self.central_config_error}')
        elif self.central:
            self.log(f'Database pusat aktif sebagai {self.central.config.bot_id}. Sumber dan status hasil dipakai otomatis.')
            self.path_entry.configure(state='disabled')
            self.file_button.configure(state='disabled')
            self.sheet_box.configure(state='disabled')
            self.batch_box.configure(state='readonly')
            self.status.set(f'Database siap: {self.central.config.source_table}')
        else:
            self.log('Database pusat belum diatur. Klik "Atur DB pusat" untuk mengaktifkannya.')
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()
        self.after(150, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close_app)

    def styles(self):
        self.configure(background='#f1f5fa')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#f1f5fa', foreground='#18314c')
        style.configure('TFrame', background='#f1f5fa')
        style.configure('TLabelframe', background='#f1f5fa', bordercolor='#d9e3ef', relief='solid')
        style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'), foreground='#244662', background='#f1f5fa')
        style.configure('TButton', padding=(10, 6), background='#e6edf7', foreground='#18314c', borderwidth=0)
        style.map('TButton', background=[('active', '#d6e4f5'), ('disabled', '#edf1f6')])
        style.configure('Accent.TButton', background='#2563eb', foreground='white', font=('Segoe UI', 10, 'bold'))
        style.map('Accent.TButton', background=[('active', '#1d4ed8'), ('disabled', '#a8b8ce')])
        style.configure('TCheckbutton', background='#f1f5fa')
        style.configure('TCombobox', padding=3, fieldbackground='white')
        style.configure('TEntry', padding=4, fieldbackground='white')
        style.configure('Treeview', background='white', fieldbackground='white', rowheight=27, borderwidth=0)
        style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), background='#e3ebf5', relief='flat')

    def build(self):
        main = ttk.Frame(self, padding=12)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='Otomasi DC  /  USAHA', font=('Segoe UI', 17, 'bold'), foreground='#163b68').pack(anchor='w')
        ttk.Label(main, text='Sumber  →  Rincian  →  Pratinjau  →  Proses', foreground='#60758f').pack(anchor='w', pady=(0, 10))
        workspace = ttk.Panedwindow(main, orient='horizontal')
        workspace.pack(fill='both', expand=True)
        form = ttk.Frame(workspace, width=780, height=600)
        form.pack_propagate(False)
        workspace.add(form, weight=3)
        output = ttk.LabelFrame(workspace, text='4. Log proses', padding=8)
        self.console = tk.Text(output, width=45, height=12, state='disabled', wrap='word', padx=12, pady=12,
                               background='white', foreground='#263d55', font=('Segoe UI', 10), relief='flat', borderwidth=0)
        ybar = ttk.Scrollbar(output, orient='vertical', command=self.console.yview)
        self.console.configure(yscrollcommand=ybar.set)
        ybar.pack(side='right', fill='y')
        self.console.pack(side='left', fill='both', expand=True)
        workspace.add(output, weight=2)

        src = ttk.LabelFrame(form, text='1. Sumber dan filter', padding=8)
        src.pack(fill='x')
        src.columnconfigure(1, weight=1)
        ttk.Label(src, text='Sumber data').grid(row=0, column=0, sticky='w')
        source_choices = ttk.Frame(src)
        source_choices.grid(row=0, column=1, columnspan=8, sticky='w', padx=5)
        ttk.Radiobutton(source_choices, text='File lokal', variable=self.source_mode, value='file',
                        command=self.source_mode_changed).pack(side='left')
        ttk.Radiobutton(source_choices, text='Database pusat', variable=self.source_mode, value='database',
                        command=self.source_mode_changed).pack(side='left', padx=14)
        ttk.Label(src, text='File XLSX / CSV').grid(row=1, column=0, sticky='w')
        self.path_entry = ttk.Entry(src, textvariable=self.path, state='readonly')
        self.path_entry.grid(row=1, column=1, columnspan=7, sticky='ew', padx=5)
        self.file_button = ttk.Button(src, text='Pilih file', command=self.choose_file)
        self.file_button.grid(row=1, column=8)
        self.sheet_label = ttk.Label(src, text='Sheet')
        self.sheet_label.grid(row=2, column=0, sticky='w', pady=5)
        self.sheet_box = ttk.Combobox(src, textvariable=self.sheet, state='readonly', width=12)
        self.sheet_box.grid(row=2, column=1, sticky='w', padx=5)
        self.sheet_box.bind('<<ComboboxSelected>>', lambda _: self.load_sheet())
        ttk.Label(src, text='Kategori').grid(row=2, column=2, sticky='w')
        ttk.Entry(src, textvariable=self.kategori, width=7).grid(row=2, column=3, padx=5)
        ttk.Label(src, text='Kode kab/kota').grid(row=2, column=4)
        ttk.Entry(src, textvariable=self.wilayah, width=9).grid(row=2, column=5, padx=5)
        ttk.Label(src, text='Batas proses').grid(row=2, column=6)
        ttk.Entry(src, textvariable=self.limit, width=7).grid(row=2, column=7, padx=5)
        batch = ttk.Frame(src)
        batch.grid(row=3, column=0, columnspan=9, sticky='w', pady=(3, 1))
        ttk.Label(batch, text='Batch bot').pack(side='left')
        self.batch_box = ttk.Combobox(
            batch, textvariable=self.batch_number,
            values=tuple(str(number) for number in range(1, DATABASE_BATCH_TOTAL + 1)),
            state='readonly' if self.source_mode.get() == 'database' else 'disabled', width=5,
        )
        self.batch_box.pack(side='left', padx=(5, 8))
        ttk.Label(batch, text='Wajib pilih 1–25 dan gunakan nomor berbeda pada setiap bot.',
                  foreground='#60758f').pack(side='left')
        opts = ttk.Frame(src)
        opts.grid(row=4, column=0, columnspan=9, sticky='w')
        ttk.Label(opts, text='Bagian:').pack(side='left')
        ttk.Combobox(opts, textvariable=self.pembagian, values=('semua','atas','bawah'), state='readonly', width=9).pack(side='left', padx=5)
        ttk.Checkbutton(opts, text='Urutan dari bawah', variable=self.reverse).pack(side='left', padx=5)
        ttk.Checkbutton(opts, text='Lewati error notebook', variable=self.skip_errors).pack(side='left', padx=5)
        opts2 = ttk.Frame(src)
        opts2.grid(row=5, column=0, columnspan=9, sticky='w')
        ttk.Checkbutton(opts2, text='Hanya baris semua remark #0/#DC_00', variable=self.only_dc00).pack(side='left', padx=(0, 5))
        ttk.Checkbutton(opts2, text='Bulatkan desimal ke rupiah terdekat (0,5 naik)', variable=self.round_values).pack(side='left', padx=5)
        ttk.Checkbutton(opts2, text='Masukkan kembali error dan baris perlu data', variable=self.retry_errors).pack(side='left', padx=5)

        mapping = ttk.LabelFrame(form, text='2. Pemetaan kolom sumber ke rincian FASIH', padding=8)
        mapping.pack(fill='x', pady=8)
        bar = ttk.Frame(mapping)
        bar.pack(fill='x', pady=(0, 5))
        ttk.Label(bar, text='Daftar perbaikan').pack(side='left')
        self.daftar_box = ttk.Combobox(bar, textvariable=self.daftar_nama, state='readonly', width=19, values=['Bawaan'])
        self.daftar_box.pack(side='left', padx=6)
        self.daftar_box.bind('<<ComboboxSelected>>', self.select_list)
        ttk.Button(bar, text='Simpan daftar', command=self.save_list).pack(side='left', padx=(0, 4))
        ttk.Button(bar, text='Tambah rincian', command=self.add_mapping).pack(side='left', padx=4)
        ttk.Button(bar, text='Bawaan', command=self.use_default).pack(side='left', padx=4)
        header = ttk.Frame(mapping)
        header.pack(fill='x')
        header.columnconfigure(1, weight=2)
        header.columnconfigure(2, weight=1)
        header.columnconfigure(3, weight=1)
        for i, text in enumerate(('Pakai', 'Rincian FASIH', 'Kolom nilai menjadi', 'Kolom remark')):
            ttk.Label(header, text=text).grid(row=0, column=i, sticky='w', padx=3)
        mapping_view = ttk.Frame(mapping)
        mapping_view.pack(fill='x')
        self.mapping_canvas = tk.Canvas(mapping_view, height=180, background='#f1f5fa', highlightthickness=0)
        mapping_scroll = ttk.Scrollbar(mapping_view, orient='vertical', command=self.mapping_canvas.yview)
        self.mapping_canvas.configure(yscrollcommand=mapping_scroll.set)
        mapping_scroll.pack(side='right', fill='y')
        self.mapping_canvas.pack(side='left', fill='both', expand=True)
        self.mapping_frame = ttk.Frame(self.mapping_canvas)
        self.mapping_window = self.mapping_canvas.create_window((0, 0), window=self.mapping_frame, anchor='nw')
        self.mapping_canvas.bind('<Configure>', lambda event: self.mapping_canvas.itemconfigure(self.mapping_window, width=event.width))
        self.mapping_frame.bind('<Configure>', lambda _: self.mapping_canvas.configure(scrollregion=self.mapping_canvas.bbox('all')))
        self.mapping_frame.columnconfigure(1, weight=2)
        self.mapping_frame.columnconfigure(2, weight=1)
        self.mapping_frame.columnconfigure(3, weight=1)
        ttk.Label(mapping, text='#0/#DC_00: hanya remark. Pilihan/KBLI dan hasil hitung: hanya remark.', foreground='#60758f').pack(anchor='w', pady=(5, 0))

        controls = ttk.Frame(form)
        controls.pack(fill='x', pady=(0, 6))
        self.preview_button = ttk.Button(controls, text='Pratinjau antrean', command=self.preview)
        self.preview_button.pack(side='left', padx=(0, 5))
        self.browser_button = ttk.Button(controls, text='Buka browser & login', command=self.open_browser)
        self.browser_button.pack(side='left', padx=5)
        self.run_button = ttk.Button(controls, text='Jalankan yang dipratinjau', command=self.start, style='Accent.TButton')
        self.run_button.pack(side='left', padx=5)
        self.stop_button = ttk.Button(controls, text='Berhenti setelah baris ini', command=self.request_stop)
        self.stop_button.pack(side='left', padx=(0, 5))
        ttk.Button(controls, text='Izinkan ulang ID tertunda', command=self.allow_retry).pack(side='left', padx=5)
        ttk.Button(controls, text='Atur DB pusat', command=self.configure_central).pack(side='left', padx=5)
        self.status = tk.StringVar(value='Belum ada file.')
        ttk.Label(controls, textvariable=self.status).pack(side='right')

        plan = ttk.LabelFrame(form, text='3. Pratinjau antrean', padding=5)
        plan.pack(fill='both', expand=True)
        self.preview_info = tk.StringVar(value='Belum ada pratinjau data.')
        ttk.Label(plan, textvariable=self.preview_info, foreground='#526b84').pack(anchor='w', pady=(0, 5))
        table = ttk.Frame(plan)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('baris','id','usaha','aksi'), show='headings', height=12)
        for key, label, width, stretch in [
                ('baris','Baris sumber',105,False),
                ('id','Assignment ID',290,False),
                ('usaha','Nama usaha',320,False),
                ('aksi','Rencana perubahan',650,True)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=80, stretch=stretch)
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        def initial_sash(event):
            if event.width > 100:
                workspace.unbind('<Configure>')
                workspace.after_idle(lambda: workspace.sashpos(0, min(max(900, int(event.width * 0.72)), event.width - 360)))
        workspace.bind('<Configure>', initial_sash)
        def resize_mapping(event):
            height = min(190, max(130, event.height - 680))
            if int(self.mapping_canvas.cget('height')) != height:
                self.mapping_canvas.configure(height=height)
        form.bind('<Configure>', resize_mapping)

    def log(self, text):
        self.console.configure(state='normal')
        self.console.insert('end', str(text) + '\n')
        self.console.see('end')
        self.console.configure(state='disabled')

    def add_mapping(self, item=None):
        if item is None:
            self.default_mapping = False
            item = {'pakai': False, 'blok': L, 'kode': 'gaji', 'nilai': '', 'remark': ''}
        target = tk.StringVar(value=RINCIAN_PILIHAN[(item['blok'], item['kode'])])
        enabled = tk.BooleanVar(value=item['pakai'])
        value, remark = tk.StringVar(value=item['nilai']), tk.StringVar(value=item['remark'])
        row = len(self.mapping_vars)
        check = ttk.Checkbutton(self.mapping_frame, variable=enabled)
        choice = ttk.Combobox(self.mapping_frame, textvariable=target, values=list(PILIHAN_RINCIAN), state='readonly', width=23)
        columns = [''] + (list(self.data.columns) if self.data is not None else [])
        a = ttk.Combobox(self.mapping_frame, textvariable=value, values=columns, state='readonly', width=17)
        b = ttk.Combobox(self.mapping_frame, textvariable=remark, values=columns, state='readonly', width=17)
        item_vars = {'pakai':enabled, 'target':target, 'nilai':value, 'remark':remark, 'widgets':(check, choice, a, b)}
        remove = ttk.Button(self.mapping_frame, text='×', width=2, command=lambda: self.remove_mapping(item_vars))
        item_vars['widgets'] += (remove,)
        for col, widget in enumerate(item_vars['widgets']):
            widget.grid(row=row, column=col, sticky='ew' if col in (1, 2, 3) else '', padx=2, pady=2)
        choice.bind('<<ComboboxSelected>>', lambda _: self.mapping_changed(item_vars))
        self.mapping_vars.append(item_vars)
        self.mapping_canvas.update_idletasks()
        self.mapping_canvas.configure(scrollregion=self.mapping_canvas.bbox('all'))

    def mapping_changed(self, item):
        self.default_mapping = False
        block, code = PILIHAN_RINCIAN[item['target'].get()]
        default = next((t for t in TARGETS if t[1] == code and block == L), None)
        columns = self.data.columns if self.data is not None else []
        item['nilai'].set(compatible_column(default[2], columns) if default else '')
        item['remark'].set(default[3] if default and default[3] in columns else '')

    def remove_mapping(self, item):
        self.default_mapping = False
        for widget in item['widgets']:
            widget.destroy()
        self.mapping_vars.remove(item)
        for row, entry in enumerate(self.mapping_vars):
            for widget in entry['widgets']:
                widget.grid_configure(row=row)

    def reset_mapping(self):
        for item in self.mapping_vars:
            for widget in item['widgets']:
                widget.destroy()
        self.mapping_vars.clear()
        for _, code, value, remark in TARGETS:
            self.add_mapping({'pakai':False, 'blok':L, 'kode':code, 'nilai':value, 'remark':remark})
        self.default_mapping = True
        if self.data is not None:
            self.refresh_mapping_columns()

    def refresh_mapping_columns(self):
        columns = [''] + (list(self.data.columns) if self.data is not None else [])
        for item in self.mapping_vars:
            item['widgets'][2].configure(values=columns)
            item['widgets'][3].configure(values=columns)
            if self.default_mapping and self.data is not None:
                item['pakai'].set(item['remark'].get() in columns)
                item['nilai'].set(compatible_column(item['nilai'].get(), columns))
                if item['remark'].get() not in columns:
                    item['remark'].set('')
        self.default_mapping = False

    def mapping_config(self):
        return [{'pakai':item['pakai'].get(), 'blok':PILIHAN_RINCIAN[item['target'].get()][0],
                 'kode':PILIHAN_RINCIAN[item['target'].get()][1], 'nilai':item['nilai'].get(),
                 'remark':item['remark'].get()} for item in self.mapping_vars]

    def apply_mapping_config(self, rows):
        for item in self.mapping_vars:
            for widget in item['widgets']:
                widget.destroy()
        self.mapping_vars.clear()
        for row in rows:
            self.add_mapping(row)
        self.default_mapping = False
        self.refresh_mapping_columns()
        self.rows = []
        self.tree.delete(*self.tree.get_children())

    def restore_lists(self):
        try:
            data = load_lists(DAFTAR_FILE)
            self.daftar_box.configure(values=['Bawaan'] + sorted(data['daftar']))
            selected = data.get('terpilih', '')
            if selected:
                self.daftar_nama.set(selected)
                self.apply_mapping_config(data['daftar'][selected])
                self.log(f'Daftar perbaikan "{selected}" dimuat. Pilih file sumber untuk melanjutkan.')
        except Exception as exc:
            messagebox.showerror('Daftar perbaikan gagal dibaca', str(exc))

    def select_list(self, _event=None):
        try:
            name = self.daftar_nama.get()
            data = load_lists(DAFTAR_FILE)
            if name == 'Bawaan':
                self.reset_mapping()
                data['terpilih'] = ''
            else:
                self.apply_mapping_config(data['daftar'][name])
                data['terpilih'] = name
            if DAFTAR_FILE.exists():
                save_lists(DAFTAR_FILE, data)
            self.rows = []
            self.tree.delete(*self.tree.get_children())
            self.log(f'Daftar perbaikan dipilih: {name}. Buat ulang pratinjau.')
        except Exception as exc:
            messagebox.showerror('Daftar gagal dipilih', str(exc))

    def use_default(self):
        self.daftar_nama.set('Bawaan')
        self.select_list()

    def save_list(self):
        try:
            rows = self.mapping_config()
            if not rows or not any(row['pakai'] for row in rows):
                raise ValueError('Pilih sedikitnya satu rincian sebelum menyimpan.')
            if self.data is not None:
                validate_mappings(self.data.columns, self.get_mappings())
            name = simpledialog.askstring('Simpan daftar perbaikan', 'Nama daftar:', parent=self)
            if name is None:
                return
            name = name.strip()
            if not name or name.casefold() == 'bawaan':
                raise ValueError('Nama daftar tidak boleh kosong atau Bawaan.')
            data = load_lists(DAFTAR_FILE)
            if name in data['daftar'] and not messagebox.askyesno('Ganti daftar?', f'Daftar "{name}" sudah ada. Ganti isinya?'):
                return
            data['daftar'][name] = rows
            data['terpilih'] = name
            save_lists(DAFTAR_FILE, data)
            self.daftar_nama.set(name)
            self.daftar_box.configure(values=['Bawaan'] + sorted(data['daftar']))
            self.log(f'Daftar "{name}" disimpan dan akan dimuat saat GUI dibuka kembali.')
        except Exception as exc:
            messagebox.showerror('Daftar gagal disimpan', str(exc))

    def choose_file(self):
        path = filedialog.askopenfilename(filetypes=[('Excel atau CSV', '*.xlsx *.csv')])
        if not path:
            return
        try:
            self.path.set(path)
            self.source_mode.set('file')
            self.source_mode_changed(clear_data=False)
            if Path(path).suffix.lower() == '.xlsx':
                with pd.ExcelFile(path) as book:
                    sheets = book.sheet_names
                self.sheet_box.configure(values=sheets)
                self.sheet.set(sheets[0])
            else:
                self.sheet_box.configure(values=['CSV'])
                self.sheet.set('CSV')
            self.load_sheet()
        except Exception as exc:
            self.data = None
            messagebox.showerror('Gagal membaca file', str(exc))

    def load_sheet(self):
        try:
            self.data = read_source(Path(self.path.get()), None if self.sheet.get() == 'CSV' else self.sheet.get())
            self.refresh_mapping_columns()
            self.rows = []
            self.tree.delete(*self.tree.get_children())
            self.status.set(f'{len(self.data)} baris dimuat')
        except Exception as exc:
            self.data = None
            messagebox.showerror('Gagal membaca sheet', str(exc))

    def source_mode_changed(self, clear_data=True):
        """Alihkan sumber tanpa mengubah perilaku mode file yang lama."""
        database_mode = self.source_mode.get() == 'database'
        self.path_entry.configure(state='disabled' if database_mode else 'readonly')
        self.file_button.configure(state='disabled' if database_mode else 'normal')
        self.sheet_box.configure(state='disabled' if database_mode else 'readonly')
        self.batch_box.configure(state='readonly' if database_mode else 'disabled')
        if clear_data:
            self.rows = []
            self.tree.delete(*self.tree.get_children())
            self.preview_info.set('Belum ada pratinjau data.')
        if not database_mode:
            self.status.set('Pilih file lokal.')
            return
        if not self.central:
            self.data = None
            self.status.set('Database pusat belum diatur')
            messagebox.showerror('Database pusat', 'Atur DB pusat terlebih dahulu, lalu pilih kembali mode Database pusat.')
            return
        try:
            columns = self.central.source_columns()
            if not columns:
                raise ValueError('Tabel sumber database tidak memiliki kolom.')
            self.data = pd.DataFrame(columns=columns)
            self.refresh_mapping_columns()
            self.status.set(f'Database siap: {self.central.config.source_table}')
            self.log(f'Mode sumber database aktif: {self.central.config.database}.{self.central.config.source_table}.')
        except Exception as exc:
            self.data = None
            self.status.set('Database sumber tidak dapat dibaca')
            messagebox.showerror('Database pusat', str(exc))

    def get_mappings(self):
        result = []
        for item in self.mapping_vars:
            if item['pakai'].get():
                block, code = PILIHAN_RINCIAN[item['target'].get()]
                result.append(Mapping(KATALOG[(block, code)][0], code, item['nilai'].get(), item['remark'].get(), block))
        return result

    def settings(self):
        return (self.source_mode.get(), self.path.get(), self.sheet.get(), self.kategori.get().strip().upper(), self.wilayah.get().strip(),
                self.batch_number.get().strip(), self.batch_total.get().strip(),
                self.limit.get().strip(), self.pembagian.get(), self.reverse.get(), self.skip_errors.get(),
                self.only_dc00.get(), self.round_values.get(), self.retry_errors.get(), tuple((m.blok, m.kode, m.nilai, m.remark) for m in self.get_mappings()))

    def configure_central(self):
        current = self.central.config if self.central else None
        token = simpledialog.askstring(
            'Database pusat',
            'Masukkan token API pusat. Token disimpan hanya di config_pusat.json pada PC ini:',
            parent=self,
            show='*',
        )
        if token is None:
            return
        token = token.strip()
        if not token:
            messagebox.showerror('Database pusat', 'Token tidak boleh kosong.')
            return
        bot_id = simpledialog.askstring(
            'Identitas PC',
            'Nama PC/bot yang akan dicatat pada database pusat:',
            parent=self,
            initialvalue=current.bot_id if current else default_bot_id(),
        )
        if bot_id is None:
            return
        try:
            config = CentralConfig(
                base_url=current.base_url if current else DEFAULT_BASE_URL,
                token=token,
                database=current.database if current else DEFAULT_DATABASE,
                table=current.table if current else DEFAULT_TABLE,
                source_table=current.source_table if current else DEFAULT_SOURCE_TABLE,
                bot_id=bot_id.strip(),
            )
            save_config(CENTRAL_CONFIG_FILE, config)
            self.central = CentralAPI(config)
            self.central_config_error = ''
            self.log(f'Database pusat diaktifkan sebagai {config.bot_id}.')
            messagebox.showinfo('Database pusat', 'Konfigurasi tersimpan. Koneksi akan diperiksa saat membuat pratinjau.')
        except Exception as exc:
            messagebox.showerror('Database pusat', str(exc))

    def preview(self):
        try:
            kategori, wilayah = self.kategori.get().strip().upper(), self.wilayah.get().strip()
            if not (wilayah.isdigit() and len(wilayah) == 4):
                raise ValueError('Kode kabupaten/kota wajib diisi tepat 4 digit, misalnya 3201.')
            retry_errors = self.retry_errors.get()
            database_mode = self.source_mode.get() == 'database'
            if database_mode:
                batch_text = self.batch_number.get().strip()
                if not batch_text.isdigit() or not 1 <= int(batch_text) <= DATABASE_BATCH_TOTAL:
                    raise ValueError('Batch bot wajib dipilih antara 1 sampai 25 saat memakai Database pusat.')
                batch_number = int(batch_text)
                batch_total = DATABASE_BATCH_TOTAL
                if self.pembagian.get() != 'semua':
                    raise ValueError('Saat memakai pembagian batch bot, pilih Bagian: semua agar tidak ada data yang terlewat.')
                if not self.central:
                    raise ValueError('Atur DB pusat sebelum memakai sumber database.')
                requested = int(self.limit.get())
                fetch_limit = min(max(requested * 20, 200), 5000)
                records = self.central.source_rows(
                    kategori, wilayah, fetch_limit, reverse=self.reverse.get(),
                    split=self.pembagian.get(), retry_errors=retry_errors,
                    batch_number=batch_number, batch_total=batch_total,
                )
                data = pd.DataFrame(records).fillna('')
                if data.empty:
                    data = pd.DataFrame(columns=self.central.source_columns())
                data.columns = data.columns.astype(str).str.strip()
                if 'id' in data.columns:
                    data['_source_id'] = data['id']
                if 'source_row' in data.columns:
                    data['_baris_sumber'] = data['source_row']
                elif 'id' in data.columns:
                    data['_baris_sumber'] = data['id']
                # Pemetaan bawaan baru dapat diaktifkan setelah nama kolom tabel
                # diketahui. Dengan ini database bisa menjadi sumber otomatis
                # tanpa query tambahan saat jendela baru dibuka.
                self.data = data
                self.refresh_mapping_columns()
                done = set()
            else:
                batch_number, batch_total = 1, 1
                if self.data is None:
                    raise ValueError('Pilih file terlebih dahulu.')
                # Muat ulang saat pratinjau agar perubahan terakhir pada file terbaca.
                data = read_source(Path(self.path.get()), None if self.sheet.get() == 'CSV' else self.sheet.get())
                done = old_ids(Path(self.path.get()).parent, kategori, wilayah,
                               self.skip_errors.get() and not retry_errors)
            mappings = self.get_mappings()
            central_count = 0
            if self.central:
                try:
                    central_done = self.central.completed_ids(kategori, wilayah)
                    central_count = len(central_done)
                    done.update(central_done)
                except Exception as exc:
                    self.log(f'PERINGATAN database pusat tidak dapat dibaca: {exc}\nPratinjau dilanjutkan memakai log lokal.')
            statuses = self.journal.statuses(include_errors=not retry_errors)
            required = {'kategori','level_2_full_code','nama_usaha','link_fasih_sm','Siap Input','Sudah Diinput'}
            if not required <= set(data.columns):
                raise ValueError('Kolom wajib tidak ditemukan: ' + ', '.join(sorted(required - set(data.columns))))
            # Pada sumber file, assignment ganda tidak aman karena aplikasi tidak
            # mengetahui cara menggabungkan beberapa usaha ke satu kuesioner.
            # Untuk database pusat, tahan saja assignment tersebut di luar antrean
            # agar assignment tunggal lainnya tetap bisa diproses.
            if not database_mode:
                check_duplicate_assignments(data, kategori, wilayah, done, statuses)
            duplicate_assignments = set()
            duplicate_rows = 0
            if database_mode and not data.empty:
                duplicate_assignments = self.central.duplicate_source_ids(data['assignment_id'])
                if duplicate_assignments:
                    assignment_values = data['assignment_id'].astype(str).str.strip().str.lower()
                    duplicate_rows = int(assignment_values.isin(duplicate_assignments).sum())
                    data = data.loc[~assignment_values.isin(duplicate_assignments)].copy()
            nonduplicate_rows = len(data)
            if self.only_dc00.get():
                if not mappings or any(not m.remark or m.remark not in data.columns for m in mappings):
                    raise ValueError('Pilih kolom remark sebelum memakai filter #0/#DC_00.')
                mask = data[[m.remark for m in mappings]].apply(
                    lambda col: col.astype(str).str.strip().str.upper().isin({'#0', '#DC_00'})
                ).all(axis=1)
                data = data.loc[mask].copy()
                if data.empty:
                    raise ValueError('Tidak ada kandidat yang seluruh remark-nya #0/#DC_00. '
                                     'Nonaktifkan filter tersebut untuk memproses usulan model dengan remark #3.')
            self.rows = make_queue(data, mappings, kategori, wilayah, done, statuses,
                                   reverse=self.reverse.get(), split=self.pembagian.get(), limit=int(self.limit.get()),
                                   round_values=self.round_values.get())
            if database_mode and not self.rows:
                if duplicate_assignments and nonduplicate_rows == 0:
                    raise ValueError('Semua kandidat pada batch ini terkait assignment yang memiliki beberapa baris. '
                                     'Tidak ada baris tunggal yang aman diproses pada batch ini.')
                raise ValueError('Tidak ada baris yang memenuhi syarat untuk diproses.')
            self.mappings = mappings
            self.preview_settings = self.settings()
            self.source_mtime = None if database_mode else Path(self.path.get()).stat().st_mtime_ns
            self.tree.delete(*self.tree.get_children())
            for row in self.rows:
                plan = ', '.join(f'{m.label}: {remark}' +
                                 (f' → {value}' + (f' (sumber: {row[m.nilai]})' if str(row[m.nilai]).strip() != value else '') if change else '')
                                 for m, remark, value, change in preview_actions(row, mappings, self.round_values.get()))
                self.tree.insert('', 'end', values=(row['_baris_sumber'], row['assignment_id'], row['nama_usaha'], plan))
            preview_count = f'{len(self.rows):,}'.replace(',', '.')
            self.preview_info.set(
                f'Ukuran pratinjau: {preview_count} baris × 4 kolom '
                '(baris sumber, assignment ID, nama usaha, rencana perubahan).'
            )
            self.status.set(f'{len(self.rows)} baris siap diproses · batch {batch_number}/{batch_total}')
            source_note = ('Data diambil bertahap dari database pusat.' if database_mode
                           else 'Log GUI dan log notebook yang sesuai sudah diperiksa.')
            self.log(f'Pratinjau batch {batch_number}/{batch_total}: {len(self.rows)} baris. {source_note}' +
                     (f' Database pusat memuat {central_count} ID berhasil untuk kategori/wilayah ini.' if self.central else ' Database pusat belum aktif.') +
                     (f' {len(duplicate_assignments)} assignment ganda ({duplicate_rows} baris pada batch) ditahan untuk penanganan gabungan.' if duplicate_assignments else '') +
                     (' Error dan baris perlu data diikutsertakan; periksa perubahan sebagian di FASIH sebelum menjalankan.' if retry_errors else ''))
        except Exception as exc:
            self.rows = []
            self.preview_info.set('Pratinjau belum tersedia karena terjadi kesalahan.')
            messagebox.showerror('Pratinjau gagal', str(exc))

    def open_browser(self):
        if self.busy:
            return
        self.busy = True
        self.commands.put(('browser', None))
        self.status.set('Membuka browser...')

    def start(self):
        try:
            if self.busy or not self.browser_ready:
                raise ValueError('Buka browser, login manual, lalu tunggu browser siap.')
            if not self.rows:
                raise ValueError('Buat pratinjau antrean yang tidak kosong.')
            wilayah = self.wilayah.get().strip()
            if not (wilayah.isdigit() and len(wilayah) == 4):
                raise ValueError('Kode kabupaten/kota wajib diisi tepat 4 digit, misalnya 3201.')
            database_mode = self.source_mode.get() == 'database'
            source_changed = (not database_mode and Path(self.path.get()).stat().st_mtime_ns != self.source_mtime)
            if self.settings() != self.preview_settings or source_changed:
                raise ValueError('Pengaturan atau file berubah. Buat ulang pratinjau.')
            if not messagebox.askyesno('Konfirmasi proses',
                f'Proses {len(self.rows)} assignment' +
                (f' dari batch {self.batch_number.get()}/{DATABASE_BATCH_TOTAL}' if database_mode else '') + '?\n\n'
                'Proses dapat revoke, mengubah nilai/catatan, mengirim dan approve. '
                f'Pembulatan desimal: {"aktif" if self.round_values.get() else "tidak aktif"}. '
                'Pastikan akun sesuai wilayah. Jika gagal setelah revoke, status perlu diperiksa manual.' +
                ('\n\nError dan baris perlu data ikut diproses ulang. Pastikan status, nilai, dan remark sudah diperiksa di FASIH.' if self.retry_errors.get() else '')):
                return
            self.busy = True
            self.stop_event.clear()
            source = (f'DB:{self.central.config.source_table}' if database_mode else self.path.get())
            sheet = 'DATABASE' if database_mode else self.sheet.get()
            self.commands.put(('run', (list(self.rows), list(self.mappings), source, sheet,
                                       self.kategori.get().strip().upper(), self.wilayah.get().strip(),
                                       self.skip_errors.get() and not self.retry_errors.get(),
                                       self.round_values.get(), self.retry_errors.get(), self.source_mode.get())))
            self.status.set('Menjalankan...')
        except Exception as exc:
            messagebox.showerror('Belum bisa dijalankan', str(exc))

    def request_stop(self):
        self.stop_event.set()
        self.log('Permintaan berhenti diterima; proses berhenti setelah assignment saat ini.')

    def allow_retry(self):
        if self.busy:
            messagebox.showwarning('Proses berjalan', 'Tunggu proses selesai sebelum mengizinkan ulang.')
            return
        aid = simpledialog.askstring('Izinkan ulang', 'Masukkan assignment ID yang sudah diperiksa di FASIH:', parent=self)
        if not aid:
            return
        aid = aid.strip().lower()
        if not messagebox.askyesno('Konfirmasi', 'Pastikan status, remark, dan kemungkinan perubahan sebelumnya sudah diperiksa di FASIH. Izinkan ID ini masuk antrean lagi?'):
            return
        try:
            source = self.journal.source_of(aid)
            if source and source.startswith('DB:'):
                if not self.central:
                    raise ValueError('Koneksi database pusat diperlukan untuk membuka ulang baris ini.')
                self.central.release_checked_source(aid)
            self.journal.allow_retry(aid)
            self.journal.export(OUTPUT)
            self.rows = []
            self.log(f'{aid}: diizinkan ulang di jurnal lokal dan, bila perlu, tabel sumber pusat. Buat pratinjau baru.')
        except Exception as exc:
            messagebox.showerror('Tidak dapat mengizinkan ulang', str(exc))

    def worker(self):
        browser = None
        while True:
            command, payload = self.commands.get()
            if command == 'close':
                if browser:
                    browser.close()
                return
            try:
                if command == 'browser':
                    from fasih import Fasih
                    if browser is None:
                        browser = Fasih(PROFILE)
                    try:
                        browser.open()
                    except Exception as exc:
                        detail = str(exc)
                        if 'ERR_NAME_NOT_RESOLVED' in detail:
                            reason = 'DNS FASIH belum dapat diakses. Periksa jaringan/VPN BPS.'
                        elif 'Target page, context or browser has been closed' in detail:
                            reason = f'Profil {PROFILE.name} gagal memulai Chromium. Tutup browser lain yang memakai profil ini.'
                        else:
                            reason = f'Periksa profil {PROFILE.name}, koneksi, dan login FASIH.'
                        raise RuntimeError(f'Browser gagal dibuka. {reason} Detail: {exc}') from exc
                    self.messages.put(('browser_ready', f'Browser terbuka dengan profil {PROFILE.name}. Silakan periksa login akun kab/kota.'))
                elif command == 'run':
                    from fasih import NeedsSourceData
                    if len(payload) == 9:  # kompatibilitas dengan pemanggil/test mode file lama
                        rows, mappings, source, sheet, kategori, wilayah, skip_errors, round_values, retry_errors = payload
                        source_mode = 'file'
                    else:
                        rows, mappings, source, sheet, kategori, wilayah, skip_errors, round_values, retry_errors, source_mode = payload
                    berhasil = gagal = perlu_data = dilewati = 0
                    for i, row in enumerate(rows, 1):
                        if self.stop_event.is_set():
                            self.messages.put(('log', 'Proses dihentikan atas permintaan pengguna.'))
                            break
                        aid = row['assignment_id']
                        self.messages.put(('log', f'\n{"-" * 48}\n[{i}/{len(rows)}] {row["nama_usaha"]}\nAssignment ID: {aid}'))
                        # Log notebook hanya berlaku untuk sumber file dan dapat berubah setelah pratinjau.
                        if source_mode == 'file' and aid in old_ids(Path(source).parent, kategori, wilayah, skip_errors):
                            dilewati += 1
                            self.messages.put(('log', 'Dilewati: sudah tercatat di notebook.'))
                            continue
                        if not self.journal.claim(aid, str(row['nama_usaha']), source, row['_baris_sumber'], retry_errors=retry_errors):
                            dilewati += 1
                            self.messages.put(('log', 'Dilewati: sudah diklaim atau tercatat di GUI.'))
                            continue
                        if source_mode == 'database':
                            try:
                                if not self.central.claim_source(row['_source_id'], retry_errors=retry_errors):
                                    self.journal.finish(aid, 'error', 'Baris database sedang diproses PC lain atau statusnya berubah.')
                                    dilewati += 1
                                    self.messages.put(('log', 'Dilewati: baris database tidak berhasil dikunci.'))
                                    continue
                            except Exception as exc:
                                self.journal.finish(aid, 'error', f'Gagal mengunci baris database: {exc}')
                                raise RuntimeError(f'Proses dihentikan karena baris database tidak dapat dikunci: {exc}') from exc
                        try:
                            browser.process(row, mappings, lambda s: self.messages.put(('log', s)), round_values=round_values)
                            self.journal.finish(aid, 'berhasil', 'Submit dan approve terverifikasi.')
                            berhasil += 1
                            self.messages.put(('log', 'HASIL: berhasil.'))
                            if source_mode == 'database':
                                try:
                                    self.central.complete_source(row['_source_id'], 'BERHASIL', 'selesai',
                                                                 'Submit dan approve terverifikasi.')
                                    self.messages.put(('log', 'Database sumber: Sudah Diinput = 1.'))
                                except Exception as exc:
                                    self.messages.put(('log', f'PERINGATAN: FASIH berhasil, tetapi status baris sumber gagal diperbarui: {exc}'))
                            _record_central(self, row, source, sheet, kategori, wilayah, 'berhasil',
                                            'selesai', None, 'Submit dan approve terverifikasi.')
                        except NeedsSourceData as exc:
                            self.journal.finish(aid, 'perlu_data', str(exc))
                            perlu_data += 1
                            self.messages.put(('log', f'HASIL: PERLU DATA\n{exc}\nLengkapi fakta yang belum ada sebelum mencoba ulang.'))
                            self.journal.export(OUTPUT)
                            if source_mode == 'database':
                                try:
                                    self.central.complete_source(row['_source_id'], 'PERLU_DATA',
                                                                 _browser_stage(browser), str(exc))
                                except Exception as update_exc:
                                    self.messages.put(('log', f'PERINGATAN status baris sumber gagal diperbarui: {update_exc}'))
                            _record_central(self, row, source, sheet, kategori, wilayah, 'perlu_data',
                                            _browser_stage(browser), _browser_code(browser), str(exc))
                            continue
                        except Exception as exc:
                            result_status = 'perlu_diperiksa' if getattr(browser, 'may_have_changed', False) is True else 'error'
                            self.journal.finish(aid, result_status, str(exc))
                            gagal += 1
                            label = 'PERLU DIPERIKSA' if result_status == 'perlu_diperiksa' else 'ERROR'
                            self.messages.put(('log', f'HASIL: {label}\n{exc}\nDicatat; periksa status di FASIH sebelum mencoba ulang. Lanjut ke baris berikutnya.'))
                            self.journal.export(OUTPUT)
                            if source_mode == 'database':
                                try:
                                    database_status = 'PERLU_DIPERIKSA' if result_status == 'perlu_diperiksa' else 'ERROR'
                                    self.central.complete_source(row['_source_id'], database_status,
                                                                 _browser_stage(browser), str(exc))
                                except Exception as update_exc:
                                    self.messages.put(('log', f'PERINGATAN status baris sumber gagal diperbarui: {update_exc}'))
                            _record_central(self, row, source, sheet, kategori, wilayah, result_status,
                                            _browser_stage(browser), _browser_code(browser), str(exc))
                            continue
                        self.journal.export(OUTPUT)
                    self.messages.put(('done', f'\n{"=" * 48}\nProses selesai / berhenti: berhasil {berhasil}, perlu data {perlu_data}, error {gagal}, dilewati {dilewati}.\nBuat pratinjau baru sebelum menjalankan lagi.'))
            except Exception as exc:
                self.messages.put(('error', str(exc)))

    def poll(self):
        while True:
            try:
                event, text = self.messages.get_nowait()
            except queue.Empty:
                break
            self.log(text)
            if event == 'browser_ready':
                self.browser_ready = True
                self.busy = False
                self.status.set('Browser siap; login manual')
            elif event in ('done', 'error'):
                self.busy = False
                self.rows = []
                self.status.set('Berhenti; buat pratinjau baru')
                if event == 'error':
                    messagebox.showerror('Kesalahan', text)
        self.after(150, self.poll)

    def close_app(self):
        if self.busy:
            messagebox.showwarning('Proses masih berjalan', 'Tunggu proses berhenti sebelum menutup aplikasi.')
            return
        if self.browser_ready and not messagebox.askyesno('Tutup aplikasi', 'Menutup aplikasi juga akan menutup browser aplikasi. Lanjutkan?'):
            return
        self.commands.put(('close', None))
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
