# Desain UI Lengkap — MARK LVI (JARVIS)

> Dokumen ini adalah **peta desain UI untuk seluruh fitur yang ada**, plus
> **rekomendasi fitur baru** yang bisa menyempurnakan asisten AI ini.
> Setiap klaim didasarkan pada apa yang ada di repo (`ui/`, `docs/mockups/`,
> `readme.md`, `docs/verification.md`), bukan asumsi.
>
> Tanggal: 2026-11-24 · Branch: `arena/a905a8af-mark-lvi`

---

## 1. Prinsip Desain

Desain baru harus mempertahankan empat sifat yang sudah menjadi identitas
proyek ini, dan menjadikannya sebagai *North Star*:

1. **Ambient, bukan invasif.** JARVIS hadir saat dibutuhkan, menghilang saat
   tidak. Orb yang memudar saat senyap, toast yang ditahan saat fokus.
2. **Jujur tentang apa yang terjadi.** Setiap hasil tool menjawab *apa yang
   diamati*, bukan apa yang dicoba: `done` = diverifikasi, `unverified` =
   permintaan dikirim tapi tidak bisa dikonfirmasi. UI harus menunjukkan
   status ini, bukan memuluskannya.
3. **Keamanan terlihat.** Konfirmasi risiko, undo, izin mikrofon/kamera,
   log aktivitas — semuanya memiliki permukaan sendiri yang eksplisit.
4. **Dapat dipercaya secara privat.** Mode lokal tidak boleh terlihat seperti
   fitur "kurang". Jika session sepenuhnya di mesin, UI harus mengatakannya.

---

## 2. Token Desain (Design Tokens)

Sumber: `ui/theme.py` (class `C`), `ui/tray_theme.py` (`PALETTES`),
`docs/mockups/README.md` (geometri).

### 2.1 Warna

| Token | Nilai | Pemakaian |
|---|---|---|
| `BG` | `#171719` | Latar utama / desktop ambient |
| `PANEL` | `#222224` | Permukaan panel (baki, kartu) |
| `PANEL2` | `#28282b` | Permukaan sekunder / input |
| `BORDER` | `#414146` | Garis halus antar permukaan |
| `BORDER_A` | `#55555c` | Garis yang lebih terlihat |
| `PRI` | `#4b9fff` | Primarer biru — fokus, orb, tombol utama |
| `PRI_DIM` / `PRI_GHO` | `#3675bd` / `#24364c` | Biru redup & glow latar |
| `ACC` | `#ff6b00` | Aksen oranye — peringatan, highlight |
| `ACC2` | `#ffcc00` | Aksen kuning — status netral/informasi |
| `GREEN` / `GREEN_D` | `#00ff88` / `#00aa55` | Status sukses / terverifikasi |
| `RED` / `MUTED_C` | `#ff3355` / `#ff3366` | Risiko, error, penolakan |
| `TEXT` / `TEXT_DIM` / `TEXT_MED` | `#ededf2` / `#9b9ba4` / `#b8b8c0` | Teks utama / sekunder / tersier |
| Desktop chrome | `#15212f` / `#1b2a3b` / `#0b1725` / `#3b5269` | Panel desktop, sidebar, bar, border |
| Desktop text | `#eef5fd` / `#aabbd0` | Teks desktop / redup |

### 2.2 Tipografi

- Font UI: **sans-serif modern** (Courier New untuk data teknis/log, sesuai
  aturan `AGENTS.md`: `QFont("Courier New", size)` untuk angka dan log).
- Skala (dari lembar desain artboard 21): ukuran teks tiga tingkat — besar
  (judul panel), normal (isi), kecil (caption, log, timestamp).
- Hierarki: judul panel > label bidang > isi > caption. Jangan lebih dari
  tiga tingkat dalam satu permukaan.

### 2.3 Geometri & Elevasi

| Komponen | Ukuran | Sumber |
|---|---|---|
| Orb | 146 px (dengan titik alert) | `ui/orb_paint.py` |
| Command bar | 640 × 184 px | `ui/command_bar.py` |
| Toast card | 340 px | `ui/toast_card.py` |
| Panel baki | 460 px lebar | `ui/tray_pages.py` |
| Radius sudut | 8–10 px (tombol/kartu), 5 px (pane tab) | `ui/theme.py` |
| Glow orb | gradien radial `PRI_GHO` → transparan | `ui/orb_paint.py` |

