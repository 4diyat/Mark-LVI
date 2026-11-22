# JARVIS — Sistem Desain Ambient

Dua berkas, satu sumber:

| Berkas | Isi |
|---|---|
| `jarvis-design-system.html` | **22 artboard**, SVG inline, tanpa jaringan. Buka langsung. |
| `build.py` | Generator lembar itu. Ubah angka di sini, jalankan `python docs/mockups/build.py`, HTML ditulis ulang. |

Artboard **tidak** memuat penjelasan desain. Semua asumsi, rasio kontras, dan alasan
ada di bagian Ringkasan **di dalam** HTML, setelah artboard 22.

## Dua puluh dua artboard, satu penomoran

Lembar ini **22 artboard**, bernomor 1–22 dan tidak lebih. Tabel di bawah adalah
isi setiap artboard — yang benar-benar digambar `build.py: bNN()`, bukan daftar
keinginan.

| # | Artboard | Yang digambar | Ada di `ui/`? |
|---|---|---|---|
| 1 | Desktop ambient | Desktop contoh, orb 56 px + glow di pojok, satu toast | ya — `orb_paint`, `orb_overlay` |
| 2 | Command bar | Kotak 640×184, gradien, tiga baris hasil dengan titik risiko | ya — `ui/command_bar.py` |
| 3 | Kontrol gestur | Tile kamera 320×236, kerangka tangan, pil gestur aktif | ya — `ui/hand_feed.py` (di dalam jendela suara, bukan panel sendiri) |
| 4 | Mode suara | Glow tepi layar penuh, orb, pil transkrip, lima bar level | ya — `ui/voice_paint.py`, `ui/voice_overlay.py` |
| 5 | Panel baki sistem | 460×640: segmen, empat aksi cepat, percakapan, tiga izin, kolom perintah | ya — `ui/tray_pages.py`, `ui/tray_panel.py` |
| 6 | Izin & privatisasi | Empat izin akses dengan kartu (72 px pitch), log aktivitas bertimestamp, Ekspor/Hapus | ya — `ui/tray_pages.py` (`build_permissions()`) |
| 7 | Onboarding 2/4 | Layar izin mikrofon, tiga kalimat privasi, dua tombol | ya — `ui/pages_people.py` (Langkah 1 dari 1) |
| 8 | Riwayat tugas | Enam baris hari ini, status per baris, saring/pulihkan, hapus | ya — `ui/tray_pages.py` (`build_history()`) |
| 9 | Memori personal | Enam fakta tentang Anda, "12 hal yang JARVIS ingat" | ya — `ui/pages_memory.py` |
| 10 | Detail memori | Satu memori: isi, sumber, keyakinan, dipakai oleh | ya — `ui/pages_memory.py` (tiga bidang; sumber/keyakinan tidak disimpan) |
| 11 | Rutinitas & saran | Tiga rutinitas aktif dengan jadwalnya, tiga saran proaktif | ya — `ui/pages_people.py` (tanpa toko rutinitas) |
| 12 | Alat cepat & clipboard | Tiga alat tersering, clipboard cerdas (rekening terdeteksi), cari berkas bahasa alami | ya — `ui/pages_people.py` (susun jendela tidak ada) |
| 13 | Dikte · baca layar · isi form | Tiga panel: dikte, pembaca layar kontekstual, isi form dengan tinjau dulu | ya — `ui/pages_people.py` (isi form tidak ada) |
| 14 | Keamanan | Tiga tingkat risiko, mode tamu, izin layar/kamera, kontrol OS | ya — `ui/pages_admin.py` + `ui/confirm_banner.py` |
| 15 | Bahasa & gestur | Bahasa UI, ukuran teks, kontras, kurangi animasi, gestur kustom | ya — `ui/pages_admin.py` (kontras & gestur kustom tidak ada) |
| 16 | Plugin & ponsel | Dua dari lima plugin aktif, sinkron ponsel, kode pasangan | ya — `ui/pages_admin.py` (sinkron ponsel tidak ada) |
| 17 | Tema terang — panel baki | Panel 5 dalam token terang, dengan sakelarnya | ya — `ui/tray_pages.py` (`PALETTES["light"]`), `ui/tray_theme.py` |
| 18 | Tema terang — izin & privasi | Panel 6 dalam token terang | ya — `ui/pages_admin.py` + `PALETTES["light"]` |
| 19 | Peta gestur | Enam gestur dengan bentuk tangannya, 720×640 | ya — `ui/pages_people.py` (gambar, bukan kontrol) |
| 20 | Status orb | Empat status orb, dibedakan lewat siluet bukan warna | ya — `ui/orb_paint.py` (`paint_orb`) |
| 21 | Brand & ikon | Ikon aplikasi, empat ikon baki, swatch, skala huruf, komponen | ya — `ui/pages_admin.py` (lembar spesifikasi) |
| 22 | Installer 1/4 | Layar pemasangan: pilih mode kehadiran | ya — `ui/pages_admin.py` (pemilihan mode saja) |
### Enam keadaan, digambar di bawah artboard-nya

