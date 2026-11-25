# JARVIS — cara mengadopsi desain ini

> Urutannya penting: **token dulu, komponen kedua, halaman terakhir.**
> Membalik urutan ini adalah bagaimana tiga putaran sebelumnya dikerjakan, dan
> hasilnya halaman yang benar satu per satu tetapi tidak konsisten bersama.

---

## Kenapa berurutan

Kalau kita mulai dari halaman, setiap halaman mendapat tokennya sendiri — persis
bug yang sekarang: 15 ukuran teks untuk 5 peran. Kalau kita mulai dari token,
setiap halaman yang dimigrasikan **tidak punya pilihan** selain konsisten.

Aturannya: setelah langkah 1 selesai, tidak ada kode baru yang boleh menulis
angka piksel untuk teks.

---

## Status pelaksanaan

| Langkah | Keadaan | Catatan |
|---|---|---|
| 1 · token | **selesai** | `ui/tokens.py` + `tests/test_tokens.py` (18 fungsi, 25 kasus) |
| 2 · komponen | **selesai** | `ui/components.py` + `tests/test_components.py` (11 fungsi, 11 kasus) |
| 3 · Memori | **selesai** | daftar bergulir; 6 kartu tampil dari N |
| 4 · 12 halaman | belum | |
| 5 · bersihkan | belum | |

**Titik keputusan langkah 3 sudah lewat**, jadi langkah 4 menunggu penilaian Anda atas
render daftar memori (hasil token; tool renderer pensiun 2026-11-25 bersama
sumber visual lain, jadi tidak ada lagi gambar acuan untuk ini).

### Apa yang berubah saat pelaksanaan, dan kenapa

Tiga hal ditemukan saat mengerjakan, semuanya dicatat karena mengubah rencana:

1. **Enam peran teks, LIMA ukuran.** `WORDMARK` dan `BODY` sama-sama 13 px.
   Rencana awal menuntut enam angka berbeda; setelah dikerjakan itu salah —
   wordmark butuh bobot dan tracking berbeda, bukan ukuran berbeda. Memaksa 12
   atau 14 px hanya untuk mendapat angka keenam adalah kebiasaan lama yang
   menciptakan 15 ukuran. Test sekarang menuntut **lima ukuran, enam peran**.

2. **Klaim kontras di `01-tokens.md` salah dan sudah dikoreksi.** Dokumennya
   menyebut `LMUTED` gagal di atas base terang. Diukur: **4.67:1**, masih lolos.
   Alasannya ditulis ulang dengan benar (margin tinggal ~0.4, jadi tidak boleh
   digelapkan lebih lanjut), dan test mengunci kedua angka.

3. **`tray_panel.py` melewati 600 baris** saat `memory_open_id` ditambahkan.
   Yang dipindahkan bukan "apa saja yang muat": empat method tema pindah ke
   `ui/tray_theme.py` sebagai fungsi murni (`cycle`, `is_valid`, `resolve`),
   karena itu kebijakan tentang satu setelan — bukan lifecycle panel.

### Bug stub yang ditemukan, dan kenapa itu penting

Test yang dimigrasikan langsung menangkap **empat** cara `tests/qtstub.py`
menelan state, yang berarti empat kelas bug produksi tidak akan pernah terlihat:

| Yang ditelan | Akibatnya kalau tidak diperbaiki |
|---|---|
| `setLayout` pada widget anak | `QWidget(card)` menimpa layout kartu; setiap baris tampak kosong |
| `addStretch`/`takeAt` | daftar yang membersihkan diri tidak pernah bersih → baris berlipat tiap paint |
| `setSpacing` | kartu berhimpit, dan tidak ada test yang bisa melihatnya |
| `setMinimumHeight` | tinggi kartu hilang, irama 64 px lenyap |

`setLayout` yang paling serius: `_Object.__init__` menjalankan `a[0].setLayout(self)`
untuk **setiap** widget, bukan hanya layout. Jadi `QWidget(card)` — anak dari
sebuah kartu — memasang dirinya sebagai layout kartu itu. Pohon widget halaman
mana pun yang punya baris dua kolom terlihat kosong bagi test.

### Alat render juga buta terhadap halaman bergulir (historis)

