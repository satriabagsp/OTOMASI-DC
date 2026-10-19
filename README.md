# Otomasi DC USAHA — GUI lokal

Aplikasi ini terpisah dari `USAHA 1.ipynb`. File sumber dipilih dari komputer (XLSX atau CSV); aplikasi tidak mengunggahnya ke server lain dan tidak mengubah file sumber. Otomasi FASIH menggunakan profil browser notebook dan login manual. Bawaan aplikasi adalah tujuh rincian keuangan USAHA seperti sebelumnya.

## Menjalankan

Di terminal, dari folder ini:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Setelah dependensi terpasang, pengguna Windows juga dapat menjalankan aplikasi dengan membuka `Mulai GUI.bat`.

1. Pilih file dan sheet. Header harus memiliki `kategori`, `level_2_full_code`, `nama_usaha`, `link_fasih_sm`, `Siap Input`, dan `Sudah Diinput`.
2. Masukkan kategori dan kode kabupaten/kota sesuai akun. Tentukan bagian antrean dan pilih rincian beserta kolom nilai dan/atau remark. Kolom standar G dipilih otomatis jika tersedia. Untuk menambah, pilih **Tambah rincian**, pilih label dan kode, tentukan kolomnya lalu centang **Pakai**. Tanda × menghapus satu baris pemetaan.
3. Klik **Pratinjau antrean**, periksa nama, ID, remark dan nilai. Batasi 1 baris untuk uji pertama.
4. Klik **Buka browser & login** dan periksa bahwa akun yang aktif sesuai wilayah. GUI memakai `../fasih_profile_r1_copy`, user-agent dan argumen yang sama dengan notebook. Profil mengandung sesi rahasia. Profil tidak bisa dipakai oleh dua browser bersamaan: tutup browser notebook sebelum membuka browser GUI. Pengaturan ini tidak menjamin situs tidak menampilkan pemeriksaan bot.
5. Setelah login, klik **Jalankan yang dipratinjau**, baca konfirmasi dan setujui jika sesuai. Tombol berhenti menunggu assignment saat ini selesai.

### Menyimpan daftar perbaikan

- Setelah memilih rincian dan kolom, klik **Simpan daftar**, berikan nama, lalu konfirmasi jika ingin mengganti daftar dengan nama sama.
- Daftar yang terakhir disimpan atau dipilih dimuat ketika aplikasi dibuka lagi. Pilih kembali file sumber; nama kolom tersimpan tetap dipakai dan akan diperiksa pada pratinjau. Jika nama kolom sumber berbeda, sesuaikan pemetaannya.
- Tombol **Bawaan** mengembalikan tujuh rincian keuangan standar. Daftar tersimpan tetap tersedia di pilihan daftar. Pengaturan disimpan di `daftar_perbaikan.json`; file ini berisi nama daftar dan kolom, bukan data sumber atau kredensial.
- Katalog label, blok, kode, dan batas dukungan disimpan di `katalog_rincian.py`. Katalog berdasarkan satu contoh SE2026-L dan bukan daftar lengkap semua kondisi atau kuesioner.

## Perilaku dan batasan penting

