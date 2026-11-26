# Analisis `design/new-ui-proposal/` — Acuan Refaktor UI/UX

> Dokumentasi analisis 17 mockup visual di `design/new-ui-proposal/` sebagai
> **acuan visual target** untuk refaktor UI/UX (pilihan B, agreed 2026-11-25).
>
> CATATAN METODE: mockup adalah gambar statis. Analisis di sini dilakukan
> secara teknis (dimensi, tema, probe palet terhadap token `ui/tokens.py`),
> kemudian dipetakan ke dokumen desain (`design/NEW-UI-DESIGN.md` §4) dan
> status implementasi di `ui/`. Verifikasi per-pixel tetap langkah manual
> (konvensi `docs/verification.md`). Lembar artboard lama
> (`docs/mockups/`, 22 artboard + generatornya) pensiun pada 2026-11-25:
> `design/new-ui-proposal/` adalah SATU-SATUNYA sumber visual.

## 1. Ringkasan teknis

- **17 gambar**, semuanya `.png`.
- **16 gelap + 1 terang**: hanya `16-light-theme.png` yang tema terang
  (board 17 + 18), sisanya gelap.
- **Palet sesuai token**: setiap gambar hanya mengandung warna dari keluarga
  `BG`/`PANEL`/`PANEL2` (gelap) atau `LIGHT-BG`/`LIGHT-PANEL`/`TEXT` (terang),
  plus aksen `PRI` (#4b9fff), `ACC` (#ff6b00), `GREEN`, `AMBER`, `RED`.
  **Tidak ada warna di mockup yang belum punya token** — artinya tidak ada
  komponen visual yang memerlukan token baru.
- Aksen paling sering muncul: `PRI` (ambient, voice, onboarding, orb-status,
  brand) — sesuai identitas orb/fokus. `ACC` (oranye) muncul di help
  (board 13, titik aksi) dan brand (swatch). Semua lima aksen muncul di
  `15-brand-icons.png` — itu lembar spesifikasi, sudah sesuai fungsinya.

**Kesimpulan metode**: karena palette-nya sudah 100% token, implementasi dari
gambar ini adalah pekerjaan pemetaan elemen → token/komponen, bukan
penemuan warna baru.

## 2. Peta gambar → board → status implementasi

| # | File | Board | Layar (dari NEW-UI-DESIGN.md §7) | Tema | Status implementasi saat ini |
|---|---|---|---|---|---|
| 1 | `01-ambient-main.png` | 1 + 5 | Desktop ambient: orb + glow + panel baki + toast | gelap | ✅ `orb_paint/overlay/place/snap`, `toast_card/stack`, panel baki |
| 2 | `02-command-bar.png` | 2 | Command bar 640×184 dengan titik risiko | gelap | ✅ `command_bar.py`, `command_paint.py` (titik risiko verified/unverified/gagal) |
| 3 | `03-gesture-control.png` | 3 | Kontrol gestur: tile kamera + kerangka tangan | gelap | ✅ `hand_feed.py` (di dalam jendela suara) |
| 4 | `03-voice-mode.png` | 4 | Mode suara: glow tepi, orb, bar level, transkrip | gelap | ✅ `voice_overlay/paint/wiring` |
| 5 | `04-security-permissions.png` | 6 + 14 | Keamanan & izin: tingkat risiko + log aktivitas | gelap | ✅ `build_permissions`, halaman keamanan + verifikasi suara; mode tamu sengaja **tidak** ditampilkan (pemilik) |
| 6 | `05-tray-panel.png` | 5 | Panel baki penuh (460×660) | gelap | ✅ `tray_panel` + `pages_*` |
| 7 | `05-onboarding.png` | 7 + 22 | Onboarding: izin mikrofon + presensi | gelap | ✅ 4-langkah `core.onboarding` + installer dependensi (board 22) |
| 8 | `06-task-history.png` | 8 | Riwayat tugas: status per baris + undo | gelap | Sebagian: daftar urungkan sesi berpaginasi dan tiga entri audit terbaru; bukan riwayat tugas penuh |
| 9 | `07-memory-personal.png` | 9 + 10 | Memori personal + detail memori | gelap | ✅ list **scroll** + detail jujur (3 bidang tidak disimpan). Diperbaiki pada sesi ini |
| 10 | `08-routines-suggestions.png` | 11 | Rutinitas & saran proaktif | gelap | Sebagian: rutinitas tersimpan, scheduler dan pembuatan harian dengan perintah; **engine saran proaktif belum ada** |
| 11 | `09-tools-clipboard.png` | 12 | Alat cepat & clipboard cerdas | gelap | ✅ sebagian: clipboard + cari berkas nyata; susun jendela — UI ada (`window_layout`), perilaku OS belum |
| 12 | `10-help-dictation.png` | 13 | Dikte · baca layar · isi form | gelap | Sebagian: tiga kartu bantuan jujur dan tautan ke input suara; pembaca layar dan pengisian form di panel belum tersedia |
| 13 | `11-language-accessibility.png` | 15 | Bahasa & aksesibilitas | gelap | Sebagian: bahasa dan kontras tinggi panel; ukuran teks, animasi dan rebind gestur belum tersambung ke renderer/controller |
| 14 | `12-plugins-phone.png` | 16 | Plugin & pasangan ponsel | gelap | Sebagian: daftar registry plugin dengan pagination dan tinjauan izin; pairing ponsel di panel **belum tersedia** (simulasi lokal dinonaktifkan) |
| 15 | `13-gesture-map.png` | 19 | Peta gestur (6 gestur) | gelap | ✅ permukaan dokumentasi (`paint_gestures`) |
| 16 | `14-orb-status.png` | 20 | Status orb — 4 status siluet | gelap | ✅ `paint_orb` (siluet, bukan hanya warna) |
| 17 | `15-brand-icons.png` | 21 | Brand & ikon — lembar spesifikasi | gelap | ✅ `paint_brand` (swatch dari palette sendiri) |
| 18 | `16-light-theme.png` | 17 + 18 | Tema terang — panel & izin | **terang** | ✅ palet `light` + halaman light; board 18 diverifikasi lewat render offscreen; verifikasi desktop asli belum |

## 3. Prioritas refaktor UI/UX berdasarkan gambar

Urutan berdasarkan **gap antara gambar dan kenyataan**, terbesar dulu:

1. **Board 9/10 — memori (`07-memory-personal.png`)** — SELESAI pada sesi ini:
   list scroll, header hitung store, kartu kosong yang jujur, detail tanpa
   persentase. Acuan gambar sudah terpenuhi.
2. **Board 18 — tema terang izin (`16-light-theme.png`)** — kartu dan teks
   sudah diverifikasi dengan render Qt offscreen dalam tema terang dan gelap.
   Verifikasi interaksi pada desktop asli tetap diperlukan.
3. **Board 12 — susun jendela (`09-tools-clipboard.png`)** — UI tiga
   thumbnail ada, tetapi perilaku OS di belakangnya belum. Refaktor:
   perilaku nyata atau hapus klaim (desain jujur: tidak menggambar kontrol
   yang tidak bekerja).
4. **Board 11 — saran proaktif (`08-routines-suggestions.png`)** — kartu
   saran digambar, engine-nya belum. Atau implementasi engine sederhana,
   atau katakan di halaman bahwa sektor itu tidak aktif (desain jujur).
5. **Board 16 — plugin dan ponsel (`12-plugins-phone.png`)** — panel tidak
   tersambung ke transport pairing dashboard; kontrol simulasi dinonaktifkan.
   Daftar menggunakan registry runtime, pagination, dan dialog izin sebelum
   aktivasi; deklarasi izin bukan sandbox. Integrasi dashboard memerlukan
   peninjauan kesiapan dan keamanan, termasuk kemungkinan HTTP tanpa enkripsi.
6. **Board 14 — mode tamu (`04-security-permissions.png`)** — sengaja tidak
   ditampilkan (pemilik: tidak ada yang membuat seluruh permukaan berhenti
   membaca memori). Tetap di luar refaktor.

## 4. Catatan kesenjangan (record of what has no surface)

Ini adalah pengganti `docs/mockups/NOT-IN-MOCKUP.md` yang pensiun pada
2026-11-25: rekam kesenjangan antara desain dan implementasi. Setiap baris
yang menyatakan "tidak ada permukaan" adalah keputusan, bukan kelalaian —
dan karena tidak ada permukaan, satu-satunya tempat yang bisa menyatakannya
adalah teks.

| Kesenjangan | Penjelasan |
|---|---|
| Setting notifikasi desktop | Setting (`desktop_notifications`) tetap ada dan berfungsi, tetapi tidak ada kontrol di layar untuk mengubahnya (drawer lama dihapus bersama mockup lama). Di-toggle lewat `config/api_keys.json`. |
| Skema `jarvis://` | Tidak ada tombol: pendaftaran skema sekarang hanya lewat command line (`core/deeplink.py` menjawab dari OS). Cara masuknya harus disebutkan — fitur tanpa tombol dan tanpa cara masuk yang tercatat adalah fitur yang tidak ada. |
| Mode tamu | Dihapus dari panel, wiring, dan kedua katalog: mode tamu membutuhkan SELURUH permukaan berhenti membaca memori & riwayat, dan tidak ada yang melakukannya. Pemilik: jika tidak bisa, jangan digambar. |
| Susun jendela (board 12) | UI tiga thumbnail ada, perilaku OS di belakangnya belum — lihat prioritas 3. |
| Engine saran proaktif (board 11) | Kartu saran digambar, engine belum — lihat prioritas 4. |
| Form dan baca layar (board 13) | Belum tersedia di panel. Adapter lama dinonaktifkan: ia tidak memverifikasi halaman aktif dan tidak meminta tinjauan pengguna. Input suara di Alat menuju asisten, bukan mengetik ke aplikasi lain. |
| Pairing dan handoff ponsel (board 16) | Tidak tersedia di panel; `PairingSession` lokal bukan koneksi ponsel. Dashboard jarak jauh memiliki jalur tersendiri yang belum terhubung ke kartu ini. |
| Wajah floating (face bubble) | Simpanan lama yang sengaja dipertahankan **hanya opt-in**: `ui_mode` `"bubble"`. `python main.py` di mode `hud`/`ambient` menunjukkan board 1 (orb + panel + toast) **tanpa** avatar — avatar tidak ada di 22 mockup. |

## 5. Aturan refaktor ke depan (dari analisis ini)

- **Satu sumber visual**: `design/new-ui-proposal/` adalah acuan visual.
  `docs/design/` + token + tes adalah acuan mesin (struktur/perilaku).
  Jangan membuat desain kedua.
- **Setiap gambar ⇒ satu pemetaan**: lihat gambar → petakan elemen ke
  `ui/tokens.py` + `ui/components.py` → implementasi builder/painter →
  kunci perilaku dengan tes (`tests/test_board_pages.py` gaya) → verifikasi
  visual manual.
- **Desain jujur tetap aturan**: jika gambar menunjukkan kontrol yang
  tidak bisa diimplementasikan sekarang, hapus dari UI atau nyatakan
  ketidaktersediaannya di halaman (seperti board 10 tanpa persentase).
- **Tidak ada warna baru**: semua warna di 17 gambar sudah tercakup token.
  Jika di masa depan ada warna baru, tambahkan ke `ui/tokens.py` dulu,
  lalu ke `ui/theme.py` (satu penulis palette).

## Pembaruan implementasi panel utama

Panel utama kini menggunakan kartu aksi dua kolom dan area percakapan sesi yang
mengikuti `05-tray-panel.png`, dengan tema terang/gelap yang sama. Isi chat
berasal dari perintah yang diketik dan transkrip sesi, bukan contoh dalam
mockup; hingga 100 pesan disimpan hanya dalam memori proses. Navigasi dari
halaman lain memiliki tombol kembali, dan tombol kirim memakai isi kolom.

Empat kartu pada mode Aktif/Senyap kini mengikuti gambar: Chat, Ringkas
Dokumen, Analisis Data, dan Buat Konten. Kartu menyiapkan draf dan tidak pernah
mengirim otomatis atau menimpa draf yang sudah ada. Tangkap layar dan dikte tetap
bisa dijalankan dari halaman Alat; pencarian berkas tetap berada di halaman itu.
Mode Fokus mempertahankan kontrolnya sendiri. Mikrofon ditampilkan sebagai petunjuk
deteksi perangkat, bukan izin OS. Sakelar berkas dan kontrol aplikasi dinonaktifkan:
keduanya aksi bawaan, bukan plugin, sehingga konfigurasi plugin tidak membatasi
eksekusinya. Tampilan menyatakan kontrol akses belum tersedia. Pilihan susun
jendela dinyatakan sebagai preferensi yang disimpan saja: aplikasi belum
memindahkan jendela OS.

Bilah perintah sekarang memperlihatkan hingga tiga hasil terminal yang benar-benar
tercatat di audit, bukan tiga contoh statis. Warna menunjukkan status yang
tercatat, bukan klasifikasi risiko; baris hanya untuk dibaca, sedangkan Enter
mengirim teks yang diketik. Status `done` disebut "tercatat selesai", bukan
klaim verifikasi independen atas hasil setiap tool.

Ini **belum merupakan penerapan visual lengkap seluruh proposal**. Indikator
izin mengikuti model izin aktual (kamera belum menjadi kontrol di panel utama).
Halaman-halaman lain tetap memakai implementasi sebelumnya dan perlu dibandingkan
lagi dengan gambar. Verifikasi visual Qt masih perlu dilakukan pada desktop yang
memiliki dependensi sistem Qt dan perangkat nyata.

## Pembaruan halaman Alat

Kartu Alat kini memiliki header dan permukaan sesuai tema. Clipboard hanya
menampilkan teks terkini; kegagalan baca dibedakan dari clipboard tanpa teks.
Tombol dinonaktifkan jika tidak ada teks, dan peringatan hanya dapat diabaikan
untuk teks yang masih sama ketika diklik. Deteksi pola bukan pemeriksaan
keamanan. Bersihkan memeriksa ulang teks sebelum menulis, tetapi akses clipboard
tidak menyediakan operasi atomik sehingga tetap ada kemungkinan perubahan
di antara pemeriksaan dan penulisan. Pencarian terbatas pada pencocokan nama
berkas dalam Documents, Downloads dan Desktop, bukan pemahaman bahasa alami;
penelusuran direktori berjalan pada worker tunggal dengan pembatalan kooperatif;
hasil lama diabaikan. Pembatalan tidak dapat menghentikan panggilan filesystem
yang sudah macet di OS.

## Navigasi dan batas kontrol aksesibilitas

Kartu pada daftar halaman menerima klik pada teks maupun area kartu, mengikuti
tema yang dipilih, dan tombol kembali mengikuti riwayat panel. Pengaturan ukuran
teks, kurangi animasi, dan perubahan gestur dinonaktifkan karena nilai simpanannya
belum diterapkan oleh renderer/controller. Kontras tinggi berlaku pada panel,
bukan klaim seluruh aplikasi. Pembuatan rutinitas harian kini meminta waktu lokal HH:MM dan perintah; pengguna
dapat menelusuri seluruh rutinitas dalam halaman tiga baris. Aksi mengacu pada
identitas rutinitas yang ditampilkan dan transaksi store berbagi lock antar-thread
dalam satu proses. File yang rusak tidak ditimpa sebagai daftar kosong. Lock ini
tidak melindungi proses aplikasi lain atau penyunting eksternal. Scheduler
menandai rutinitas saat diambil, bukan saat pengiriman terbukti berhasil;
pengiriman yang gagal tidak diulang. Jadwal lain selain harian belum tersedia
dari formulir.

## Pembaruan halaman Riwayat

Halaman Riwayat menampilkan daftar urungkan sesi dan tiga entri audit terbaru,
bukan daftar semua tugas atau status verifikasi yang tidak tersedia. Baris
berpaginasi, dan hanya item terbaru memiliki tombol urungkan. Identitas entri
diperiksa secara atomik sebelum urungkan, sehingga perubahan stack tidak
mengalihkan aksi ke item lain. Operasi undo berjalan pada worker; hasilnya
adalah laporan callback, bukan verifikasi independen. Mengosongkan daftar
memerlukan konfirmasi dan hanya berjalan jika snapshot stack tidak berubah.
Ini melupakan kemampuan undo, bukan menghapus audit atau membatalkan perubahan.

## Pembaruan halaman Bantuan

Halaman Bantuan kini menampilkan tiga kartu sesuai tema dan menyediakan tautan
ke Alat untuk input suara. Input tersebut menuju sesi asisten, bukan dikte ke
aplikasi lain; membacakan layar dan mengisi form belum tersedia pada panel.
Kontrol yang belum tersedia dinonaktifkan. Adapter form lama juga menolak
pemanggilan langsung: sebelumnya URL tidak diperiksa terhadap halaman aktif,
selector ditebak, tidak ada tinjauan pengguna, dan operasi browser dapat
memblokir thread Qt. Kebijakan murni `core.form_fill` bukan integrasi browser.
