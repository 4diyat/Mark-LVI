# Mockup & Acuan Desain JARVIS

Folder ini berisi **konsep tampilan**, bukan kode yang berjalan. Tujuannya: jadi acuan
implementasi yang bisa diperiksa, bukan gambar yang bikin kode terlihat "salah".

## Mana yang dipakai?

| Berkas | Status | Keterangan |
|---|---|---|
| `jarvis-desktop-spec.html` | **acuan utama** | Setiap garis, warna, dan angka diturunkan dari kode di `bb02ce1`. Ada tabel token, tabel geometri, tabel audit, dan daftar usulan. Hanya memakai CSS/SVG inline — bisa dibuka tanpa jaringan. |
| `jarvis-desktop.png` | ilustrasi saja | Dibuat dengan model gambar. Berguna untuk melihat nuansanya, **jangan** dipakai mengukur. Beberapa elemennya keliru (lihat tabel audit di dalam HTML). |

## Angka yang tidak boleh ditebak

Semua diambil dari sumbernya langsung:

- **Warna** — `ui/theme.py` (`C.BG`, `C.PRI`, `C.DESKTOP_*`, `C.DOCK_*`, dst.).
- **Menu bar 30 px** — `ui/desktop_layout.py` → `build_menu_bar`.
- **Navigasi 170 px, tombol 32 px** — `build_navigation`, `ui/window.py:_LEFT_W`.
- **Metric bar 38 px** — `ui/metric_bar.py`.
- **Footer 22 px** — `ui/window.py:_build_footer`.
- **Files 2% / 7% / 37% / 36%, Assistant 63% / 10% / 35% / 80%, lantai H−90, breakpoint 1100**
  — `ui/desktop_workspace.py:initial_window_geometry`.
- **Panggung emblem ≤320 × 350, top 18%** — `position_emblem`.
- **Dock: tinggi 76, y = H−86, 8 tombol, ikon 44 px** — `position_dock` + tuple `buttons`.

## Temuan penting (belum diperbaiki)

1. **Sidebar 170 px tidak tampil saat aplikasi dibuka.** `_left_panel` dimasukkan ke
   subwindow MDI `navigation` lalu `.hide()` (`ui/desktop_workspace.py:695`).
2. **Footer 22 px juga disembunyikan** (`ui/window.py:575`), padahal footer itu dibangun
   lengkap dengan tombol F4/F11.
3. **Emblem menulis nama asisten**, bukan status seperti pada gambar PNG.
4. **Subwindow navigasi 240 px memuat panel 170 px** → 70 px ruang mati.

## Usulan terbuka

- **U1** Promosikan navigasi menjadi kolom tetap (mengubah start, perlu PR sendiri).
- **U2** Tampilkan footer, atau hapus kodenya — jangan dibiarkan setengah jadi.
- **U3** Samakan caption emblem dengan nama asisten.
- **U4** Rapikan lebar subwindow navigasi.

Urutan kerja yang disarankan: **U4 → U2 → U3 → U1**.

## Batasan

- Gambar dan lembar ini **tidak** diverifikasi di mesin ber-Qt. Semua ukuran berasal dari
  membaca kode, bukan dari tangkapan layar aplikasi yang berjalan.
- Tidak ada perubahan kode pada commit ini; ini tahap konsep.
