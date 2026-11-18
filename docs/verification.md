# Status fitur dan panduan verifikasi JARVIS

Dokumen ini memisahkan **cakupan pengujian**, **persyaratan**, dan hal yang
**belum diverifikasi**. “Lulus tes” tidak berarti bebas bug atau berfungsi di
semua komputer. Hasil uji lokal tidak otomatis menjadi hasil CI atau rilis.

## Matriks verifikasi

| Area | Cakupan otomatis saat ini | Masih perlu diuji pada perangkat/layanan nyata |
|---|---|---|
| Workspace desktop & navigasi | Tes struktur/stub; CI memiliki smoke Qt offscreen Linux | Tampilan, fokus, ukuran dan aksesibilitas pada Windows, monitor serta DPI berbeda |
| Remote HTTP/HTTPS | Endpoint, pairing, sertifikat CA/IP dan handshake TLS lokal; smoke kontrol Qt dijadwalkan di CI | Ponsel Android/iPhone, trust CA browser, akses mikrofon, firewall dan jaringan privat |
| Kontrol tangan workspace | Sampel landmark sintetis, smoothing, pinch, pelacakan dan pembatalan; gesture UI pada Qt offscreen Linux di CI | Webcam Windows, MediaPipe, latency, presisi, pencahayaan dan penggunaan dua tangan sebenarnya |
| MT5 ORB/read-only | Perhitungan dan perilaku data dengan fake/fixture | Terminal MT5 Windows, data broker dan zona waktu sesi sebenarnya |
| Order MT5 dan stop darurat | Validasi, persetujuan/hasil simulasi, race stop memakai fake; smoke kontrol Qt dijadwalkan di CI | Terminal dan akun **demo**, koneksi dan respons broker; LIVE belum diverifikasi |
| Editor kode/gambar dan papan tangan | Tes logika serta sebagian operasi Qt offscreen | Dialog file, font, gambar, penyimpanan dan penggunaan interaktif pada desktop pengguna |
| Provider suara, mikrofon & speaker | Tes logika dan mock; pilihan perangkat | Perangkat audio, driver, privasi dan koneksi provider yang dipakai |
| Plugin dan layanan eksternal | Discovery/manifest dan tes plugin menggunakan fixture/mock | Kredensial, perubahan API, izin, kuota, jaringan dan akun yang dipakai |

Fitur kontrol tangan dan order MT5 tetap **eksperimental**. Smoke offscreen
memverifikasi interaksi yang diprogram, bukan kesesuaian visual, performa nyata,
keamanan seluruh sistem, atau hasil CI yang belum dijalankan.

### Kontrol tangan di workspace

Kontrol ini implementasi mandiri di dalam proses JARVIS, bukan aplikasi atau
server Barehands. Pada Windows yang didukung, pengguna mengaktifkannya sendiri
melalui **Aplikasi → Kontrol**. Cubit satu tangan lalu lepas untuk klik; tahan
pada judul untuk memindahkan jendela; gerakkan cepat lalu lepas untuk flick
(perpindahan singkat dan dibatasi viewport). Dua cubitan mengubah posisi dan ukuran
jendela JARVIS yang dipilih bersama-sama; dua jari terbuka menggulir. Jendela
maksimal harus dipulihkan sebelum diubah geometri. Kontrol tidak menghasilkan
input OS dan tidak dapat menyetujui dialog modal atau konfirmasi sensitif.
Kehilangan tracking yang terdeteksi, fokus pindah atau kamera berhenti membatalkan
interaksi. Kehilangan antar-frame UI dan jeda kamera lebih dari 0,35 detik
ditahan sebagai sinyal batal; penahanan cubitan dimulai ulang jika target
berubah atau posisi bergeser lebih dari 25 piksel. Beberapa perubahan cubitan
atau jumlah tangan yang terlewat juga membatalkan; setelah pembatalan, semua
tangan yang terlihat harus terbuka sebelum dapat memulai interaksi lagi.
Satu tangan mencubit sementara tangan lain terlihat terbuka tidak mengaktifkan
gesture satu tangan. Deteksi tetap dapat keliru pada penggunaan nyata dan
tidak menjamin keselamatan untuk tindakan sensitif.

`tests/test_workspace_transform.py` menguji geometri dengan sampel sintetis;
`tools/check_desktop_qt.py` memiliki smoke dua tangan di Qt offscreen untuk CI.
Keduanya bukan pengujian dengan webcam. Gesture clap, claw serta
rotasi bebas jendela tidak diklaim sebagai fitur yang tersedia.

### Pembaruan visual desktop

Mockup acuan: `design/jarvis-desktop-visual-revisi.png`. Implementasi memakai
wallpaper biru-grafit, palet bersama untuk panel workspace, emblem JARVIS
ornamental, file di kiri dan percakapan di kanan pada layar lebar. Pada layar
kecil emblem disembunyikan agar ruang tetap untuk aplikasi. Badge kontrol tangan
hanya muncul saat controller benar-benar mulai atau aktif; bukan gambar status
kamera statis. Emblem di desktop bersifat dekoratif; HUD dalam panel asisten
masih menjadi sumber status JARVIS. Tata letak dan widget asli tetap dapat
dioperasikan; tidak menggunakan gambar mockup sebagai UI.

