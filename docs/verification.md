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
