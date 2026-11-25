# JARVIS — prinsip desain

> **Status dokumen ini.** Ini spesifikasi, bukan catatan. Kalau dokumen di
> `docs/design/` dan implementasi berbeda, **dokumen desain yang
> menang** (keputusan pemilik, 2026-11-23). Gambar proposal
> (`design/new-ui-proposal/`) tetap berguna sebagai referensi visual — warna,
> nuansa, proporsi — tetapi tidak lagi menjadi sumber kebenaran untuk ukuran
> teks, jarak, atau susunan.

---

## Kenapa dokumen ini ada

Tiga putaran dikerjakan dengan satu kriteria: "samakan dengan artboard". Hasilnya
tetap terasa salah, dan pengukuran menunjukkan mengapa:

| Yang diukur | Angka | Akibatnya |
|---|---|---|
| Ukuran teks di 22 artboard | **15 ukuran berbeda** untuk ~5 peran | Teks goyah: 10 / 10.5 / 11 / 11.5 px dipakai bergantian untuk hal yang sama |
| Posisi absolut di `ui/` | **102** `setGeometry` manual | Tidak ada layout; satu angka meleset = tumpang tindih |
| `QScrollArea` | **0 modul** | Halaman mati begitu data melebihi yang muat |
| Pitch vertikal | **15 nilai berbeda** (26, 28, 30, 32, 46, 48, 56, 66, 68, 70, 72, 74, 76, 92, 96) | Setiap daftar punya iramanya sendiri |
| Panjang panel (artboard) | **640** (bNN) vs **660** (nNN) | Dua artboard mendefinisikan tinggi panel yang berbeda |

Tidak satu pun dari ini adalah kesalahan penyalinan. Masalahnya: **tidak pernah
ada aturan di balik angkanya.** Menyalin artboard lebih teliti hanya membuat
kita sampai di akhir yang sama lebih lambat.

---

## Lima aturan

Aturan-aturan ini dipakai untuk **memutus sengketa**, bukan untuk dekorasi.
Kalau sebuah keputusan desain bertentangan dengan salah satunya, keputusan itu
yang salah — bukan aturannya.

### 1. Satu panel, satu kolom, satu tugas

460 px bukan batas yang perlu dilawan; itu bentuk produknya. Panel baki adalah
jendela yang muncul dari taskbar dan harus bisa dibaca tanpa menggeser apa pun.

Konsekuensinya: **tidak ada halaman yang punya dua tujuan.** Kalau sebuah
halaman butuh "dan juga", itu halaman lain.

### 2. Semua yang tumbuh bisa digulir

Daftar memori, daftar plugin, riwayat tugas, log aktivitas — isinya berapa pun,
kerangkanya tetap. Yang bisa berubah panjang **selalu** berada di dalam satu
wadah gulir; kepala dan aksi bawah tidak ikut bergulir.

Ini aturan yang paling banyak dilanggar build sekarang: 6 kartu memori dan 3
baris plugin ditulis sebagai angka mati.

### 3. Kejujuran mengalahkan kelengkapan

Kalau build ini tidak bisa melakukan sesuatu yang digambar, **slotnya tetap
digambar** dan menuliskan bahwa ia tidak tersedia. Tidak dihapus (menyembunyikan
kekurangan), tidak dikarang (berbohong). Ini aturan lama yang tetap berlaku dan
tidak boleh dilunakkan oleh dokumen ini.

### 4. Tidak ada teks di bawah 12 px, kecuali satu peran

Satu-satunya pengecualian adalah **label bagian**: huruf kapital, tracking lebar,
11 px. Itu bukan teks yang dibaca berurutan — itu penanda letak.

Alasannya bukan selera. 10 px pada 100% scaling masih terbaca; pada layar
1366×768 dengan scaling Windows 125% ia menjadi ~7.5 px efektif. Panel ini
dibuka untuk dibaca sekilas, bukan dipelajari.

### 5. Warna menandakan status

Sian = aksi atau keadaan aktif. Amber = risiko. Abu = tidak ada atau tidak
tersedia. Nol dekorasi: tidak ada warna yang dipakai hanya karena enak dilihat.

Paletnya sendiri **sudah benar dan tidak diubah** — semua pasangan lolos 4.5:1
(lihat `01-tokens.md`).

---

## Yang secara eksplisit tidak kita lakukan

- **Menyalin koordinat artboard sebagai sumber kebenaran.** Artboard menjadi
  referensi visual; susunan dan ukuran datang dari token.
- **Menambah halaman.** 13 halaman dipertahankan (keputusan pemilik,
  2026-11-23). Beban perawatan dikurangi lewat token dan komponen bersama,
  bukan dengan menggabung halaman.
- **Membuat mesin otomasi baru** untuk mengisi formulir. (Keputusan lama,
  `skip_13`, tetap berlaku.)
- **Menghidupkan kembali mode tamu** (06a). Sudah dihapus lewat keputusan
  pemilik; tidak boleh muncul lagi.
