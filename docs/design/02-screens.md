# JARVIS — 13 layar

> Satu tabel per halaman. Kolom **Susunan** adalah yang mengikat; koordinat
> adalah konsekuensinya, dihitung dari token, bukan ditulis.
>
> **13 halaman dipertahankan** (keputusan pemilik, 2026-11-23). Yang berubah
> adalah cara mereka disusun: kepala tetap, isi bisa digulir, aksi bawah tetap.

---

## Kerangka bersama

Setiap halaman adalah tiga baris:

```
┌──────────────────────────────────────┐
│  KEPALA — tetap, 96 px               │  orb · judul halaman · subjudul
├──────────────────────────────────────┤
│                                      │
│  ISI — digulir                       │  kartu, baris, segmen
│                                      │
├──────────────────────────────────────┤
│  AKSI — tetap (kalau ada)            │  satu atau dua pil
└──────────────────────────────────────┘
```

| Bagian | Tinggi | Isi |
|---|---|---|
| Kepala | **88 px** | Orb 26 px di (24, 40); judul baseline 36 di x=62; subjudul baseline 54 di x=62 |
| Isi | sisa, **digulir** | Mulai y=88, 24 px dari kiri, 412 px lebar |
| Aksi | 72 px | Pil, rata bawah, `S5` dari tepi |

**Kenapa kepala 88, bukan 96.** Subjudul duduk di baseline 54 dengan tinggi
baris `round(10.5 × 1.45) = 15` px di atas baseline, jadi kotaknya berakhir di
`54 + 15 = 69`. Label bagian pertama butuh `S5` (24) ruang di atasnya:
`69 + 24 = 93` — tetapi kotak teks label sendiri mulai 13 px di atas
baseline-nya, jadi yang benar-benar perlu dikosongkan adalah
`69 + 24 − 13 = 80`, dan 88 memberi 8 px margin. Angka 96 menyisakan 16 px —
cukup untuk terlihat sebagai kesalahan, tidak cukup untuk apa pun.

**Hasilnya, ruang isi:**

```
660 − 88 (kepala) − 72 (aksi) = 500 px
```

500 px adalah anggaran vertikal setiap halaman. Dengan pitch 76 itu **6 baris
penuh atau 6 kartu**; dengan pitch 93, **5**. Ini yang membuat aturan 2
("semua yang tumbuh bisa digulir") bukan teori: daftar panjang **harus**
menggulir, karena tidak mungkin muat.

**Kepala memuat judul halaman itu, bukan "JARVIS".** Artboard `build.py`
menggambar kata "JARVIS" di setiap kepala karena `panel_head()` mengabaikan
argumen judulnya — itu bug di artboard, bukan keputusan desain. `n10()` (artboard
panel 460×660) menggambar "Riwayat tugas" di posisi yang sama, dan **itu yang
benar**.

**Subjudul adalah kalimat artboard, diformat dari data nyata saat digambar.**
Kalau artboard menulis "12 hal yang JARVIS ingat", panel menulis
"0 yang diingat JARVIS" ketika store kosong. Angka 12 di artboard adalah contoh,
bukan nilai.

---

## 01 · Memori

| | |
|---|---|
| **Tugas** | Melihat, menambah, dan menghapus fakta yang JARVIS ingat |
| **Kepala** | Judul: `Memori personal` · Sub: `{n} yang diingat JARVIS` |
| **Susunan** | label `FAKTA TENTANG ANDA` → daftar kartu (gulir) → aksi bawah |
| **Kartu** | Judul = kunci (16 px, `MUTED`), isi = nilai (16 px, `TEXT`), tombol hapus `×` kanan |
| **Pitch** | 76 px (kartu 64 + `S3` 12) |
| **Aksi bawah** | `Tambah memori` (sekunder) · `Hapus semua` (sekunder) |
| **Kosong** | Satu kartu berisi: "Belum ada yang diingat — sebutkan satu fakta, dan ia muncul di sini." |
| **Absen** | — |
| **Digulir** | Ya. Daftar bisa sepanjang apa pun |

