# Mockup & Acuan Desain JARVIS

Folder ini berisi **konsep tampilan**, bukan kode yang berjalan. Tujuannya: jadi acuan
implementasi yang bisa diperiksa, bukan gambar yang bikin kode terlihat "salah".

## Mana yang dipakai?

| Berkas | Status | Keterangan |
|---|---|---|
| `jarvis-design-system.html` | **acuan visual** | 22 artboard, bernomor 1–22, SVG inline tanpa jaringan. Dibuat oleh `build.py` — bukan ditulis tangan. |
| `build.py` | sumber lembar itu | Setiap artboard adalah satu fungsi `bNN()`. Daftar artboard DITURUNKAN dari fungsi-fungsi itu, jadi sebuah artboard tidak bisa ada tanpa muncul di lembar. |
| `DESIGN-ambient.md` | catatan keputusan | Kontras terukur, asumsi A1–A6, dan kolom "ada di `ui/`?" per artboard. |
| `NOT-IN-MOCKUP.md` | rekaman keputusan | Setiap permukaan yang digambar tetapi belum dibangun, dan setiap permukaan yang dibangun tetapi tidak digambar. |
| `jarvis-desktop-spec.html` | **bukan acuan lagi** | Lembar lama (1440×900) untuk jendela yang sudah dihapus. Disimpan sebagai riwayat keadaan kode di `bb02ce1`. |
| `jarvis-desktop.png` | ilustrasi saja | Dibuat dengan model gambar. Berguna untuk nuansanya, **jangan** dipakai mengukur. |

Regenerasi setelah mengubah `build.py`:

```bash
python docs/mockups/build.py
```

`tests/test_design_sheet_complete.py` gagal kalau lembar yang di-commit berbeda
dari keluaran generator, atau kalau jumlah artboard di lembar, di `README.md`,
di `DESIGN-ambient.md` dan di kode tidak sama.

## Angka yang tidak boleh ditebak

Angka yang berlaku sekarang berasal dari **`build.py`**, dan `tests/` membandingkan
kode dengan angka itu:

- **Token warna** — `BASE, PANEL, LINE, LINE_ACC, CYAN, AMBER, TEXT, MUTED` di
  `build.py`, disalin ke `ui/confirm_banner.py`, `ui/command_bar.py`,
  `ui/orb_paint.py` dan `ui/tray_pages.py`. `tests/test_visual_conformance.py`
  menolak warna di luar daftar itu.
- **Geometri panel 460 px** — `GEOMETRY` di `ui/tray_pages.py`, dibandingkan
  dengan `n05()`/`b05()` oleh `tests/test_tray_geometry.py`.
- **Orb 146 px** dan titik alert-nya — `ui/orb_paint.py`, diuji sebagai aritmatika
  oleh `tests/test_orb_overlay_board1.py`.
- **Kartu toast 340 px** — `ui/toast_card.py`, dari `toast()` di `build.py`.
- **Command bar 640 × 184** — `GEOMETRY` di `ui/command_bar.py`, dari `n03()`.

Angka di bawah berasal dari **jendela yang sudah dihapus** dan disimpan sebagai
riwayat; `ui/window.py` dan `ui/desktop_workspace.py` tidak ada lagi:

- Menu bar 30 px, navigasi 170 px, metric bar 38 px, footer 22 px.
- Files 2% / 7% / 37% / 36%, dock tinggi 76 px, emblem ≤320 × 350.

## Sistem desain ambient (22 artboard)

Palet dan geometri di atas adalah satu sistem: `#04080D` dasar, `#4FD8F0` aksen,
`#F5A524` peringatan, `#FF6B6B` tingkat risiko ketiga, tema terang
`#F6F9FB`/`#0A7A93`. Semua SVG, tanpa font atau jaringan eksternal.

**Yang perlu diingat saat mengubah lembar:**

- Artboard ditambahkan sebagai fungsi `bNN()` **dan** satu baris di
  `BOARD_TITLES`. Fungsi tanpa judul tidak muncul; judul tanpa fungsi tidak
  menghasilkan artboard. `tests/test_design_sheet_complete.py` menolak keduanya.
- Nomor berakhir di 22. Keadaan (Fokus, Senyap, konfirmasi, riwayat, izin, tema
  terang) bukan artboard baru — ia `EXTRA`, digambar sebagai `NNx` di bawah
  artboard induknya.
- Artboard yang digambar tetapi belum dibangun **tetap di lembar** dan dicatat di
  `NOT-IN-MOCKUP.md`. Menghapusnya dari lembar akan menyembunyikan pekerjaan yang
  belum selesai, bukan menyelesaikannya.