Alat renderer (`tools/render_board_overlay.py` dan `tools/render_list.py`)
**sudah pensiun pada 2026-11-25** bersama semua sumber visual lain;
keluarannya di `docs/verification/` juga dihapus, jadi tidak ada lagi gambar
acuan dari mereka. Saat masih aktif, overlay hanya melihat widget yang menjadi
anak langsung halaman. Setelah Memori pindah ke kolom gulir, kartunya menjadi
cucu, dan alat itu mencetak **kartu contoh milik artboard** — persis jenis
kebingungan yang pernah saya alami di board 16. Dua perbaikan yang dulu:

* overlay menelusuri rantai parent (`_inside`), bukan hanya satu tingkat;
* `render_list.py` mengukur kolom dari token dan menggambar kartunya,
  karena widget yang di-layout tidak punya `setGeometry` untuk dibaca.

---

## Langkah 1 — `ui/tokens.py` (1 sesi)

Satu modul, tanpa Qt, tanpa impor dari `ui/` yang lain.

```python
# teks
LABEL, META, BODY, CARD_TITLE, DISPLAY, WORDMARK = 11, 12, 13, 16, 26, 13
# jarak
S1, S2, S3, S4, S5, S6, S7, S8 = 4, 8, 12, 16, 24, 32, 48, 64
# radius
R_CARD, R_PANEL, R_PILL, R_INSET = 12, 16, 21, 10
# komponen
TOGGLE_W, TOGGLE_H = 40, 22
PILL_H, SEG_H = 42, 38
# geometri panel
PANEL_W, PANEL_H = 460, 660
CONTENT_W = PANEL_W - 2 * S5          # 412
CARD_PAD = 20                          # isi mulai di 24 + 20 = 44
```

**Kriteria selesai:** `ui/tokens.py` ada, dan `tests/test_tokens.py` mengunci
setiap nilai. Test itu bukan formalitas — ia yang membuat "jangan diubah
sepihak" menjadi aturan.

---

## Langkah 2 — `ui/components.py` (1 sesi)

Fungsi yang **mengembalikan widget siap pakai**, bukan angka. Ini yang
menggantikan 102 `setGeometry` manual.

```python
def card(parent, x, y, *, height=None) -> QLabel      # tinggi dari isi
def toggle(parent, x, y, *, checked) -> QPushButton   # 40x22, tanpa teks
def pill(parent, x, y, w, text, *, primary) -> QPushButton
def segment(parent, x, y, items, *, active) -> QWidget
def label_row(parent, x, y, *, name, meta, right=None) -> QWidget
def scroll_column(parent) -> tuple[QWidget, QVBoxLayout]   # untuk daftar
```

**Kriteria selesai:**

- Setiap komponen punya test yang memeriksa `size()` sesuai token — bukan
  koordinat absolut, karena posisi kini urusan layout
- `scroll_column` dipakai minimal satu halaman sebagai bukti