Fokus, Senyap, konfirmasi risiko, riwayat, izin dan tema terang **bukan** artboard
bernomor sendiri. Dulu mereka 23–28, dan penomoran kedua itu bentrok dengan yang
pertama: 05-nya artboard panel baki dan `b05` juga. Keputusan pemilik repo
(2026-11-22): satu penomoran, 1–22. Setiap keadaan digambar tepat di bawah
artboard yang bersangkutan, berlabel `05a`, `05b`, `06a`, `08a`, `14a`, `17a`:

| Label | Keadaan | Digambar oleh |
|---|---|---|
| 05a | Fokus — toast ditahan dan dihitung | `n07()` |
| 05b | Senyap — orb memudar dan menyusut | `n08()` |
| 06a | Izin & Privasi — halaman penuh panel, **pensiun**: artboard-nya menuntut MODE TAMU yang sudah dihapus, jadi halaman itu sekarang digambar board 6 | `n11()` |
| 08a | Riwayat tugas + Urungkan | `n10()` |
| 14a | Konfirmasi risiko | `n09()` |
| 17a | Panel baki versi terang | `n12()` |

Angka `n07`–`n12` di tabel itu adalah **nama fungsi**, bukan nomor artboard.

## Yang digambar tapi belum dibangun

Kolom terakhir tabel di atas adalah keadaan hari ini, dan sengaja tidak
dibulatkan ke atas: **dua puluh dua artboard punya permukaan di `ui/`** —
tujuh belas terpenuhi (1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 14, 15, 16, 18, 19, 20,
21) dan lima yang permukaannya nyata tetapi belum bisa melakukan semua yang
digambar artboardnya (3, 7, 13, 17, 22).** Tujuh belas tambah lima sama dengan
dua puluh dua, dan itu seluruh artboard: hitungannya harus habis, bukan
mendekati. Tidak ada lagi baris "belum dibangun" — dan itu bukan karena
klaimnya dilonggarkan, melainkan karena kelima artboard itu sekarang punya
halaman yang mengatakan sendiri apa yang belum bisa dilakukannya.

Itu perbedaan yang penting, dan sengaja ditulis di sini: "terpenuhi" berarti
halaman itu ada, bisa dibuka pengguna, dan membaca toko yang sebenarnya — bukan
berarti setiap piksel artboardnya ditiru. Kelima yang tersisa adalah:

* **3** — petak kamera dengan kerangka 21 sendi: ada, digambar dari feed kamera
  yang nyata (`ui/hand_feed.py`), tetapi jendelanya masih jendela suara, bukan
  panel tersendiri.
* **7** — alur empat langkah: yang ada satu langkah (izin mikrofon), dan
  halamannya menulis "Langkah 1 dari 1" alih-alih "2 dari 4".
* **13** — dikte dan baca layar nyata dan disebut namanya; **pengisian form
  tidak ada backend-nya**, jadi kartunya menyatakan itu.
* **17** — tema terang ada sebagai palet dan board 18 menggambarnya; yang belum
  adalah pemeriksaan visual, bukan permukaannya.
* **22** — pemilihan mode nyata lewat `presence_mode.set_mode`; pemasangan
  dependensi tidak punya UI, dan halamannya tidak berpura-pura punya.

Setiap kalimat itu ada di dalam halamannya sendiri, di tempat artboard
menggambar hal yang tidak ada, karena pengguna tidak membaca
`NOT-IN-MOCKUP.md`.

Artboard bernomor surat (`5a`, `5b`, `8a`, `14a`, `17a`) tidak dihitung sendiri
di sini — mereka pandangan dari board induknya, bukan artboard terpisah, dan
karena itu tidak menambah jumlah. Dua puluh dua artboard, dua puluh dua
permukaan, hitungannya habis.

## Prinsip yang dipegang di setiap artboard

1. **Ambient dulu.** Orb kecil + ikon baki. Jendela besar hanya saat dipanggil
   (artboard 1, 5, 22).
2. **Tidak merebut fokus.** Toast punya dua tombol dan hilang sendiri 8 detik (1).
3. **Dipanggil kapan saja.** Ctrl+Space (2), kata kunci, dan gestur (3, 19).
4. **Transparan soal privasi.** Empat izin eksplisit, log aktivitas, tombol hapus riwayat
   (6, 7, 18).
5. **Aman.** Tiga tingkat risiko; berisiko selalu minta konfirmasi fisik (14, 14a).

## Kontras yang sudah dihitung (bukan diklaim)

Semua pasangan teks lolos 4.5:1. Yang paling tipis:

| Pasangan | Rasio |
|---|---|
| Tema terang: redup `#5B7480` pada latar `#F6F9FB` | **4.67** |
| Tema terang: aksen `#0A7A93` pada putih | **4.98** |
| Tema terang: putih pada aksen `#0A7A93` | **4.98** |
| Gelap: amber `#F5A524` pada panel `#0A1722` | 8.88 |
| Gelap: teks `#E6F4F8` pada dasar `#04080D` | 17.84 |

Tabel lengkap 10 baris ada di ringkasan HTML.

## Asumsi yang perlu disetujui

Spesifikasi tidak memberi angka untuk ini; saya pilih dan catat di ringkasan HTML (A1–A6):

- **Font:** Space Grotesk tidak dimuat dari jaringan. Lembar jatuh ke font sistem. Di Qt,
  font harus dibundel (OFL).
- **Skala tipe:** 10 / 11.5 / 13 / 19 / 26 px.
- **Target sentuh:** tepat 44 px tidak muat berdampingan di panel 460 px; tombol 40 px
  visual dengan area tekan 44 px.
- **Warna risiko ketiga:** `#FF6B6B`, karena permintaan hanya menyediakan cyan dan amber.

## Tiga benturan yang saya putuskan

1. **"Tanpa emoji"** — semua ikon digambar sebagai jalur SVG; tidak ada karakter emoji
   di berkas (sudah diperiksa dengan regex).
2. **"Amber hanya untuk peringatan"** — artboard 20 butuh empat status; amber dipakai
   tepat untuk satu status ("Butuh perhatian").
3. **"Bedakan lewat terang-gelap, bukan hue"** — cyan dan amber luminansinya berdekatan,
   jadi setiap peringatan membawa bentuk tambahan: tanda seru, garis kiri, atau label.

## Belum digambar, dan kenapa

- Onboarding langkah 1, 3, 4 dan installer langkah 2–4: spesifikasi hanya meminta satu
  langkah masing-masing; polanya bisa dipakai ulang.
- Isi plugin pihak ketiga: belum ada di kode, jadi artboard 16 hanya memuat baris generik.

## Batasan shell

- Mockup ini **stack-neutral**: digambar dari perilaku (frameless, transparan, always-on-top),
  bukan dari API-nya, sehingga tetap valid untuk Tauri maupun PyQt6.
- Spesifikasi Tauri 2 + React + TypeScript adalah **aplikasi baru**; repo ini 354 berkas
  Python + PyQt6. Menulis ulang shell bukan bagian dari lembar ini.
- Panel baki memakai 460×660 (bukan 640) karena tiga baris izin + input butuh 20 px ekstra.

## Batasan

- Lembar ini **konsep visual**. Yang diperiksa secara terprogram hari ini, oleh
  `tests/test_design_sheet_complete.py`:

  - semua 22 artboard ada, bernomor 1–22 tanpa celah, dan setiap fungsinya
    menghasilkan SVG pada ukuran yang tabel di atas sebutkan;
  - setiap artboard adalah **XML yang valid**, tidak menggambar elemen di luar
    kanvasnya, dan tidak menggambar bentuk berukuran nol;
  - lembar yang di-commit identik dengan keluaran `build.py`;
  - jumlah artboard yang disebut `README.md`, dokumen ini, dan lembar itu sama.

  Yang **tidak** diperiksa dan karenanya jangan diklaim: apakah hasilnya *terlihat*
  benar. Perender SVG di sandbox punya keterbatasan (gradien radial dan teks
  diskalakan berbeda), dan tidak ada perbandingan tangkapan layar di repo ini.

## Target implementasi: repo ini, Python + PyQt6

Keputusan perilaku yang menyertai modul pertama ada di
[`EXECUTION-PATH.md`](EXECUTION-PATH.md): tiga tingkat risiko, jalur konfirmasi
yang tidak bisa dipalsukan model, dan janji "3 tertahan" pada mode Fokus.


Keputusan: **tidak** ditulis ulang ke Tauri/React. Kedua puluh dua artboard digambar
stack-neutral dan berlaku apa adanya untuk implementasi Python.

### Bagian spesifikasi yang **sudah ada** di repo

| Kebutuhan spesifikasi | Modul yang ada | Baris |
|---|---|---|
| Tray + 6 item menu | `ui/tray.py` | 271 |
| Notifikasi + kebijakan 45 s | `core/notify.py` | 242 |
| Global hotkey (Ctrl+Space dst.) | `core/hotkey.py` | 532 |
| Gestur tangan | `core/hand_gesture.py`, `core/gesture_os.py` | 325 |
| Konfirmasi yang tidak bisa dipalsukan model | `core/confirm.py` | — |
| Riwayat percakapan/tugas | `core/history.py` | — |
| Memori personal | `memory/memory_manager.py` | 486 |
| STT lokal (faster-whisper, Vosk) | `core/stt.py` | 93 |
| Wake word | `core/wake_word.py` | — |
| TTS | `core/tts.py` | 442 |
| Plugin + manifest izin | `core/plugin_manifest.py`, `plugins/` | — |
| Clipboard | `actions/computer_control.py` (pyperclip, lazy) | — |