- Pratinjau tidak membuka assignment, tidak revoke, dan tidak mengubah data. Menjalankan proses dapat revoke, mengisi nilai/remark, mengaktifkan sakelar anomali yang spesifik, mengirim, dan approve.
- Nama usaha dicocokkan. Tahun operasi dibaca sebelum revoke: tahun 2026 atau tahun tidak valid dicatat sebagai error, karena rincian bulanan dan periode nilainya belum ditangani.
- Pemetaan dapat memakai kolom nilai saja, remark saja, atau keduanya. Jika keduanya dipilih, `#DC_00` hanya menambah remark; remark lain mengharuskan nilai. Jika hanya kolom remark dipilih, tidak ada nilai yang diubah. Sebagian angka sumber mengandung desimal meskipun tampilan Excel bulat. Jika pengguna menyetujuinya, centang **Bulatkan nilai desimal**: dibulatkan ke rupiah terdekat, 0,5 naik. Pratinjau menampilkan nilai yang akan dikirim dan nilai sumber jika berbeda. Jika tidak dicentang, angka pecahan ditolak, tanpa pembulatan otomatis. Angka harus tanpa pemisah ribuan; format ambigu ditolak. Nilai setelah diisi diperiksa ulang. Input kosong atau rincian yang tidak unik menghentikan assignment.
- Rincian katalog bertipe `teks`, `angka` dan `rupiah` dapat dipilih untuk perubahan nilai; tipe `catatan` hanya bisa diberi remark, dan `informasi` belum dapat diproses. Pilihan radio, KBLI, persentase dan hasil hitung belum didukung untuk perubahan nilai. Kehadiran dan kemampuan edit target tetap diperiksa pada setiap assignment. Rincian keuangan di blok usaha kuesioner L, UB, dan Pengisian Mandiri menggunakan kode yang sama; blok lain untuk UB/Mandiri belum didukung. Tahun operasi 2026 tetap dilewati.
- KBLI belum didukung. Jika `KBLI (menjadi)` berisi nilai, proses berhenti untuk pemeriksaan manual. Jangan gunakan aplikasi ini untuk memilih atau mengubah KBLI.
- Jika ada tepat satu GALAT `Tampilkan Anomali Usaha dan Keluarga — Wajib diisi`, aplikasi mencoba mengaktifkan sakelar dan memeriksa ulang. GALAT CV pada `Perubahan Nama usaha/perusahaan` dapat memperbaiki akhiran nama menjadi `,CV` hanya ketika nama di isian masih sesuai sumber. GALAT lain menghentikan assignment tersebut. Jika FASIH menampilkan `Masih Ada yang Belum Dijawab`, aplikasi mencatat pertanyaan wajib yang tersisa sebagai `perlu_data` dan tidak mengirim assignment.
- Log CSV selesai dan file error XLSX notebook yang ada pada folder sumber dibaca. Pekerjaan GUI disimpan terpisah di `hasil/status_gui.sqlite3`, dengan ekspor `selesai_gui.csv`, `error_gui.csv`, `rekap_error_gui.xlsx`, `perlu_data_gui.csv`, dan `perlu_diperiksa_gui.csv`. Berkas sumber dan log notebook tidak diubah.
- Secara bawaan, status GUI `error`, `perlu_data`, atau `berjalan` tidak dicoba ulang. Centang **Masukkan kembali error dan baris perlu data** dan buat pratinjau baru untuk mengikutsertakan error GUI, baris perlu data, maupun error notebook yang memenuhi filter dan batas antrean; pilihan ini mengesampingkan **Lewati error notebook**. Status selesai dan `berjalan` tetap dilewati. Alternatifnya, gunakan **Izinkan ulang ID tertunda** untuk satu ID setelah diperiksa; log error notebook masih perlu disesuaikan secara terpisah.
- Kuesioner UB dapat memblokir Kirim ketika Kecamatan/Kelurahan atau rincian wajib lain kosong. Kuesioner Pengisian Mandiri menggunakan blok usaha yang berbeda, tetapi tujuh rincian keuangannya dapat diproses. Kode dan nama SLS yang kosong tetap perlu diisi dari data yang benar sebelum Kirim; aplikasi tidak mengisi fakta yang tidak ada di sumber.
- Periksa status, nilai, dan remark di FASIH sebelum mencoba error kembali: percobaan sebelumnya mungkin sudah melakukan sebagian perubahan. Jika proses ulang berhasil sampai submit dan approve terverifikasi, error tersebut hilang dari `error_gui.csv` dan `rekap_error_gui.xlsx` dan tercatat di `selesai_gui.csv`. Riwayat tetap ada di database GUI. File error notebook tetap tidak diubah; keberhasilan di jurnal GUI mencegah ID tersebut masuk antrean lagi.
- Jangan menjalankan notebook dan GUI secara bersamaan untuk wilayah yang sama. Antarmuka GUI memakai klaim atomik untuk GUI lain yang memakai jurnal yang sama, tetapi tidak dapat mengunci notebook lain. Jika menggunakan bagian atas dan bawah, file, filter, dan urutan harus sama dan tidak berubah sepanjang proses.
- Satu assignment yang muncul pada beberapa baris sumber dihentikan untuk penanganan gabungan manual; aplikasi tidak menandai sebagian usaha sebagai selesai.
- Jika satu assignment gagal, error dicatat dan proses berlanjut ke assignment berikutnya. Jika gagal setelah revoke atau sesudah submit, perubahan sebagian mungkin sudah tersimpan dan status assignment mungkin belum approved; periksa manual sebelum mengulangi. Gangguan pencatatan atau antrean dapat menghentikan keseluruhan proses. Menutup aplikasi menutup browser GUI; program tidak menutup tab di browser lain.

Uji aplikasi dengan satu assignment yang memang diperbolehkan dan diawasi terlebih dahulu. Uji otomatis hanya menggunakan data dan halaman tiruan lokal, bukan mengirim perubahan ke FASIH.
