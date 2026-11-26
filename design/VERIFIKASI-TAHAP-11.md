# Verifikasi integrasi UI — tahap 11

## Cakupan dan hasil

- Sesi, bar perintah, dan panel baki berbagi maksimum 100 pesan di memori proses. Permukaan yang dibuka belakangan memperoleh percakapan yang sudah ada; ini bukan riwayat permanen. Pengiriman yang belum selesai, gagal, atau tidak pasti tidak ditampilkan sebagai berhasil.
- Tes integrasi Qt baru memeriksa navigasi dan draf, pengiriman `Future` yang tertunda/berhasil/tidak pasti, sinkronisasi antarsurface, tema baki, serta pembatalan konfirmasi tindakan berisiko. Pengujian ini memakai pesan, konfigurasi, dan hasil simulasi, bukan layanan eksternal.
- **Suite headless penuh: 3.022 lulus, 2 dilewati** (API Windows), dengan satu peringatan deprecation Starlette/httpx. PyQt diblokir dalam proses utama agar tes yang memang menggunakan stub Qt tidak mencampurkan stub dengan widget asli; tes Qt yang dibuat sebagai subprocess tetap menggunakan PyQt asli.
- **Regresi terpilih dengan PyQt asli/offscreen: 540 lulus**, termasuk tes Qt yang menjalankan layar nyata dalam subprocess. Ini bukan klaim bahwa seluruh suite lulus dalam satu proses PyQt asli: percobaan tersebut gagal pada tes painter lama yang mengasumsikan `QBrush` stub, dan percobaan sebelumnya berhenti saat tes headless membuat widget tanpa `QApplication`.
- `ruff check .`, `git diff --check`, dan kompilasi Python bersih. Pemeriksaan dilakukan di lingkungan sandbox; tidak ada commit atau push.
- Dashboard opsional sekarang melaporkan dependensi FastAPI/uvicorn yang hilang tanpa lebih dulu gagal dengan `NameError`. Ini bukan verifikasi pairing atau akses jaringan dashboard.

## Snapshot

`design/snapshots/tahap-11-sesi-simulasi.png`, `tahap-11-baki-simulasi.png`, dan `tahap-11-riwayat-uji.png` ditangkap dari `main.main()` dengan konfigurasi dan audit terisolasi. Pesan dan catatan audit adalah data uji; runner Live dinonaktifkan. Sesi ditampilkan tidak tersambung.

## Batas verifikasi yang masih berlaku

- Koneksi Live ke layanan gagal dalam sandbox; pengiriman ke server, hasil tindakan jarak jauh, suara masuk/keluar, mikrofon fisik, dan kamera belum diverifikasi end-to-end.
- Shortcut global, baki OS, perilaku native Windows/macOS, dan kontrol gestur fisik memerlukan uji pada desktop dan perangkat yang didukung. Persetujuan fisik pada tindakan berisiko tetap diperlukan.
- Status izin perangkat tidak sama dengan izin OS yang diberikan. Panduan awal tidak mengubah atau memverifikasi izin mikrofon. Phone pairing tidak tersedia pada layar baru.
- Tema terang dan kontras tinggi berlaku pada panel baki, bukan seluruh aplikasi; pilihan otomatis memakai preferensi tersimpan, bukan pembacaan langsung tema OS.
- Audit mungkin tidak lengkap dan bukan bukti semua hasil telah diverifikasi. Kunci API disimpan dalam konfigurasi lokal dan dikirim ke penyedia saat pengecekan/penggunaan; jangan memasukkan kunci ke snapshot atau log uji.
- Kunci sinkronisasi Memori dan rutinitas hanya berlaku dalam proses ini. Penjadwal rutinitas berjalan saat sesi tersambung dan menandai jadwal sebelum pengiriman; kegagalan tidak otomatis dicoba lagi hari itu, dan rutinitas yang jatuh tempo dapat langsung berjalan saat sesi tersambung.

## Menjalankan suite headless terisolasi

Instal dependensi pengujian proyek dan Pillow dalam lingkungan virtual. Contoh di Linux, dari root repositori; `QT_QPA_PLATFORM=offscreen` memungkinkan subprocess Qt asli berjalan bila library sistem Qt tersedia:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import importlib.abc, os, sys, tempfile
from pathlib import Path
import pytest

with tempfile.TemporaryDirectory(prefix='jarvis-tests-') as directory:
    base = Path(directory)
    os.environ['JARVIS_STATE_DIR'] = str(base)
    from memory import config_manager
    config_manager.CONFIG_DIR = base
    config_manager.CONFIG_FILE = base / 'api_keys.json'
    config_manager._LAST_GOOD = {}

    class NoQtInParent(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == 'PyQt6' or fullname.startswith('PyQt6.'):
                raise ModuleNotFoundError('PyQt6 disabled in headless parent')
    sys.meta_path.insert(0, NoQtInParent())
    raise SystemExit(pytest.main(['-o', 'addopts=', '-q', '-rs', 'tests']))
PY
```

Tes Qt riil memerlukan `PyQt6` dan pustaka sistem yang sesuai. Dua skip Windows dan peringatan dependensi dapat berbeda menurut platform dan versi paket.