### Yang **belum** ada dan perlu modul baru

| Kebutuhan | Modul | Status |
|---|---|---|
| Tool registry | `core/tool_registry.py` | **belum** — sementara `risk_policy.register()` sudah bisa dipakai untuk mendeklarasikan tingkat |

### Sudah dikerjakan (dan diuji)

| Kebutuhan | Modul | Tes |
|---|---|---|
| Toast berantre + kapasitas + hitungan yang dibuang | `ui/toast_queue.py` | `tests/test_toast_queue.py` |
| Kartu toast 340 px + jendela tanpa fokus | `ui/toast_card.py`, `ui/toast_stack.py` | `tests/test_toast_card.py`, `tests/test_toast_stack.py` |
| Batas 3 saran/hari | `core/suggestion_quota.py` | `tests/test_suggestion_quota.py` |
| Risiko 3 tingkat, default `risky` | `core/risk_policy.py` | `tests/test_risk_policy.py` |
| Audit log terpisah dari `logs/jarvis.log` | `core/audit_log.py` | `tests/test_audit_log.py` |
| Mode Aktif/Fokus/Senyap | `core/presence_mode.py` | `tests/test_presence_mode.py` |
| Gerbang eksekusi: klasifikasi → catat → jalan/tahan | `core/action_gate.py` | `tests/test_action_gate.py` |
| Tingkat per panggilan (`computer_settings` ≠ satu tingkat) | `core/tool_risk.py` | `tests/test_tool_risk.py` |
| Sambungan gate ke `main.py` + daftar aksi berpagar sendiri | `main.py` | `tests/test_gate_wiring.py` |
| Orb overlay 146 px (board 1), hanya cincin yang bisa diklik; meredup di Fokus/Senyap | `ui/orb_overlay.py`, `ui/orb_place.py`, `ui/orb_canvas.py` | `tests/test_orb_overlay_board1.py`, `tests/test_orb_place.py` |
| Board 4: klik kiri → panel, klik kanan → menu cepat, drag menempel ke tepi | `ui/ambient_shell.py`, `ui/orb_snap.py` | `tests/test_orb_board4.py` |
| Board 05a: strip Fokus tanpa tenggat, tiga baris aksi sendiri, jeda penjadwalan yang tersimpan | `ui/tray_paint.py`, `ui/tray_panel_model.py`, `actions/proactive.py`, `ui/tray_panel_wiring.py` | `tests/test_focus_board23.py` |
| Startup: setiap permukaan benar-benar dibangun saat aplikasi dijalankan | `main.py`, `ui/lifecycle.py` | `tests/test_startup_board7.py` |
| Board 6: IZIN AKSES 72 px, LOG AKTIVITAS dari `core.audit_log`, Ekspor/Hapus yang menyentuh log yang sama dengan kartunya | `ui/tray_pages.py` (`build_permissions()`), `ui/tray_paint.py`, `ui/tray_panel_wiring.py` | `tests/test_tray_panel.py`, `tests/test_privacy_board27.py` |
| Board 05b: orb Senyap 18 px, bertitik, dan menulis namanya di bawah cincin | `ui/orb_paint.py`, `ui/orb_canvas.py` | `tests/test_quiet_board24.py` |
| Command bar Ctrl+Space, Esc mengembalikan fokus | `ui/command_bar.py` | `tests/test_command_bar.py` |
| Sambungan mode → orb, chord, dan baki | `ui/lifecycle.py`, `memory/config_manager.py` | `tests/test_presence_wiring.py` |

`core/undo_journal.py` **tidak dibuat**: `core/undo.py` sudah melakukan itu
(`push_undo`/`undo_last`, kedalaman 10). Menambah modul kedua hanya akan menjadi
salinan yang berbeda perilaku.

### Batasan platform yang harus diuji di Windows

- Orb: **hanya cincin yang menerima klik.** Keputusan ini berubah — dulu di sini
  tertulis bahwa orb sengaja TIDAK click-through dan klik di luar cincin ditolak
  oleh hit test. Penolakan itu terjadi SESUDAH jendela mengambil klik, jadi klik
  di sudut transparan hilang: desktop di bawahnya tidak pernah menerimanya.
  Board 1 menulis "overlay ±150 px, click-through", dan pemilik repo memilih
  artboard-nya. Sekarang jendela dipasangi mask (`ui/orb_place.overlay_mask`)
  seukuran lingkaran yang bisa diklik, jadi sudutnya tidak ada lagi untuk
  mengambil klik. `inside_hit_region` tetap berlaku sebagai jawaban kedua untuk
  klik yang memang sampai ke jendela — dua-duanya harus sepakat, dan itu diuji.
  Yang belum bisa dibuktikan: apakah window manager benar-benar menghormati
  `setMask` pada jendela frameless transparan di setiap platform.
