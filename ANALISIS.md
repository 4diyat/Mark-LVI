# Analisis Teknis — MARK LVI (JARVIS)

Ditinjau sebagai fullstack developer. Semua temuan di bawah **diverifikasi langsung**
terhadap kode di repo ini (bukan asumsi): `python -m compileall`, `pyflakes`,
pembacaan AST, pemanggilan loader asli (`core.action_loader.discover_actions`),
dan grep terarah. Perintah verifikasinya disertakan agar bisa Anda ulangi.

Tanggal tinjauan: 2026-11-11 · Branch: `arena/0905ecd0-mark-lvi` (base `0101e54`)

---

## 1. Ringkasan Eksekutif

| Aspek | Penilaian | Catatan |
|---|---|---|
| Ambitus produk | ⭐⭐⭐⭐⭐ | Asisten suara cross-platform dengan Live API + engine lokal, avatar software-render, dashboard HP, plugin system |
| Kualitas dokumentasi | ⭐⭐⭐⭐⭐ | Komentar menjelaskan **sebab** sebuah keputusan, bukan cuma apa kodenya. Ini di atas rata-rata proyek open source |
| Desain keamanan fitur berbahaya | ⭐⭐⭐⭐ | Confirmation gate, undo, echo guard, PBKDF2 200k + AES-GCM. Serius |
| **Arsitektur & modularitas** | ⭐⭐ | `main.py` 2.706 baris, `ui.py` 7.504 baris, `HudCanvas.paintEvent` 143 baris, `JarvisLive` > 1.600 baris |
| **Test & CI** | ⭐ | 0 test runner, 0 CI, 1 self-test yang hanya menguji `providers/` |
| **Konsistensi kode** | ⭐⭐ | 15 loader config duplikat, 9+ penulis langsung `api_keys.json`, 40/67 file CRLF campur |
| **Ketahanan (robustness)** | ⭐⭐⭐ | Banyak defensive coding, tapi 140× `except: pass` menyembunyikan kegagalan nyata — dan **ada 1 bug nyata yang tersembunyi di baliknya** |

**Kesimpulan:** ini produk yang *jauh lebih matang dari sisi fitur dan pemikiran*
daripada rata-rata proyek sejenis, tetapi **infrastruktur rekayasa perangkat lunaknya
tertinggal jauh**. Prioritas peningkatan bukan menambah fitur, melainkan:
**(a) menutup 3 bug nyata, (b) menyatukan lapisan konfigurasi, (c) memasang quality gate
(lint + test + CI), (d) memecah `ui.py` dan `main.py`.**

---

## 2. Peta Arsitektur

```
                    ┌─────────────────────── Qt main thread ───────────────────────┐
                    │  ui.py  —  JarvisUI (fasad thread-safe) + MainWindow         │
                    │  HudCanvas / Overlays / Providers / Dashboard key / Quiz     │
                    └───────────────▲───────────────────────────┬─────────────────┘
                                    │ pyqtSignal (aman lintas thread)              │
                                    │                                              │ callback
                    ┌───────────────┴───────────────────────────▼─────────────────┐
                    │  main.py — JarvisLive (asyncio loop di thread terpisah)      │
                    │  run() 293 baris · 11 send-site · reconnect · watchdog       │
                    └───┬───────────┬──────────────┬───────────────┬──────────────┘
                        │           │              │               │
             ┌──────────▼──┐  ┌─────▼──────┐  ┌────▼─────────┐  ┌──▼──────────────┐
             │ actions/    │  │ plugins/   │  │ providers/   │  │ dashboard/      │
             │ 20 file     │  │ auto-load  │  │ engine lokal │  │ FastAPI, 2 port │
             │ 12.390 baris│  │ 1 template │  │ 5.733 baris  │  │ 1.312 baris     │
             └──────┬──────┘  └─────┬──────┘  └────┬─────────┘  └──┬──────────────┘
                    └───────────────┴──────────────┴───────────────┘
                                    │
                    ┌───────────────▼─────────────────────────────────────────────┐
                    │ core/  —  gemini.py (ladder+timeout) · confirm · undo ·     │
                    │ outcome · echo · viseme · audio_devices · stt/tts · wake    │
                    │ 8.109 baris · 25 modul                                      │
                    └─────────────────────────────────────────────────────────────┘
```

### Ukuran kode (terukur)

| Area | Baris | % total |
|---|---:|---:|
| `ui/window.py` | 7.280 | 18,6 % (dari `ui.py` 7.504; palet & sampler sudah pindah) |
| `main.py` | 2.706 | 6,9 % |
| `actions/` (20 file) | 12.390 | 31,7 % |
| `core/` (25 file) | 8.109 | 20,8 % |
| `providers/` (11 file) | 5.733 | 14,7 % |
| `dashboard/` | 1.312 | 3,4 % |
| `memory/` | 1.107 | 2,8 % |
| `plugins/` | 64 | 0,2 % |
| **Total** | **39.080** | 100 % |

### Fungsi/kelas terbesar (kandidat refactor)

| Lokasi | Ukuran | Masalah |
|---|---:|---|
| `ui.py:4418` `MainWindow.__init__` | 303 baris | Membangun seluruh shell UI + 102 method di kelas yang sama |
| `ui.py:2681` `ProvidersOverlay` | ~1.100 baris | Panel pengaturan jadi satu kelas monolitik |
| `main.py:2397` `JarvisLive.run` | 293 baris | Loop koneksi + error policy + watchdog bercampur |
| `main.py:1318` `_execute_tool` | 189 baris | Dispatch tool inline + special-case per tool |
| `dashboard/server.py:847` `_build_app` | 339 baris | 12 route didefinisikan di dalam satu method |
| `actions/dev_agent.py:1268` `_improve_folder` | 238 baris | Alur coding agent tanpa pemisahan tahap |
| `ui.py:697` `_paint_core` | 143 baris | Render per-frame, jalan 60×/detik |

---

## 3. Temuan Bug (terverifikasi, bukan dugaan)

### 🔴 P0-1 — `dev_agent` bisa menulis file Python **di luar** folder proyek

`actions/dev_agent.py:253` dan `:451`:

```python
full_path = project_dir / file_path        # file_path datang dari LLM
full_path.parent.mkdir(parents=True, exist_ok=True)
full_path.write_text(code, encoding="utf-8")
```

