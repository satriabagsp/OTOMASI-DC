"""Katalog rincian yang terlihat pada contoh SE2026-L; bukan skema lengkap FASIH.

Jenis: rupiah, angka, teks dapat diisi; catatan hanya mendukung remark;
informasi belum didukung untuk penulisan. Setiap assignment tetap diperiksa.
"""

P = 'SE2026 - P'
L = 'SE2026 - L BLOK II'
W = 'IDENTITAS WILAYAH'
J = 'KETERANGAN PEMBERI JAWABAN'
C = 'CATATAN'

RINCIAN = [
    (W,'prov','Provinsi','informasi'), (W,'kab','Kabupaten/Kota','informasi'),
    (W,'kec','Kecamatan','informasi'), (W,'desa','Desa/Kelurahan','informasi'),
    (W,'klas_desa','Klasifikasi desa/kelurahan','informasi'), (W,'kode_sls','Kode SLS/Non-SLS/Sub-SLS','informasi'),
    (W,'nama_sls','Nama SLS/Non-SLS','informasi'), (W,'kodepos','Kode pos','informasi'),
    (P,'jenis_prelist','Jenis Prelist','informasi'), (P,'is_new','Tambah keluarga/bangunan lainnya','catatan'),
    (P,'pilih_umkm','Daftar usaha non-prelist','catatan'), (P,'nama_usaha_bang','Nama bangunan/usaha/perusahaan','teks'),
    (P,'ada_bang_usaha','Keberadaan bangunan lainnya/usaha','catatan'), (P,'jalan_domisili','Nama jalan/gang/kompleks','teks'),
    (P,'nomor_domisili','Blok/nomor rumah','teks'), (P,'no_bangunan_terbesar','Nomor urut bangunan terbesar','informasi'),
    (P,'no_bang','Nomor urut bangunan','angka'), (P,'kode_bang','Kode penggunaan bangunan','catatan'),
    (P,'banr','Gunakan BANR','informasi'), (P,'geotag','Geotagging','catatan'),
    (P,'jumlah_usaha_ditemukan','Jumlah usaha ditemukan','informasi'),
    (L,'no_usaha','7. Nomor urut usaha','informasi'), (L,'keberadaan_usaha','Keberadaan usaha','informasi'),
    (L,'nama_komersial','8b. Nama komersial','teks'), (L,'alamat_usaha_view','8c. Alamat usaha','teks'),
    (L,'rt','RT','teks'), (L,'rw','RW','teks'), (L,'kode_pos','Kode pos','informasi'),
    (L,'kode_area','Kode area telepon','teks'), (L,'no_telp','Nomor telepon','teks'),
    (L,'eks','Ekstensi','teks'), (L,'email','Email','teks'), (L,'hp','Nomor HP/WhatsApp','teks'),
    (L,'website','Website','teks'), (L,'jenis_kawasan','8d. Jenis kawasan beroperasi','catatan'),
    (L,'punya_nib','10a. Memiliki NIB','catatan'), (L,'nib','10b. NIB','teks'),
    (L,'badan_usaha','11a. Status badan usaha','catatan'), (L,'lap_keuangan','11d. Laporan keuangan','catatan'),
    (L,'pengusaha','12a. Nama pengusaha/penanggung jawab','teks'), (L,'jk','12b. Jenis kelamin','catatan'),
    (L,'umur','12c. Umur','angka'), (L,'nik_pengusaha','12d. NIK pengusaha','teks'),
    (L,'keg_utama','13a. Kegiatan utama','teks'), (L,'produk_sendiri','13b1. Memproduksi barang','catatan'),
    (L,'layanan_mamin','13b2. Menyediakan layanan makan minum','catatan'), (L,'keg_penjualan','13b3. Penjualan barang','catatan'),
    (L,'lokasi_usaha','13c. Lokasi usaha','catatan'), (L,'produk','13f. Produk utama','teks'),
    (L,'kbli_genai','13g. Pilihan kode KBLI','catatan'), (L,'kbli','Pilih dari master KBLI','catatan'),
    (L,'kategori','13h. Kategori lapangan usaha','informasi'), (L,'jaringan','14a. Jaringan usaha','catatan'),
    (L,'internet','16a. Menggunakan internet','catatan'), (L,'internet_pesanan','16b1. Internet untuk pesanan','catatan'),
    (L,'internet_produksi','16b2. Internet untuk produksi','catatan'), (L,'internet_distribusi','16b3. Internet untuk distribusi','catatan'),
    (L,'internet_beli','16b4. Membeli bahan baku online','catatan'), (L,'internet_promosi','16b5. Internet untuk promosi','catatan'),
    (L,'internet_lainnya','16b6. Internet untuk lainnya','catatan'), (L,'digital','16c. Teknologi digital','catatan'),
    (L,'produksi_lingkungan','17a. Produksi ramah lingkungan','catatan'), (L,'perlindungan_lingkungan','17b. Perlindungan lingkungan','catatan'),
    (L,'produk_seni','18. Produk seni, teknologi, atau budaya','catatan'), (L,'halal','19a. Sertifikat halal','catatan'),
    (L,'belum_halal','19c. Varian belum bersertifikat halal','angka'), (L,'mitra_kdkmp','21. Mitra KDKMP','catatan'),
    (L,'peran_mbg','22. Keterlibatan MBG','catatan'), (L,'barang_non_pddk','23a. Barang dengan bukan penduduk','catatan'),
    (L,'jasa_non_pddk','23b. Penjualan jasa kepada bukan penduduk','catatan'), (L,'beli_jasa_non_pddk','23c. Pembelian jasa dari bukan penduduk','catatan'),
    (L,'tk_laki','24a1. Pekerja laki-laki','angka'), (L,'tk_pr','24b1. Pekerja perempuan','angka'),
    (L,'total_tk_jk','24c1. Total pekerja menurut jenis kelamin','catatan'), (L,'tk_dibayar','24a2. Pekerja dibayar','angka'),
    (L,'tk_tdk_dibayar','24b2. Pekerja tidak dibayar','angka'), (L,'total_tk_bayar','24c2. Total pekerja menurut pembayaran','catatan'),
    (L,'tahun_operasi','25. Tahun mulai beroperasi','catatan'),
    (L,'gaji','26a. Upah dan gaji','rupiah'), (L,'biaya_produksi','26b. Biaya produksi','rupiah'),
    (L,'biaya_pembelian','26c. Biaya pembelian','rupiah'), (L,'operasional','26d. Biaya operasional','rupiah'),
    (L,'non_operasional','26e. Biaya non-operasional','rupiah'), (L,'total_pengeluaran','26f. Total pengeluaran','catatan'),
    (L,'nilai_pendapatan','27a. Nilai penjualan barang dan jasa','rupiah'), (L,'pendapatan_lain','27b. Pendapatan lainnya','rupiah'),
    (L,'total_pendapatan','27c. Total nilai penjualan','catatan'), (L,'pendapatan_online','27d. Persentase pendapatan online','catatan'),
    (L,'aset_usaha_thn','28a. Aset tanah dan bangunan','rupiah'), (L,'aset_lain_thn','28b. Aset selain tanah dan bangunan','rupiah'),
    (L,'total_aset_thn','28c. Total aset','catatan'), (L,'luas_tanah_thn','28d. Luas tanah usaha','angka'),
    (L,'pribadi','29a. Kepemilikan pribadi','catatan'), (L,'non_profit','29b. Kepemilikan lembaga nonprofit','catatan'),
    (L,'publik','29c. Kepemilikan korporasi publik','catatan'), (L,'non_publik','29d. Kepemilikan korporasi nonpublik','catatan'),
    (L,'pemerintah','29e. Kepemilikan pemerintah','catatan'), (L,'asing','29f. Kepemilikan asing','catatan'),
    (L,'info_total','29g. Total kepemilikan','catatan'),
    (J,'nama_info_list','Nama pemberi informasi','catatan'), (J,'telp_info','Nomor HP/telepon pemberi informasi','teks'),
    (J,'email_info','Email pemberi informasi','teks'), (J,'persetujuan_responden','Persetujuan responden','informasi'),
    (C,'catatan','Catatan umum','teks'), (C,'catatan_anomali_admin','Penjelasan penyelesaian anomali oleh admin','teks'),
    (C,'anomali_admin','Anomali diselesaikan oleh admin','informasi'), (C,'cek_anomali_button','Tampilkan anomali usaha dan keluarga','informasi'),
]

KATALOG = {(blok, kode): (label, jenis) for blok, kode, label, jenis in RINCIAN}