- **Jendela orb 146 px, bukan 96 px.** `n01()` menggambar kotak `r × 2.6`. Yang
  membuat ini bukan soal selera: `paint_ring` menggambar titik alert amber pada
  `r × 2.24` = 62,7 px dari pusat, sedangkan setengah jendela 96 px hanya 48 px.
  Indikator "ada yang butuh Anda" tergambar di luar jendela dan terpotong, dan
  tidak ada tes yang membandingkan jangkauan painter dengan ukuran jendela.
  Angka itu sekarang diuji sebagai aritmatika di `tests/test_orb_overlay_board1.py`.
- **Orb bisa digeser dan posisinya diingat** (`orb_position` di
  `config/api_keys.json`). Posisi yang tersimpan di monitor yang sudah dicabut
  tidak dipulihkan: pusat orb harus berada di area layar yang tersedia, kalau
  tidak orb ada di tempat yang tidak bisa dijangkau — dan itu terlihat persis
  seperti aplikasi yang mati.
- Fokus kembali setelah Esc bergantung pada window manager; `FocusLedger`
  mencatat permintaan dan hasilnya, tetapi `activateWindow()` tidak melaporkan
  apakah berhasil.
- **Keputusan pemilik repo:** Fokus dan Senyap **meredupkan orb**, bukan hanya
  menahan notifikasi. Board 05b (28→18 px, cincin titik-titik) sekarang menjadi
  perilaku yang diuji, bukan asumsi.

- **Board 2: "sisanya antre" TIDAK diterapkan sebagai tumpukan yang tumbuh.**
  Artboard menulis "+2 lain dalam antrean", dan kata *antrean* berarti menunggu.
  Yang dipilih pemilik repo: kartu keempat **menggantikan yang tertua** dan
  jumlahnya diucapkan ("+2 lain dalam antrean"), karena antrean notifikasi yang
  tumbuh tanpa akhir di permukaan desktop adalah antrean yang tidak pernah
  dikosongkan siapa pun. Yang tidak boleh terjadi adalah diam-diam: angka itu
  ada supaya kehilangannya terlihat.
- **Kartu toast sekarang benar-benar digambar.** Sebelum toast dikerjakan
  (dulu "board 2"; nomor itu sekarang artboard command bar),
  `ui/toast_queue.py` hanya menyimpan aritmatika dan **tidak dipakai di mana
  pun** selain smoke test; satu-satunya yang dilihat pengguna adalah notifikasi
  OS dari `core/notify.py`. `ui/toast_card.py` menggambar kartunya dan
  `ui/toast_stack.py` adalah jendelanya. `core/notify.py` tetap ada dan tetap
  dipakai untuk notifikasi OS — keduanya menjawab pertanyaan berbeda: notifikasi
  OS untuk "jawabannya sudah jadi saat Anda di aplikasi lain", kartu untuk
  "berapa sisa kuota hari ini".

- **Klik kiri pada orb membuka PANEL, bukan command bar, dan itu disengaja.**
  Sebelumnya klik kiri membuka command bar (artboard 2, satu baris). Keputusan
  yang lalu — diambil dari artboard orb versi lama — adalah "KLIK KIRI — buka
  panel baki", jadi klik kiri sekarang membuka panel 460×660. Command bar tidak
  kehilangan jalannya: Ctrl+Space tetap ada (2), dan panel sendiri punya kolom
  perintah. Catatan lama yang menyebut orb sebagai pintu command bar sudah tidak
  berlaku.
- **Klik kanan punya menu sendiri: Aktif / Fokus / Senyap, Riwayat, Privasi,
  Keluar.** Artboard hanya menulis "menu cepat" tanpa daftar isi, jadi menu itu
  sengaja pendek: apa yang orang minta tepat di orb dan tidak lebih. Menu dibuat
  saat diminta dan dibuang saat ditutup — popup yang di-cache adalah popup yang
  menampilkan centang kemarin.
- **Drag menempel ke tepi dengan ambang 64 px.** Drop dalam 64 px dari sebuah
  sisi duduk di sisi itu pada jarak 24 px; drop di tengah tetap di tempat.
  Menempel saat pointer masih bergerak membuat orb melompat dari bawah tangan,
  jadi snap hanya terjadi saat dilepas.

### Board 05a — Fokus (toast ditahan)

