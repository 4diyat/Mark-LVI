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

## Arah: ambient-only

Permintaan terakhir: **JARVIS hanya mode ambient.** Kondisi kode sekarang belum begitu —
`UI_MODES = ("hud", "ambient", "bubble")` dengan default `"hud"`.

Karena itu lembar acuan dibagi dua:

- **Bagian A** (Artboard 1–2) — jendela yang **dipanggil**. Setelah ambient-only, ini bukan lagi
  keadaan saat aplikasi dibuka.
- **Bagian B** (Artboard 3–4) — keadaan ambient yang sesungguhnya: desktop pengguna bersih,
  hanya ikon tray 22 px, tooltip `JARVIS — {STATE}`, banner notifikasi (`core/notify.py`),
  dan varian wajah melayang 260 px.

### Usulan ambient (belum dikerjakan)

| Kode | Isi | Dampak |
|---|---|---|
| **A2** | Panggilan memakai jendela tersimpan, bukan `showMaximized()` | Membuat ambient benar-benar berbeda dari hud |
| **A4** | Ikon tray berubah warna per keadaan | Status terbaca tanpa hover |
| **A5** | Cincin di bubble dibuat 180°-simetris (2/4/2/4/2 busur) | Hanya bubble, bukan HUD |
| **A6** | Bubble menjepret ke tengah / ke margin 24 px saat dilepas | Menghormati posisi pilihan pengguna |
| **A7** | Ikon tray dua garis cermin | Mengganti huruf “J” yang asimetris |
| **A1** | `hud` dan `bubble` dihapus dari `UI_MODES` | 8 berkas tes, i18n, tray, `--hidden`/`--show` |

Urutan: **A2 → A5 → A6 → A4 → A1**. **A3 dicabut** — wajah melayang tetap ada atas keputusan Anda.

## Simetris — apa yang sebenarnya tidak simetris

Dua hal berbeda, dan keduanya nyata:

1. **Posisi.** `_place()` memakai margin 24 px dari sudut kanan bawah, jadi bubble memang tidak
   pernah di tengah. `_on_release()` tidak menjepret apa pun, sehingga melepas bubble dekat
   tengah meninggalkannya beberapa piksel melenceng.
2. **Gambar.** Cincin HUD punya lima baris busur dengan `count` 2 / 3 / 1 / 4 / 2
   (`ui/hud_canvas.py:431-435`). Hanya `count` **genap** yang otomatis simetris terhadap pusat;
   baris 3 dan 1 tidak. Artboard 5 memperlihatkan keduanya berdampingan.

### Usulan jendela (ditangguhkan selama ambient-only)

U2 (footer 22 px), U3 (caption emblem), U4 (lebar subwindow navigasi) tetap berlaku di dalam
jendela yang dipanggil. **U1 ditangguhkan** — mengangkat sidebar jadi kolom tetap justru
menambah chrome permanen.

## Batasan

- Gambar dan lembar ini **tidak** diverifikasi di mesin ber-Qt. Semua ukuran berasal dari
  membaca kode, bukan dari tangkapan layar aplikasi yang berjalan.
- Tidak ada perubahan kode pada commit ini; ini tahap konsep.

## Sistem desain ambient (22 artboard)

Spesifikasi ambient menggantikan arah jendela di atas untuk pekerjaan baru:

- `jarvis-design-system.html` — 22 artboard, palet baru (`#04080D` / `#4FD8F0` / `#F5A524`),
  tema gelap dan terang, semuanya SVG inline tanpa jaringan.
- `build.py` — generator lembar itu; jalankan untuk regenerasi.
- `DESIGN-ambient.md` — ringkasan keputusan: kontras terukur, asumsi A1–A6, tiga benturan
  spesifikasi, dan apa yang sengaja belum digambar.

Lembar lama (`jarvis-desktop-spec.html`, `jarvis-desktop.png`) tetap disimpan sebagai
dokumentasi keadaan kode pada `bb02ce1`, tetapi **bukan** acuan visual lagi.
