# Otomasi DC USAHA — GUI lokal

Aplikasi ini terpisah dari `USAHA 1.ipynb`. Sumber dapat berupa file lokal (XLSX/CSV) atau tabel pusat `OTOMASI_DC.data_split_usaha_20261016`. Mode file tetap tidak mengubah file sumber. Otomasi FASIH menggunakan profil browser notebook dan login manual. Bawaan aplikasi adalah tujuh rincian keuangan USAHA seperti sebelumnya.

## Menjalankan

Di terminal, dari folder ini:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Setelah dependensi terpasang, pengguna Windows juga dapat menjalankan aplikasi dengan membuka `Mulai GUI.bat`.

Jika `config_pusat.json` tersedia dan valid, GUI langsung memilih **Database pusat** saat dibuka dan memuat informasi tabel secara otomatis. Opsi **Bulatkan desimal ke rupiah terdekat (0,5 naik)** juga aktif secara bawaan; pengguna tetap dapat menonaktifkannya bila sumber memang harus ditolak ketika memiliki pecahan rupiah.

Jendela menyesuaikan hampir seluruh ukuran layar. Area pratinjau menampilkan ukuran data dalam format **jumlah baris × 4 kolom**, dengan ruang lebih besar untuk nomor baris sumber, assignment ID, nama usaha, dan rencana perubahan.

### Database pusat antar-PC

GUI dapat memakai tabel `hasil_otomasi_dc` pada database `OTOMASI_DC` sebagai daftar hasil bersama. Klik **Atur DB pusat**, masukkan token API dan identitas PC/bot. Token disimpan pada `config_pusat.json` di PC ini; file tersebut diabaikan Git. URL bawaan adalah `http://103.54.218.181:8555/api/v1/gateway`. URL, database, dan tabel dapat diubah melalui `config_pusat.json` atau environment variable `OTOMASI_DC_API_URL`, `OTOMASI_DC_DATABASE`, dan `OTOMASI_DC_TABLE`. Token juga dapat diberikan melalui `OTOMASI_DC_API_TOKEN`.

Saat **Pratinjau antrean** ditekan, GUI mengambil `assignment_id` berstatus `berhasil` untuk kategori dan wilayah yang dipilih, lalu menggabungkannya dengan log notebook dan jurnal SQLite lokal. Jika API pusat tidak tersedia, pratinjau tetap dibuat dari log lokal dan menampilkan peringatan. Setelah setiap assignment selesai atau gagal, GUI mengirim satu baris dengan mode `append`. Kegagalan sinkronisasi pusat tidak menghapus hasil pada jurnal lokal.

Status pusat terdiri dari `berhasil`, `error`, `perlu_data`, dan `perlu_diperiksa`. Status terakhir digunakan jika proses gagal setelah revoke atau kemungkinan perubahan data. Hanya `berhasil` yang dianggap selesai ketika menyaring antrean. Nama file dikirim tanpa path lengkap; nama usaha dan isi jawaban tidak dikirim.

### Dua mode sumber data

- **File lokal** mempertahankan alur lama: pilih XLSX/CSV dan sheet. File sumber tidak diubah.
- **Database pusat** membaca batch kecil dari `data_split_usaha_20261016`, dengan syarat `Siap Input = 1` dan `Sudah Diinput` belum bernilai 1. Pilih kategori, wilayah, dan batas proses lalu buat pratinjau.
- Mode database tidak mengunduh seluruh tabel. Aplikasi membaca maksimal sejumlah kecil kandidat untuk membentuk antrean.
- Assignment yang terkait dengan beberapa baris sumber ditahan dari antrean untuk penanganan gabungan; assignment tunggal lainnya tetap dapat dipratinjau dan diproses. Pemeriksaan dilakukan dalam batch kecil agar tidak membebani gateway pusat.
- Sebelum membuka assignment, aplikasi mengunci baris berdasarkan `id` dan mencatat PC pada kolom `automation_*`. Jika FASIH berhasil sampai approve terverifikasi, `Sudah Diinput` menjadi 1. Jika gagal, nilainya tetap 0 dan status kegagalan disimpan pada `automation_status`, jurnal lokal, serta tabel log pusat.
- Pencatatan status ke tabel sumber dan tabel log pusat dilakukan otomatis oleh GUI; pengguna tidak perlu menekan tombol penyimpanan database terpisah.
- Pilihan **atas** membaca dari ID kecil dan **bawah** dari ID besar. Opsi **Urutan dari bawah** membalik arah tersebut.
- Satu assignment yang ditemukan pada beberapa baris siap input tetap ditolak untuk penanganan gabungan.

### Mengimpor folder SIAP INPUT UB

Skrip `import_siap_input_ub.py` menyiapkan seluruh XLSX dalam folder `SIAP INPUT UB` untuk tabel sumber pusat. Skrip selalu mulai sebagai dry-run, tidak mengubah XLSX, tidak memakai mode `replace`, dan menyimpan laporan CSV/JSON ke folder `hasil`.

