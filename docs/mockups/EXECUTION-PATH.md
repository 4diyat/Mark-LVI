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

---

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

> **Belum diputuskan:** apakah Fokus/Senyap juga meredupkan orb. Board 24
> mengasumsikan redup 28→18 px, glow hilang, cincin jadi titik-titik. Itu
> keputusan produk, bukan implementasi — jangan diambil sendiri.

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
| `ui/orb_overlay.py` | **belum** | klik-tembus hanya bisa dibuktikan di Windows |
| `ui/command_bar.py` | **belum** | Ctrl+Space, Esc mengembalikan fokus — Windows |
| `core/undo_journal.py` | **tidak perlu** | `core/undo.py` sudah melakukan ini |
| `core/tool_registry.py` | belum | `risk_policy.register()` sudah jadi tempatnya |
| sambungan ke `main.py` | belum | `action_gate` belum dipanggil dari loop mana pun |

Tiga hal hanya bisa dibuktikan di Windows dan **jangan** diklaim berfungsi:
klik-tembus orb (`WindowTransparentForInput` berbeda di X11/macOS), fokus
kembali setelah Esc, dan DPAPI.

`core/action_gate.py` sudah siap dipakai tetapi belum disambungkan ke pemanggil
tool mana pun. Menyambungkannya mengubah perilaku setiap tindakan, jadi itu
langkah tersendiri — bukan efek samping dari commit ini.