> Angka "12" di artboard adalah contoh isi. Yang benar adalah `count` dari store.

## 02 · Detail memori

| | |
|---|---|
| **Tugas** | Satu fakta, dengan konteksnya |
| **Kepala** | Judul: `Detail memori` · Sub: fakta itu sendiri (dipotong) |
| **Susunan** | kartu besar (kunci + nilai) → meta (kapan diingat, dari mana) → aksi |
| **Aksi bawah** | `Ubah` · `Hapus` |
| **Kosong** | Tidak tercapai — halaman ini hanya dibuka dari sebuah kartu |
| **Absen** | Kalau fakta tidak punya sumber, baris "dari mana" **tidak digambar**. Bukan diisi "—" |

## 03 · Rutinitas

| | |
|---|---|
| **Tugas** | Apa yang JARVIS lakukan sendiri, dan kapan |
| **Kepala** | Judul: `Rutinitas` · Sub: `{n} rutinitas aktif` |
| **Susunan** | label `AKTIF` → daftar kartu (gulir) → label `NONAKTIF` → daftar → aksi |
| **Kartu** | Nama (16 px) · jadwal (12 px `MUTED`) · saklar 40×22 di kanan |
| **Pitch** | 76 px |
| **Kosong** | "Belum ada rutinitas. JARVIS tidak melakukan apa pun tanpa Anda minta." |
| **Absen** | **Kalimat "penjadwalan belum ada di build ini"** di tempat daftar akan berada |

> Board 11 punya 4 dari 6 klaim yang bisa dipenuhi. Dua sisanya (membuat
> rutinitas baru, mengubah jadwal) tidak punya backend — halaman ini tetap
> menggambar barisnya dan menuliskan bahwa ia belum ada.

## 04 · Tools & Actions

| | |
|---|---|
| **Tugas** | Apa yang JARVIS bisa lakukan sekarang |
| **Kepala** | Judul: `Tools` · Sub: `{n} alat tersedia` |
| **Susunan** | label `AKSI CEPAT` → kisi 2×N kartu 196 px → label `LAINNYA` → daftar baris |
| **Kartu aksi** | Kotak ikon 32×32 (glyph 1 huruf) · nama (13 px) · pintasan (12 px `MUTED`) |
| **Pitch kisi** | kartu 64, jarak 12 vertikal / 16 horizontal |
| **Kosong** | Tidak mungkin — selalu ada minimal satu alat |
| **Absen** | **`Susun jendela`** digambar, dengan keterangan "belum ada di build ini" |

## 05 · Keamanan

| | |
|---|---|
| **Tugas** | Tiga tingkat risiko, dan apa yang ada di masing-masing |
| **Kepala** | Judul: `Keamanan` · Sub: `Tiga tingkat risiko` |
| **Susunan** | label `TINGKAT` → tiga kartu 412×104 → label `SISTEM` → kartu status → aksi |
| **Kartu tingkat** | Nama (16 px) · keterangan (12 px `MUTED`) · jumlah `{n}` rata kanan (16 px `CYAN`) |
| **Tinggi tetap 104** | Ketiga kartu sama tinggi karena isinya sama bentuknya |
| **Kosong** | Jumlah `0` **tetap ditampilkan**. Nol adalah fakta; baris kosong adalah pertanyaan |
| **Absen** | **Kartu "status OS"** — tidak ada API-nya. Digambar, berisi satu kalimat |

> `ALLOWED_GAPS` mencatat security (378, 216) sebagai slot yang tidak bisa diisi.
> Slot itu tetap digambar.

## 06 · Aksesibilitas

