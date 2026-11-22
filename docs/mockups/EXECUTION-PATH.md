# Jalur eksekusi — dari permintaan model ke tindakan

Dokumen ini menjawab satu pertanyaan: **kalau model meminta sesuatu yang menyentuh
mesin, apa yang terjadi sebelum dan sesudahnya?** Ia melengkapi
[`DESIGN-ambient.md`](DESIGN-ambient.md), yang menjelaskan tampilannya, dan
jangan dianggap sebagai pengganti: shell ambient tidak punya jendela untuk
bertanya, jadi keputusan harus tinggal di bawah antarmuka.

Semua yang dijelaskan di sini sudah ada di repo, sudah dites, dan **tidak**
memerlukan Qt, jaringan, atau Windows.

---

## Satu putaran

```
model meminta tool
       │
       ▼
core.action_gate.check(tool, run, …)        core/action_gate.py
       │
       ├─ 1. core.risk_policy.decide(tool, undo_registered)
       │         safe   → jalankan
       │         medium → jalankan, ada undo terdaftar
       │         medium tanpa undo → DITAIKKAN ke risky
       │         risky  → butuh manusia
       │
       ├─ 2. catat "requested"               core/audit_log.py
       │
       ├─ 3. risky → core.confirm.request()  ← satu-satunya banner
       │         tidak ada UI terikat → MENOLAK, tidak menjalankan
       │
       └─ 4. catat hasil: done / unverified / failed
```

Poin yang mudah terlewat: **langkah 2 dan 4 terpisah.** Log yang hanya mencatat
apa yang selesai tidak bisa menjawab "ia minta mengirim email itu — saya izinkan
atau tidak?". Dialog konfirmasi justru kasus yang pertanyaannya paling penting.

---

## Tiga tingkat, dan satu default yang tidak boleh melunak

| Tingkat | Arti | Contoh | Perilaku |
|---|---|---|---|
| `safe` | bisa dibaca ulang, tidak mengubah apa pun | `web_search`, `clipboard_read` | langsung jalan |
| `medium` | mengubah keadaan, **tetapi ada jalan kembali** | `file_move`, `open_app` | jalan, `undo` terdaftar |
| `risky` | tidak bisa dibatalkan, atau terlihat orang lain | `send_message`, `mt5_trade`, `code_run` | **selalu** lewat `core.confirm` |

Dua aturan yang menjaga tabel ini dari pembusukan:

1. **Nama yang tidak dikenal dianggap `risky`.** Plugin baru, salah ketik, atau
   tool dari versi berikutnya tidak boleh lolos ke jalur tanpa konfirmasi.
2. **`medium` tanpa undo dinaikkan ke `risky`.** Tingkat menengah *menjanjikan*
   jalan kembali; kalau janji itu tidak ada, bertanya lebih baik daripada
   diam-diam menghilangkan jaminannya.

Test yang memegang aturan 1 dan 2 ada di `tests/test_risk_policy.py`, dan
keduanya sudah diperiksa dengan mutasi: mengubah default ke `safe` membuat dua
tes gagal.

### Tingkat melekat pada **panggilan**, bukan pada tool

`core/risk_policy.py` memetakan satu tool ke satu tingkat, dan bentuk itu tidak
bertahan pada tool yang benar-benar ada di repo ini:

| Tool | Satu tool, banyak aksi | Kalau diklasifikasi per tool |
|---|---|---|
| `computer_settings` | ~50 aksi: `volume_up` sampai `shutdown` | membaca volume butuh konfirmasi, atau mematikan mesin lolos |
| `file_controller` | `read` dan `delete` di bawah satu nama | salah satunya pasti salah |
| `code_helper` | `syntax` dan `run` | sama |

`core/tool_risk.py` karena itu mengklasifikasi `(tool, args)`. Tiga tabel
eksplisit — `_RISKY_ACTIONS`, `_SAFE_ACTIONS`, `_REVERSIBLE_ACTIONS` — dan satu
aturan: **sub-aksi yang tidak terdaftar dianggap `risky`**, bukan mewarisi
tingkat induknya. Mewarisi terlihat lebih rapi dan merupakan lubang: hari di
mana salah satu induk itu dilonggarkan ke `medium`, semua aksi tak terdaftar di
bawahnya ikut lolos tanpa suara.

`organize_desktop` sengaja muncul di dua tabel (punya undo, **dan** memindahkan
seluruh desktop sekaligus). Yang lebih ketat menang, dan test memastikan
keduanya tidak pernah bertentangan tanpa terlihat.

