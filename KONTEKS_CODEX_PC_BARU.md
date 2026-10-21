# Serah-terima Codex — Otomasi DC USAHA

Dokumen ini merangkum percakapan dan kondisi proyek per 19 Oktober 2026. Kode dan log di PC baru bisa sudah berubah; baca file aktual sebelum mengambil kesimpulan. Dokumen ini sengaja tidak memuat kata sandi atau kredensial.

## Tujuan dan cara kerja

Pengguna adalah petugas BPS yang mengembangkan aplikasi desktop Python untuk membantu perbaikan data dan remark kuesioner di FASIH-SM. GUI mempunyai dua mode sumber: file XLSX/CSV lokal dan tabel pusat `OTOMASI_DC.data_split_usaha_20261016`. Keduanya memfilter kategori, kabupaten/kota, `Siap Input`, dan `Sudah Diinput`, lalu memakai antrean dan mesin FASIH yang sama. Pengguna login sendiri dengan akun yang memiliki akses wilayah terkait. Setelah pengguna menjalankan proses, aplikasi mengedit assignment sesuai pemetaan kolom sumber ke rincian FASIH, mengirim, dan melakukan approve.

Pemetaan rincian dan kolom nilai/remark dapat dipilih secara dinamis dan disimpan sebagai daftar perbaikan. Bawaan berisi tujuh rincian keuangan. Apabila nilai dan remark sama-sama dipetakan, `#0` dan `#DC_00` berarti hanya menambah remark tanpa mengubah nilai; remark lain memerlukan nilai perbaikan. Jika hanya remark dipetakan, nilai tidak diubah. Nilai rupiah desimal hanya dibulatkan jika opsi pengguna diaktifkan. Jangan mengasumsikan bahwa semua rincian atau KBLI sudah didukung; lihat `README.md` dan kode aktual.

Mulai 21 Oktober 2026, `#0` juga diperlakukan sebagai remark tanpa perubahan nilai. Jika seluruh tindakan pada satu baris hanya berisi `#0`/`#DC_00` dan assignment masih approved, `fasih.py` memvalidasi tombol catatan dari halaman review, melakukan revoke, mengisi catatan dari halaman review, lalu approve kembali. Cabang ini tidak menekan Edit atau Kirim. Jika tombol Revoke tidak tersedia, alur lama tetap dipakai karena status review belum memenuhi cabang tersebut.

Pratinjau tidak menulis ke FASIH. Proses nyata bisa revoke, mengubah nilai, menambahkan remark, memperbaiki GALAT tertentu, mengirim, dan approve. Kesalahan dapat terjadi setelah sebagian tindakan sudah berhasil: periksa assignment secara langsung sebelum mencoba ulang. Status berhasil GUI dicatat setelah tahapan submit dan approve terverifikasi; jangan menyamakan catatan tersimpan atau submit dengan approve.

## File penting

Semua path di bawah relatif terhadap folder aplikasi ini:

- `app.py`: GUI, pratinjau, pemilihan dan jalannya proses.
- `core.py`: pembacaan, validasi dan antrean sumber serta jurnal SQLite.
- `fasih.py`: interaksi Playwright dan alur FASIH.
- `katalog_rincian.py`: daftar label, blok, kode dan jenis rincian yang diketahui.
- `daftar_perbaikan.py` dan `daftar_perbaikan.json` (jika ada): pengelolaan pilihan pemetaan yang disimpan pengguna.
- `hasil/status_gui.sqlite3`: sumber status dan riwayat GUI; file CSV/XLSX di `hasil/` adalah ekspor untuk dibaca, bukan pengganti database.
- `requirements.txt`, `Mulai GUI.bat`, dan `test_*.py`: dependensi, peluncur Windows, dan tes lokal.
- `pusat.py` dan `config_pusat.json`: koneksi tabel log dan tabel sumber pusat. Konfigurasi lokal memuat `source_table`; bawaan tetap `data_split_usaha_20261016` bila properti lama belum memilikinya.
- `MODEL/`: proyek lain yang berada di bawah folder ini; punya petunjuk dan konteks sendiri.