| | |
|---|---|
| **Tugas** | Bahasa, ukuran baca, gerak, gestur |
| **Kepala** | Judul: `Aksesibilitas` · Sub: `Bahasa & gestur` |
| **Susunan** | label `BAHASA UI` → segmen 3 slot (Indonesia · English · Campur) → label `UKURAN TEKS` → slider + keterangan → label `KONTRAS` → segmen → label `GERAK` → kartu + saklar → label `GESTUR` → tiga baris → catatan kaki |
| **Segmen bahasa** | **Urutan dari desain: id, en, campur.** Bukan urutan `i18n.available()` |
| **Slot Campur** | Digambar, nonaktif, berisi "Campur" dengan keterangan "tidak tersedia" |
| **Kartu gerak** | Nama (13 px) · keterangan (12 px) · saklar 40×22, **tanpa teks di dalam saklar** |
| **Baris gestur** | Nama (13 px) · aksi (13 px `CYAN`) · keadaan (12 px `MUTED`, rata kanan) |
| **Kontras** | Hanya satu tingkat. Segmen dua slot digambar, slot "Tinggi" menuliskan ketiadaannya |
| **Kosong** | Tidak berlaku |
| **Catatan kaki** | "Target sentuh minimal 44 px · kontras teks ≥ 4.5:1" |

## 07 · Plugin

| | |
|---|---|
| **Tugas** | Apa yang terpasang, versinya, dan apakah ia menyala |
| **Kepala** | Judul: `Plugin` · Sub: `{on} dari {total} plugin aktif` |
| **Susunan** | label `PLUGIN` → daftar kartu (gulir) → label `SINKRON PONSEL` → kartu → label `KODE PASANGAN` → kotak |
| **Kartu plugin** | Nama (16 px) · `{versi} · {tingkat}` (12 px `MUTED`) · saklar kanan |
| **Baris kedua** | `1.0.0 · berisiko` — versi dan **`level` dari manifest**, bukan "resmi/pihak ketiga" |
| **Pitch** | 76 px |
| **Digulir** | **Ya.** 15 plugin sekarang; dulu hanya 3 yang digambar dan sisanya dihitung |
| **Sinkron ponsel** | Digambar, satu kalimat: "Tidak ada sinkron ponsel di build ini." |
| **Kode pasangan** | Digambar, satu kalimat: "Tidak ada kode — tidak ada perangkat yang bisa dipasangkan." |
| **Kosong** | "Belum ada plugin terpasang." |

> **Yang dihapus:** `resmi` / `pihak ketiga`. Itu karangan — kelima belas manifest
> berauthor `MARK-LVI` dan semuanya mendeklarasikan izin, jadi aturan lama
> menulis "pihak ketiga" di setiap baris. `level` (safe/medium/risky) adalah
> yang benar-benar ada di manifest dan yang dipakai loader.

## 08 · Tema terang

| | |
|---|---|
| **Tugas** | Bukan halaman — ini **varian palet** dari seluruh panel |
| **Susunan** | Sama persis dengan halaman lain, palet `light` |
| **Catatan** | Di artboard, board 18 adalah board 6 (izin) dalam tema terang. Sebagai *halaman* ia tidak punya tugas sendiri |

> **Rekomendasi:** jadikan tema properti panel (`PALETTES[theme]`), bukan halaman.
> Kalau tetap halaman, ia harus punya tugas yang bisa ditulis dalam satu kalimat —
> dan "menampilkan hal yang sama tetapi terang" bukan tugas.

## 09 · Gestur

| | |
|---|---|
| **Tugas** | Gerakan tangan yang dikenali, dan artinya |
| **Kepala** | Judul: `Gestur` · Sub: `{n} gestur dikenali` |
| **Susunan** | daftar baris gestur (gulir) → catatan kaki |
| **Baris** | Nama (13 px) · arti (13 px `CYAN`) · keadaan (12 px `MUTED`, rata kanan) |
| **Pitch** | 48 px (baris 36 + `S3` 12) |
| **Kosong** | Tidak berlaku — gestur adalah tabel tetap |
| **Absen** | **"Mengubah gestur belum ada"** di kolom keadaan — menggantikan "ubah" |

## 10 · Brand