Elevasi: semua permukaan menggunakan **translusi** (kelas `C.PANEL`) dengan
garis `BORDER`, bukan bayangan pekat — supaya tidak bertabrakan dengan glow
ambient. Glow hanya dipakai untuk orb dan status aktif.

### 2.4 Gerak & Animasi

- **Reduce motion** adalah toggle nyata (`ui/pages_admin.py`), bukan
  asumsi. Desain harus tetap berbahasa tanpa animasi.
- Orb: pulsa halus saat mendengar, memudar & menyusut saat senyap (artboard
  05b), empat status orb dibedakan lewat **siluet**, bukan warna (artboard 20).
- Transisi: 200–300 ms, ease-out, tanpa bouncing berlebihan.

### 2.5 Aksesibilitas

- Dua palet: **dark** (default) dan **light** (`PALETTES["light"]`).
- Kontras: kedua palet harus melewati WCAG AA. Menambah opsi **high-contrast**
  adalah rekomendasi fitur baru (lihat §5).
- Ukuran teks dapat diubah (`ui/pages_admin.py` sudah punya toggle).
- Status tidak boleh hanya bergantung pada warna — gunakan siluet, ikon,
  dan teks (aturan "empat status orb" sudah menegakkan ini).

---

## 3. Inventori Komponen (yang sudah ada)

| Komponen | File | Kegunaan |
|---|---|---|
| Orb + glow + status | `ui/orb_canvas.py`, `ui/orb_overlay.py`, `ui/orb_paint.py`, `ui/orb_place.py`, `ui/orb_snap.py` | Identitas utama, status sesi |
| Command bar | `ui/command_bar.py`, `ui/command_paint.py` | Input perintah + hasil + titik risiko |
| Panel baki (tray) | `ui/tray_panel.py`, `ui/tray_panel_model.py`, `ui/tray_panel_wiring.py`, `ui/tray_paint.py`, `ui/tray_theme.py`, `ui/tray.py`, `ui/tray_pages.py` | Navigasi utama semua halaman |
| Toast | `ui/toast_card.py`, `ui/toast_queue.py`, `ui/toast_stack.py`, `ui/notify_bridge.py` | Notifikasi sementara |
| Konfirmasi risiko | `ui/confirm_banner.py` | Persetujuan untuk aksi berbahaya |
| Wajah / avatar | `ui/face_bubble.py`, `ui/face_canvas.py`, `ui/avatar*.py` (core) | Ekspresi asisten |
| Mode suara | `ui/voice_overlay.py`, `ui/voice_paint.py`, `ui/voice_wiring.py`, `ui/voice_hand.py` | Layar penuh saat berbicara |
| Ambient shell | `ui/ambient_shell.py`, `ui/shell.py`, `ui/lifecycle.py` | Layar utama yang hidup |
| Halaman | `ui/pages_access.py`, `ui/pages_actions.py`, `ui/pages_admin.py`, `ui/pages_build.py`, `ui/pages_memory.py`, `ui/pages_more.py`, `ui/pages_people.py`, `ui/pages_paint.py` | 22 artboard dalam bentuk halaman |
| Setup & installer | `ui/setup_screen.py`, `ui/setup_window.py` | Onboarding kunci API |
| Hand feed (gestur) | `ui/hand_feed.py` | Pratinjau kamera + kerangka tangan |

---

## 4. Desain Per Layar — Semua Fitur yang Ada

22 artboard di `docs/mockups/jarvis-design-system.html` adalah **daftar
lengkap** permukaan UI. Berikut desain per layar, dengan status implementasi
(dari `docs/mockups/NOT-IN-MOCKUP.md`).

### Board 1 — Desktop ambient (utama)
- **Apa yang ditampilkan:** desktop contoh, orb 56 px + glow di pojok,
  satu toast.
- **Desain:** latar `BG`, orb di pojok kanan bawah dengan glow radial
  `PRI_GHO`, ring waveform kecil di sekeliling orb saat listening. Toast
  muncul di sisi kiri atas, 340 px, auto-dismiss.
- **Interaksi:** klik orb → buka panel baki; klik kosong → fokus ke desktop.
- **Status:** ✅ terimplementasi (`orb_paint`, `orb_overlay`).

### Board 2 — Command bar
- **Apa yang ditampilkan:** kotak 640×184, gradien, tiga baris hasil dengan
  titik risiko.