Kesesuaian piksel, komposisi pada DPI berbeda, keterbacaan dan responsivitas
memerlukan pemeriksaan manual dengan Qt nyata di perangkat pengguna. Wallpaper
adalah aset baru yang terinspirasi mockup, bukan salinan persis latarnya.

## Menjalankan tes lokal

Di lingkungan Python proyek, pasang dependensi sesuai `requirements.txt` dan
`requirements-dev.txt`, lalu jalankan:

```text
python -m pytest -q
ruff check .
```

CI juga menjalankan `tools/check_desktop_qt.py` pada Linux dan
`tools/check_security_qt.py` pada Linux dan Windows menggunakan Qt offscreen
dengan dependensi aplikasi. Jalankan manual hanya setelah dependensi Qt dan
library OS terpasang; tidak ada server, akun atau webcam nyata yang diperlukan.
Untuk Linux/macOS, contoh:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tools/check_security_qt.py
```

Untuk PowerShell:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONPATH='.'
python tools/check_security_qt.py
```

Jangan menafsirkan kegagalan import karena library OS yang tidak terpasang
sebagai bukti bahwa fitur gagal di semua perangkat.

## Checklist uji manual yang belum dilakukan

Catat tanggal, versi commit, OS/Python, jenis perangkat, langkah, hasil aktual,
dan apakah lulus/gagal. Jangan sertakan token, kode pairing, email, nomor akun
lengkap, audio atau kredensial dalam laporan.

### Windows desktop & kamera

- [ ] Uji navigasi workspace, ukuran jendela, scroll, fokus keyboard, label
      Indonesia/Inggris dan monitor/DPI yang digunakan.
- [ ] Di Windows AMD64 Python 3.10–3.12, aktifkan kontrol tangan melalui
      **Aplikasi → Kontrol**. Coba klik, seret, dua tangan dan kehilangan tracking.
- [ ] Catat model webcam, pencahayaan, posisi, perkiraan latency dan klik tak
      sengaja. Coba ketika kamera sibuk dan ketika JARVIS kehilangan fokus.
- [ ] Pastikan gesture tidak dapat menyetujui dialog sensitif atau mengendalikan
      aplikasi di luar workspace. Jangan mengandalkan gesture untuk order.

### Remote HTTPS

- [ ] Pada jaringan privat yang dikuasai sendiri, aktifkan HTTPS di Remote
      Control, restart, lalu verifikasi URL `https://IP-LAN:8001`.
- [ ] Ikuti instruksi CA lokal di README. Verifikasi sidik jari CA melalui kanal
      tepercaya; jangan pernah memindahkan atau membagikan file private key.
- [ ] Uji pairing, revoke, kembali tersambung dan mikrofon dengan sertifikat
      yang benar-benar dipercaya pada browser Android/iPhone yang dipakai.
- [ ] Uji sertifikat kedaluwarsa/IP berubah dan port terblokir; pastikan pesan
      jelas dan tidak terjadi fallback HTTP. Jangan mengekspos port ke internet.

### MT5 — demo saja untuk validasi awal

- [ ] Gunakan terminal dan akun **demo** milik sendiri. Pastikan identitas,
      server dan mode di dialog benar sebelum melakukan tindakan.
- [ ] Review order dengan SL dan limit risiko; uji pembatalan, penolakan broker,
      kutipan kedaluwarsa dan hasil tidak pasti tanpa mencoba ulang otomatis.
- [ ] Uji stop darurat sebelum persetujuan dan selama pemeriksaan. Pastikan
      tinjauan lama tetap tidak valid setelah resume, dan bandingkan hasil dengan
      terminal MT5. Jangan mengasumsikan permintaan yang sudah dikirim dibatalkan.
- [ ] Jika sengaja melakukan uji order demo, gunakan ukuran minimal yang broker
      izinkan dan verifikasi order, posisi, riwayat dan jurnal MT5 sesudahnya.
      Uji ini tidak membuktikan keselamatan atau perilaku akun LIVE.

### Workspace browser and SSH additions