---

## Aksi yang sudah berpagar sendiri

Empat aksi memanggil `core.confirm.request` sendiri dengan kalimat yang ditulis
untuk operasi itu ("Jalankan build.py?" bukan "code_helper:run"). `main.py`
mendaftarnya di `SELF_GATED_ACTIONS`, dan gate hanya mencatat tingkatnya tanpa
bertanya dua kali — dua banner untuk satu shutdown adalah cara membuat pengguna
membiasakan diri menutup keduanya tanpa membaca.

Daftar itu tidak bisa membusuk diam-diam: `tests/test_gate_wiring.py` membaca
sumber setiap aksi dan gagal kalau namanya ada di daftar tetapi aksinya tidak
pernah memanggil `confirm.request`. Menambah nama di sana tanpa pagar sungguhan
berarti melewati gate sepenuhnya.

## Konfirmasi tidak bisa dipalsukan model

`core.action_gate.check()` tidak punya parameter `confirmed`, `force`, `yes`,
atau `approve`. Satu tes membaca `inspect.signature` dan gagal kalau salah
satunya muncul. Alasannya bukan gaya: `core.confirm.request()` mengembalikan
kalimat yang dibaca model, dan kalau model bisa mengubah "menunggu" menjadi
"jalan" dengan argumen, seluruh lapisan UI tepercaya hanya jadi hiasan.

Yang terjadi saat menunggu:

- banner hanya boleh satu pada satu waktu; permintaan kedua **ditolak**, bukan
  diantrekan;
- tidak ada UI terikat (headless, atau panggilan sangat awal) → **menolak**,
  dengan kalimat yang menyebutkan bahwa tindakan belum dilakukan;
- hasilnya dicatat sebagai `awaiting`, lalu `confirmed` / `cancelled` /
  `expired` / `failed`.

---

## Fokus, Senyap, dan janji "3 tertahan"

`core/presence_mode.py` memegang mode, bukan widget, karena dengan mode ambient
tidak ada jendela untuk ditanyai dan toast lahir di thread penjadwal.

| Mode | Saran | Banner | Orb |
|---|---|---|---|
| `active` | tampil | boleh | penuh |
| `focus` | **ditahan**, dengan jumlah | boleh | penuh |
| `quiet` | dibuang | tidak | meredup |

Kalimat di panel baki — *"3 tertahan · akan muncul setelahnya"* — adalah kontrak,
dan tes memegangnya: `offer()` mengembalikan tiga jawaban berbeda (`show`,
`hold`, `drop`), dan meninggalkan Fokus **tidak** menghapus yang tertahan;
pemanggil mengalirkannya lewat `take_held()` supaya urutannya tetap.

**Diputuskan:** Fokus dan Senyap **meredupkan orb**. Board 24 (redup 28→18 px,
glow hilang, cincin jadi titik-titik) sekarang menjadi perilaku di
`ui/orb_overlay.appearance()` dan diuji di `tests/test_orb_overlay.py` serta
`tests/test_presence_wiring.py`.

### Dari mana mode itu datang, dan ke mana perginya

```
baki: "Aktif / Fokus / Senyap"   (satu item, menelusuri tiga mode)
        │  cycle_presence_mode()
        ▼
core.presence_mode.set_mode()  ──write──▶  config/api_keys.json
        │                                      ("presence_mode")
        ├─▶ ui.orb_overlay.set_mode()   orb meredup / menyala
        └─▶ scheduler thread            offer() → show / hold / drop

saat mulai: main.py  _presence_bound()
        │  bind(read=get_presence_mode, write=save_presence_mode)
        ▼
   presence_mode.current()  ──▶  ui.apply_presence(mode)  ──▶  orb
```

Rantai ini sempat **putus dan semua tesnya hijau**: `apply_presence_mode` tidak
pernah dipanggil, dan `presence_mode` tidak pernah di-`bind`, sehingga
`current()` selalu menjawab `active`. Akibatnya pengaturan tersimpan, orb
meredup sekali, lalu dilupakan saat restart. `tests/test_presence_chain.py`
sekarang menguji rantainya, bukan potongannya — termasuk membaca `main.py`
secara struktural untuk memastikan bind terjadi **sebelum** keputusan
notifikasi pertama.

### Desain yang terlihat, bukan hanya benar