- **Desain:** input di atas, hasil di bawah; setiap hasil punya **titik
  risiko** (hijau = verified, kuning = unverified, merah = gagal).
- **Interaksi:** ketik perintah → hasil muncul → pilih → eksekusi; titik
  risiko adalah **bahasa jujur** dari proyek (lihat prinsip §1).
- **Status:** ✅ terimplementasi (`ui/command_bar.py`).

### Board 3 — Kontrol gestur
- **Apa yang ditampilkan:** tile kamera 320×236, kerangka tangan 21 joint,
  pil gestur aktif.
- **Desain:** pratinjau kamera gelap dengan kerangka tangan berwarna `PRI`,
  pil status di bawah tile.
- **Status:** ✅ terimplementasi (`ui/hand_feed.py`, di dalam jendela suara).

### Board 4 — Mode suara
- **Apa yang ditampilkan:** glow tepi layar penuh, orb, pil transkrip, lima
  bar level.
- **Desain:** tepi layar ber-glow `PRI`, orb di tengah, transkrip sebagai
  pil transparan di bawah orb, lima bar level suara di atasnya.
- **Interaksi:** barge-in memotong bicara; bar level memberi feedback
  langsung.
- **Status:** ✅ terimplementasi (`ui/voice_paint.py`, `ui/voice_overlay.py`).

### Board 5 — Panel baki (pusat navigasi)
- **Apa yang ditampilkan:** 460×640, segmen navigasi, empat aksi cepat,
  percakapan, tiga izin, kolom perintah.
- **Desain:** header dengan segmen (Orb / Riwayat / Memori / Alat /
  Pengaturan), empat tile aksi cepat ber-radius 10 px, area percakapan,
  daftar izin, command input di bawah.
- **Interaksi:** navigasi segmen mengubah halaman di bawah.
- **Status:** ✅ terimplementasi (`ui/tray_pages.py`, `ui/tray_panel.py`).

### Board 6 — Izin & privasi
- **Apa yang ditampilkan:** empat izin akses dengan kartu (72 px pitch),
  log aktivitas bertimestamp, Ekspor/Hapus.
- **Desain:** kartu izin (mikrofon, kamera, layar, folder) dengan toggle
  dan deskripsi dampak; di bawahnya log aktivitas; di bawahnya tombol
  Ekspor log / Hapus memori.
- **Status:** ✅ terimplementasi (`build_permissions()`).

### Board 7 — Onboarding
- **Apa yang ditampilkan:** layar izin mikrofon, tiga kalimat privasi,
  dua tombol.
- **Desain:** layar tengah dengan orb besar, tiga kalimat privasi, tombol
  "Izinkan" / "Tidak, terima kasih". Tombol X ditolak selama belum disimpan
  dan menjelaskan di layar (sudah diterapkan di `ui/setup_window.py`).
- **Status:** ⚠️ **satu langkah, bukan empat** — hanya mic consent yang
  ditanyakan. Empat langkah pada artboard belum ada (lihat §5).

### Board 8 — Riwayat tugas
- **Apa yang ditampilkan:** enam baris hari ini, status per baris,
  saring/pulihkan, hapus.
- **Desain:** daftar baris per tugas dengan status chip (verified /
  unverified / gagal), tombol saring, pulihkan (undo), hapus.
- **Status:** ✅ terimplementasi (`build_history()`).

### Board 9 — Memori personal
- **Apa yang ditampilkan:** enam fakta tentang pengguna, "12 hal yang
  JARVIS ingat".
- **Desain:** daftar fakta dengan kategori chip; jika lebih dari yang
  muat, ada tombol "lihat semua" yang membuka halaman lengkap.
- **Status:** ✅ terimplementasi (`build_memory()`).

### Board 10 — Detail memori
- **Apa yang ditampilkan:** satu memori: isi, sumber, keyakinan, dipakai
  oleh.
- **Desain:** tiga bidang (isi, sumber, keyakinan) + "dipakai oleh" —
  jika tidak disimpan, halaman menggantinya dengan teks yang mengatakan
  tidak disimpan (desain **jujur**, tidak mengarang persentase).
- **Status:** ✅ terimplementasi (`build_memory_one()`), dengan catatan
  store tidak punya sumber/keyakinan.

### Board 11 — Rutinitas & saran
- **Apa yang ditampilkan:** tiga rutinitas aktif dengan jadwal, tiga saran
  proaktif.
- **Desain:** kartu rutinitas dengan jadwal + status, kartu saran proaktif
  dengan tombol terima/tolak.