```powershell
# Pemeriksaan saja; database tidak ditulis
python import_siap_input_ub.py

# Pemeriksaan dengan pembulatan rupiah desimal (0,5 naik)
python import_siap_input_ub.py --round-values

# Tulis setelah laporan dry-run sudah diperiksa
python import_siap_input_ub.py --execute --round-values
```

Baris valid disimpan dengan `Siap Input = 1`, `Sudah Diinput = 0`, dan `automation_status = SIAP_DIINPUT`. Assignment ganda yang berbeda, identitas yang bertentangan, KBLI berubah, tahun operasi yang belum didukung, serta baris database yang sedang/selesai diproses akan ditahan dan dijelaskan di laporan. Sesudah eksekusi, skrip membaca ulang hasil tulis dan memastikan status setiap baris. Opsi `--round-values` harus disebutkan secara sadar karena sebagian nilai sumber mengandung pecahan rupiah.

1. Pilih mode **File lokal** lalu pilih file dan sheet, atau pilih **Database pusat**. Sumber harus memiliki `kategori`, `level_2_full_code`, `nama_usaha`, `link_fasih_sm`, `Siap Input`, dan `Sudah Diinput`.
2. Masukkan kategori dan kode kabupaten/kota sesuai akun. Tentukan bagian antrean dan pilih rincian beserta kolom nilai dan/atau remark. Kolom standar G dipilih otomatis jika tersedia. Untuk menambah, pilih **Tambah rincian**, pilih label dan kode, tentukan kolomnya lalu centang **Pakai**. Tanda × menghapus satu baris pemetaan.
3. Klik **Pratinjau antrean**, periksa nama, ID, remark dan nilai. Batasi 1 baris untuk uji pertama.
4. Klik **Buka browser & login** dan periksa bahwa akun yang aktif sesuai wilayah. GUI memakai profil tersendiri di `../fasih_profile_gui`. Login kembali bila FASIH meminta, termasuk setelah browser ditutup. Profil mengandung sesi rahasia dan tidak bisa dipakai dua browser bersamaan. Pengaturan browser tidak menjamin situs tidak menampilkan pemeriksaan bot.
5. Setelah login, klik **Jalankan yang dipratinjau**, baca konfirmasi dan setujui jika sesuai. Tombol berhenti menunggu assignment saat ini selesai.

### Menyimpan daftar perbaikan

- Setelah memilih rincian dan kolom, klik **Simpan daftar**, berikan nama, lalu konfirmasi jika ingin mengganti daftar dengan nama sama.
- Daftar yang terakhir disimpan atau dipilih dimuat ketika aplikasi dibuka lagi. Pilih kembali file sumber; nama kolom tersimpan tetap dipakai dan akan diperiksa pada pratinjau. Jika nama kolom sumber berbeda, sesuaikan pemetaannya.
- Tombol **Bawaan** mengembalikan tujuh rincian keuangan standar. Daftar tersimpan tetap tersedia di pilihan daftar. Pengaturan disimpan di `daftar_perbaikan.json`; file ini berisi nama daftar dan kolom, bukan data sumber atau kredensial.
- Katalog label, blok, kode, dan batas dukungan disimpan di `katalog_rincian.py`. Katalog berdasarkan satu contoh SE2026-L dan bukan daftar lengkap semua kondisi atau kuesioner.

## Perilaku dan batasan penting