| | |
|---|---|
| **Tugas** | Palet dan keadaan orb — halaman referensi visual |
| **Kepala** | Judul: `Brand` · Sub: `Palet & keadaan orb` |
| **Susunan** | label `PALET` → kisi swatch → label `ORB` → baris keadaan |
| **Swatch** | Kotak 64×64 radius 10 · nama token (12 px) · nilai hex (12 px `MUTED`) |
| **Absen** | — |

> Halaman ini satu-satunya yang mengizinkan warna ditampilkan tanpa arti.
> Alasannya: tugasnya memang memamerkan warna. Ia tidak boleh memakai token
> aksi.

## 11 · Penyiap (installer)

| | |
|---|---|
| **Tugas** | Memilih bagaimana JARVIS hadir, sekali, di awal |
| **Kepala** | Judul: `Pilih cara JARVIS hadir` (26 px `DISPLAY`) · Sub: tidak ada |
| **Susunan** | tiga kartu pilihan besar → aksi `Lanjut` |
| **Kartu** | Ikon · nama mode (16 px) · keterangan satu baris (12 px `MUTED`) |
| **Kosong** | Tidak berlaku — selalu tiga mode |
| **Absen** | **Mode tamu dihapus** dan tidak muncul di sini |

## 12 · Izin mikrofon (consent)

| | |
|---|---|
| **Tugas** | Satu pertanyaan, satu kali |
| **Kepala** | Judul: `Mikrofon` · Sub: `Diperlukan untuk perintah suara dan dikte` |
| **Susunan** | kartu penjelasan → saklar izin → aksi |
| **Aksi** | `Saya mengerti, aktifkan mikrofon` (utama) · `Nanti` (sekunder) |
| **Kosong** | Kalimat penjelasan yang sama, dengan saklar mati |
| **Absen** | Kalau izin belum pernah ditanya, subjudul mengatakan "belum ditanyakan" — bukan "ditolak" |

## 13 · Bantuan

| | |
|---|---|
| **Tugas** | Cara memakai JARVIS, untuk yang belum tahu |
| **Kepala** | Judul: `Bantuan` · Sub: `{n} topik` |
| **Susunan** | daftar baris topik (gulir) → catatan versi |
| **Baris** | Judul topik (13 px) · ringkasan (12 px `MUTED`) · chevron |
| **Kosong** | Tidak berlaku |
| **Absen** | **Pratinjau jawaban** — digambar, berisi "belum dikonfigurasi" |

---

## Tiga hal yang berlaku di semua halaman

### 1. Angka selalu dari store

Subjudul yang berisi angka (`{n} yang diingat`, `{on} dari {total}`) diformat
saat paint dari data nyata. Tidak ada angka mati di template selain `{0}`.

### 2. Slot kosong bukan ruang kosong

Setiap tempat yang build ini tidak bisa isi digambar, dan berisi satu kalimat
yang mengatakannya. Yang dilarang: menghapus slot, atau mengisi dengan nilai
palsu. Ini aturan lama `show_absent`, tetap berlaku.

### 3. Kepala satu, judul satu

Tidak ada halaman yang menggambar judulnya sendiri di badan halaman. Judul ada
di kepala panel, diisi dari registry halaman. Kepala itu **satu** yang dipakai
bergantian — bukan satu per halaman.

---

## Ringkasan: 13 halaman, 3 kelompok

| Kelompok | Halaman |
|---|---|
| **Yang JARVIS ingat & lakukan** | Memori · Detail memori · Rutinitas · Tools · Bantuan |
| **Yang JARVIS kenali** | Gestur · Izin mikrofon |
| **Untuk Anda atur** | Keamanan · Aksesibilitas · Plugin · Brand · Penyiap |
| **Bukan halaman** | Tema terang — jadikan properti panel |

Kelompok ini tidak mengubah 13 halaman. Ia hanya menjelaskan mengapa 13 itu
masuk akal, dan membantu memutuskan di mana sebuah halaman baru akan masuk.