`scroll_column` adalah bagian terpenting. Ia yang membuat aturan 2 ("semua yang
tumbuh bisa digulir") bisa ditegakkan: setelah ia ada, daftar yang tidak
memakainya adalah kesalahan yang terlihat.

---

## Langkah 3 — satu halaman sebagai bukti (1 sesi)

**Memori.** Bukan karena ia yang terpenting, tetapi karena ia yang paling banyak
salah sekarang: daftar mati di 6 baris, kartu dengan tinggi yang ditebak,
header memuat angka contoh.

Yang dikerjakan:

1. Ganti 18 `setGeometry` di `pages_memory.py` dengan `scroll_column` + `card`
2. Subjudul dari store (sudah benar — pastikan tidak rusak)
3. Hapus `pl_more`-style hitungan; daftar menggulir, tidak memotong

**Kriteria selesai — dan ini titik keputusan:**

- Bandingkan dengan gambar acuan di `design/new-ui-proposal/`
- Tambah 50 entri ke store di test; halaman tetap utuh dan bisa digulir
- Kosongkan store; satu kartu berisi kalimat kosong, bukan halaman kosong

> **Kalau langkah 3 tidak meyakinkan, berhenti di sini.** Yang belum dimigrasikan
> masih berjalan seperti sebelumnya. Tidak ada kerusakan — hanya satu halaman
> yang lebih baik.

---

## Langkah 4 — 12 halaman sisanya (3–4 sesi)

Urutan berdasarkan risiko, bukan kepentingan:

| Urutan | Halaman | Alasan |
|---|---|---|
| 1 | Plugin | 15 baris → gulir; `level` bukan "resmi" |
| 2 | Gestur | Baris 48 px; kolom ketiga rata kanan |
| 3 | Aksesibilitas | Paling banyak komponen (segmen, slider, saklar) |
| 4 | Keamanan | Kartu tinggi tetap 104 |
| 5 | Rutinitas | Dua daftar dalam satu halaman |
| 6 | Tools | Kisi 2 kolom |
| 7 | Detail memori | Turunan Memori |
| 8 | Bantuan | Daftar sederhana |
| 9 | Izin mikrofon | Satu pertanyaan |
| 10 | Brand | Swatch, tanpa token aksi |
| 11 | Penyiap | Kartu besar, sekali pakai |
| 12 | Tema terang | **Bukan halaman** — pindahkan ke `PALETTES[theme]` |

Setiap halaman selesai kalau: tidak ada angka piksel teks, daftar memakai
`scroll_column`, dan render overlay tidak memperlihatkan teks bertumpuk.

---

## Langkah 5 — bersihkan (1 sesi)

Setelah semua halaman hijau:

1. `ui/board_geometry.py` dan `tools/gen_board_geometry.py` — **sudah
   dihapus/di-pin** (2026-11-25): koordinat di-pin ke token, generator
   pensiun bersama sumber artboard-nya.
2. `docs/mockups/build.py` — **sudah dihapus** (2026-11-25). Satu-satunya
   referensi visual sekarang adalah `design/new-ui-proposal/`; lihat
   `design/new-ui-proposal-ANALISIS.md`.
3. `tests/test_board_conformance.py` — tulis ulang: dari "widget ada di
   koordinat artboard" menjadi "widget memakai token dan tidak melampaui
   412 px".
4. Test penjaga baru:
   - tidak ada `setPixelSize` dengan angka literal di `ui/pages_*.py`
   - tidak ada `setGeometry(` dengan angka pertama > 1 di `ui/pages_*.py`
   - setiap daftar memakai `scroll_column`

---

## Yang bisa ditegakkan test, dan yang tidak

Jujur soal batasnya — ini pelajaran dari putaran sebelumnya.

**Bisa ditegakkan:**

- Ukuran teks datang dari token
- Lebar elemen tidak melampaui 412 px
- Daftar memakai wadah gulir
- Slot absen berisi kalimat
- Subjudul dengan angka diformat dari store

**Tidak bisa ditegakkan (dan tidak boleh berpura-pura bisa):**

- Apakah hasilnya **enak dilihat**. Itu tetap penilaian manusia.
- Apakah hierarki terasa benar.
- Apakah sebuah halaman terlalu padat.

Untuk tiga hal itu, satu-satunya alat adalah gambar acuan dan mata. Renderer
sebelumnya (`render_board_overlay.py`) pensiun 2026-11-25, jadi sekarang
acuan visualnya hanya gambar di `design/new-ui-proposal/` — bukan sebagai
bukti kebenaran, tetapi sebagai cara melihat apa yang sebenarnya tertulis.

---

## Estimasi

| Langkah | Sesi | Keluaran |
|---|---|---|
| 1 · token | 1 | `ui/tokens.py` + test |
| 2 · komponen | 1 | `ui/components.py` + test + `scroll_column` |
| 3 · Memori | 1 | bukti, **titik keputusan** |
| 4 · 12 halaman | 3–4 | semua halaman |
| 5 · bersihkan | 1 | aturan ditegakkan test |
| | **7–8** | |

Sampai langkah 3 selesai, biayanya satu sesi dan hasilnya bisa dibatalkan tanpa
kerusakan.

---

## Yang tidak berubah

Aturan-aturan lama tetap berlaku dan tidak dilunakkan oleh dokumen ini:

- **`show_absent`** — slot tidak tersedia digambar dan ditulis, tidak dihapus
  dan tidak diisi palsu
- **`skip_13`** — tidak ada mesin pengisi formulir, tidak ada permukaan otomasi
  baru
- **Mode tamu (06a)** — dihapus, tidak boleh muncul lagi
- **Panel 460×660** — bentuk produk, bukan batas yang dilawan