- **Status:** ✅ **rutinitas terjadwal nyata** — `memory/routine_store.py`
  menyimpan daftar, `core/routines.py` kebijakan murni (parsing/validasi/due),
  `core/routine_scheduler.py` thread yang menjalankan yang due, board 11
  menggambar hingga tiga kartu dengan jeda/hapus + builder satu baris. Sektor
  saran proaktif di bawah tetap seperti semula (engine saran belum ada).

### Board 12 — Alat cepat & clipboard
- **Apa yang ditampilkan:** tiga alat tersering, clipboard cerdas, cari
  berkas bahasa alami.
- **Desain:** tile alat terpakai, card clipboard (dengan "Tandai aman"),
  input cari berkas.
- **Status:** ✅ sebagian (clipboard + cari berkas nyata; **susun jendela
  tidak ada**).

### Board 13 — Dikte · baca layar · isi form
- **Apa yang ditampilkan:** tiga panel: dikte, pembaca layar, isi form
  dengan tinjau dulu.
- **Desain:** tiga kartu besar dengan ikon dan tombol aktif; card isi form
  memiliki pratinjau sebelum mengisi.
- **Status:** ✅ **isi form terimplementasi** — policy murni
  `core/form_fill.py` (validasi halaman + plan + gate tinjau dulu), adapter
  `actions/browser_form.py` ke session browser yang ada, UI builder di halaman
  Bantuan (URL + 3 field + tombol tinjau & terapkan). Lihat §5.4.

### Board 14 — Keamanan
- **Apa yang ditampilkan:** tiga tingkat risiko, mode tamu, izin
  layar/kamera, kontrol OS.
- **Desain:** tiga kartu tingkat risiko (rendah/sedang/tinggi) dengan jumlah
  aksi yang perlu konfirmasi; card mode tamu; toggle layar/kamera; kontrol
  OS.
- **Status:** ⚠️ **mode tamu belum boleh ditampilkan** (pemilik: belum ada
  yang membuat seluruh permukaan berhenti membaca memori) — rekomendasi
  §5. OS-control switch belum ada backend.

### Board 15 — Bahasa & gestur
- **Apa yang ditampilkan:** bahasa UI, ukuran teks, kontras, kurangi
  animasi, gestur kustom.
- **Desain:** dropdown bahasa, slider ukuran teks, toggle kontras, toggle
  kurangi animasi, daftar gestur.
- **Status:** ✅ sebagian (bahasa, ukuran teks, **kontras nyata** —
  kontrol segmen Standar/Tinggi yang menukar ke palette `high`, §5.9;
  kurangi animasi nyata; **gestur kustom belum** — rebinding belum ada).

### Board 16 — Plugin & ponsel
- **Apa yang ditampilkan:** plugin aktif, sinkron ponsel, kode pasangan.
- **Desain:** daftar plugin dengan toggle (aktif otomatis saat file
  ada), card sinkron ponsel, card kode pasangan.
- **Status:** ✅ **pairing ponsel terimplementasi** — policy murni
  `core/phone_pairing.py` (mint kode satu-kali-pakai, consume dengan
  clock terinjeksi, scope command/read, handoff), UI board 16 (tombol
  buat kode / pasang / putus + kode pasangan nyata + status kartu),
  i18n dua bahasa. Dashboard HP tetap surface terpisah
  (`dashboard/server.py`); card ini sekarang pairing via policy. Lihat §5.6.

### Board 17 — Tema terang (panel)
- **Apa yang ditampilkan:** panel 5 dalam token terang dengan sakelar.
- **Desain:** palet light dengan skema yang sama; sakelar tema tiga
  keadaan (gelap / terang / auto) di header.
- **Status:** ✅ terimplementasi (`PALETTES["light"]`, `ui/tray_theme.py`).

### Board 18 — Tema terang (izin)
- **Apa yang ditampilkan:** panel 6 dalam token terang.
- **Status:** ⚠️ **token hanya dicek dengan tes** — belum ada yang benar-
  benar melihat tampilannya. Rekomendasi: verifikasi visual manual (lihat
  roadmap).

### Board 19 — Peta gestur
- **Apa yang ditampilkan:** enam gestur dengan bentuk tangannya.
- **Desain:** 720×640, gambar referensi — bukan kontrol (permukaan
  dokumentasi).
- **Status:** ✅ gambar referensi (`build_gestures()`).