`tests/test_workspace_browser.py`, `tests/test_browser_autofill.py`,
`tests/test_browser_ui_logic.py`, `tests/test_ssh_manager.py`, and
`tests/test_ssh_tabs.py` cover vault/origin handling, isolated autofill logic,
tab lifecycle, and fake SSH transports. `tests/test_ssh_protocol.py` exercises
Paramiko over a local socketpair with a generated host key, including rejection
of an unknown key; no external server is involved. CI also runs
`tools/check_browser_qt.py` (Linux) and `tools/check_ssh_qt.py` (Linux and
Windows) with real Qt offscreen; SSH uses a fake transport and the browser test
does not contact a site. These checks do not establish visual fidelity, real
keychain availability, SSH interoperability, Windows camera behavior, or
security against a malicious same-origin page. Exercise those separately on the
target machine. Selected visual references are `design/proposed-graphite-desktop.png`,
`design/proposed-graphite-browser.png`, and `design/proposed-graphite-ssh.png`.
The Qt interface adapts those concepts to real controls rather than reproducing
fictitious system indicators or page contents. Workspace documents share the
same palette, tab, primary-action, menu and keyboard-focus styling; SSH key
controls follow the selected authentication mode. Browser and SSH tab labels,
status and controls, as well as the main file navigator, are retranslated in
place without resetting the selected account or session. Other existing tool
windows may need to be reopened after a language change. Shutdown first checks unsaved
edits and asks about active SSH sessions before disconnecting them. It has not yet been visually
compared with screenshots from a real target machine. The SSH mockup's simultaneous
connected and unknown-host state is deliberately not implemented: unknown host
keys must be rejected.

## Catatan audit plugin dan perubahan perilaku

- Manifest, hash entrypoint dan dialog izin adalah transparansi/consent, **bukan
  sandbox**. Discovery mengimpor kode plugin dengan hak proses aplikasi sebelum
  izin runtime diperiksa; helper tidak tercakup hash entrypoint. Hanya pasang
  plugin dari sumber yang dipercaya. Jangan memperlakukan toggle sebagai batas
  keamanan terhadap kode plugin berbahaya.
- Quick Notes kini menyatakan izin file dan default OFF pada konfigurasi baru;
  pilihan ON/OFF pengguna yang sudah tersimpan tetap berlaku. Jika arsip berhasil
  tetapi penulisan ulang todo gagal, task dapat muncul di keduanya; kegagalan
  tidak menghapus satu-satunya salinan. Kunci penulisan hanya dalam satu proses.
- `mt5_orb` memakai snapshot dan konfigurasi Trading Terminal yang sama (M1,
  zona waktu sesi dan durasi). PNG menggunakan snapshot M1 dan level yang sama
  dengan jawaban, termasuk status dan waktu tick. Trading Terminal dapat refresh
  terpisah, sehingga datanya bisa berubah. Uji akun demo tetap diperlukan.
- Tool browser lama mengarahkan URL/search ke browser internal. `get_text`
  membaca tab browser aktif hanya setelah konfirmasi lokal setiap permintaan;
  input, formulir, frame dan konten tersembunyi dikecualikan sebisa mungkin.
  Teks terlihat tetap bisa mengandung data pribadi dan dikirim ke provider AI.
  Hasil ditandai sebagai data tidak tepercaya. Flight Finder dapat membuka
  permintaan Google Flights dan, setelah pengguna memeriksa dan memfokuskan tab,
  meminta pembacaan dengan persetujuan lokal; model percakapan menafsirkan teks.
  Detail dan harga harus diperiksa lagi pada situs; situs bisa mengubah tata
  letak, tidak memuat atau gagal mengisi permintaan. Klik/ketik otomatis belum
  tersedia. Tidak ada klaim halaman dimuat sebelum status jendela menunjukkannya.
- Pada provider dengan budget tool, tool yang terpotong dicatat di activity log
  dan tidak lagi dicantumkan dalam daftar kemampuan prompt. Budget tetap dapat
  membuat plugin yang aktif tidak tersedia ke model; sesuaikan pengaturan model.
- Perubahan ini belum membuktikan aksesibilitas screen reader, kesesuaian visual
  mockup, terjemahan semua status dinamis, atau gesture/DPI Windows; semua masih
  perlu uji pada perangkat target. Kontrol utama editor, terminal, dan dialog
  order diterjemahkan ulang tanpa membangun ulang dokumen; data yang berubah
  dipertahankan.

### Pembacaan browser internal

`tests/test_browser_read.py` memeriksa persetujuan, pembatalan timeout,
pergantian tab, pembatasan dan penandaan hasil, serta menjalankan skrip pada DOM
palsu di Node. Ini **bukan** uji nyata WebEngine terhadap situs atau pembuktian
bahwa semua data sensitif dapat disaring. Sebelum digunakan pada akun nyata,
verifikasi pada desktop target bahwa dialog persetujuan lokal muncul, pilihan
TIDAK membatalkan, pergantian tab membatalkan hasil, serta hanya konten yang
memang ingin dibagikan dikirim ke provider. Klik dan pengetikan otomatis tetap
tidak tersedia.

### Flight Finder internal

`tests/test_flight_finder_internal.py` memeriksa validasi rute, tanggal dan
penumpang, URL yang di-encode, pembatasan asal dan perlakuan data halaman
tanpa jaringan atau API model. Ini belum memverifikasi Google Flights nyata,
kebenaran pengisian formulir, hasil, zona waktu atau harga. JARVIS tidak
memesan penerbangan; periksa rute, tanggal dan harga langsung pada situs.