`paint_orb` sempat **tidak pernah dipanggil**: painter-nya objek biasa tanpa
`paintEvent`, jadi jendela orb dibuat, ditampilkan, transparan — dan kosong.
Geometri, tiga mode, dan hit region semuanya lulus tes, dan tak satu pun dari
itu yang menaruh piksel di layar. Itu beda antara desain yang **diimplementasi**
dan desain yang **terlihat**.

Sekarang `_build_canvas()` membuat `QWidget` sungguhan dengan `paintEvent`, dan
tesnya memeriksa hal struktural — "ada yang tersambung ke siklus paint" —
bukan hanya aritmetika. Tingkat audio juga mengalir ke glow lewat
`set_audio_level`, dengan nilai di-clamp: Qt menolak gradien dengan stop di
luar 0..1, dan kegagalannya muncul sebagai cincin biasa tanpa penjelasan.

Tiga permukaan (tooltip, bubble, orb) diperbarui **independen**. Sebelumnya satu
orb yang gagal mengecat bisa menjatuhkan pembaruan tray — dan justru di situ
tooltip adalah satu-satunya bacaan yang tersisa.

Label item baki menyebut **mode**, bukan aksinya ("Fokus — saran ditahan"),
dan dibaca ulang setelah setiap klik: menu yang masih menampilkan mode lama
adalah bug yang sama dengan centang yang basi, satu baris lebih bawah.

---

## Anggaran harian saran

`core/suggestion_quota.py`: tiga saran per **hari kalender lokal**, disimpan
sebagai `{"date", "used"}` saja — tidak ada riwayat, tidak ada isi saran. Berkas
yang rusak atau dari hari lain menghasilkan hari yang baru, bukan error. Batas
nol berarti nol.

`take()` sengaja menggabungkan periksa dan potong dalam satu kunci: dua penjadwal
yang berbagi anggaran tidak boleh sama-sama menghabiskan slot terakhir. Ada tes
20-thread untuk itu.

---

## Log audit, terpisah dari log diagnostik

`logs/jarvis.log` berputar di 2 MB dengan tiga cadangan dan mencampur exception
Qt dengan riwayat tindakan. Halaman Privasi menjanjikan daftar aktivitas yang
bisa dibaca dan bisa dihapus; keduanya butuh berkas sendiri.

- `config/audit.jsonl`, satu objek JSON per baris;
- **5.000 catatan**, sisakan 2.500 saat berputar (memotong berdasarkan jumlah,
  bukan ukuran, agar "sebulan lalu" tidak hilang sekaligus);
- `detail` dipotong 200 karakter — isi berkas yang dibaca tidak boleh ikut masuk;
- `erase()` untuk tombol *Hapus riwayat*;
- kegagalan tulis **tidak pernah** menjadi exception pemanggil.

Keduanya masuk `.gitignore`: log audit menyebut nama berkas dan keputusan
pribadi, dan hitungan saran hari ini tidak berarti apa pun setelah di-commit.

---

## Apa yang belum dikerjakan

| Modul | Status | Catatan |
|---|---|---|
| `ui/toast_queue.py` | **selesai** | antrean, kapasitas 3, hitungan yang dibuang; bebas Qt |
| `ui/orb_overlay.py` | **selesai** | 96 px, meredup di Fokus/Senyap; `paintEvent` sungguhan |
| `ui/command_bar.py` | **selesai** | Ctrl+Space, riwayat 10 baris; fokus kembali dicatat, bukan diklaim |
| `core/undo_journal.py` | **tidak perlu** | `core/undo.py` sudah melakukan ini |
| `core/tool_registry.py` | belum | `risk_policy.register()` sudah jadi tempatnya |
| sambungan ke `main.py` | **selesai** | dua jalur registry lewat `action_gate.check`; `self_gated` untuk empat aksi |

Tiga hal hanya bisa dibuktikan di Windows dan **jangan** diklaim berfungsi:
klik-tembus orb (`WindowTransparentForInput` berbeda di X11/macOS), fokus
kembali setelah Esc, dan DPAPI.

`core/action_gate.py` **sudah tersambung** ke jalur action dan plugin di
`main.py`. Yang belum: jalur `tool_dispatch` (`recall_memory`, `undo`,
`system_status`, …) — semuanya read-only atau sudah reversibel, jadi gate hanya
akan menambah catatan audit, bukan gerbang. Itu langkah berikutnya kalau
diinginkan.
