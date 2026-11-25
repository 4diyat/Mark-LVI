# Spec Implementasi — Verifikasi Suara (Voice Verification)

> Spesifikasi lengkap untuk fitur **Verifikasi Suara**: JARVIS memverifikasi
> suara pengguna (voiceprint) saat dijalankan, sebelum asisten menjawab
> perintah. Tujuan, kebijakan murni, arsitektur engine, integrasi
> file-by-file, permukaan UI, rencana tes, dan batasan yang jujur.
>
> Tanggal: 2026-11-24 · Branch: `arena/a905a8af-mark-lvi`
> Pendamping: `design/NEW-UI-DESIGN.md` §5.1
> Menggantikan: `design/SPEC-GUEST-MODE.md` (dihapus — Mode Tamu
> ditolak, arah keamanan berubah ke verifikasi identitas suara).

---

## 1. Tujuan & Latar Belakang

Pemilik menginginkan **verifikasi suara** saat menjalankan JARVIS: sebelum
asisten menjawab perintah, ia memverifikasi bahwa suara yang datang
adalah **pemilik**, bukan orang lain di ruangan.

Fitur ini dibangun di atas infrastruktur yang **sudah ada**, bukan dari
kosong:

| Komponen yang ada | Peran di verifikasi suara |
|---|---|
| `core/wake_word.py` | **Model arsitektur**: model lokal yang di-import secara lazy, thread terpisah, `feed(frame_int16)` dari callback mikrofon, tidak membebani jalur audio real-time |
| `core/echo.py` (`EchoGuard`) | **Penolakan echo**: memastikan suara JARVIS sendiri (TTS output) tidak memenuhi verifikasi |
| `core/voice_interrupt.py` | Interaksi dengan barge-in: saat verifikasi, interupsi dikelola agar tidak menutupi proses verifikasi |
| `core/audio_devices.py` | Pemilihan input/output, `measure_input` untuk level meter pendaftaran |
| `memory/config_manager.py` | Penyimpanan setting (`get/save_*` pattern) |
| `memory/` (gitignored) | Penyimpanan lokal voiceprint |
| `assets/i18n/` (en + id) | Semua kalimat di dua bahasa |
| `providers/` (STT lokal) | Referensi model lokal yang tidak mengirim audio ke jaringan |

**Prinsip yang ditegakkan** (dari `AGENTS.md` dan docs):
- **Lokal & privat**: audio dan voiceprint **tidak pernah** meninggalkan
  mesin. Tidak ada jaringan ke penyedia suara untuk verifikasi.
