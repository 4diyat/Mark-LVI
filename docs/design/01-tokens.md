# JARVIS — token

> Angka di dokumen ini menggantikan 15 ukuran teks dan 15 pitch vertikal yang
> sekarang tersebar di `docs/mockups/build.py`. Setiap nilai di bawah
> **diturunkan dari artboard**, bukan dikarang — kolom "asal" menunjukkan dari
> mana ia diukur.
>
> **Semua nilai di bawah sudah diperiksa saling konsisten.** Rumus di bagian
> [Kartu](#kartu-tingginya-tumbuh) menghasilkan angka yang sama dengan tabel
> pitch; kalau Anda mengubah satu token, jalankan `03-adopt.md` langkah 1 dan
> biarkan test yang memberi tahu apa yang ikut berubah.

---

## Teks

Enam peran, lima ukuran. Itu saja.

| Token | Ukuran | Peran | Asal (artboard) |
|---|---|---|---|
| `LABEL` | **11 px** | Penanda bagian: KAPITAL, tracking 1.8 | 74 pemakaian 10 px + 4× 9.5 px → dinaikkan |
| `META` | **12 px** | Baris kedua kartu, keterangan, bantuan | 25× 10.5 px + 13× 11 px |
| `BODY` | **13 px** | Isi percakapan, label baris, tombol | 20× 11.5 px + 12× 12 px |
| `CARD_TITLE` | **16 px** | Judul kartu | 12.5–13 px → dinaikkan (aturan 4) |
| `DISPLAY` | **26 px** | Angka besar, pertanyaan pembuka | 26 px (`Pilih cara JARVIS hadir`) |
| `WORDMARK` | **13 px** | "JARVIS" di kepala panel | 13 px, bobot 700, tracking 1.4 — **sama dengan `BODY`**, beda peran bukan beda ukuran |

### Yang berubah, dan kenapa

**Label bagian naik 10 → 11 px.** Ini satu-satunya teks di bawah 12 px, dan
alasan ia tetap kecil adalah karena ia penanda, bukan bacaan. Tapi 9.5 px untuk
`KLIK KIRI` terlalu kecil bahkan untuk penanda.

**Ukuran 10.5 / 11.5 / 12.5 dihapus.** Mereka adalah hasil mengetik angka
sambil menggambar, bukan keputusan. Selisih 0.5 px tidak terlihat sebagai
hierarki — ia terlihat sebagai ketidaktelitian.

**Judul kartu naik 13 → 16 px.** Pada 13 px, judul kartu dan isi kartu hanya
beda 1 px. Hierarki yang tidak terlihat bukan hierarki.

### Bobot dan tracking

| Pemakaian | Bobot | Tracking |
|---|---|---|
| `WORDMARK`, `DISPLAY` | 700 | 1.4 |
| `CARD_TITLE`, label baris | 500 | — |
| `LABEL` | 500 | **1.8** |
| `BODY`, `META` | 400 | — |

Tracking hanya dipakai pada `LABEL` (kapital) dan wordmark. Teks lain tanpa
tracking; huruf yang direnggangkan pada teks bacaan memperlambat membaca.

---

## Jarak

Skala 4 px. Delapan nilai; tidak ada yang di antaranya.

| Token | Nilai | Dipakai untuk |
|---|---|---|
| `S1` | 4 px | Antara label dan nilainya di dalam satu baris |
| `S2` | 8 px | Antara judul kartu dan isinya |
| `S3` | 12 px | Jarak antar kartu dalam satu daftar |
| `S4` | 16 px | Padding dalam kartu (vertikal) |
| `S5` | 24 px | **Tepi panel** — semua isi mulai di x=24 |
| `S6` | 32 px | Antara bagian besar (label → kartu) |
| `S7` | 48 px | Antara kepala panel dan isi pertama |
| `S8` | 64 px | Antara blok yang tidak berhubungan |

**Tepi 24 px adalah hukum, bukan pilihan.** Ia muncul 135× di artboard dan
menentukan lebar isi:

```
460 − 24 − 24 = 412 px
```

Setiap kartu, segmen, dan tombol selebar 412 px. Kalau sebuah elemen tidak
selebar itu, ia memang bukan elemen penuh.

**Padding dalam kartu 20 px.** Isi kartu mulai di `x = 24 + 20 = 44`, yang juga
muncul 50× di artboard.

---

## Bentuk

| Token | Nilai | Dipakai untuk |
|---|---|---|
| `R_CARD` | **12 px** | Kartu, kotak isian, potongan kode |
| `R_PANEL` | **16 px** | Sudut panel itu sendiri |
| `R_PILL` | **21 px** | Tombol pil, segmen, saklar (`h/2` untuk h=42) |
| `R_INSET` | **10 px** | Elemen di dalam kartu (kotak kode, potongan) |

Radius pil selalu `tinggi / 2`, supaya bentuknya benar di ukuran apa pun. Untuk
saklar 40×22 itu berarti 11.

---

## Komponen

Ukuran diambil dari definisi artboard, dan **tidak boleh ditulis ulang di
halaman**. Kalau sebuah halaman butuh saklar, ia memanggil komponennya.

| Komponen | Ukuran | Detail |
|---|---|---|
| **Saklar** | 40 × 22 | Knob `r = 8`, 3 px dari tepi. Aktif: track sian, knob gelap. Nonaktif: track `#13242E`, knob abu |
| **Pil tombol** | tinggi 42 (utama), 40 (sekunder) | Utama: isi sian, teks gelap. Sekunder: transparan, garis `LINE_ACC`, teks `TEXT` |
| **Segmen** | tinggi 38, lebar 412 | Track `#0B1A22` radius `h/2`; item aktif: isi sian, teks gelap |
| **Slider** | track 380 × 3, knob r=7 | Track `#13242E`; isi sian selebar persentase |
| **Kartu** | lebar 412, tinggi **tumbuh** | Radius 12, isi `CARD`, garis `LINE` |
| **Baris daftar** | tinggi 64 + 12 jarak = pitch 76 | Bukan 70, bukan 72 — lihat `02-screens.md` |

### Kartu: tingginya tumbuh

Artboard menggambar kartu 60, 62, 64, 66, 104, 116, 130, 150, 158, 176 px —
sepuluh tinggi berbeda untuk satu bentuk. Itu bukan sepuluh komponen; itu satu
komponen yang isinya berbeda-beda.

Kartu mendapat tinggi dari isinya, dan hanya ada dua bentuk:

```
kartu 2 baris (judul + meta)
  S4 + CARD_TITLE + S1 + META + S4
  16 + 16         + 4  + 12   + 16  = 64

kartu 3 baris (judul + meta + isi)
  S4 + CARD_TITLE + S1 + META + S1 + BODY + S4
  16 + 16         + 4  + 12   + 4  + 13   + 16 = 81
```

**Pitch (tinggi + jarak antar kartu):**

| Bentuk | Tinggi | + `S3` | Pitch | Baris per 492 px isi panel |
|---|---|---|---|---|
| 2 baris | 64 | +12 | **76** | **6** |
| 3 baris | 81 | +12 | **93** | **5** |

> **Catatan jujur soal pitch 76.** Artboard board 16 memakai pitch 70 dan
> memuat 8 baris. Dengan token ini pitch menjadi 76 karena judul kartu naik
> 13 → 16 px (aturan 4 di `00-principles.md`). Konsekuensinya: **6 baris
> penuh**, bukan 8. Ini harga dari teks yang bisa dibaca, dan ia dibayar
> dengan **daftar yang bisa digulir** — bukan dengan mengecilkan teks lagi.
> Kalau 6 terasa terlalu sedikit, yang boleh berubah adalah `S3` (12 → 8),
> bukan ukuran huruf.

---

## Warna

**Palet tidak berubah.** Ia sudah diukur dan lolos semua ambang. Yang berubah
adalah *aturan pemakaiannya*.

### Gelap

| Token | Nilai | Kontras di kartu | Ambang |
|---|---|---|---|
| `BASE` | `#04080D` | — | latar jendela |
| `PANEL` | `#0A1722` | — | latar panel |
| `CARD` | `#081520` | — | latar kartu, **lebih gelap dari panel** |
| `LINE` | `#17323F` | — | garis pasif |
| `LINE_ACC` | `#2A6477` | — | garis tombol sekunder |
| `TEXT` | `#E6F4F8` | **16.39 : 1** | ✅ |
| `MUTED` | `#8FA9B5` | **7.48 : 1** | ✅ |
| `CYAN` | `#4FD8F0` | **10.90 : 1** | ✅ |
| `AMBER` | `#F5A524` | **9.04 : 1** | ✅ |

### Terang

| Token | Nilai | Kontras di kartu | Ambang |
|---|---|---|---|
| `BASE` | `#F6F9FB` | — | latar jendela |
| `CARD` | `#FFFFFF` | — | latar kartu |
| `LINE` | `#D8E3E9` | — | garis pasif |
| `LTEXT` | `#0B1A24` | **17.68 : 1** | ✅ |
| `LMUTED` | `#5B7480` | **4.94 : 1** | ✅ (margin tipis) |
| `LACC` | `#0A7A93` | **4.98 : 1** | ✅ (margin tipis) |

> **Catatan tentang margin tipis.** Palet terang hampir tidak punya ruang
> gerak: `LMUTED` 4.94:1 di atas putih dan **4.67:1** di atas `BASE` terang
> (`#F6F9FB`); `LACC` 4.98:1. Semuanya **lolos**, tetapi dengan margin ~0.4.
>
> **Koreksi.** Draf pertama dokumen ini mengklaim `LMUTED` *gagal* di atas base
> terang, dan memakai itu untuk membenarkan aturan "kartu terang selalu putih".
> Setelah diukur, klaim itu salah — 4.67 masih lolos. Aturannya tetap
> dipertahankan, tetapi dengan alasan yang benar: kartu putih memberi ~0.27
> margin ekstra yang berarti pada palet yang tinggal punya 0.4. `tests/test_tokens.py`
> sekarang mengunci kedua angka itu, dan akan memberi tahu kalau suatu saat
> ruang geraknya melebar sehingga alasannya boleh dilonggarkan.
>
> **Yang mengikat:** jangan menggelapkan `LMUTED` atau `LACC`, dan jangan
> meletakkannya di atas latar terang selain `#FFFFFF` atau `#F6F9FB`.

### Aturan pemakaian

1. **Sian hanya untuk aksi dan keadaan aktif.** Tombol utama, saklar aktif,
   item segmen terpilih, aksen progres.
2. **Amber hanya untuk risiko.** Tidak untuk peringatan biasa, tidak untuk
   dekorasi.
3. **Abu untuk yang tidak ada.** Slot kosong, fitur tidak tersedia, meta data.
4. **Warna tidak pernah satu-satunya penanda.** Setiap status amber juga punya
   kata ("berisiko"), setiap status sian juga punya posisi (saklar di kanan).
   Alasannya buta warna: sian dan amber bisa tampak serupa.

---

## Kode sumber token

Saat diimplementasikan, semua nilai ini hidup di satu modul — **bukan** tersebar
di stylesheet halaman:

```
ui/tokens.py     ukuran teks, jarak, radius, warna — satu sumber
ui/components.py saklar, pil, segmen, kartu — dibaca, bukan digambar ulang
```

Halaman **tidak boleh** memuat angka piksel. Kalau sebuah halaman butuh
`13`, ia menulis `tokens.BODY`, bukan `13`.

Aturan ini bisa ditegakkan test: `grep` angka di `ui/pages_*.py` harus kosong
untuk ukuran teks. Itulah satu-satunya cara aturan ini bertahan lebih dari
seminggu.