- **Strip Fokus tidak menyebut tenggat, karena tidak ada tenggat.** Artboard
  menulis "Fokus aktif sampai 17.00", dan `17.00` itu **literal di dalam
  `ui/tray_paint.py`** — tidak ada satu pun durasi fokus di seluruh build. Pemilik
  memilih kalimat yang jujur ("Fokus aktif. Notifikasi ditahan sampai Fokus
  berakhir.") dan **menolak** dua alternatif: menambah timer 45 menit yang
  mengakhiri Fokus sendiri, dan membiarkan 17.00. Kunci i18n
  `ui.panel.focus.active_until` dihapus dari `id.json` dan `en.json`; tidak ada
  baris pengganti yang menyebut jam.
- **Empat baris "AKSI CEPAT" di artboard menjadi tiga baris nyata, dan "Ubah
  durasi" sengaja tidak digambar.** Baris itu membuka pengaturan untuk durasi yang
  tidak ada. Yang digambar: "Lihat yang tertahan" (dengan jumlah di kolom chord),
  "Akhiri fokus sekarang", "Jeda semua penjadwalan". Panel 460 px memberi blok itu
  empat baris; di Fokus baris keempat disembunyikan, bukan dihapus — mengubah
  jumlah widget akan menggeser setiap bagian di bawahnya 48 px.
- **"Lihat yang tertahan" hanya melihat.** Baris itu melaporkan jumlahnya dan
  tidak mengosongkan antrean: panel di atasnya berjanji isi antrean muncul
  *setelah* Fokus berakhir, dan rasa ingin tahu pengguna tidak boleh membatalkan
  janji itu. Yang melepas adalah keluar dari Fokus, lewat `presence_mode.set_mode`.
- **"Jeda semua penjadwalan" menjeda mesin yang benar-benar dipakai.**
  `ProactiveEngine` mendapat `pause()`/`resume()`/`toggle_pause()`, dan jedanya
  **disimpan di `config/api_keys.json`** supaya restart tidak membatalkan
  keputusan pengguna. Jeda tidak menyentuh jam pendinginan: lanjut setelah satu jam
  tidak boleh langsung memicu pesan, karena jeda bukan pesan.
- **Kalimat kuota kedua hanya ada di Fokus, dan angkanya dihitung.** "Dua sisanya
  ditahan sampai fokus berakhir" muncul dari `quota_note()` dengan `limit - used`
  dari kuota yang sama dengan baris di atasnya. Di luar Fokus kalimatnya kosong —
  di sana tidak ada yang ditahan, hanya belum terpakai. Kalimat ini duduk **di
  bawah** kartu saran, bukan di dalamnya: kartu board 5 dipatok 62 px oleh
  `tests/test_tray_geometry.py`, dan baris ketiga tidak muat tanpa mengubah kotak
  yang diukur board lain.

### Startup — kenapa JARVIS tidak muncul sama sekali

- **`main()` tidak pernah memanggil `ui.lifecycle.start_interface`.** Fungsi itu
  membangun baki, face bubble, orb, command bar, overlay suara, dan hotkey
  summon — semuanya. Pemanggilnya hanya tes. Jadi `python main.py` membuat satu
  `QApplication` tanpa jendela, menjalankan `app.exec()` di atas aplikasi kosong,
  dan menunggu mikrofon: proses yang hidup, mendengarkan, dan tidak bisa dilihat
  maupun ditutup selain lewat Task Manager. Satu-satunya jendela yang mungkin
  muncul adalah layar setup API key, karena `wait_for_api_key()` membukanya dari
  thread runner; setelah kunci disimpan, layar itu ditutup dan tidak ada apa pun
  yang menggantikannya.
- **Kenapa 2.344 tes hijau selama itu.** Setiap tes memanggil
  `lifecycle.start_interface(shell)` langsung. Tidak satu pun bertanya apakah
  aplikasi memanggilnya. Permukaan yang dibangun lalu tidak pernah ditampilkan
  dan permukaan yang tidak pernah dibangun sama-sama tidak terlihat dari dalam
  tes. Ini kelas yang sama dengan `_ready` yang tidak pernah menjadi `True` dan
  clamp mati di `snap_to_edge`: tes tidak bisa gagal karena tidak ada yang diuji.
- **Pemanggilan itu duduk di thread Qt, setelah `_launch` terpasang, sebelum
  `exec()`.** Sebelum `exec()` karena permukaan yang dibuat setelahnya tidak
  pernah sempat dilukis. Di thread Qt karena QWidget dibuat di thread yang
  menjalankan event loop. Setelah `_launch` karena `--hidden` dan tautan
  `jarvis://` dibaca oleh permukaan yang dibangun di dalamnya.
- **`--hidden` akhirnya berarti sesuatu, dan artinya dijaga.** Sebelumnya flag
  itu tidak berpengaruh karena tidak ada yang tampil. Sekarang ia menyembunyikan
  **wajah**, bukan orb: orb adalah satu-satunya permukaan yang membuka panel
  dengan klik (artboard 1), jadi menyembunyikannya akan membuat `--hidden` berarti
  "mulai tanpa cara mouse apa pun".
- **Satu permukaan yang gagal tidak boleh menjatuhkan yang lain.** Memindahkan
  pemanggilan ke `main()` menciptakan jalan baru untuk mati: exception yang lolos
  dari `start_interface` sekarang membunuh proses sebelum `exec()`. Tiga dari
  `start_*` tidak menangkap exception sendiri, dan mereka membuat objek Qt.
  Setiap permukaan sekarang punya pengamannya sendiri, dan kegagalannya dicatat
  dengan nama permukaannya.

### Board 6 — Izin & Privasi (dan mengapa 06a dipensiunkan)

- **MODE TAMU tidak digambar, dan itu keputusan, bukan kelalaian.** Artboard
  menggambar switch "Sembunyikan memori & riwayat" yang bisa diklik; `set_guest`
  hanya menulis "mode tamu belum ada" lalu mengembalikan False, dan paint
  berikutnya mengembalikan switch ke posisi semula. Pemilik memilih **menghapus
  section itu**, bukan menonaktifkannya: switch nonaktif tetap berjanji bahwa
  fiturnya ada dan pengguna belum diizinkan. Itu berbeda dari `screen` dan
  `microphone`, yang memang kemampuan nyata dan mesin yang memutuskan — dua itu
  tetap digambar, nonaktif, dengan alasannya. Fungsi `set_guest` dihapus, bukan
  dibiarkan sebagai no-op, dan ketiga kunci i18n-nya dihapus dari kedua bahasa.
- **"Hapus semua data lokal" menjadi "Hapus audit log lokal".** Tombol itu selalu
  hanya menghapus audit log: tidak menyentuh berkas riwayat percakapan, tidak
  menyentuh API key, dan tidak bisa menjangkau apa pun yang sudah terkirim ke
  model. Docstring-nya jujur sejak awal; labelnya tidak. Yang berubah labelnya —
  perilakunya sudah benar, dan tesnya membuktikan keduanya.
- **Setiap halaman punya dua barisnya sendiri.** Sebelumnya ketiga halaman
  menulis "JARVIS / Panel baki · mengikuti posisi taskbar", yaitu identitas
  APLIKASI, bukan halaman. `ui.panel.privacy.title` sudah ada di katalog dalam
  dua bahasa dan **tidak dipanggil oleh apa pun**. Judul dibaca dari snapshot,
  dan `paint()` menyesuaikannya dengan halaman yang sedang tampil — kalau tidak,
  judulnya basi pada klik Riwayat pertama.
- **Kartu artboard digambar.** `rect(24, 208, 412, 56)` di belakang tiap baris
  izin dan `rect(x, 102, 132, 62)` di belakang tiap indikator. Tanpa keduanya,
  empat baris izin terbaca sebagai satu paragraf, bukan empat keputusan terpisah.
  Kuncinya diberi awalan sendiri (`permx_*`, `indicator_*`) karena `GEOMETRY`
  yang lama adalah halaman utama artboard 5 dan dipatok `tests/test_tray_geometry.py`.
- **Stub Qt sekarang merekam geometri.** `setGeometry` dulu tidak menyimpan
  apa pun, jadi `card.x()` menjawab lewat `__getattr__` — sebuah lambda, bukan
  angka. Itu persis kelas kesalahan yang sudah ditulis di docstring `_RectF`:
  tes tidak bisa membedakan kartu di (24, 208) dari kartu di (0, 0). Itu sebabnya
  kartu yang tidak pernah dibuat pun bisa "lulus" pemeriksaan geometri.

### Board 05b — Senyap

- **Senyap digambar 18 px, bukan 14.** Artboard menulis sendiri "Orb menyusut
  28 → 18 px", dan 14 adalah angka yang masuk akal yang ditulis dari ingatan
  tentang artboard, bukan dari artboard. Itu kelas bug yang sama dengan "Fokus
  aktif sampai 17.00": angka ajaib yang tidak dibandingkan dengan gambarnya oleh
  satu tes pun.
- **Fokus menjadi 22 px, dan itu diturunkan, bukan dikarang.** Board 05b hanya
  mematok Senyap (18) dan tidak memberi ukuran untuk Fokus. Sebelum ini Fokus
  18. Membiarkan keduanya 18 membuat dua mode berbeda identik ukurannya, dan tes
  lama menuntut urutannya dengan alasan yang benar: "two states must not be
  distinguishable by hue alone". 22 berada di antara 28 dan 18, jadi ketiga
  ukuran terbaca sebagai urutan, bukan dua nilai dengan satu duplikat. Alpha
  juga menjaga urutan: 255 → 165 → 110.
- **Orb menulis namanya di bawah cincin.** Alasan board 05b sendiri adalah
  "status harus terbaca tanpa warna": meredupkan cincin, menghapus glow dan
  membuatnya bertitik adalah tiga perbedaan di kanal yang SAMA — kecerahan —
  dan di desktop gelap sebuah tangkapan layar tidak bisa membedakan orb Senyap
  dari orb Aktif. Kata bisa. Kosakata yang dipakai `ui.panel.mode.*`, kunci yang
  sudah ada di kedua katalog dan sudah dipakai kontrol segmen di baki — bukan
  kosakata kedua untuk tiga mode yang sama.
- **Label itu opt-in lewat tinggi yang tersedia.** `paint_ring` dipakai overlay
  desktop DAN HUD. Overlay selalu punya ruang (cincin 28 px menyisakan 45 px di
  dalam jendela 146 px; cincin 18 px menyisakan 55). HUD yang menggambar caption
  10 px di atas isinya sendiri adalah caption yang menghalangi, jadi labelnya
  hanya muncul saat pemanggil menyatakan ada ruang.
- **Caption tidak boleh menjatuhkan orb.** `draw_label` mengembalikan bool dan
  berhenti pada painter yang tidak punya `setFont`/`drawText`. Orb yang hilang
  karena captionnya tidak bisa digayakan adalah kegagalan yang lebih buruk
  daripada caption tanpa tracking.

### Board 14a — Risiko: konfirmasi

- **Judulnya BERISIKO, bukan "⚠  KONFIRMASI".** Dua kesalahannya berbeda kelas.
  Yang lama menuliskan keadaan dialognya ("ini konfirmasi" — sudah jelas dari dua
  tombol di bawahnya) alih-alih tingkat risikonya, dan menyisipkan glif yang
  tidak ada di artboard. Artboard menaruh kata itu di kiri atas dengan tracking
  2, warna amber, 10 pt: satu kata yang menjawab "seberapa berbahaya ini?"
  sebelum mata membaca judulnya.
- **"Tindakan ini tidak bisa diurungkan." adalah kalimat keselamatan, bukan
  hiasan.** Ia satu-satunya teks di dialog yang menyatakan AKIBAT, bukan isi
  permintaan. Ia tidak diterjemahkan lewat katalog karena ia harus ada bahkan
  ketika katalognya rusak — persis alasan `KEYS_HINT` juga konstanta. Artboard
  menulis "diurangkan" (salah ketik); yang dirilis "diurungkan".
- **Enter mengonfirmasi, Esc membatalkan — dan fokus awal tetap di Batal.**
  Artboard mencetak "Enter · Esc" di sudut, jadi diam-diam membuat Enter tidak
  melakukan apa-apa berarti tombolnya berbohong. Yang menjaga properti lama
  ("Enter nyasar tidak boleh mengeksekusi") bukan lagi tidak adanya handler,
  melainkan FOKUS AWAL: Enter tanpa menyentuh apa pun diserap tombol Batal.
- **ASAL PERMINTAAN harus benar, bukan tebakan.** Satu-satunya kalimat di dialog
  ini yang bisa menjadi dusta adalah yang menyebut siapa yang meminta. Karena
  itu sumbernya dicatat di pintunya masing-masing (`core/input_source`, dipanggil
  dari `_on_text_command` dan dari transkripsi input), bukan disimpulkan di
  dalam banner. Nota penting: penandaan suara menempel pada TRANSKRIPSI, bukan
  pada chunk audio — setiap chunk audio juga berbunyi saat ada suara ruangan,
  dan itu akan menulis "Perintah suara" untuk permintaan yang datang dari plugin.
  Ketika tidak ada yang tercatat, dialog berkata "Tidak diketahui" dan itu
  jawaban yang benar.
- **Store-nya tidak boleh mengimpor apa pun.** `core/input_source` dipanggil dari
  callback audio; `ui/confirm_banner` mengimpor PyQt6 di level modul. Menaruh
  store di sana berarti mesin tanpa Qt melempar pengecualian di dalam mikrofon.
- **Jamnya diambil saat pertanyaan ditampilkan, dan diperbarui saat banner
  dipakai ulang.** Dua bug ditemukan tes, bukan ditulis: `set_title` dulu keluar
  lebih awal ketika tidak ada detail (jalur yang paling umum), sehingga banner
  yang dipakai ulang mempertahankan asal DAN jam pertanyaan sebelumnya — satu-
  satunya baris di dialog ini yang menjadi dusta bila basi.
- **Baris detail selalu dibangun, hanya disembunyikan.** Versi yang membangunnya
  hanya bila konstruktor menerima detail membuat baris artboard
  ("Lampiran: anggaran.xlsx · 3 penerima") mustahil tampil di jalur nyata:
  `build_confirm_window()` memanggil konstruktor dengan `""` dan detailnya baru
  datang lewat `set_title`.
- **Yang belum terbukti:** dialog ini belum pernah dirender Qt sungguhan di sini.
  Geometri, ukuran font, dan perilaku fokus yang sesungguhnya tetap belum diuji;
  yang diuji adalah widget yang dibangun, teksnya, dan handler tombolnya.