- Pratinjau tidak membuka assignment, tidak revoke, dan tidak mengubah data. Menjalankan proses dapat revoke, mengisi nilai/remark, mengaktifkan sakelar anomali yang spesifik, mengirim, dan approve.
- Nama usaha dicocokkan. Tahun operasi dibaca sebelum revoke: tahun 2026 atau tahun tidak valid dicatat sebagai error, karena rincian bulanan dan periode nilainya belum ditangani.
- Pemetaan dapat memakai kolom nilai saja, remark saja, atau keduanya. Remark `#0` dan `#DC_00` tidak mengubah nilai. Filter **Hanya baris semua remark #0/#DC_00** dipakai khusus untuk baris tanpa perubahan nilai; nonaktifkan filter itu saat memproses usulan model yang mengandung remark `#3`. Jika seluruh rincian pada satu baris hanya memakai kedua remark tersebut dan assignment masih berstatus approved, aplikasi memvalidasi tombol catatan, melakukan revoke, mengisi catatan langsung dari halaman review, lalu approve kembali tanpa membuka Edit dan tanpa Kirim. Remark lain dengan kolom nilai mengharuskan nilai perbaikan. Jika hanya kolom remark dipilih, tidak ada nilai yang diubah. Sebagian angka sumber mengandung desimal meskipun tampilan Excel bulat. Jika pengguna menyetujuinya, centang **Bulatkan nilai desimal**: dibulatkan ke rupiah terdekat, 0,5 naik. Pratinjau menampilkan nilai yang akan dikirim dan nilai sumber jika berbeda. Jika tidak dicentang, angka pecahan ditolak, tanpa pembulatan otomatis. Angka harus tanpa pemisah ribuan; format ambigu ditolak. Nilai setelah diisi diperiksa ulang. Input kosong atau rincian yang tidak unik menghentikan assignment.
- Rincian katalog bertipe `teks`, `angka` dan `rupiah` dapat dipilih untuk perubahan nilai; tipe `catatan` hanya bisa diberi remark, dan `informasi` belum dapat diproses. Pilihan radio, KBLI, persentase dan hasil hitung belum didukung untuk perubahan nilai. Kehadiran dan kemampuan edit target tetap diperiksa pada setiap assignment. Rincian keuangan di blok usaha kuesioner L, UB, dan Pengisian Mandiri menggunakan kode yang sama; blok lain untuk UB/Mandiri belum didukung. Tahun operasi 2026 tetap dilewati.
- KBLI belum didukung. Jika `KBLI (menjadi)` berisi nilai, proses berhenti untuk pemeriksaan manual. Jangan gunakan aplikasi ini untuk memilih atau mengubah KBLI.
- Jika ada tepat satu GALAT `Tampilkan Anomali Usaha dan Keluarga — Wajib diisi`, aplikasi mencoba mengaktifkan sakelar dan memeriksa ulang. GALAT CV pada `Perubahan Nama usaha/perusahaan` dapat memperbaiki akhiran nama menjadi `,CV` hanya ketika nama di isian masih sesuai sumber. GALAT lain menghentikan assignment tersebut. Jika FASIH menampilkan `Masih Ada yang Belum Dijawab`, aplikasi mencatat pertanyaan wajib yang tersisa sebagai `perlu_data` dan tidak mengirim assignment.
- Log CSV selesai dan file error XLSX notebook yang ada pada folder sumber dibaca. Pekerjaan GUI disimpan terpisah di `hasil/status_gui.sqlite3`, dengan ekspor `selesai_gui.csv`, `error_gui.csv`, `rekap_error_gui.xlsx`, `perlu_data_gui.csv`, dan `perlu_diperiksa_gui.csv`. Berkas sumber dan log notebook tidak diubah.
- Secara bawaan, status GUI `error`, `perlu_data`, `perlu_diperiksa`, atau `berjalan` tidak dicoba ulang. Centang **Masukkan kembali error dan baris perlu data** dan buat pratinjau baru untuk mengikutsertakan error GUI, baris perlu data, maupun error notebook yang memenuhi filter dan batas antrean; pilihan ini mengesampingkan **Lewati error notebook**. Status selesai, `perlu_diperiksa`, dan `berjalan` tetap dilewati sampai pengguna mengizinkan ulang ID tersebut. Gunakan **Izinkan ulang ID tertunda** untuk satu ID setelah status FASIH diperiksa. Untuk baris database dengan status `PERLU_DIPERIKSA` milik bot ini, tombol tersebut juga mengembalikan status pusat ke `SIAP_DIINPUT` secara bersyarat; buat pratinjau baru setelahnya. Log error notebook masih perlu disesuaikan secara terpisah.
- Kuesioner UB dapat memblokir Kirim ketika Kecamatan/Kelurahan atau rincian wajib lain kosong. Kuesioner Pengisian Mandiri menggunakan blok usaha yang berbeda, tetapi tujuh rincian keuangannya dapat diproses. Kode dan nama SLS yang kosong tetap perlu diisi dari data yang benar sebelum Kirim; aplikasi tidak mengisi fakta yang tidak ada di sumber.
- Periksa status, nilai, dan remark di FASIH sebelum mencoba error kembali: percobaan sebelumnya mungkin sudah melakukan sebagian perubahan. Jika proses ulang berhasil sampai submit dan approve terverifikasi, error tersebut hilang dari `error_gui.csv` dan `rekap_error_gui.xlsx` dan tercatat di `selesai_gui.csv`. Riwayat tetap ada di database GUI. File error notebook tetap tidak diubah; keberhasilan di jurnal GUI mencegah ID tersebut masuk antrean lagi.
- Jangan menjalankan notebook dan GUI secara bersamaan untuk wilayah yang sama. Antarmuka GUI memakai klaim atomik untuk GUI lain yang memakai jurnal yang sama, tetapi tidak dapat mengunci notebook lain. Jika menggunakan bagian atas dan bawah, file, filter, dan urutan harus sama dan tidak berubah sepanjang proses.
- Satu assignment yang muncul pada beberapa baris sumber dihentikan untuk penanganan gabungan manual; aplikasi tidak menandai sebagian usaha sebagai selesai.
- Jika satu assignment gagal, error dicatat dan proses berlanjut ke assignment berikutnya. Jika gagal setelah revoke atau sesudah submit, perubahan sebagian mungkin sudah tersimpan dan status assignment mungkin belum approved; periksa manual sebelum mengulangi. Gangguan pencatatan atau antrean dapat menghentikan keseluruhan proses. Menutup aplikasi menutup browser GUI; program tidak menutup tab di browser lain.

Uji aplikasi dengan satu assignment yang memang diperbolehkan dan diawasi terlebih dahulu. Uji otomatis hanya menggunakan data dan halaman tiruan lokal, bukan mengirim perubahan ke FASIH.