- **Zero cost saat tidak digunakan**: jika fitur mati atau belum
  terdaftar, tidak ada model yang di-import, tidak ada thread, tidak
  ada biaya (pattern `core/wake_word.py`: "ZERO cost when the feature
  is off").
- **Jujur tentang apa yang bisa dilakukan**: batasan diterangkan
  di §7, seperti semua spec proyek ini.

---

## 2. Definition of Done (Syarat yang Dapat Diuji)

1. `get_voice_auth_enabled()` default **False** — verifikasi tidak
   aktif tanpa disengaja oleh pengguna (pattern `get_wake_word_enabled`).
2. **Pendaftaran** (enrollment): pengguna rekam ≥ N sampel suara;
   voiceprint disimpan lokal di `memory/voiceprint.json` (gitignored);
   hanya setelah pendaftaran berhasil fitur bisa diaktifkan.
3. Saat fitur **aktif dan terdaftar**, sesi berjalan dalam keadaan
   **terkunci** sampai suara pemilik lolos verifikasi; setelah lolos,
   asisten menjawab perintah (keadaan **terverifikasi**).
4. **Setiap verifikasi**: hasilnya `AuthResult(score, passed)`;
   `score ∈ [0,1]`; `passed` jika `score >= threshold` (default
   imilai di antara detection seperti `core/wake_word.py`
   `DEFAULT_THRESHOLD`).
5. **Gagal N kali** → lockout selama `LOCKOUT_SECONDS` (default
   30 s); selama lockout, verifikasi ditolak dengan kalimat yang
   jelas (bukan diam).
6. **Penolakan echo**: selama verifikasi aktif, audio output (TTS
   JARVIS sendiri) **tidak** boleh membuat verifikasi lolos — reuse
   `EchoGuard` (`note_output` / `is_user_speech`).
7. **Keadaan** bisa dibunuh: timeout verifikasi (misal suara berhenti
   10 s saat keadaan verifikasi) → kembali ke keadaan terkunci.
8. Semua kalimat (prompt verifikasi, hasil, lockout, kesalahan
   pendaftaran) ada di **dua katalog bahasa** (`assets/i18n/en.json`
   + `id.json`).
9. **Tes kebijakan murni 100% tanpa Qt** (gaya `tests/test_risk_policy.py`).
10. **Tes AST** memastikan tidak ada tool/plugin yang membaca
    voiceprint atau mengatur verifikasi secara langsung (gaya
    `tests/test_paths.py`).
11. Voiceprint **tidak pernah** masuk git (`.gitignore`).

---

## 3. Arsitektur & Kebijakan Murni — `core/voice_auth.py` (baru)

Module ini mengikuti pola `core/echo.py` (kebijakan murni + engine)
dan `core/wake_word.py` (lazy import model, thread terpisah). **Tidak
ada Qt, tidak ada I/O langsung di policy functions.**

### 3.1 Kebijakan murni (fungsi, tanpa state I/O)

| Fungsi | Signature | Berarti |
|---|---|---|
| `decide(score, threshold, attempts, locked_until) -> Decision` | `-> Decision` | Inti keputusan: score vs threshold, escalate attempts, lockout |
| `next_attempt(attempts) -> int` | `-> int` | increment + clamp |
| `is_locked(locked_until, now) -> bool` | `-> bool` | apakah sedang lockout |
| `should_verify(state) -> bool` | `-> bool` | apakah keadaan memerlukan verifikasi (terkunci / harus verifikasi ulang) |
| `timeout_state(now, verified_at, timeout) -> str` | `-> str` | "verified" / "needs_verify" berdasarkan waktu |

`Decision` (dataclass frozen, seperti `risk_policy.Decision`):

```python
@dataclass(frozen=True)
class Decision:
    passed: bool          # score >= threshold dan tidak lockout
    score: float          # score mentah
    threshold: float
    attempts: int
    locked: bool          # True jika sedang lockout
    reason: str           # kalimat pendamping (bukan hanya True/False)
```

### 3.2 Keputusan kebijakan (dengan alasan)

- **Threshold**: nilai tengah yang bisa disesuaikan per lingkungan
  (ruang bergema, mic berbeda). Default mengikuti pola
  `core/wake_word.py: DEFAULT_THRESHOLD` — tunable, bukan magic
  number tanpa komentar.
- **Escalating attempts**: gagal berturut-turut menaikkan attempts;
  lockout setelah N kegagalan untuk mencegah brute-force dengan
  rekaman berulang. Setiap keputusan memberi **reason** — tidak ada
  penolakan diam-diam (pelajaran dari `except: pass`).
- **Verifikasi ulang**: keadaan "terverifikasi" memiliki **timeout**;
  setelah timeout (atau suara tidak cocok lagi), kembali ke keadaan
  terkunci. Ini mencegah verifikasi sekali di awal menjadi lubang
  permanen.
- **Echo adalah musuh**: audio yang dihasilkan JARVIS sendiri tidak
  boleh menjadi kunci. `EchoGuard` yang sudah ada (dengan `note_output`
  dari jalur playback) digunakan untuk menolak output audio selama
  verifikasi — bukan sesuatu yang baru dibuat.

### 3.3 Engine — `VoiceAuth` (class)

Seperti `WakeWordDetector`, engine ini:

- **Lazy import** backend model — backend yang berat **tidak**
  di-import saat module di-load. Pattern `importlib.util.find_spec`
  seperti `wake_word.is_installed()`.
- **Thread terpisah** untuk inference yang berat; callback mikrofon
  hanya melakukan `feed()` non-blocking (pattern `WakeWordDetector.feed`).
- **Backend pluggable** melalui protocol `Embedder`:

```python
class Embedder(Protocol):
    def embed(self, pcm, sr: int) -> "np.ndarray": ...
```

| Backend | Implementasi | Ketergantungan |
|---|---|---|
| `BandEnergyEmbedder` (**default**) | Fingerprint energi per band FFT — **reuse logika `core/echo.py: band_energies`**; score = cosine similarity antara sampel vs voiceprint. Bekerja **tanpa dependency berat**. | numpy (sudah ada, dari echo guard) |
| `OnnxEmbedder` (**opsional**) | Embedding speaker nyata (mis. ECAPA-TDNN via ONNX/speechbrain). Di-import **hanya** jika dipasang & diaktifkan pengguna. | Model lokal, lazy import |

- API engine:

```
class VoiceAuth:
    def __init__(self, *, threshold=DEFAULT_THRESHOLD, embedder=None)
    def is_enabled(self) -> bool
    def is_enrolled(self) -> bool
    def enroll(samples: list[bytes], sr: int) -> EnrollResult   # N sampel → voiceprint
    def verify(pcm: bytes, sr: int) -> AuthResult               # (score, passed)
    def reset(self) -> None                                      # hapus attempts/lockout, tetap terdaftar
    def forget(self) -> None                                    # hapus voiceprint (hanya dari UI/owner)
    def state(self) -> str                                       # "locked"/"verifying"/"verified"/"enrolled_off"
```

- `enroll()` menyimpan voiceprint **lokal**:
  `memory/voiceprint.json` (gitignored, seperti `memory/long_term.json`).
  Format minimal: `{"created": "...", "samples": N, "embedder": "band_energy", "embedding": [...]}`.
- `verify()` mengembalikan `AuthResult(score, passed)` **tanpa
  menyimpan audio** — hanya embedding sementara yang dihitung.

### 3.4 Modul tidak boleh

- Tidak mengirim audio ke jaringan (fitur ini **local-first**).
- Tidak membuat widget Qt (aturan `AGENTS.md`: policy di `core/`,
  UI di `ui/`).
- Tidak mengaktifkan/menonaktifkan sendiri — state dibaca dari
  config, ditulis lewat `save_voice_auth_enabled` dari UI.

---

## 4. Integrasi — File by File

### 4.1 `core/voice_auth.py` (baru)
Kebijakan murni + engine seperti §3. Tidak ada Qt.

### 4.2 `memory/voiceprint_store.py` (baru)
Penyimpanan lokal voiceprint (load/save/delete), dengan **lock**
(RLock, pattern `memory/memory_manager.py`) dan penulisan atom
(pattern `_write_atomic`). File: `memory/voiceprint.json`.

### 4.3 `memory/config_manager.py` (modifikasi)
Tambahkan, mengikuti pola `get_wake_word_enabled`:

```python
def get_voice_auth_enabled() -> bool:
    return bool(load_api_keys().get("voice_auth_enabled", False))

def save_voice_auth_enabled(enabled: bool) -> bool:
    return set_config_values(voice_auth_enabled=bool(enabled))
```

Opsional: `get_voice_auth_threshold()` / `save_voice_auth_threshold(float)`
jika pengguna ingin menyetel threshold.

### 4.4 `.gitignore` (modifikasi)
Tambahkan `memory/voiceprint.json` di bagian "Personal data" (setelah
`memory/long_term.json`), dan tambahkan aturan itu ke
`tests/test_gitignore.py` — mengikuti pola yang sudah ada: **setiap
aturan diuji dengan `git check-ignore`**.

### 4.5 `main.py` (modifikasi) — integrasi sesi
- Saat boot: `VoiceAuth` di-inisialisasi, reader terikat
  (pattern `core/presence_mode.bind`) ke `get/save_voice_auth_enabled`.
- **Gate verifikasi**: di loop sesi (`JarvisLive.run`), sebelum
  menjawab perintah saat fitur aktif & terdaftar:
  - keadaan `locked` → minta pengguna berbicara (prompt), `verify()`;
    jika `passed` → keadaan `verified`, lanjut; jika gagal →
    increment attempts / lockout dengan kalimat.
  - keadaan `verified` → periksa timeout (§3.2); jika melebihi,
    kembali ke `locked`.
- **Echo rejection**: di jalur playback (`note_output` dari
  `EchoGuard`), output audio selama verifikasi **tidak** boleh
  memberi sinyal input — verifikasi hanya menerima audio dari
  callback mikrofon yang lolos `EchoGuard.is_user_speech`.
- **Interplay barge-in** (`core/voice_interrupt`): saat verifikasi
  aktif, barge-in dikelola agar tidak memotong proses verifikasi
  tengah jalan (pattern yang sudah ada).
- **Tidak aktif**: behavior **100% seperti sekarang** (zero cost).

### 4.6 `core/echo.py` (modifikasi ringan)
- Reuse eksisting; pastikan `is_user_speech()` digunakan oleh
  `VoiceAuth` saat memisahkan input mikrofon dari output TTS selama
  verifikasi. Tidak ada perubahan logika inti.

### 4.7 `ui/` — permukaan
- **Pendaftaran** (`ui/pages_admin.py` atau `ui/setup_screen.py`
  extend): layar "Verifikasi Suara": tombol rekam, level meter
  (`audio_devices.measure_input`), playback cek, progress N sampel,
  hasil (terdaftar / gagal). Hanya jika `is_installed()` (backend
  tersedia).
- **Status**: chip di header panel ("Terverifikasi" hijau
  `#00ff88` / "Perlu verifikasi" kuning `#ffcc00` / "Terkunci"
  merah `#ff3355`), sesuai palette `ui/theme.py`.
- **Kartu di halaman Keamanan** (board 14): toggle aktif + status
  pendaftaran + tombol "Hapus voiceprint" (confirm gate,
  `core/confirm.py`) + tombol "Daftar ulang".
- **Orb** (board 20): keadaan tambahan **"verifying"** — dibedakan
  lewat siluet (bukan hanya warna), mengikuti aturan empat status
  orb.
- Ingat: **widget hanya di Qt thread**; engine di thread sendiri,
  komunikasi lewat pyqtSignal (aturan `AGENTS.md`).

### 4.8 `assets/i18n/en.json` + `assets/i18n/id.json` (modifikasi)
Tambahkan kunci (di **kedua** katalog): `voice_auth.*`:
`enroll_start`, `enroll_recording`, `enroll_samples`, `enroll_done`,
`enroll_failed`, `verify_prompt`, `verify_passed`, `verify_failed`,
`verify_locked`, `verify_timeout`, `voice_auth_deleted`,
`voice_auth_not_installed`.

### 4.9 `AGENTS.md` (modifikasi)
Aturan baru:
- *"Verifikasi suara adalah fitur lokal: audio dan voiceprint tidak
  pernah meninggalkan mesin. Tool/plugin tidak boleh membaca
  `memory/voiceprint.json` atau mengatur verifikasi — semua lewat
  `core/voice_auth`."*
- Audio verification hanya dari `core/voice_auth` + `core/echo`;
  tidak ada pengecekan suara di `actions/` atau `plugins/`.

### 4.10 Dokumen (modifikasi)
- `docs/verification.md`: tambahkan baris Verifikasi Suara ke matriks
  verifikasi: cakupan otomatis + yang perlu diuji perangkat nyata.
- `design/new-ui-proposal-ANALISIS.md`: catat board 14 kartu Verifikasi
  Suara + keadaan orb "verifying".

---

## 5. Permukaan UI (Desain)

Berdasarkan `design/NEW-UI-DESIGN.md` §4 dan visual yang ada
(`04-security-permissions.png`, `05-onboarding.png`):

- **Layar pendaftaran**: seperti onboarding (board 7) — orb besar,
  level meter, progress sampel, tombol "Rekam"/"Selesai". Cerita
  pendaftaran: rekam 3–5 sampel kalimat pendek (atau kalimat
  bebas), playback cek setiap sampel, hasil akhir.
- **Chip status** di header panel: hijau/kuning/merah dengan kalimat
  di dua bahasa.
- **Kartu Verifikasi Suara** di halaman Keamanan (board 14): toggle,
  status pendaftaran, hapus voiceprint (dengan konfirmasi), daftar
  ulang.
- **Keadaan orb "verifying"**: siluet berbeda (misal orb dengan
  cincin pemisah), bukan hanya warna.

Visual tambahan dapat dibuat jika perlu (misal `17-voice-verify.png`)
— ditentukan saat implementasi UI.

---

## 6. Rencana Tes

Mengikuti konvensi repo: **kebijakan murni tanpa Qt**, tes engine
dengan embedder palsu, tes AST, konformansi.

### 6.1 `tests/test_voice_auth.py` (baru) — kebijakan murni
Gaya `tests/test_risk_policy.py`:

| Tes | Yang dijamin |
|---|---|
| `test_score_at_threshold_passes` | score == threshold → passed |
| `test_score_below_threshold_fails` | score < threshold → failed + reason |
| `test_failed_attempts_increment` | attempts naik tiap kegagalan |
| `test_lockout_after_max_attempts` | N gagal → locked, alasan disebut |
| `test_lockout_expires` | setelah `locked_until` lewat → verifikasi bisa lagi |
| `test_should_verify_states` | locked/verifying → True; verified → False |
| `test_timeout_returns_to_locked` | verified_at + timeout → needs_verify |
| `test_no_enrollment_blocks` | tidak terdaftar → tidak bisa verifikasi (error) |

### 6.2 `tests/test_voice_auth_engine.py` (baru) — engine dengan embedder palsu
- FakeEmbedder: embedding konstan/terkontrol → verify pass/fail
  sesuai skenario.
- `test_enroll_then_verify_passes` — terdaftar → verifikasi lolos.
- `test_verify_without_enroll_raises/errors` — tidak terdaftar.
- `test_verify_wrong_voice_fails` — embedder berbeda → gagal + attempts.
- `test_reset_clears_attempts` — reset → attempts 0, tetap terdaftar.
- `test_forget_removes_voiceprint` — forget → is_enrolled False.

### 6.3 `tests/test_voice_auth_echo.py` (baru) — penolakan echo
- Menggunakan **EchoGuard asli** dengan sinyal synthetic:
- `test_output_audio_does_not_pass_verification` — audio output TTS
  (yang catat `note_output`) **tidak** membuat verify lolos.
- `test_user_speech_passes_when_calibrated` — setelah kalibrasi,
  input mikrofon lolos.

### 6.4 `tests/test_voice_auth_ast.py` (baru) — keamanan arsitektur
Pattern `tests/test_paths.py`:
- Tidak ada file di `actions/` atau `plugins/` yang mengimpor
  `voiceprint.json`, `core.voice_auth`, atau `memory.voiceprint_store`
  secara langsung.
- Tidak ada plugin yang bisa mengaktifkan verifikasi (hanya
  `save_voice_auth_enabled` dari UI/security page).

### 6.5 `tests/test_gitignore.py` (perluas)
- `memory/voiceprint.json` termasuk aturan yang dicek `git
  check-ignore`; baris tidak boleh mengandung `#`.

### 6.6 Tes integrasi
- `tests/test_config.py`: round-trip `voice_auth_enabled`.
- `tests/test_voice_auth_store.py` (baru): load/save/delete
  voiceprint, penulisan atom, tidak corrupt pada baca ulang.

### 6.7 Catatan kualitas
- **Tidak ada tes yang membutuhkan mikrofon/jaringan/Qt**. Semua
  tes menggunakan PCM sintetis + embedder palsu.
- Gunakan `tmp_path` untuk voiceprint (aturan: tes tidak menulis
  config/data nyata, lihat `pyproject.toml`).

---

## 7. Batasan yang Jujur (What It Cannot Do)

1. **Bukan forensic-grade.** Backend default (`BandEnergyEmbedder`)
   adalah fingerprint fitur — bekerja untuk pemindaian "suara yang
   sama vs suara lain" di ruangan dekat dengan mic yang sama, bukan
   identifikasi forensik. Backend ONNX opsional memperkuat, tetapi
   tetap bukan jaminan mutlak.
2. **Serangan rekaman ulang (replay).** Backend default tidak
   membedakan rekaman suara asli vs putar ulang. Mitigasi: kalimat
   verifikasi acak (challenge-response) di versi berikutnya, atau
   backend yang mendukung anti-replay. **Sebut ini di UI**, jangan
   janji.
3. **Memerlukan pendaftaran.** Tanpa pendaftaran, fitur tidak
   aktif — seperti wake word yang perlu model terpasang. Ini
   **bukan kekurangan**, tetapi syarat.
4. **Asumsi perangkat sama.** Voiceprint belajar dari mic tertentu;
   perubahan mic besar (USB → built-in) dapat menurunkan akurasi —
   daftar ulanglah jika akurasi turun.
5. **Tidak melindungi data lain.** Verifikasi suara adalah **pintu
   masuk**, bukan enkripsi memori/riwayat. Data lain tetap di bawah
   kontrol fitur keamanan yang sudah ada (risk_policy, confirm,
   permissions).
6. **Permukaan UI tidak bisa diuji sepenuhnya tanpa perangkat
   nyata** (Qt offscreen smoke di CI hanya verifikasi interaksi
   terprogram) — seperti semua permukaan di `docs/verification.md`.

---

## 8. Langkah Implementasi (Urutan)

1. **Kebijakan murni** — `core/voice_auth.py` (fungsi decide/next_
   attempt/is_locked/should_verify/timeout_state) +
   `tests/test_voice_auth.py`.
2. **Penyimpanan** — `memory/voiceprint_store.py` +
   `tests/test_voice_auth_store.py`; `.gitignore` + perluas
   `tests/test_gitignore.py`.
3. **Engine + embedder** — `VoiceAuth`, `BandEnergyEmbedder`
   (reuse `band_energies` dari echo.py), backend opsional
   `OnnxEmbedder` lazy-load + `tests/test_voice_auth_engine.py`.
4. **Penolakan echo** — integrasi `EchoGuard` di `verify()` +
   `tests/test_voice_auth_echo.py`.
5. **Storage config** — `get/save_voice_auth_enabled` di
   `memory/config_manager.py` + `tests/test_config.py`.
6. **Integrasi sesi** — gate verifikasi di `main.py` (state machine
   locked/verifying/verified, timeout, interplay barge-in).
7. **UI** — layar pendaftaran, chip status, kartu di halaman
   Keamanan, keadaan orb, i18n dua bahasa.
8. **Tes AST & dokumen** — `tests/test_voice_auth_ast.py`,
   `AGENTS.md`, `docs/verification.md`,
   `design/new-ui-proposal-ANALISIS.md`.

**Ukuran upaya:** Sedang. Bagian terbesar adalah state machine
integrasi sesi + UI pendaftaran; policy murni dan store relatif
kecil. Audio tetap lokal, tidak ada dependency jaringan.