### Board 20 — Status orb
- **Apa yang ditampilkan:** empat status orb, dibedakan lewat siluet.
- **Desain:** idle / listening / speaking / error dibedakan siluet, bukan
  hanya warna (aksesibilitas).
- **Status:** ✅ terimplementasi (`paint_orb`).

### Board 21 — Brand & ikon
- **Apa yang ditampilkan:** ikon aplikasi, empat ikon baki, swatch, skala
  huruf, komponen.
- **Desain:** lembar spesifikasi — bukan kontrol; swatch diambil dari
  palette program sendiri sehingga tidak bisa menyebut warna yang tidak
  digunakan.
- **Status:** ✅ lembar spesifikasi (`build_brand()`).

### Board 22 — Installer / presensi
- **Apa yang ditampilkan:** layar pemasangan memilih mode presensi.
- **Desain:** tiga pilihan mode presensi (desktop penuh / baki / headless)
  dengan penjelasan; setelah dipilih, masuk ke setup.
- **Status:** ⚠️ **hanya pemilihan mode**, bukan installer penuh —
  tidak ada UI instalasi dependensi.

### Keadaan khusus (state)
- **05a Fokus** — toast ditahan dan dihitung.
- **05b Senyap** — orb memudar dan menyusut.
- **08a Riwayat + Urungkan** — undo dari riwayat.
- **14a Konfirmasi risiko** — banner persetujuan sebelum aksi berbahaya.
- **17a Panel terang** — versi terang panel.

Semua keadaan ini harus tetap dipertahankan dalam desain baru.

---

## 5. Rekomendasi Fitur Baru

Fitur baru diurut berdasarkan **dampak × kemudahan**, dan masing-masing
disertakan: mengapa, permukaan UI-nya, serta risikonya. Semuanya
menyempurnakan prinsip §1.

### 5.1 Verifikasi Suara (Voice Verification) — *prioritas tinggi*
- **Mengapa:** Pemilik ingin JARVIS **memverifikasi suara pengguna** saat
  dijalankan — pintu masuk biometrik sebelum asisten menjawab perintah.
  Menggantikan Mode Tamu (ditolak: Mode Tamu dihapus, arah keamanan
  berubah ke verifikasi identitas suara).
- **UI:** Layar pendaftaran (rekam N sampel + level meter + playback
  cek), status chip "Terverifikasi" di header/panel, kartu Verifikasi
  Suara di halaman Keamanan (board 14), dan keadaan orb "verify".
- **Risiko:** Biometrik sensitif — sampel suara disimpan **lokal**, tidak
  ke jaringan; penolakan echo (suara JARVIS sendiri) agar tidak tertipu
  TTS-nya sendiri.
- **Effort:** Sedang (policy murni + engine lokal + pendaftaran +
  integrasi gate sesi). Detail: `design/SPEC-VOICE-VERIFICATION.md`.

### 5.2 Health / Status panel (Observabilitas) — *prioritas tinggi*
- **Mengapa:** `tools_diag.py` sudah ada untuk mendiagnosis hang, tapi
  pengguna tidak melihatnya. Asisten AI yang "jujur" harus bisa melaporkan
  kondisinya sendiri: kuota provider, latensi, kesehatan perangkat audio,
  mic/kamera, CPU/mem, status ladder model.
- **UI:** Halaman baru "Kesehatan" di panel baki: kartu status (provider
  aktif, kuota, latensi rata-rata), kartu perangkat (mikrofon, speaker,
  kamera), indikator CPU/mem, tombol "Diagnostics" yang menjalankan
  `tools_diag` dan menampilkan hasil ringkas.
- **Risiko:** Rendah. Data sudah ada, hanya perlu dikumpulkan.
- **Effort:** Sedang.

### 5.3 Rutinitas terjadwal dengan builder — *prioritas tinggi*
- **Mengapa:** Artboard 11 menggambar tiga rutinitas terjadwal, tapi
  hanya rutinitas proaktif yang ada. Ini adalah **gap antara gambar dan
  kenyataan** terbesar di panel.