Log notebook lama berada di folder yang sama dengan file sumber yang dipilih, bukan di `hasil/`. Misalnya, `G.xlsx` dan `G_3201_selesai_atas.csv` berada di `../DATA/` pada PC asal. GUI membaca log notebook yang namanya sesuai kategori dan wilayah. Jika file itu tidak dipindahkan bersama sumber, GUI bisa tidak mengetahui assignment yang sebelumnya diproses lewat notebook.

## Menyiapkan PC baru dengan aman

1. Hentikan proses GUI/notebook dan tutup browser profil otomasi di PC lama. Tunggu aplikasi benar-benar berhenti sebelum menyalin database/log, agar salinannya konsisten. Simpan cadangan asli di lokasi yang aman sesuai kebijakan BPS.
2. Pindahkan seluruh folder aplikasi, termasuk `hasil/status_gui.sqlite3` dan `daftar_perbaikan.json` bila ada. Pindahkan juga file sumber dan log notebook terkait ke folder yang sama satu sama lain. Struktur yang disarankan: `USAHA/OTOMASI DC/` untuk folder aplikasi dan `USAHA/DATA/` untuk sumber beserta log notebook. Sumber nantinya tetap harus dipilih kembali di GUI.
3. Data sumber, log, dan database berisi data survei atau informasi operasional: batasi akses sesuai ketentuan BPS. `__pycache__/` tidak diperlukan. Profil browser dapat berisi sesi, cookie, dan informasi rahasia; tidak dianjurkan menyalinnya. Login ulang secara manual di PC baru. Jika organisasi memang mengharuskan migrasi profil, gunakan cara transfer yang disetujui dan jangan menganggap sesi akan tetap berlaku di PC lain.
4. `app.py` saat ini menggunakan profil di `../fasih_profile_r1_copy`, yaitu folder saudara aplikasi, **bukan** `profil_browser/` di dalam folder aplikasi. Pada PC baru, biarkan Playwright membuat profil baru di lokasi itu lalu login manual. Jangan mengakses profil yang sama bersamaan dari notebook atau browser lain. Jangan menjanjikan bahwa profil, user-agent, atau opsi browser akan selalu mencegah pemeriksaan bot.
5. Pasang Python untuk Windows dengan Tkinter; Python 3.12 digunakan pada PC asal. Di PowerShell, dari folder aplikasi, contoh memakai virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m playwright install chromium
   .\.venv\Scripts\python.exe -m unittest
   .\.venv\Scripts\python.exe app.py
   ```

   Jika Python 3.12 tidak tersedia, sesuaikan perintah setelah memeriksa versi yang dipasang. Dependensi di `requirements.txt` tidak dipatok ke versi tepat, sehingga uji kembali setelah instalasi. `Mulai GUI.bat` memakai `python` dari PATH, bukan otomatis Python di `.venv`; gunakan perintah di atas jika ingin memastikan environment yang benar. Tes otomatis memakai halaman/data tiruan dan tidak membuktikan layanan FASIH langsung berfungsi.
6. Pilih lagi file dan sheet, periksa kategori/wilayah dan pemetaan, lalu buat pratinjau. Uji awal dengan batas satu baris yang memang diizinkan, setelah login dan status akun diperiksa. Jangan langsung mengulang error sebelum memeriksa kondisi FASIH.

Untuk mode file, jangan jalankan dua salinan pada PC berbeda untuk wilayah yang sama secara bersamaan: masing-masing database lokal tidak saling mengunci. Mode database mengunci setiap baris pusat secara bersyarat memakai `id`, `automation_status`, dan `automation_bot_id` sebelum membuka FASIH. Database GUI tetap tidak dapat mengunci proses notebook.

## Mode database pusat

Mode ini mengambil batch kecil, bukan seluruh tabel. Baris kandidat harus memiliki `Siap Input = 1`, `Sudah Diinput` belum 1, serta kategori dan wilayah yang dipilih. Sebelum proses, baris dikunci menjadi `automation_status = BERJALAN`. Keberhasilan yang sudah mencapai submit dan approve terverifikasi mengubah `automation_status = BERHASIL` dan `Sudah Diinput = 1`. Kegagalan memakai `ERROR`, `PERLU_DATA`, atau `PERLU_DIPERIKSA` dan tidak menandai `Sudah Diinput`.

Pembaruan selalu memakai `id` sumber. Satu `assignment_id` yang muncul pada beberapa baris siap input ditolak karena memerlukan penanganan gabungan. Mode file lama tetap tidak mengubah XLSX/CSV. Per 20 Oktober 2026, pembacaan nyata ke tabel pusat berhasil dan pratinjau satu baris siap input berhasil dibuat tanpa menulis data; perubahan status pusat diuji dengan respons tiruan saja agar pengujian tidak menyentuh assignment nyata.

Folder `SIAP INPUT UB` dapat dimasukkan secara terpisah memakai `import_siap_input_ub.py`. Bawaan skrip adalah dry-run; penulisan memerlukan `--execute`, menggunakan insert `append` untuk baris baru, dan memperbarui baris lama hanya bila statusnya masih aman. Gunakan `--round-values` jika pembulatan pecahan rupiah memang disetujui. Setiap percobaan membuat laporan lokal baru di `hasil/`, sedangkan eksekusi memverifikasi kembali bahwa baris tersimpan berstatus `SIAP_DIINPUT`. File Excel sumber tidak diubah.

## Log, status, dan kondisi yang pernah ditemukan

Jurnal GUI menggunakan status seperti `berhasil`, `error`, `perlu_data`, dan `berjalan`. Secara bawaan, baris yang sudah tercatat selesai, error, perlu data, atau masih berjalan tidak otomatis diproses ulang. GUI menyediakan pilihan memasukkan kembali error dan baris perlu data serta tombol untuk mengizinkan ulang ID tertunda. Gunakan hanya setelah memeriksa kemungkinan perubahan sebagian; detail filter ada di `README.md`. Mengekspor atau mengedit CSV saja tidak memperbarui database SQLite.

Kuesioner L, UB, dan Pengisian Mandiri pernah diuji untuk rincian keuangan, tetapi dukungan ini tidak berarti semua jenis blok/rincian sudah didukung. Usaha tahun operasi 2026 membutuhkan penanganan bulanan yang belum tersedia. Jika ada pertanyaan wajib yang jawabannya tidak ada di sumber, GUI mencatat `perlu_data`; jangan mengarang jawabannya. Beberapa kasus lama wilayah 3201 membutuhkan kecamatan/kelurahan, status halal, persentase pendapatan online, atau kode/nama SLS. Periksa status terkini di `hasil/` dan FASIH sebelum bertindak.

GUI pernah diperbaiki untuk masalah navigasi pertama, sakelar anomali wajib, dan GALAT akhiran nama CV yang spesifik; aturan GALAT lain belum tentu dapat diselesaikan otomatis. Per 21 Oktober 2026, 41 tes lokal lulus dan satu kasus CV dari pengujian sebelumnya berhasil submit serta approve. Ini bukan jaminan terhadap perubahan halaman FASIH.

### Masalah terakhir yang belum terselesaikan

Pengguna melaporkan assignment `198b76af-8159-46c0-a3e2-e4de682cfb94` mengalami timeout menunggu tombol approve/revoke setelah log `Sakelar anomali diaktifkan; periksa ulang GALAT.` Penelusuran kode menunjukkan pemanggil mencapai tahap menunggu tombol review setelah alur Kirim berhasil melewati dialog sukses dan `Kembali ke Review`; namun penyebab tombol tidak terlihat dan status nyata assignment belum diverifikasi. Pengguna melihat kuesioner masih terbuka, yang bisa juga terjadi di halaman review. **Jangan langsung mengulang atau mengubah status:** periksa URL, tampilan, status submit/approve, dan perubahan yang sudah tersimpan pada assignment terkait. Setelah ada bukti, diagnosis dan perbaiki jika diminta.

## Preferensi pengguna

Jawab dalam bahasa Indonesia dengan penjelasan langsung dan praktis. Jika diminta contoh notebook, berikan kelompok tahapan per sel, komentar singkat, dan jangan membuat fungsi tambahan bila pengguna meminta satu alur. Untuk perubahan GUI, pertahankan daftar perbaikan bawaan dan pilihan tersimpan. Saat diminta hanya menjelaskan atau memeriksa, jangan diam-diam memodifikasi file atau FASIH. Jangan mencantumkan kredensial dalam dokumentasi.
