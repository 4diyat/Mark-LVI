# Desain JARVIS

Spesifikasi desain untuk panel baki 460×660. Dibaca berurutan.

| Dokumen | Isi |
|---|---|
| [`00-principles.md`](00-principles.md) | Lima aturan yang memutus sengketa, dan alasan ia ada |
| [`01-tokens.md`](01-tokens.md) | Enam peran teks (lima ukuran), delapan jarak, empat radius, palet — semuanya terukur |
| [`02-screens.md`](02-screens.md) | 13 halaman, satu tabel per halaman: tugas, susunan, keadaan kosong |
| [`03-adopt.md`](03-adopt.md) | Urutan migrasi dan apa yang bisa ditegakkan test |

## Aturan tertinggi

> **Kalau dokumen ini dan gambar proposal berbeda, dokumen ini yang menang.**
>
> Gambar proposal (`design/new-ui-proposal/`) tetap menjadi referensi visual —
> warna, nuansa, proporsi. Tetapi ia **bukan** sumber kebenaran untuk ukuran
> teks, jarak, atau susunan. Pemilik memutuskan ini pada 2026-11-23 setelah
> tiga putaran "samakan dengan artboard" tetap terasa salah.

## Ringkas: apa yang berubah

| | Sebelum | Sesudah |
|---|---|---|
| Ukuran teks | 15 nilai | **6 peran** |
| Jarak | 15 pitch | **8 langkah** (kelipatan 4) |
| Posisi | 102 `setGeometry` manual | Layout + komponen bersama |
| Daftar panjang | Tidak bisa digulir | Selalu dalam wadah gulir |
| Jumlah halaman | 13 | **13** (dipertahankan) |
| Palet | Terukur, lolos 4.5:1 | **Tidak diubah** |

## Cara angka-angka ini diperoleh

Tidak ada nilai yang dikarang. Setiap angka di `01-tokens.md` berasal dari salah
satu dari tiga sumber:

1. **Diukur dari artboard (acuan visual sekarang: `design/new-ui-proposal/`)** — jarak tepi 24 px (135×), isi kartu
   44 px (50×), lebar isi 412 px, saklar 40×22, radius 12/16/21.
2. **Turunan aritmetika dari token lain** — tinggi kartu 64 = `16+16+4+12+16`,
   pitch 76 = `64+12`, ruang isi 500 = `660−88−72`. Semua rumusnya tertulis di
   dokumennya, jadi bisa dihitung ulang.
3. **Keputusan yang dinyatakan sebagai keputusan** — teks minimum 11/12 px
   (aturan 4), judul kartu 13 → 16 px. Ini bukan pengukuran; ini pilihan, dan
   dokumennya mengatakan begitu.

Kalau sebuah angka tidak bisa dilacak ke salah satu dari tiga ini, angka itu
salah. Itu juga yang membuat `03-adopt.md` langkah 1 menaruh semuanya di
`ui/tokens.py` dengan test: setelah tokennya terkunci, konsistensinya tidak
bergantung pada siapa yang mengingat.

## Yang pertama harus dibaca

`00-principles.md`, aturan 1 dan 2. Kalau hanya satu halaman yang boleh dibaca
dari seluruh direktori ini, itu dua aturan tersebut:

1. Satu panel, satu kolom, satu tugas.
2. Semua yang tumbuh bisa digulir.

Keduanya menjelaskan sebagian besar bug yang ada sekarang.
