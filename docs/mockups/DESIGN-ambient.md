# JARVIS — Sistem Desain Ambient

Dua berkas, satu sumber:

| Berkas | Isi |
|---|---|
| `jarvis-design-system.html` | **22 artboard**, SVG inline, tanpa jaringan. Buka langsung. |
| `build.py` | Generator lembar itu. Ubah angka di sini, jalankan `python docs/mockups/build.py`, HTML ditulis ulang. |

Artboard **tidak** memuat penjelasan desain. Semua asumsi, rasio kontras, dan alasan
ada di bagian Ringkasan **di dalam** HTML, setelah artboard 22.

## Tambahan: shell ambient (Fase 1)

Artboard **1–6** dan **23–28** menggambar perilaku jendela sesuai spesifikasi Tauri:

| # | Artboard | Yang ditunjukkan |
|---|---|---|
| 1 | Orb overlay | Overlay ±150 px transparan, hanya orb 56 px yang menerima klik |
| 2 | Toast | Tiga kartu menumpuk; yang keempat **menggantikan yang tertua** dan dihitung (bukan antre — lihat catatan di bawah), batas 3 saran/hari |
| 3 | Command bar | Ctrl+Space, input fokus, Esc kembali ke jendela sebelumnya |
| 4 | Orb | Klik kiri/kanan/seret, empat status dibaca dari isi orb |
| 5 | Panel baki | Mengikuti taskbar, segmented Aktif/Fokus/Senyap |
| 6 | Overlay suara + kamera | Glow tepi hanya saat aktif, preview gestur kecil |
| 23 | Fokus | Toast **ditahan**, bukan dibuang — jumlahnya bisa dilihat |
| 24 | Senyap | Orb menyusut 28→18 px, glow hilang, cincin jadi titik |
| 25 | Konfirmasi risiko | Dirender UI tepercaya, tombol besar, ada asal permintaan |
| 26 | Riwayat tugas | Urungkan/ulang, audit log bertimestamp, ekspor |
| 27 | Izin & Privasi | Indikator mikon/kamera/layar, izin eksplisit, mode tamu |
| 28 | Tema terang | Panel baki versi terang dengan token terang |

## Ringkasan isi

| Kelompok | Artboard |
|---|---|
| Desktop 1280×720 | 1 desktop ambient · 2 command bar · 3 kontrol gestur · 4 mode suara |
| Panel 460×640 | 5 baki · 6 izin · 7 onboarding (2/4) · 8 riwayat · 9 memori · 10 detail memori · 11 rutinitas · 12 alat cepat · 13 dikte/baca/form · 14 keamanan · 15 aksesibilitas · 16 plugin & ponsel · 17–18 tema terang |
| Lainnya | 19 peta gestur 720×640 · 20 status orb 1280×300 · 21 brand & ikon 1280×640 · 22 installer 720×480 |

## Prinsip yang dipegang di setiap artboard

1. **Ambient dulu.** Orb kecil + ikon baki. Jendela besar hanya saat dipanggil
   (artboard 1, 5, 22).
2. **Tidak merebut fokus.** Toast punya dua tombol dan hilang sendiri 8 detik (artboard 1).
3. **Dipanggil kapan saja.** Ctrl+Space (2), kata kunci, dan gestur (3, 19).
4. **Transparan soal privasi.** Empat izin eksplisit, log aktivitas, tombol hapus riwayat
   (6, 7, 18).
5. **Aman.** Tiga tingkat risiko; berisiko selalu minta konfirmasi fisik (14).

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

- Lembar ini **konsep**, belum kode. Tidak ada berkas `core/` atau `ui/` yang disentuh.
- Perender SVG di sandbox ini punya keterbatasan (gradien radial dan teks diskalakan
  berbeda), jadi gambar pratinjau bisa sedikit berbeda dari peramban. Geometri, warna,
  dan teks sudah diperiksa secara terprogram: 22 artboard valid, tanpa elemen meluber,
  tanpa bentuk berukuran nol.

## Target implementasi: repo ini, Python + PyQt6

Keputusan perilaku yang menyertai modul pertama ada di
[`EXECUTION-PATH.md`](EXECUTION-PATH.md): tiga tingkat risiko, jalur konfirmasi
yang tidak bisa dipalsukan model, dan janji "3 tertahan" pada mode Fokus.


Keputusan: **tidak** ditulis ulang ke Tauri/React. Artboard shell (1–6, 23–28) digambar
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
| Board 23: strip Fokus tanpa tenggat, tiga baris aksi sendiri, jeda penjadwalan yang tersimpan | `ui/tray_paint.py`, `ui/tray_panel_model.py`, `actions/proactive.py`, `ui/tray_panel_wiring.py` | `tests/test_focus_board23.py` |
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
  menahan notifikasi. Board 24 (28→18 px, cincin titik-titik) sekarang menjadi
  perilaku yang diuji, bukan asumsi.

- **Board 2: "sisanya antre" TIDAK diterapkan sebagai tumpukan yang tumbuh.**
  Artboard menulis "+2 lain dalam antrean", dan kata *antrean* berarti menunggu.
  Yang dipilih pemilik repo: kartu keempat **menggantikan yang tertua** dan
  jumlahnya diucapkan ("+2 lain dalam antrean"), karena antrean notifikasi yang
  tumbuh tanpa akhir di permukaan desktop adalah antrean yang tidak pernah
  dikosongkan siapa pun. Yang tidak boleh terjadi adalah diam-diam: angka itu
  ada supaya kehilangannya terlihat.
- **Kartu toast sekarang benar-benar digambar.** Sebelum board 2 dikerjakan,
  `ui/toast_queue.py` hanya menyimpan aritmatika dan **tidak dipakai di mana
  pun** selain smoke test; satu-satunya yang dilihat pengguna adalah notifikasi
  OS dari `core/notify.py`. `ui/toast_card.py` menggambar kartunya dan
  `ui/toast_stack.py` adalah jendelanya. `core/notify.py` tetap ada dan tetap
  dipakai untuk notifikasi OS — keduanya menjawab pertanyaan berbeda: notifikasi
  OS untuk "jawabannya sudah jadi saat Anda di aplikasi lain", kartu untuk
  "berapa sisa kuota hari ini".

- **Board 4 mengubah arti klik kiri pada orb, dan itu disengaja.** Sebelumnya
  klik kiri membuka **command bar** (board 3, satu baris). Board 4 menulis
  "KLIK KIRI — buka panel baki", jadi klik kiri sekarang membuka panel 460×660.
  Command bar tidak kehilangan jalannya: Ctrl+Space tetap ada (board 3), dan
  panel sendiri punya kolom perintah. Catatan lama di board 1 yang menyebut orb
  sebagai pintu command bar sudah tidak berlaku.
- **Klik kanan punya menu sendiri: Aktif / Fokus / Senyap, Riwayat, Privasi,
  Keluar.** Artboard hanya menulis "menu cepat" tanpa daftar isi, jadi menu itu
  sengaja pendek: apa yang orang minta tepat di orb dan tidak lebih. Menu dibuat
  saat diminta dan dibuang saat ditutup — popup yang di-cache adalah popup yang
  menampilkan centang kemarin.
- **Drag menempel ke tepi dengan ambang 64 px.** Drop dalam 64 px dari sebuah
  sisi duduk di sisi itu pada jarak 24 px; drop di tengah tetap di tempat.
  Menempel saat pointer masih bergerak membuat orb melompat dari bawah tangan,
  jadi snap hanya terjadi saat dilepas.

### Board 23 — Fokus (toast ditahan)

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