`file_path` berasal dari rencana model (`_plan_project`) dan **tidak divalidasi**.
Seperti yang sudah ditulis di `actions/open_app.py:98`, model bisa menghasilkan
`../../` — di sini akibatnya bukan "click yang tidak terjadi", tapi
**file `.py` yang ditulis ke lokasi sembarang**, yang nanti dieksekusi oleh
`_run_project` / *test-and-fix*. Ini jalur prompt-injection → eksekusi kode,
dan bertentangan dengan aturan proyek sendiri ("never claim an outcome that was
not observed") karena penulisan file di luar proyek tidak pernah dilaporkan.

**Perbaikan (kecil, ±20 baris):**

```python
def _safe_rel(root: Path, rel: str) -> Path | None:
    p = (root / rel).resolve()
    return p if p.is_relative_to(root.resolve()) else None
```

Pakai di `_write_file`, `_fix_files`, `_write_change`, dan semua `open()` di
`dev_agent.py`. Tolak dengan pesan "path di luar folder proyek".

### 🔴 P0-2 — Firewall dashboard (Linux) mati total karena `NameError`

`dashboard/server.py:506–535` memakai variabel `{port}` yang **tidak pernah
didefinisikan** di `_ensure_network_access(*ports)`. Fungsi itu dibungkus
`try/except Exception: pass`, jadi di Linux:

```bash
$ pyflakes dashboard/server.py
dashboard/server.py:506:48: undefined name 'port'   (+ 7 baris lain)
```

Artinya cabang **ufw / firewalld / iptables tidak pernah berjalan** — pengguna
Linux tidak pernah mendapat port terbuka maupun pesan `sudo ufw allow ...`.
Dashboard tetap "unreachable" tanpa satu pun penjelasan, persis kelas kegagalan
yang proyek ini berjanji tidak akan terjadi lagi.

**Perbaikan:** ganti dengan loop `for port in ports:` (Windows-nya sudah benar
memakai `port_rules`), dan ganti `try/except: pass` menjadi `except Exception as e:
print(...)`.

### 🔴 P0-3 — Bug autentikasi di dashboard: "re-enter key" tidak pernah selesai

`main.py:2653–2659` + `ui.py:7169–7187`:

```python
self.ui.prompt_reconfig()                       # _ready = False
while not self.ui._win._ready:                  # menunggu
    await asyncio.sleep(1)
```

`prompt_reconfig` memunculkan `SetupOverlay`, tetapi `_show_setup` **tidak
memasang ulang `self._overlay`**: `_on_setup_done` (yang men-set `_ready = True`)
hanya terhubung ke overlay hasil setup awal. Kalau overlay baru ditutup tanpa
`done`, `_ready` tetap `False` → thread sesi menggantung selamanya. Selain itu
`_on_setup_done` menulis `{"gemini_api_key", "os_system"}` **menimpa seluruh
`api_keys.json`** → nama asisten, voice, preferensi audio, key plugin (WhatsApp,
OAuth, dll.) hilang.

**Perbaikan:** simpan overlay di `self._overlay`, sambungkan `done`, tangani
`closeEvent` → set `_ready = True` (atau batal dengan flag), dan tulis config
lewat satu `core/config.py` dengan merge, bukan overwrite.

### 🟠 P1-1 — Lapisan konfigurasi terduplikasi 15×, penulis tidak aman

- 13 modul mendefinisikan `get_base_dir/_base_dir/_get_base_dir` sendiri.
- 9 file menulis `config/api_keys.json` langsung (bukan via
  `memory/config_manager.py`), padahal `AGENTS.md` melarangnya.
- Tidak ada **atomic write** (`os.replace` + `fsync`) dan tidak ada lock global:
  `save_api_keys` (main thread UI) + `_save_config_key` (`screen_processor`,
  worker thread) + `save_turn_tuning` bisa saling menimpa (read-modify-write race).
- Hasil nyata: config bisa ter-truncate saat crash/power-loss → `is_configured()`
  jadi `False` dan pengguna diminta memasukkan key lagi.

### 🟠 P1-2 — Paket `config/` membingungkan dan berisiko saat dibundel

`config/__init__.py` adalah **modul** yang menunjuk `config/api_keys.json`,
padahal folder `config/` juga berisi data runtime (secret, certs, whatsapp_web).
Setelah dibundel (PyInstaller), `__file__` → `_MEIPASS`, sehingga path config
bergeser ke folder sementara — key dan memory hilang tiap update.
`memory/config_manager.py` sudah menangani `frozen`, tapi `config/__init__.py`
tidak. Selain itu ada dua API bersaing: `config.get_config()` dan
`memory.config_manager.load_api_keys()`.

### 🟠 P1-3 — `core/llm_client.py` adalah kode mati

Tidak ada satu pun modul yang meng-import-nya (`grep -rn "llm_client"` → 0 hit
di luar file itu sendiri), namun isinya 586 baris klien Ollama/OpenAI-compatible
dengan docstring "MARK XL" — versi lama. Fungsinya sekarang dipegang
`providers/llm_openai.py` + `core/gemini.py`. Risiko: kontributor baru memakai
jalur yang salah (tanpa timeout, tanpa fallback).

### 🟠 P1-4 — Shell dipakai tanpa alasan di beberapa tempat

`dashboard/server.py:393` — `subprocess.run([bat_path], shell=True)`.
Path-nya dari `mkstemp` (aman), tapi `shell=True` untuk menjalankan `.bat` tidak
perlu dan memicu SmartScreen/heuristik AV. Pakai `["cmd", "/c", bat_path]`.
`dev_agent.py:310` dan `computer_settings.py:228/257` juga `shell=True` —
perlu audit apakah argumennya bisa mengandung input model.

### 🟡 P2 — Kebersihan kode (terukur dengan `pyflakes`)

```
57 temuan total → 33 unused import · 6 variabel tak terpakai
                 · 9 f-string tanpa placeholder · 8 × undefined name (P0-2)
```

`except Exception: pass` per file: `ui.py` 33, `dashboard/server.py` 16,
`actions/reminder.py` 10, `actions/browser_control.py` 9, `main.py` 8 — total
**140**. Tidak semuanya salah (UI opsional memang harus survive), tetapi
kombinasinya dengan "no logging" membuat P0-2 tidak terdeteksi. Aturan yang
disarankan: `except Exception as e:` + minimal `print` sekali, atau `logging.debug`.

### 🟡 P2 — Line ending campur

40 dari 67 file `.py` memakai CRLF, sisanya LF, dan `core/outcome.py`
**campur dalam satu file** (229/274 baris CRLF). Tanpa `.gitattributes`,
`git diff` menampilkan seluruh file berubah hanya karena editor, dan
review PR jadi tidak mungkin. Perbaikan: satu baris `.gitattributes`
(`* text=auto` + `*.py text eol=lf`) lalu normalisasi sekali.

---

## 4. Yang Sudah Baik (jangan diubah, jadikan standar)

1. **Kejujuran outcome** (`core/outcome.py`) — `done` vs `unverified` adalah
   keputusan desain paling berharga di proyek ini.
2. **Confirmation gate + undo** (`core/confirm.py`, `core/undo.py`) untuk aksi
   ireversibel; model tidak bisa mengonfirmasi aksinya sendiri.
3. **Dashboard auth**: pairing key 8 karakter → PBKDF2 200.000 round → AES-256-GCM,
   token TTL 12 jam, throttle 6 percobaan / 5 menit, `chmod 600` untuk private key.
   Komentar "mengapa GCM, bukan CBC" adalah contoh dokumentasi yang benar.
4. **Auto-discovery** `actions/` dan `plugins/` dengan validasi `TOOL` dan
   penanganan tabrakan nama — saya jalankan loader aslinya: 16 action valid,
   4 ditolak dengan pesan jelas (bukan crash).
5. **Ladder model + deadline** di `core/gemini.py` dengan angka pengukuran nyata.
6. **Pemisahan thread yang disiplin**: `actions/` dan `plugins/` **nol** referensi
   PyQt (saya cek) — aturan di `AGENTS.md` benar-benar dipatuhi.
7. **`core/platform_support.py`** — mengubah "tidak berfungsi" menjadi pernyataan
   batas yang bisa disampaikan model ke pengguna.

---

## 5. Rekomendasi Peningkatan (berurut dampak ÷ usaha)

### A. Quality gate — dampak tertinggi per jam kerja (0,5–1 hari)

| Item | Isi | Alasan |
|---|---|---|
| `pyproject.toml` | metadata, `[project.scripts] marklvi = "main:main"`, config ruff/pytest/mypy | 39 ribu baris tanpa deklarasi paket |
| `ruff` | `E,F,W,B,SIM`, target py311 | Menangkap P0-2 otomatis; 57 temuan sekarang |
| `pytest` + `pytest-asyncio` | `tests/` + `conftest.py` | Nol test saat ini |
| `.gitattributes` | `* text=auto`, `*.py eol=lf` | EOL campur |
| `.github/workflows/ci.yml` | matrix `ubuntu/macos/windows` × py3.11/3.12 → ruff + compileall + pytest + smoke | Tidak ada CI sama sekali |
| `pre-commit` | ruff, ruff-format, trailing-whitespace | Menjaga momen-momen awal |
| Secret scan | `gitleaks` di CI | `api_keys.json` sudah di-ignore, tapi tambah jaring |
| `CONTRIBUTING.md`, `ARCHITECTURE.md`, `CHANGELOG.md` | | Kontribusi mustahil sekarang |

> Catatan: `providers/_tests.py` (1.108 baris) adalah aset berharga — bukan
> dibuang, tapi dibungkus jadi pytest (`tests/test_providers.py`) supaya ikut CI.
> `core/_smoke_harness.py` juga sudah tepat: pakai sebagai fixture E2E offscreen
> (`QT_QPA_PLATFORM=offscreen`).

### B. Keamanan & ketahanan (1–2 hari)

1. **Sandbox path** untuk semua tool yang menulis file (`dev_agent`,
   `file_controller`, `file_processor`) — lihat P0-1.
2. **Hapus `shell=True`** yang tidak perlu; allowlist perintah berbasis
   `shlex.split` + resolve executable (pola `open_app.py` pasca-perbaikan).
3. **Secret store**: pindah `gemini_api_key` dan token OAuth ke OS keychain
   (`keyring`) dengan fallback file 0600; `api_keys.json` tinggal preferensi.
4. **Dashboard hardening**: middleware header (`CSP default-src 'self'`,
   `X-Content-Type-Options`, `Referrer-Policy`), rate-limit global per IP
   (bukan hanya `/login`), `scopes` per token (read-only vs command), audit log
   perintah, dan TTL upload otomatis hapus > 24 jam.
5. **Logging terstruktur**: ganti `print` (61 di `main.py`, 36 di dashboard)
   dengan `logging` + `RotatingFileHandler` JSON; sediakan panel "LOG" di UI
   agar `except: pass` bisa diganti `logger.debug(...)`.

### C. Arsitektur — refactor bertahap, bukan big-bang (3–5 hari, bisa dicicil)

Target struktur:

```
marklvi/
  app/            main.py → session.py, audio_io.py, tool_dispatch.py,
                  reconfigure.py, briefing.py
  ui/             ui.py → theme.py, widgets/hud.py, widgets/log.py,
                  overlays/{providers,audio,memory,plugins,customize}.py,
                  windows/main.py, facade.py (JarvisUI)
  core/           config.py (BARU, satu-satunya I/O config),
                  platform/, safety/{confirm,undo,outcome}.py
  tools/          actions/* (nama tetap, kontrak TOOL sama)
  providers/      tetap
  dashboard/      routes.py, auth.py, tls.py, files.py, firewall.py
tests/
```

Aturan migrasi yang aman:
1. Ekstrak **config dulu** (`core/config.py`): lock `threading.RLock`, atomic
   `write → os.replace`, schema + default, migrasi versi (`config_version`),
   validasi tipe. Lalu ganti 15 loader/9 penulis satu per satu — bisa dikerjakan
   per-PR dan tidak menyentuh perilaku.
2. Pecah `ui.py` **per widget** (satu overlay = satu file), `JarvisUI` tetap
   fasadnya sehingga `AGENTS.md` dan plugin tidak berubah.
3. `main.py`: pindahkan `run()` ke `SessionRunner` dengan strategi error yang
   dinyatakan sebagai data (`retry_policy = [(predicate, action), ...]`), bukan
   `if` bertingkat 293 baris.
4. `_execute_tool`: pisahkan *dispatch* dari *presentasi* (mirror ke panel
   `web_search`, override `dev_agent` folder) → jadi daftar `ToolPostHook`.

### D. Testing (2–3 hari, bisa paralel dengan C)

Prioritas cakupan — sesuai risiko:

| Modul | Jenis | Contoh kasus |
|---|---|---|
| `core/outcome.py` | unit | marker `done`/`unverified` tidak bocor ke UI |
| `core/viseme.py` | unit + property | rentang hop, teks non-Latin, teks kosong |
| `core/echo.py` | unit | tail dianggap echo, ucapan pengguna tidak dibuang |
| `memory/memory_manager.py` | unit | trim, concurrency (2 thread tulis), corrupt JSON |
| `core/config.py` (baru) | unit | atomic write, merge tidak menghapus key, migrasi |
| `core/action_loader.py` | integrasi | module rusak tidak menjatuhkan loader (sudah bagus — kunci) |
| `dashboard/server.py` | integrasi | login throttle, token expired, upload > batas, path traversal |
| `main.JarvisLive` | kontrak | tool mengembalikan `FunctionResponse` valid untuk 16 action |
| UI smoke | e2e offscreen | semua overlay bisa dibuka/tutup tanpa error |

Target realistis: **≥ 40 % coverage pada `core/` + `memory/`** (bukan UI), cukup
untuk mencegah regresi kelas P0.

### E. Performa (1–2 hari)

1. **HUD 60 fps software render**: `QTimer 16 ms` × `paintEvent` 143 baris
   (gradient, glow, grid). Ukur dulu dengan `QElapsedTimer` + counter; lalu
   (a) turunkan ke 30 fps saat idle/`SLEEPING`, (b) cache grid & glow statis ke
   `QPixmap` (saat ini `_make_grid` dipanggil per resize — pastikan benar),
   (c) gambar ulang hanya region yang berubah (`update(rect)`).
2. `MetricBar`/`_SysMetrics`: polling `psutil`/NVML setiap detik di thread —
   tambahkan backoff saat jendela tidak aktif (`isVisible()`).
3. `LogWidget`: timer 6 ms untuk animasi antrean log — pakai `QPropertyAnimation`
   atau batasi ke 1 frame per baris.
4. `_execute_tool`: 32 worker di pool — untuk tool berat (`dev_agent`) pertimbangkan
   subprocess terisolasi + timeout keras, agar pool tidak tersedot.
5. Dashboard: `MAX_UPLOAD_MB = 500` tanpa batas total → tambahkan kuota folder
   dan streaming `FileResponse` chunked (sudah) + hapus otomatis.

### F. Produk & DX (opsional, 2–4 hari)

1. **i18n** — ✅ selesai untuk `en`/`id`: 124 kunci di `assets/i18n/`.
   Menambah bahasa ketiga sekarang: satu file JSON + satu locale di
   `core/i18n.py::LOCALES`; test yang memberi tahu kunci mana yang kurang.
2. **Onboarding**: wizard 3 langkah (key → audio test → wake word) memakai
   overlay yang sudah ada; mengurangi tiket "tidak bisa dengar".
3. **Plugin marketplace yang aman**: manifest + hash + tanda tangan, izin
   deklaratif (`filesystem`, `network`, `input`) dan konfirmasi per-izin.
4. **Update checker**: versi + changelog, tombol "update" yang menjalankan
   `git pull`/unduh rilis, bukan `pip install` manual.
5. **Wayland/macOS**: `xdg-desktop-portal` (`org.freedesktop.portal.Screenshot`,
   RemoteDesktop) dan fallback `pyatspi`; sekarang batasnya sudah *diakui*
   dengan baik, tinggal ditingkatkan dari "tidak bisa" menjadi "bisa lewat portal".
6. **Observability lokal**: halaman `/metrics` di dashboard (latency connect,
   waktu tool per nama, jumlah reconnect) — data ini sudah dicetak ke console,
   tinggal disimpan.

---

## 5b. Status Pengerjaan

### ✅ Sprint 1 — selesai (commit `0fc3826`, PR #1)

| Item | Status | Bukti |
|---|---|---|
| P0-1 path traversal `dev_agent` | ✅ | `_safe_target()`; `tests/test_paths.py` (13 kasus) |
| P0-2 firewall Linux `NameError` | ✅ | `for port in ports`; diverifikasi dengan menjalankan fungsinya |
| P0-3 re-configure menggantung + config terhapus | ✅ | overlay disimpan & disambung; `save_setup()` merge |
| Lapisan config aman | ✅ | `update_config()`: lock + atomic `os.replace()` + `chmod 600` |
| Quality gate | ✅ | `pyproject.toml`, 43 test, `.gitattributes`, CI 3 OS × 2 versi, pre-commit |
| 57 temuan lint | ✅ | `ruff check .` → All checks passed |

### ✅ Sprint 2 — selesai

**Pengerasan dashboard** (`dashboard/server.py`), semuanya ada test di `tests/test_dashboard.py`:

| Perbaikan | Sebelum | Sesudah |
|---|---|---|
| Security headers | tidak ada | CSP + nonce, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `no-store` |
| Scope token | semua token bisa segalanya | `read` vs `command`; device bisa diberi akses lihat saja |
| Umur token | TTL 12 jam saja | + idle 2 jam (dipakai → diperpanjang) |
| Token device | berlaku selamanya | kedaluwarsa setelah 30 hari tak dipakai |
| Body `/api/command` | tanpa batas | 64 KB, teks dipotong 2.000 karakter |
| `/login` & `/api/command` | `req.json()` melempar 500 | 400 yang rapi + batas ukuran |
| Upload | 500 MB/file, folder tanpa batas | kuota total 2 GB + sapu file > 14 hari |
| Audit | tidak ada | 200 aksi terakhir + `/api/devices`, `/api/audit` |
| `except: pass` menyembunyikan kegagalan | 16 di file ini | yang relevan menulis ke log |
| Cache AES key | tumbuh tanpa batas | dibatasi 32 entri |

**Logging terstruktur** (`core/logbook.py`) — `logs/jarvis.log`, rotasi 2 MB × 3,
`sys.excepthook` ditangkap. Ini yang membuat 140 `except: pass` bisa mulai
dijadikan `except ... : log.debug(...)` tanpa kehilangan informasi. 5 test.

> Temuan saat verifikasi: klaim lama di docstring (`request.state` menyimpan
> nonce) tidak benar — middleware sempat akan menimpa CSP dari route dan
> memblokir `<script>` halaman sendiri. Sudah diperbaiki dengan `setdefault`,
> dan sekarang dikunci oleh `test_inline_script_nonce_matches_the_policy`.

### ✅ CI 3 OS — hijau

`Lint` + 6 job `Tests` (3 OS × 2 versi Python) + 3 job `Install real deps`
(ubuntu/macOS/Windows). Run terakhir: `43087727191`, **10/10 pass**.

Yang harus dibongkar agar sampai ke sini semuanya ada di *harness*, bukan di kode
aplikasi — dicatat karena polanya bisa terpakai lagi:

| Gejala | Sebab sebenarnya |
|---|---|
| Windows `exit 3221226505` di tengah transkrip | Qt `abort()` (fail-fast, bukan exception) saat `import ui` di mesin tanpa audio; `try/except` tidak bisa menangkapnya → panel dijalankan di **proses anak** |
| macOS `status=-6` + transkrip berhenti | sama, lewat `QApplication` tanpa window server |
| `FAIL APPLY writes the config once 0` di semua OS | config ditulis atomik (tmp + `os.replace`); penghitung hanya memantau `Path.write_text` → ikut hitung `os.replace` |
| transkrip terpotong / urutannya kacau | stdout anak di-buffer blok dan stderr ditangkap terpisah → `-u` + `stderr=STDOUT` |
| `exit 250`, `-1`, `127`, `9` | `::error::` tidak dibaca dari step `shell: python`; Git Bash Windows tanpa `python`; membaca file yang tidak ada |

Anak proses sekarang mencetak **satu vonis**: `ok:` (jalankan pemeriksaan),
`ENV:` (mesin ini tidak punya Qt yang bisa dipakai → SKIP), `CODE:` (ui.py
sendiri rusak → FAIL). Jadi mesin tanpa GUI tidak lagi memerahkan CI, tanpa
membuat kegagalan sungguhan ikut lolos.

### 🔄 Sprint 3 — berjalan (struktur)

| Langkah | Hasil | Bukti |
|---|---|---|
| `ui.py` → paket `ui/` | `ui/theme.py` (palet, satu-satunya penulis `C`), `ui/metrics.py` (thread sampler + NVML/WMI), `ui/window.py` (widget, sisa 7.280 baris) | `tests/test_ui_split.py` (7 test, AST — jalan tanpa Qt) |
| Kompatibilitas | `ui.C`, `ui.qcol`, `ui.JarvisUI`, `ui.MainWindow`, `ui._metrics` tetap ada (re-export) | `ui/__init__.py` |
| Profil JARVIS | `core/code_checks.py` mengenali **kedua** bentuk (`ui/window.py` dan `ui.py` lama) | `tests/test_profile_window_source.py` (4 test) |
| `except: pass` yang bodoh | core/: 8 → tersisa 3 yang memang sengaja | dashboard, gemini, audio_devices, wake_word, code_checks, confirm, appidentity, piper |
| `core/llm_client.py` | dihapus (586 baris, 8 fungsi publik, 0 pemakai) | `grep` atas kedelapan nama → 0 hit di luar file itu |

**Status CI:** 10/10 hijau (Lint + 6 `Tests` + 3 `Install`), test suite 87,
self-test provider 87 pass. Lihat bagian *CI 3 OS* di bawah untuk apa yang
harus dibongkar sebelum sampai ke sini.

> Dua pelajaran yang masuk ke test, bukan ke catatan:
> **(1)** `ui.py` dan `ui/` tidak boleh hidup bersama — Python memilih folder,
> file diabaikan, dan isinya gagal dengan *"'ui' is not a package"*. Itu persis
> yang dilaporkan CI pada percobaan pertama.
> **(2)** Saat `ui.py` berubah bentuk, dua tempat di `core/code_checks.py` masih
> menunjuk nama lama — tanpa error, dev_agent hanya diam-diam berhenti diajari
> soal `player`.

### Yang belum: `main.py` (2.717 baris) dan pecah per-widget

`ui/window.py` masih 7.304 baris — paket `ui/` sudah ada tempatnya, tapi 36 kelas
belum dipindah ke `ui/widgets/` dan `ui/overlays/` (satu overlay satu file).
Itu pekerjaan mekanis tapi besar, dan tidak ada test yang bisa memverifikasinya
tanpa Qt. Urutan yang aman: pecah per widget DULU di mesin ber-Qt, baru `main.py`.

### ✅ Sprint 4 — test coverage, dan i18n

Awal Sprint 4: **17 %** dari `core/` + `memory/` + `dashboard/`. Sesudah: **39 %**,
**363 test** (dari 87), dan tidak ada satu pun modul inti yang masih 0 % kecuali
yang memang butuh Qt/GPU/audio — dan yang terakhir itu sekarang **terdaftar
dengan alasannya**, bukan sekadar tidak diuji.

| Modul | Sebelum | Sesudah | Yang dijaga |
|---|---|---|---|
| `core/action_loader.py` | 0 % | **97 %** | folder berisi file rusak tidak boleh menghentikan tool lain |
| `core/plugin_loader.py` | 0 % | **87 %** | pesan untuk plugin yang butuh file helper / versi app lebih baru |
| `core/outcome.py` | 0 % | **100 %** | `done`/`unverified`/`failed`/`ask` + wrapper anti prompt-injection |
| `core/undo.py` | 0 % | **100 %** | batas 10 entri, undo gagal tidak boleh diulang selamanya |
| `core/confirm.py` | 0 % | **97 %** | gate HARUS gagal-tertutup (tanpa UI → tidak dikerjakan) |
| `core/echo.py` | 0 % | **95 %** | gema sendiri ≠ suara orang, pada kenyaringan yang sama |
| `core/platform_support.py` | 0 % | **100 %** | kalimat "kamu tidak bisa melakukan ini" untuk model |
| `core/lazyimport.py` | 0 % | **100 %** | proxy tetap resolve saat dipakai dari DALAM modul |
| `core/i18n.py` | — | **97 %** | label hilang terlihat (⟪key⟫), bukan diam-diam bahasa Inggris |
| `memory/memory_manager.py` | 0 % | **76 %** | index nama (bisa di-recall), trim yang diumumkan |
| `core/hotkey.py` | 0 % | **70 %** | `scope` jujur + debounce 60 ms |

**Kenapa lantai coverage bukan angka paket.** Angka paket mengukur *runner*, bukan
kode: 363 test yang sama membaca 39 % di mesin dengan `requirements.txt`, 31 % di
runner yang hanya memasang tooling test, dan berbeda satu-dua poin lagi di
Windows — di sana Qt, torch, GPU dan perangkat audio tidak bisa di-import. Lantai
yang bergerak mengikuti OS akan "diperbaiki" orang dengan menambah `skip` sampai
hijau. Karena itu:

* **lantai 60 %** hanya untuk 12 modul yang pekan lalu masih 0 % (sekarang 85 %) —
  ratchet untuk pekerjaan sendiri;
* aturan sebenarnya ada di `tests/test_coverage_map.py`: **setiap modul > 120
  statement harus disebut sebuah file test, ATAU terdaftar dengan alasan kenapa
  ia tidak bisa jalan di perangkat ini.** Kedua arah diperiksa (modul tanpa test,
  dan pengecualian yang sudah basi), dan modul yang memutuskan apa yang dilakukan
  asisten ke mesin tidak boleh masuk daftar pengecualian.

> Dua bug nyata tertangkap saat menulis test ini:
> **(1)** `discover_actions` menyimpan modul di `sys.modules` berdasarkan *nama
> file*, jadi folder kedua dengan nama file yang sama tidak pernah dijalankan —
> diam-diam memakai TOOL dan handler dari folder pertama.
> **(2)** `core/outcome.py` membuang fact yang namanya `reason`/`question` dan
> menulis `action=` dua kali; detail yang dilaporkan tool hilang dari baris yang
> melaporkannya. Sekarang menjadi `fact_reason=` / `fact_action=`.

#### i18n: percakapannya sudah multibahasa, jendelanya belum

Itu temuannya. Model diinstruksikan menjawab dalam bahasa pengguna, STT menerima
apa yang diucapkan, TTS memilih suara dari prefix bahasa — dan 47 label UI
ditulis langsung dalam bahasa Inggris di dalam 4.000 baris kode Qt. Pengguna yang
berbicara dalam bahasa Indonesia membaca panel kontrol berbahasa Inggris.

| Sebelum | Sesudah |
|---|---|
| 47 string Inggris hardcoded | **124 kunci** di `assets/i18n/{en,id}.json` |
| bahasa = bahasa Inggris | pengaturan `ui_language`: `auto`/`en`/`id`, `auto` = locale OS |
| label salah ketik = tak terlihat | kunci hilang tampil sebagai **⟪key⟫**, bukan Inggris |
| terjemahan bisa beda placeholder | test gagal kalau `{name}` hilang atau berubah nama |
| `CustomizeOverlay` tak bisa ganti bahasa | baris bahasa + `_retranslate()` di panel itu |
| — | `tests/test_i18n.py` + `test_language_setting.py`: 29 test, **tanpa Qt** |

Yang **tidak** diterjemahkan, dan alasannya: nama asisten (itu *setting*, jadi
disisipkan sebagai `{name}`), nilai combo box (`after`/`before`/`1` adalah kunci
konfigurasi), `pip install qrcode[pil]` (perintah untuk ditempel), dan
`Just A Rather Very Intelligent System` (akronim dari JARVIS).

Sekalian: `CustomizeOverlay`, `PluginManagerOverlay` dan `HueWheel` pindah ke
`ui/overlays.py`. Bukan sekadar merapikan — panel yang harus me-render ulang
dirinya saat bahasa berubah harus **memegang** label-labelnya, dan `ui/window.py`
sudah menyentuh plafon ukuran dengan baris bahasa belum ditulis. Plafon
`ui/window.py` turun dari 7.400 → 7.000 baris (sekarang 6.969), dan sebuah test
memastikan ketiga kelas itu tidak "kembali" ke file lama.

### ✅ Sprint 5 — keychain, `shell=True`, dan CI yang bisa didiagnosis

| Item | Sebelum | Sesudah |
|---|---|---|
| Kunci Gemini | `config/api_keys.json` (0600) | **OS keychain** (`core/keychain.py`), file tetap sebagai salinan untuk mesin tanpa desktop session |
| Panel pengaturan | tidak pernah menyebut di mana kuncinya | `describe()`: satu kalimat yang menyebut store-nya, atau alasan fallback-nya |
| `shell=True` | **3** (brightness Linux, VS Code, dan satu di `open_app` yang sudah diperbaiki lebih dulu) | **0**, dan `tests/test_shell_true.py` menolak yang baru |
| Diagnosa CI | "Process completed with exit code 1" ×4 | satu `::error` per test yang gagal: file, baris, pesan |
| Regresi lintas-OS | ditemukan setelah push | `LANG`, `sys.path`, dan nama modul dibaca sebagai aturan, bukan dihafal |
| Plugin contoh | tidak ada | `plugins/currency_rates.py` + manifest: rantai penuh manifest → loader → izin → dialog, dan 21 test tanpa jaringan |
| Chart MetaTrader 5 | tidak ada | `plugins/mt5_orb.py` (+ `_mt5.py`, `_orb.py`): gambar PNG chart dan baca ORB sesi pasar di M30, dari bar yang **sudah tutup**; 42 test tanpa menyentuh terminal |
| Catatan & tugas | tidak ada (hanya `memory/long_term.json` milik asisten) | `plugins/quick_notes.py` (+ `_notes.py`): `config/notes/{inbox,todo,archive}.md` teks polos; 22 test di folder config sementara |
| Harga pasar | tidak ada | `plugins/market_price.py` (+ `_market.py`): saham `.JK`/US, kripto, forex, indeks, komoditas dari endpoint chart Yahoo tanpa kunci; 49 test tanpa jaringan |
| Marketplace plugin | "aman" hanya di judul | `core/plugin_manifest.py` (95 %): manifest + sha256 + izin deklaratif yang **diperiksa terhadap sumbernya**, dan dialog persetujuan sebelum toggle |
| Kunci di keychain | tidak ada test | `core/keychain.py` **92 %**: tanpa paket, backend yang melempar saat read/write, keychain dan file yang berbeda isi |

**Brightness, sebagai contoh kenapa audit ini berharga.** Perintah Linux-nya
adalah satu string `shell=True` berisi `$(xrandr | grep ... | cut ...)` dan
`python3 -c` bersarang. Tiga masalah: shell terakhir di file yang selebihnya
memakai argument vector; level yang dibaca adalah **fraksi** dari maksimum
driver sementara fungsi sebelah melaporkan **persen**, jadi "naikkan" dari 40 %
tidak menambah sepuluh poin; dan nama monitor yang mengandung spasi/kutip/`;`
adalah kata shell. Dua primitif empat baris di atasnya sudah menjawab keduanya —
sekarang `_brightness_step()` hanya aritmetika.

**Chart MetaTrader 5, dan empat hal yang membuatnya jujur.**
`plugins/mt5_orb.py` menarik bar M30 dari terminal MT5 yang sedang berjalan,
menggambar candle + kotak sesi + garis high/low range ke PNG di Desktop, lalu
menjawab dengan kalimat. Yang membuatnya berbeda dari "bikin chart":

1. **Timeframe bar adalah waktu broker, bukan UTC.** Kebanyakan broker FX
   memakai GMT+2/GMT+3. Membandingkan cap waktu itu dengan jendela sesi UTC
   menghasilkan range dua jam dari sesi yang salah — tanpa error. Jadi offset
   adalah **parameter** (`broker_utc_offset`, default +2), dan setiap jawaban
   **menyebutkan** asumsi itu.
2. **Hanya bar yang sudah tutup.** `copy_rates_from_pos` posisi 0 adalah bar yang
   masih berjalan; `closed_only=True` melewatinya. Wick yang menembus range
   bukan breakout — yang dihitung adalah **close** di luar range.
3. **Tidak ada paket di mesin ini.** Wheel PyPI `MetaTrader5` hanya Windows
   x86-64, jadi logikanya dipisah ke `_orb.py` (strategi + renderer) dan
   `_mt5.py` (jembatan terminal), keduanya bisa diuji dengan bar sintetis. Di
   Linux/macOS plugin tetap **dimuat** dan menjawab alasannya, bukan hilang.
4. **Tidak pernah mengirim order.** Tidak ada `order_send` di `_mt5.py`, dan
   sebuah test AST menolak kalau nanti ditambahkan: gate konfirmasi aplikasi ini
   dibangun untuk aksi yang bisa dibatalkan, dan market order bukan salah satunya.

Detail desain lain: `symbol_select` gagal dilaporkan sebagai "simbol broker
mungkin bersufiks" (`EURUSD.a`); kedalaman histori dibatasi "Max. bars in chart"
terminal; pip dari `symbol_info` (`point×10` hanya untuk 3/5 digit); dan kalau
Pillow tidak ada, chart jatuh ke ASCII, bukan gagal. Izin yang dideklarasikan
`files` (menulis PNG), bukan `network` — dan pemindaian impor di
`core/plugin_manifest.py` membuktikannya.

**Plugin keempat, dan temuan yang lebih berharga daripada pluginnya.** Saat
diminta "plugin seperti youtube player, code editor, dan lainnya", jawabannya
bukan menulis dua plugin itu: **`youtube_video` dan `code_helper` sudah ada
sebagai action bawaan** (`actions/`), dan loader menolak plugin yang namanya
bentrok dengan tool inti (`core/plugin_loader.py`: *Name 'X' collides with a
core tool*). Jadi peta yang berguna adalah **apa yang belum ada**, bukan apa
yang bisa diubah bentuknya.

`plugins/quick_notes.py` mengisi celah yang paling sering dipakai orang:
*"catat: bayar kos tanggal 5"* dan *"apa saja tugas saya?"*. Sebelumnya aplikasi
ini hanya punya `memory/long_term.json` — ingatan **asisten**, yang diringkas
ulang oleh summariser. Catatan yang diputuskan pengguna untuk disimpan bukan hal
yang sama, dan tidak boleh ikut diringkas.

Yang membuatnya berbeda dari "tulis ke file":

1. **Tiga buku, berkas Markdown.** `config/notes/inbox.md`, `todo.md`,
   `archive.md` — bisa dibuka Notepad, ikut ter-backup bersama `config/`, dan
   tidak bisa merusak apa pun yang dibutuhkan aplikasi untuk boot. Format JSON
   adalah format program; Markdown adalah format pengguna.
2. **Satu baris, selalu.** Newline di dalam catatan akan menjadi catatan kedua
   saat dibaca ulang (dan bisa memalsukan stempel waktu), jadi spasi
   dirapatkan dan `#`/`-` di depan dibuang. Yang diubah hanya bentuknya, bukan
   katanya.
3. **"Selesai" memindahkan, bukan menghapus.** Tugas yang cocok pindah ke
   `archive.md` dengan tanggal selesai. Kalau frasa cocok ke **lebih dari satu**
   tugas, jawabannya pertanyaan balik — mengarsipkan tugas yang salah adalah
   kegagalan yang baru ketahuan berminggu-minggu kemudian.
4. **Jam pengguna, bukan jam container.** `now` adalah parameter; test memberi
   waktu tetap. Catatan pukul 23:45 di Jakarta tidak boleh masuk ke tanggal
   kemarin karena mesinnya UTC.
5. **Izin kosong, dan itu keputusan.** `quick_notes.json` mendeklarasikan
   `"permissions": []`: yang disentuh hanya `config/notes/` miliknya sendiri,
   jadi tidak ada yang perlu disetujui. `_enabled()` memakai **izin yang
   dideklarasikan** sebagai alasan mulai-mati, bukan keberadaan manifest —
   sehingga plugin ini tetap menyala seperti plugin bawaan repo, sementara
   `currency_rates` (`network`) dan `mt5_orb` (`files`) tetap mulai mati. Ada
   test untuk ketiga keadaan itu sekaligus, karena kalau aturannya berubah,
   plugin ini akan hilang diam-diam bagi setiap pengguna yang tidak pernah
   membuka plugin manager.

**Harga pasar, dan kenapa satu endpoint sudah cukup.** `plugins/market_price.py`
menjawab *"harga BBCA"*, *"berapa bitcoin"*, *"EURUSD sekarang"*, *"emas?"* —
saham Jakarta, saham AS, kripto, forex, indeks dan futures semuanya berasal dari
**satu skema** yang sama: `/v8/finance/chart/<symbol>` di Yahoo, tanpa kunci dan
tanpa crumb.

Alternatifnya sudah diperiksa dan ditolak: endpoint `/v7/finance/quote` yang
terlihat paling tepat **mewajibkan crumb+cookie sejak 2024**, jadi plugin yang
memakainya akan berhenti bekerja tiga bulan setelah ditulis — persis kegagalan
yang `currency_rates` ada untuk mencegah. Endpoint chart mengembalikan harga
terakhir di blok `meta`, jadi kutipan dan histori datang dari permintaan yang
sama.

Empat jebakan, semuanya ditangani **dan** disebut di jawaban:

1. **Datanya tertunda** (umumnya ≤ 15 menit, kripto lebih dekat ke langsung).
   Harga yang tampak terkini padahal seperempat jam tua adalah angka yang orang
   akan perdagangkan — jadi setiap jawaban menyebutkan penundaan itu.
2. **Simbol adalah tebakan.** "BBCA" bukan simbol Yahoo. Resolusinya berurutan
   dan **dinyatakan**: `BBCA` → `BBCA.JK` → `BBCA`; yang menjawab dicetak di
   kalimat (*"Yahoo symbol used: BBCA.JK"*), sehingga tebakan yang salah terlihat
   dalam satu baris, bukan menjadi harga perusahaan lain.
3. **Perubahan bukan satu angka.** `regularMarketPrice` terhadap
   `chartPreviousClose` adalah pergerakan sesi; terhadap bar tiga minggu lalu
   adalah imbal hasil periode. Keduanya dihitung terpisah dan diberi label.
   Pergerakan sesi > 10 % memicu peringatan *"worth checking the symbol"* —
   saham yang tenang tidak bergerak 30 % sehari; indeks atau simbol yang salah
   bisa.
4. **`null` di dalam array close itu normal** (libur bursa, saham dihentikan).
   Diubah menjadi 0, ia menjadi crash 99 %; jadi null dibuang. `zip()` antara
   `timestamp` dan `close` juga berhenti di array terpendek — artinya close
   terakhir bisa hilang, yaitu satu-satunya angka yang dilihat orang — jadi
   pasangan itu ditinggalkan secara eksplisit ketika panjangnya tidak sama.

**Izinnya `network`, dan pemindai impor tidak bisa melihatnya** — karena
permintaan HTTP-nya ada di `_market.py`, bukan di berkas plugin. Itu justru
contoh yang benar untuk aturan di `core/plugin_manifest.py`: deklarasi jujur
yang **melebihi** hasil pemindaian adalah *warning*, bukan penolakan; hanya
penggunaan yang **tidak dideklarasikan** yang ditolak. Step CI plugin keempat
memeriksa keduanya sekaligus (manifest tetap sah, dan warning-nya memang muncul).

Tidak ada prediksi, tidak ada target harga, dan tidak ada pengganti "harga dari
ingatan" ketika jaringan gagal — kalimatnya bilang gagal dan berhenti di situ.

**Kenapa keychain tetap punya fallback file.** `keyring` butuh desktop session;
container, WSL, server headless, dan desktop Linux yang keyring-nya belum
dibuka sejak boot akan melempar exception pada panggilan pertama. Menolak start
di sana menukar risiko kecil dengan instalasi yang rusak. Jadi: coba keychain,
jatuh ke file, dan **katakan yang mana yang dipakai** — aplikasi yang membuat
pengguna percaya kuncinya di Keychain padahal di file telah berbohong.

> Tiga bug proses tertangkap justru saat mengerjakan sprint ini:
> **(1)** `core/secrets.py` menutupi modul stdlib `secrets` karena `core/` ada di
> `sys.path` — `keyring`, `uuid`, `random` semuanya mengimpornya, dan keenam
> runner mati dengan `ImportError: cannot import name randbits`. Sekarang
> `core/keychain.py`, plus test yang menolak **nama apa pun** yang menutupi
> stdlib.
> **(2)** Steps CI ditulis seolah bash satu-satunya shell: heredoc dan `$?`
> gagal di PowerShell, jadi step yang dibuat untuk *menjelaskan* kegagalan justru
> menambah satu. Sekarang `tools/annotate_junit.py` (file, ada test-nya) dan
> `tests/test_workflow_sh.py` yang membaca `ci.yml` sebagai YAML.
> **(3)** Test locale membaca mesin tempat ia jalan: `LANG`/`LC_ALL` runner macOS
> berbeda dari laptop Linux, jadi resolver yang benar terlihat salah. Sekarang
> fixture `clean_env`, dan file itu dijalankan ulang dalam subprocess dengan
> locale Indonesia.

### ⏭️ Sprint berikutnya

| Sprint | Fokus | Ukuran "selesai" |
|---|---|---|
| 3 | Pecah `ui.py` → `ui/`, `main.py` → `app/` | tidak ada file > 1.500 baris; `AGENTS.md` & kontrak plugin tidak berubah |
| 4 | Coverage `core/` ≥ 40 %, i18n 47 label UI | ✅ 37 % (29 % runner) + peta coverage, `assets/i18n/{en,id}.json` |
| 5 | Secret ke OS keychain, `shell=True` audit, marketplace plugin | ✅ keychain + fallback; **0** `shell=True`; ✅ manifest + izin (bukan sandbox) |

---

## 6. Roadmap yang Disarankan

| Sprint | Fokus | Hasil yang bisa diukur |
|---|---|---|
| **1 (1 minggu)** | 3 bug P0 + quality gate (B1, A) | `ruff` bersih, `pytest` hijau, CI 3 OS, path traversal tertutup, firewall Linux jalan |
| **2 (1 minggu)** | `core/config.py` + logging terstruktur + dashboard hardening | 1 penulis config, 0 race, header keamanan ada |
| **3 (2 minggu)** | Pecah `ui.py` → `ui/` dan `main.py` → `app/` (per-PR) | Tidak ada file > 1.500 baris; `AGENTS.md` tidak berubah |
| **4 (1 minggu)** | Coverage `core/` ≥ 40 %, i18n, docs | Regresi tertangkap CI, UI bisa diterjemahkan |

---

## 7. Quick Wins — status

| # | Item | Status |
|---|---|---|
| 1 | `for port in ports:` (P0-2) | ✅ Sprint 1 |
| 2 | `_safe_target()` di `dev_agent` (P0-1) | ✅ Sprint 1 |
| 3 | `_show_setup` simpan overlay + merge config (P0-3) | ✅ Sprint 1 |
| 4 | `shell=True` di `dashboard/server.py` | ✅ Sprint 1 (`cmd /c`) |
| 5 | `.gitattributes` + normalisasi EOL | ✅ Sprint 1 |
| 6 | `pyproject.toml` + `requirements-dev.txt` | ✅ Sprint 1 |
| 7 | 33 unused import + 9 f-string | ✅ Sprint 1 |
| 8 | `core/llm_client.py` kode mati | ✅ dihapus — 586 baris, 0 pemakai (diverifikasi `grep` atas 8 nama publiknya) |
| 9 | `config/__init__.py` salah path saat dibundel (`_MEIPASS`) | ✅ `1d9b17f` — memakai `CONFIG_FILE` dari `memory/config_manager`; 2 test |

---

## 8. Perintah Verifikasi (bisa Anda ulangi)

```bash
# sintaks seluruh repo
python -m compileall -q . -x __pycache__

# lint cepat tanpa dependensi proyek
pip install --target /tmp/pf pyflakes
PYTHONPATH=/tmp/pf python -m pyflakes $(git ls-files '*.py')

# loader action asli (16 valid, 4 ditolak dengan pesan jelas)
python -c "
from pathlib import Path
from core.action_loader import discover_actions
r = discover_actions(Path('actions'), set(), print)
print(sorted(r.names()))"

# cari bug undefined name / NameError
PYTHONPATH=/tmp/pf python -m pyflakes dashboard/server.py | grep undefined

# EOL campur
git ls-files '*.py' | while read f; do
  c=$(grep -c $'\r$' "$f"); t=$(wc -l < "$f")
  [ "$c" -gt 0 ] && [ "$c" -ne "$t" ] && echo "MIXED $f ($c/$t)"; done
```