- **UI:** Halaman Rutinitas: daftar rutinitas dengan jadwal, tombol
  "Buat rutinitas", builder berbahasa alami ("setiap hari jam 07,
  bacakan ringkasan dan cek gmail") → pratinjau tersusun → simpan.
  Setiap rutinitas punya status dan tombol nonaktif sementara.
- **Risiko:** Scheduling di background; perlu validasi jadwal.
- **Effort:** Sedang–besar.
- **Status:** **sudah diimplementasi** — store + kebijakan murni + scheduler
  + integrasi sesi + UI board 11. Builder adalah satu baris jadwal (bukan NLU
  penuh); parsing jadwal Indonesia sederhana dan konservatif.

### 5.4 Isi form (form filling) dengan tinjau dulu — *selesai*
- **Mengapa:** Artboard 13 menggambarnya. Sekarang punya backend.
- **UI:** Card "Isi form" di halaman Bantuan (board 13): field URL halaman,
  tiga field nilai yang dapat diedit, pratinjau status, tombol "Tinjau &
  terapkan". **Tinjau dulu** adalah prinsip keamanan: plan dibangun,
  ditinjau (`FormFillPlan.review()`), baru diterapkan ke browser.
- **Backend:** `core/form_fill.py` (policy murni, tidak ada I/O) +
  `actions/browser_form.py` (adapter ke `_BrowserSession.fill_form`).
  Hanya halaman `https://` yang dapat diisi; nilai disanitasi; plan yang
  belum ditinjau menolak untuk diterapkan.
- **Risiko:** Medium — berinteraksi dengan aplikasi lain.
- **Effort:** Selesai.

### 5.5 Ringkasan sesi & timeline tercari — *prioritas menengah*
- **Mengapa:** Riwayat ada (board 8), tapi "tadi kita bicara apa" belum
  bisa dijawab dari transkrip secara terstruktur. Ini melengkapi prinsip
  **jujur** dan memory.
- **UI:** Halaman Riwayat diperluas: pencarian teks, filter waktu, dan
  card "Ringkasan hari ini" yang dihasilkan dari transkrip. Klien bisa
  klik ringkasan → lompati ke transkrip asli.
- **Risiko:** Ringkasan model harus ditandai sebagai ringkasan, bukan
  transkrip.
- **Effort:** Sedang.

### 5.6 Handoff ponsel (lanjutkan percakapan) — *sebagian: pairing selesai*
- **Mengapa:** Dashboard ponsel ada, tapi terpisah. Saat pengguna pergi
  dari desktop, ia harus memulai percakapan baru di ponsel.
- **UI:** Pada dashboard ponsel dan desktop: tombol "Lanjutkan di ponsel"
  / "Lanjutkan di desktop" dengan daftar sesi aktif. Setelah pairing,
  session berpindah dengan konteks yang sama.
- **Backend (pairing selesai):** `core/phone_pairing.py` policy murni —
  mint kode satu-kali-pakai (8 karakter, alfabet tanpa O/I/L/0/1, TTL 5
  menit, satu kode hidup), consume dengan validasi expiry/one-time/scope,
  catat device dengan scope command/read, dan gate handoff berdasarkan
  scope. UI board 16: tombol buat kode/pasang/putus, kode pasangan nyata,
  status kartu. **Transfer konteks (memory + riwayat) adalah transport,
  belum diimplementasi** — pairing dan gate handoff-nya sudah.
- **Risiko:** Konteks harus ditransfer dengan aman (memory + riwayat).
- **Effort:** Pairing selesai; handoff konteks belum.

### 5.7 Izin per plugin & matriks — *prioritas menengah*
- **Mengapa:** Plugin aktif otomatis saat file ada. Beberapa plugin
  (gmail, ssh, kamera) menyentuh data sensitif. Pengguna harus bisa
  melihat dan membatasi **apa yang boleh dilakukan plugin**.
- **UI:** Halaman Plugin: setiap plugin punya card detail dengan
  daftar izin yang dibutuhkan (jaringan, folder, kunci) dan toggle per
  izin. Status "terpercaya / dibatasi / ditolak".
- **Risiko:** Backend permission enforcement.
- **Effort:** Sedang.

### 5.8 Suara kustom (opt-in, lokal) — *prioritas rendah*
- **Mengapa:** Voice selection ada (`providers/`). Suara kustom dari
  sampel singkat yang disimpan lokal adalah penyempurnaan personalisasi
  tanpa langganan.
- **UI:** Halaman Suara: daftar suara, tombol "Gunakan suara saya",
  rekaman sampel 30 detik dengan feedback level, preview hasil. Jelas
  tertulis bahwa sampel disimpan lokal dan bisa dihapus.
- **Risiko:** Privasi — harus opt-in eksplisit dan lokal.
- **Effort:** Besar (tergantung provider engine).

### 5.9 Mode kontras tinggi & navigasi keyboard — *prioritas rendah*
- **Mengapa:** Board 15 tidak menawarkan kontras karena kedua palet
  sudah lewat. Tapi pengguna dengan gangguan penglihatan tetap membutuhkan
  opsi kontras lebih tinggi dan navigasi keyboard lengkap.
- **UI:** Opsi ketiga di tema (gelap / terang / **kontras tinggi**),
  plus tab-order dan label aksesibilitas lengkap di semua permukaan.
- **Status:** **Kontras tinggi sudah diimplementasi** (palette `high` +
  kontrol segmen Standar/Tinggi di board 15, orthogonal terhadap tema
  dark/light). Navigasi keyboard belum.
- **Risiko:** Rendah.
- **Effort:** Sedang.

### 5.10 Ekspansi i18n — *prioritas rendah*
- **Mengapa:** i18n hanya en + id. Basis terjemahan sudah ada
  (`assets/i18n/`), framework-nya siap.
- **UI:** Tidak ada UI baru — penambahan catalog bahasa dan tombol
  beranda komunitas di halaman Bahasa.
- **Risiko:** Rendah.
- **Effort:** Rendah–sedang.

---

## 6. Roadmap Implementasi

**Phase 1 — Menutupi janji yang sudah ditulis (gap terbesar, dampak keamanan)**
1. Verifikasi Suara (5.1) — policy murni + engine lokal + pendaftaran, lalu
   integrasi gate sesi.
2. Health / Status panel (5.2) — kumpulkan data yang sudah ada.
3. Verifikasi visual manual board 18 (token terang) dan board 12 (susun
   jendela) — yang hanya dicek oleh tes.

**Phase 2 — Nilai baru**
4. Rutinitas terjadwal (5.3).
5. Ringkasan sesi & timeline (5.5).
6. Handoff ponsel (5.6).
7. Izin per plugin (5.7).

**Phase 3 — Penyempurnaan**
8. Isi form (5.4) — bergantung pada Phase 2 (konfirmasi sudah kuat).
9. Suara kustom (5.8).
10. Kontras tinggi + keyboard (5.9), i18n (5.10).

**Catatan:** Setiap fitur baru harus punya tes di `tests/` sesuai
konvensi repo: tes untuk **logika kebijakan murni** (tanpa Qt) plus
tes untuk permukaan UI dengan stub, dan harus menyebutkan apa yang
**tidak** bisa dilakukan (seperti gaya `docs/verification.md`).

---

## 7. Visual Kunci

Visual proposal dihasilkan di `design/new-ui-proposal/`, satu gambar per
layar (bukan kolase). Berikut peta setiap board ke visualnya:

| File | Board | Layar |
|---|---|---|
| `01-ambient-main.png` | 1 + 5 | Desktop ambient: orb + glow + panel baki + toast |
| `02-command-bar.png` | 2 | Command bar 640×184 dengan titik risiko |
| `03-gesture-control.png` | 3 | Kontrol gestur: tile kamera + kerangka tangan |
| `03-voice-mode.png` | 4 | Mode suara: glow tepi, orb, bar level, transkrip |
| `04-security-permissions.png` | 6 + 14 | Keamanan & izin: tingkat risiko + log aktivitas |
| `05-tray-panel.png` | 5 | Panel baki penuh (460×640), navigasi utama |
| `05-onboarding.png` | 7 + 22 | Onboarding: izin mikrofon + presensi |
| `06-task-history.png` | 8 | Riwayat tugas: status per baris + undo |
| `07-memory-personal.png` | 9 + 10 | Memori personal + detail memori |
| `08-routines-suggestions.png` | 11 | Rutinitas & saran proaktif |
| `09-tools-clipboard.png` | 12 | Alat cepat & clipboard cerdas |
| `10-help-dictation.png` | 13 | Dikte · baca layar · isi form |
| `11-language-accessibility.png` | 15 | Bahasa & aksesibilitas |
| `12-plugins-phone.png` | 16 | Plugin & pasangan ponsel |
| `13-gesture-map.png` | 19 | Peta gestur (6 gestur) |
| `14-orb-status.png` | 20 | Status orb — 4 status siluet |
| `15-brand-icons.png` | 21 | Brand & ikon — lembar spesifikasi |
| `16-light-theme.png` | 17 + 18 | Tema terang — panel & izin |
