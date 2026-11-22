# Status fitur dan panduan verifikasi JARVIS

Dokumen ini memisahkan **cakupan pengujian**, **persyaratan**, dan hal yang
**belum diverifikasi**. “Lulus tes” tidak berarti bebas bug atau berfungsi di
semua komputer. Hasil uji lokal tidak otomatis menjadi hasil CI atau rilis.


> ## BACA DULU: banyak baris di bawah sudah tidak berlaku
>
> Build ini **menghapus** seluruh permukaan yang tidak digambar mockup
> (`docs/mockups/jarvis-design-system.html`, 12 papan). Yang tersisa hanya:
> orb, toast, command bar, panel baki, konfirmasi risiko, face bubble, dan
> `AmbientShell`. Catatan lengkap beserta cara mengembalikannya ada di
> **`docs/mockups/NOT-IN-MOCKUP.md`**.
>
> Baris matriks berikut menjelaskan fitur yang **tidak ada lagi** di build ini,
> dan sengaja tidak dihapus supaya riwayat klaimnya tetap terbaca:
>
> | Baris | Keadaan sekarang |
> |---|---|
> | Workspace desktop & navigasi | dihapus — `ui/window.py`, `ui/desktop_workspace.py` |
> | Kontrol tangan workspace | dihapus — papan 6 masih usulan |
> | Order MT5 / ORB | dihapus — `ui/mt5_trade.py`, `ui/trading_terminal.py` |
> | Editor kode/gambar, penampil OBJ | dihapus |
> | Remote HTTP/HTTPS (dashboard) | model tetap; tidak ada UI |
> | Widget mengambang, Layer Dashboard, Dokumen mengambang | dihapus |
> | Cincin pointer desktop, Tangan → OS | dihapus — `core/` tetap, tanpa pemanggil |
> | Akses file penuh | model tetap; prompt-nya widget, jadi tidak ada yang bertanya |
>
> Yang **masih** berlaku dan masih diuji: mikrofon, briefing, bibir/jadwal audio,
> transkrip, prompt, reconnect, provider, plugin, integrasi OS, Obsidian,
> riwayat percakapan, dan seluruh permukaan ambient.
>
> **Panel baki (papan 5, 23, 26, 27, 28) sekarang ada**, termasuk saklar tema
> tiga keadaan di header (papan 28). `auto` membaca `ui_os_theme` dari
> `config/api_keys.json`, bukan kueri desktop langsung — deteksi tema berjalan
> adalah urusan pemilik QApplication. Bila kunci itu tidak ada, `auto` = gelap. Empat hal yang
> digambar tetapi belum sepenuhnya didukung, dan mengatakannya di layar:
> *Susun jendela* (tidak ada kode window-snapping di pohon ini), *Mode tamu*
> (belum ada yang berhenti membaca memori), *Dikte* (tahan enam detik lewat
> timer, bukan tekan-tahan), dan *Cari berkas* (membuka command bar dengan
> awalan, bukan mencari sendiri). Tiga chord di baris aksi cepat adalah milik
> artboard dan **tidak** terdaftar sebagai hotkey; hanya summon dan command bar
> yang benar-benar terikat. Rinciannya di `docs/mockups/NOT-IN-MOCKUP.md`.

## Matriks verifikasi

| Area | Cakupan otomatis saat ini | Masih perlu diuji pada perangkat/layanan nyata |
|---|---|---|
| Workspace desktop & navigasi | Tes struktur/stub; CI memiliki smoke Qt offscreen Linux | Tampilan, fokus, ukuran dan aksesibilitas pada Windows, monitor serta DPI berbeda |
| Remote HTTP/HTTPS | Endpoint, pairing, sertifikat CA/IP dan handshake TLS lokal; smoke kontrol Qt dijadwalkan di CI | Ponsel Android/iPhone, trust CA browser, akses mikrofon, firewall dan jaringan privat |
| Kontrol tangan workspace | Sampel landmark sintetis, smoothing, pinch, pelacakan dan pembatalan; gesture UI pada Qt offscreen Linux di CI | Webcam Windows, MediaPipe, latency, presisi, pencahayaan dan penggunaan dua tangan sebenarnya |
| MT5 ORB/read-only | Perhitungan dan perilaku data dengan fake/fixture | Terminal MT5 Windows, data broker dan zona waktu sesi sebenarnya |
| Order MT5 dan stop darurat | Validasi, persetujuan/hasil simulasi, race stop memakai fake; smoke kontrol Qt dijadwalkan di CI | Terminal dan akun **demo**, koneksi dan respons broker; LIVE belum diverifikasi |
| Editor kode/gambar dan penampil OBJ | Tes logika serta sebagian operasi Qt offscreen | Dialog file, font, gambar, penyimpanan dan penggunaan interaktif pada desktop pengguna |
| Provider suara, mikrofon & speaker | Tes logika dan mock; pilihan perangkat | Perangkat audio, driver, privasi dan koneksi provider yang dipakai |
| Plugin dan layanan eksternal | Discovery/manifest dan tes plugin menggunakan fixture/mock | Kredensial, perubahan API, izin, kuota, jaringan dan akun yang dipakai |
| Integrasi OS (auto-start, `jarvis://`, identitas aplikasi) | Format entri Windows/LaunchAgent/`.desktop`, quoting path berspasi, round-trip tulis-baca, parser `jarvis://` dan penolakannya, urutan pemasangan identitas; registry Windows diuji lewat shell palsu | Klik `jarvis://` sungguhan, grup dan ikon taskbar Windows, entri login setelah restart, dock/`StartupWMClass` Linux, dialog "buka dengan" macOS |
| Riwayat percakapan | Penulisan/format JSONL, batas ukuran dan retensi, baris terpotong, pembersihan per hari, tool `recall_history` dengan argumen aneh | Isi transkrip dari sesi suara nyata: apakah setiap giliran benar-benar tercatat, dan apakah pertanyaan "tadi kita bicarakan apa" dijawab dari transkrip, bukan dari memori |
| Interupsi suara (barge-in) | Palet keputusan murni: kapan memotong, kapan mengabaikan, gema sendiri, jeda, ruang bising, guard belum terkalibrasi; pemanggilan di callback mikrofon dan penekanannya per jawaban | Apakah memotong benar-benar terasa nyaman dengan mikrofon dan speaker sungguhan: berapa lama jeda sebelum berhenti, apakah tersela gema di ruang bergema, dan apakah suara latar memicu pemotongan |
| Obsidian | Penemuan vault dari `obsidian.json`, penelusuran yang melewati `.obsidian`/`.trash`, pencarian dan kutipan baris, append yang menjaga CRLF, penolakan menimpa, penolakan symlink keluar, uji sumber yang melarang penghapusan | Vault Obsidian **sungguhan** milik pengguna: apakah Obsidian membaca ulang perubahan tanpa konflik, apakah nama catatan dengan spasi/emoji bekerja, dan apakah vault yang disinkronkan (Obsidian Sync/iCloud) tidak bentrok |
| Widget mengambang | Kebijakan murni tanpa Qt: daftar boleh/tidak **beserta alasannya**, nama yang sudah dipensiunkan (`hud`, `camera_preview`, `metric_bar`) ditolak dengan alasan penggantinya, penolakan Wayland atas always-on-top, penguncian posisi ke layar, penyimpanan posisi per widget; baris drawer diuji dengan stub (label bukan tombol mati, tinggi tidak terpotong 26px, state dilukis ulang tiap kali drawer dibangun) | Desktop **sungguhan** di Windows, macOS, X11 dan Wayland: apakah caption benar-benar tetap di atas aplikasi lain, apakah ia kembali ke indeks layout yang sama, apakah sesi Wayland memberi tahu pengguna bahwa jendela bisa tertutup, apakah posisi bertahan setelah monitor dicabut atau resolusi berubah, dan apakah label catatan terbaca utuh di lebar drawer 220px |
| Satu tangan, satu tempat | Gestur workspace dan gestur OS memakai **sampel yang sama di frame yang sama**. Aturan `os_owns_the_hand()` diuji tanpa kamera: workspace berdiri saat desktop sedang digerakkan, tetap bekerja saat pointer dibekukan (JARVIS fokus/konfirmasi), dan `gestures.reset()` — bukan sekadar disembunyikan — agar seret yang setengah jadi tidak melompat saat pointer membeku. 6/6 mutan tertangkap | Kursor sungguhan: apakah menyeret kartu benar-benar berhenti saat OS aktif, apakah kursor bergerak >30 fps tanpa jitter yang membuat klik meleset, dan apakah cubitan yang lepas di luar kamera benar-benar melepas tombol mouse |
| Layer Dashboard | Konsep macOS Dashboard, bukan jendela mengambang: satu papan penuh yang dimasuki dengan sengaja. Aturannya diuji tanpa layar — konfirmasi order LIVE **tidak pernah** bisa muncul di papan, widget tak dikenal ditolak dengan kalimat (bukan diizinkan secara default), satu nama buruk tidak membatalkan seluruh papan, dan widget yang dipinjam **dikembalikan ke slot asalnya** pada setiap jalan keluar (Esc, tombol, kehilangan fokus, shutdown). 12/12 mutan tertangkap | Layar sungguhan: apakah papan menutupi seluruh jendela dan mengikuti resize, apakah caption benar-benar kembali ke tempatnya (bukan ke sudut) setelah keluar, apakah Esc tidak 'dimakan' saat papan tertutup, dan apakah papan tidak pernah terbuka lagi setelah aplikasi dimulai ulang |
| Apa yang dikatakan tentang mikrofon | Kalimat mikrofon dipisah ke `core/mic_status.py`: **setiap** pemulihan diumumkan (bukan hanya yang pertama — dulu flag-nya tidak pernah direset, jadi pemulihan kedua berlangsung senyap), pemulihan tidak mencetak dua baris, `state_for()` menolak mengecat LISTENING saat wake word membisukan mikrofon, dan kalimat gagal menyebut bahwa mengetik masih bisa. 10/10 mutan tertangkap | Perangkat sungguhan: cabut dan colok kembali headset USB **dua kali** (pemulihan kedua harus tetap diumumkan), matikan Bluetooth headset saat bicara, dan pada mesin tanpa mikrofon sama sekali: sesi harus tetap hidup dan mengetik tetap bekerja |
| Kata-kata briefing pagi | Teks briefing dipisah ke `core/briefing.py`: ringkasan sesi bertanggal **masa depan** tidak pernah dibaca sebagai "-3 hari lalu", klausa bahasa selalu menyerah pada bahasa pengguna, fetch kosong dianggap gagal (bukan berita), dan briefing serta panel `web_search` kini memakai **satu** definisi "tidak ada hasil" — dulu keduanya punya daftar sendiri. 11/11 mutan tertangkap | Pembukaan sungguhan: apakah sapaan benar-benar diucapkan <1 detik, apakah berita yang dibacakan sesuai panel di layar, apakah plugin morning_brief yang mati disebut apa adanya, dan apakah bahasa sapaan mengikuti bahasa balasan pengguna |
| Kapan bibir boleh bergerak | Jadwal audio dipisah ke `core/playback_timing.py`: batch pertama dijangkar **satu periode callback** setelah `now` (bukan `stream.latency`, yang melaporkan kapasitas antrean — inilah asal lag setengah detik di Windows), kursor yang sudah lewat `now` atau melampaui buffer dijangkar ulang, batch kosong tetap memajukan kursor, dan tiga puluh batch 40 ms tidak bergeser satu milidetik pun. 9/9 mutan tertangkap | Speaker sungguhan: apakah bibir dan caption benar-benar tepat pada suara di Windows (buffer 300–500 ms) **dan** di Linux dengan buffer kecil, apakah tidak ada lag setelah 10 menit bicara terus-menerus, dan apakah setelah interupsi bibir tidak mundur ke jadwal lama |
| Transkrip dan level audio | Dua hal yang hanya bisa dicapai lewat `import main` kini di `core/transcript.py` dan diuji tanpa sesi: penanda kontrol tidak pernah sampai ke log, baris baru tidak ikut dibuang, chunk pendek hanya dibandingkan dengan chunk sebelumnya ("ya, ya" adalah kalimat), blok yang bukan audio menghasilkan 0 dan **bukan** bar penuh, dan tidak ada `RuntimeWarning` per frame untuk blok kosong. 10/10 mutan tertangkap | Perangkat sungguhan: apakah bar waveform bergerak wajar untuk suara pelan, apakah barge-in masih memicu saat JARVIS berbicara, dan apakah log aktivitas bersih tanpa `<ctrl…>` selama percakapan panjang |
| Prompt yang dibangun untuk model | Isi prompt dipindah ke `core/prompt_build.py` dan diuji tanpa sesi: build tuli dinyatakan tidak bisa mendengar, build buta dinyatakan tidak punya penglihatan, refusals platform muncul sebelum keterbatasan build, tool yang tidak bisa dilayani engine benar-benar hilang dari daftar yang dijanjikan, dan `str.format` tidak pernah dipakai (satu kurung kurawal di prompt tidak boleh mematikan aplikasi). 10/10 mutan tertangkap | Mesin sungguhan: apakah model benar-benar berhenti menawarkan `screen_process` pada engine tanpa penglihatan, apakah ia menyebut keterbatasan platform dengan benar saat ditanya, dan apakah nama asisten baru dari config muncul di jawaban tanpa ada yang menyunting prompt |
| Cincin pointer desktop | Satu definisi untuk dua tempat: gaya/ukuran/offset hanya di `core/pointer_ring.py`, dan tes AST menolak salinan stylesheet di `ui/hand_gesture.py`. Cincin desktop diuji dengan kursor tiruan: digambar dari posisi kursor **yang sebenarnya** (bukan dari intent), `WindowTransparentForInput` menyala, tidak direstyle saat keadaan tidak berubah, dan `visible()` menolak saat mode mati, saat pointer dibekukan, dan saat platform tidak mengizinkan input | Desktop **sungguhan** dengan kamera: apakah cincin benar-benar berada tepat di bawah kursor Windows pada DPI 100% dan 150%, apakah ia tidak menghalangi klik pada tombol kecil, apakah ia hilang seketika saat JARVIS diberi fokus, dan apakah ia tidak tertinggal di layar setelah kontrol tangan dimatikan |
| Kebijakan reconnect | Murni dan tanpa impor aplikasi: timeout tidak boleh terbaca sebagai kuota, jawaban tangga model dipakai saat predikat modul tidak mengenali pesannya, `keep_context` untuk ganti suara, backoff berlipat dan berbatas, error tak dikenal tidak menurunkan model, dan `run()` benar-benar memanggil `decide()` (diperiksa lewat AST, bukan teks) | Sesi **sungguhan** dengan jaringan nyata: apakah kabel dicabut di tengah percakapan benar-benar kembali setelah backoff, apakah kuota habis benar-benar berpindah model dan menyebut namanya, dan apakah ini semua tidak menahan percakapan lebih lama dari yang tertulis di layar |
| Dokumen mengambang | Lapisan Qt diuji dengan stub yang mencatat: `removeSubWindow` saat keluar, `addSubWindow` saat kembali (subwindow yang hanya di-reparent adalah widget di 0,0), reset `WindowNoState` untuk subwindow yang semula maximised, Wayland tidak meminta always-on-top, `order_dialog` ditolak, kind tak dikenal diizinkan, manifest hanya boleh *menyebut* `window` dan tidak pernah mengambangkan, dan toggle plugin mengembalikan window-nya **sebelum** menyimpan status OFF | Desktop **sungguhan**: apakah dokumen yang mengambang benar-benar tetap di atas aplikasi lain, apakah ia kembali ke posisi dan ukuran MDI yang sama, apakah menutup window mengambang masih memunculkan dialog simpan, dan apakah mematikan plugin saat ada window mengambang benar-benar mengembalikannya tanpa kehilangan kerja |
| Rahasia tidak ikut ter-commit | `.gitignore` punya komentar inline yang **tidak ada** di sintaksnya: sepuluh aturan blok "Secrets" dibaca git sebagai satu nama file yang berisi `# …`, jadi tidak pernah cocok, dan `config/api_keys.json` serta `config/audit.jsonl` dilacak sejak awal. Blok itu ditulis ulang tanpa komentar inline, kedua file di-`git rm --cached`, dan `config/api_keys.example.json` (tanpa rahasia) ditambahkan. `tests/test_gitignore.py` menjalankan `git check-ignore` untuk **setiap** aturan, bukan hanya yang pernah salah, dan menolak baris yang memuat `#`. 3/3 mutan tertangkap | Riwayat git sudah diperiksa: tidak ada commit yang pernah memuat `gemini_api_key` bernilai, jadi tidak ada kunci yang perlu dirotasi. Yang tidak dapat dibuktikan di sini: apakah sebuah kunci **baru** yang ditulis layar setup benar-benar tidak muncul di `git status` pada mesin Windows/macOS dengan `.gitignore` yang sama — itu diuji dengan git, bukan dengan Qt, dan `test_gitignore.py` melakukannya dengan git yang sama |
| Tangan → OS | Kebijakan murni: hanya tiga aksi, pembekuan saat fokus ada di JARVIS/konfirmasi/modal, pelepasan tombol saat tangan hilang atau mode dimatikan, penolakan lompatan sampel, margin sudut layar; uji AST yang melarang pemanggilan `press`/`hotkey`/`write` dan melarang impor allowlist shortcut | Desktop **Windows sungguhan**: apakah pointer benar-benar mengikuti tangan pada DPI dan monitor berbeda, apakah klik nyasar tidak pernah mengenai tombol tutup jendela, apakah tombol mouse benar-benar lepas saat tangan keluar frame, dan apakah tracking tetap layak dipakai di ruangan dengan cahaya redup |
| Akses file penuh | Kebijakan murni: default = home saja, opt-in hanya dari `true` literal, penolakan kredensial (`~/.ssh`, `System32`, penyimpan sandi browser) meski folder induknya diizinkan, penolakan kunci milik aplikasi sendiri, resolusi symlink sebelum pemeriksaan, alasan penolakan, dan uji AST yang memastikan tidak ada tool/plugin yang bisa memanggil `save`/`disable` | Folder **sungguhan** di Windows (`C:\`), macOS (`~/Library`) dan Linux (`/`): apakah folder sistem benar-benar tertolak, apakah reparse point/junction Windows dan symlink OneDrive/Dropbox tidak menyelinap, dan apakah dialog pemilih folder mengembalikan path yang bisa disimpan |

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

Hand Board dan perintah kartunya telah dihapus: kontrol tangan bekerja langsung
pada jendela JARVIS. Catatan dan gambar menggunakan fitur catatan dan editor
gambar yang sudah ada; kartu sesi lama tidak dipersistenkan dan tidak dapat
dipindahkan. Penampil Model 3D dibuka lewat Aplikasi atau workspace_control,
dan menerima OBJ yang dipilih pengguna secara lokal. Ini hanya wireframe; yaw,
pitch, dan pemisahan komponen diatur dengan slider; claw satu tangan juga
mengatur pemisahan pada canvas model dengan beberapa komponen. Ini bukan
kontrol 3D dua tangan.
Memilih file menghentikan kontrol tangan sebelum dialog sistem terbuka.

`tests/test_workspace_transform.py` masih menguji geometri dengan sampel
sintetis, dan `tests/test_gesture_os.py` menguji aturan pointer/klik/scroll.

**Yang hilang dari bagian ini:** seluruh lapisan UI gestur
(`ui/hand_gesture.py`, `ui/gesture_os_bridge.py`, `ui/desktop_ring.py`) DIHAPUS
bersama jendela — lihat `docs/mockups/NOT-IN-MOCKUP.md`. Papan 6 pada mockup
menggambar tile kamera gestur, tetapi tile itu masih **usulan**, bukan desain
yang sudah dikirim. Jadi bagian ini TIDAK dapat diverifikasi pada build ini:
tidak ada permukaan yang menggerakkan pointer, dan `core/gesture_os.py`
sekarang tidak punya pemanggil.

### Pembaruan visual desktop

Mockup acuan: `design/jarvis-desktop-visual-revisi.png`. Implementasi memakai
wallpaper biru-grafit, palet bersama untuk panel workspace, emblem JARVIS
ornamental, file di kiri dan percakapan di kanan pada layar lebar. Editor kode
kosong dibuka di bawah Files pada layar lebar setelah registry siap, hanya jika
plugin editor valid dan aktif; pada layar sempit editor tidak dibuka otomatis.
Menu desktop menghubungkan aksi nyata dan Files memiliki riwayat navigasi.
Pada layar kecil emblem disembunyikan agar ruang tetap untuk aplikasi. Badge
kontrol tangan hanya muncul saat controller benar-benar mulai atau aktif; bukan
gambar status kamera statis. Wajah tengah menggunakan instance dan status HUD
yang sama; pada layar lebar panel HUD yang duplikat disembunyikan saat mode
wajah aktif, sedangkan hasil, kuis, dan audio dapat muncul saat diperlukan.
Mode orb/core dan layar sempit tetap menampilkan HUD panel. Saat kamera kontrol tangan mulai atau aktif,
panel di kanan atas menampilkan status controller dan tombol berhenti; penunjuk
berubah saat mencubit dan garis hanya muncul saat transformasi dua tangan sedang
berlangsung. Panel disembunyikan saat modal, konfirmasi atau aplikasi tidak fokus.
Tata letak dan widget asli tetap dapat dioperasikan; tidak menggunakan gambar
mockup sebagai UI.

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

CI juga menjalankan `tools/check_ambient_qt.py` pada Linux menggunakan Qt
offscreen dengan dependensi aplikasi. Skrip itu MEMBANGUN setiap permukaan yang
masih ada — orb pada tiga mode, command bar, antrean toast, face bubble, dialog
konfirmasi — dengan `QApplication` sungguhan, lalu memaksa satu siklus cat
lewat `render()`, bukan `update()`.

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tools/check_ambient_qt.py
```

Empat tool lama (`check_desktop_qt.py`, `capture_desktop_qt.py`,
`check_browser_qt.py`, `check_ssh_qt.py`, `check_security_qt.py`,
`check_rotation_*.py`) mengimpor `ui/window.py` dan modul permukaan yang sudah
dihapus, sehingga ikut dihapus; riwayatnya ada di commit `376909f1`.

**Board 6 (overlay suara + kamera gestur) menambah tiga hal yang diuji tanpa
layar.** `ui/voice_overlay.py` memisahkan tiga janji catatan kaki artboard
menjadi fungsi yang mengembalikan angka atau bool — glow nol saat nonaktif, Esc
menutup, Ctrl+Alt+G menjeda tanpa menghapus transkrip — dan
`tests/test_voice_overlay.py` memeriksa keduanya: nilai yang dikembalikan DAN
panggilan yang benar-benar sampai ke painter, lewat `tests/fakepainter.py` yang
mencatat setiap `drawText`/`fillRect`/`drawRect`. Di mesin ini `QtGui` tidak
dapat diimpor (`libxkbcommon.so.0` tidak ada), jadi yang diuji adalah kode di
`ui/voice_paint.py`, dengan tipe Qt pengganti yang memiliki tanda tangan sama.
Satu mutasi yang lolos: menggambar tepi di `x = 0` alih-alih `x = 1` membuat
separuh garis 2 px berada di luar jendela — terlihat, dan sekarang gagal.

**Yang hanya dapat dibuktikan di Windows.** Klik-tembus
(`WindowTransparentForInput`), fokus kembali setelah Esc, transparansi jendela
frameless dan DPAPI memerlukan desktop Windows nyata dengan compositor.
`QT_QPA_PLATFORM=offscreen` tidak punya window manager sama sekali, jadi
`check_ambient_qt.py` hanya membuktikan bahwa jendela dan flag-nya DIBUAT, bukan
bahwa window manager menerimanya. Klaim-klaim itu tetap belum terbukti.

**Tangan yang menggerakkan kursor tidak dapat dibuktikan di sini.** `core/gesture_bridge.py`
memerlukan pyautogui, kamera, dan desktop sungguhan; ketiganya tidak ada di
runner ini. Yang diuji adalah jahitannya: kebijakan menerima sampel yang benar,
`disable()` melepas tombol yang sedang ditahan, fokus dan banner membekukan
tangan, dan sampel yang hilang melepas tombol pada frame yang sama. Pengiriman
diuji dengan mouse perekam, bukan dengan kursor nyata. Di Windows jalurnya
dibatasi tiga nama yang sama dengan allowlist `OsPointer` — `moveTo`,
`mouseDown`, `mouseUp`, `scroll` — dan sebuah tes gagal bila nama kelima muncul.

Untuk board 6 ada satu klaim tambahan yang TIDAK dibuat, dan itu disengaja:
overlay ini tidak memakai `WindowTransparentForInput`. Klik-tembus akan membuat
jendela tidak bisa menerima Esc — padahal catatan kaki artboard menjanjikan Esc
menutup overlay. `test_the_window_flags_are_the_three_that_matter_and_not_click_through`
menjaga ketiadaan itu. Di Windows, apakah fokus kembali ke aplikasi di bawahnya
setelah Esc belum diuji dan tetap dicatat sebagai belum terbukti.

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

### Integrasi OS — Windows, macOS, Linux

Tiga area di bawah hanya terbukti formatnya di CI. Yang menentukan adalah
perilaku shell yang sebenarnya, dan itu tidak dapat disimulasikan.

- [ ] **Identitas taskbar (Windows).** Jalankan `python main.py`, lalu lihat
      taskbar: tombolnya harus bergrup sendiri dengan ikon arc reactor dan
      label `J.A.R.V.I.S`, **bukan** bergabung dengan `python.exe`. Uji juga
      saat ikon di-pin dan saat ada skrip Python lain berjalan bersamaan.
      Catat versi Windows dan apakah pin lama perlu dilepas dulu.
- [ ] **Auto-start.** Nyalakan dari tray, restart mesin, lalu pastikan JARVIS
      muncul **di tray** (bukan layar penuh) dan tidak meminta API key ulang.
      Lalu hapus `main.py` sementara dan buka SETUP: entri harus terbaca
      **BROKEN**, bukan "ON". Kembalikan file setelah uji.
- [ ] **`jarvis://`.** Dari browser ketik `jarvis://summon`, lalu
      `jarvis://ask?text=halo` saat JARVIS sudah berjalan: jendela harus muncul
      **dan** teksnya masuk sebagai giliran pengguna — bukan hanya jendela tanpa
      alasan. Uji juga satu link rusak (`jarvis://run`) dan pastikan alasannya
      muncul di log aktivitas dan aplikasi tetap mau start. Ulangi tombol
      ON/OFF di SETUP, lalu hapus entri handler dengan tangan dan pastikan
      tombol kembali menunjukkan OFF.
- [ ] **Linux.** Di X11, pastikan jendela memakai ikon dari `.desktop` dan
      tidak muncul sebagai dua entri terpisah di dock (`StartupWMClass`).
      Ulangi di Wayland dan catat apa yang memang tidak didukung.
- [ ] **macOS.** Setelah `jarvis://` didaftarkan, pastikan dialog "buka dengan"
      menyebut J.A.R.V.I.S, dan bundle di `~/Applications` memakai ikon aplikasi.

### Riwayat percakapan

- [ ] Lakukan satu percakapan suara nyata (minimal 3 giliran), lalu buka
      `logs/history/YYYY-MM-DD.jsonl` dengan editor teks: setiap giliran harus
      ada, satu baris per giliran, dan teksnya sama dengan yang tampil di HUD.
- [ ] Tanya "tadi kita bicarakan apa" pada sesi **baru** dan pastikan jawabannya
      berasal dari transkrip. Ini menguji `recall_history`, bukan memori.
- [ ] Hentikan JARVIS paksa (kill) saat sedang berbicara, lalu buka filenya:
      baris terakhir boleh rusak, tapi giliran sebelumnya harus tetap utuh.
- [ ] Periksa ukuran folder dan pastikan pemangkasan 30 hari berjalan sesuai
      yang tertulis, serta bahwa menghapus file hari itu tidak membuat aplikasi
      gagal start.

### Interupsi suara (barge-in)

- [ ] Dengan **speaker** (bukan headphone), minta jawaban panjang lalu potong di tengah
      dengan bicara biasa. Catat: berapa lama sampai suara berhenti, dan apakah
      potongannya terasa wajar.
- [ ] Ulangi di ruang bergema (kamar mandi, ruang kosong) dan catat apakah asisten
      memotong dirinya sendiri. Kalau ya, catat `echo floor` dari baris log — itu
      angka yang dipakai untuk menaikkan ambang.
- [ ] Uji dengan suara latar: musik, TV, percakapan orang lain. Tidak boleh memotong.
- [ ] Uji batuk, ketukan keyboard, dan pintu tertutup. Tidak boleh memotong.
- [ ] Pastikan interrupt tidak memotong **tool yang sedang berjalan** — pagar itu
      memang tidak dijanjikan, dan uji ini memastikan tidak ada klaim palsu.
- [ ] Dengan headphone (tanpa gema sama sekali), pastikan pemotongan tetap bekerja
      dan tidak justru lebih lambat.

### Obsidian

- [ ] Dengan vault asli, minta "cari catatan tentang <topik>". Pastikan hasil yang
      disebut benar-benar ada dan baris yang dikutip sesuai isi file.
- [ ] Tambahkan satu baris ke catatan harian, lalu buka Obsidian: perubahan harus
      muncul tanpa konflik dan tanpa mengubah format file.
- [ ] Ulangi pada vault yang disinkronkan (Obsidian Sync / iCloud / OneDrive) dan
      catat apakah ada konflik atau file duplikat.
- [ ] Coba nama catatan dengan spasi, huruf besar-kecil berbeda, dan emoji.
- [ ] Pastikan folder `.trash` dan catatan yang sudah dihapus **tidak** muncul.
- [ ] Uji dengan lebih dari satu vault: asisten harus bertanya, bukan memilih.

### Akses file penuh

- [ ] Biarkan **MATI**, lalu minta asisten membaca file di luar home. Harus ditolak,
      dan penolakannya menyebut "outside your home" — bukan sekadar "Access denied".
- [ ] Nyalakan lewat baris **FULL FILE ACCESS** di drawer CONTROLS, pilih satu folder
      (misalnya `D:\Kerja`). Tombol harus berubah menjadi AKTIF dengan jumlah folder.
- [ ] Minta asisten membaca file di folder itu: harus berhasil. Lalu file di folder
      lain yang **tidak** dipilih: harus tetap ditolak.
- [ ] Dengan folder induk home diizinkan, minta ia membaca `~/.ssh/id_rsa` dan
      `C:\Windows\System32\drivers\etc\hosts`. Keduanya harus ditolak meski
      induknya diizinkan.
- [ ] Minta ia membaca `config/api_keys.json`. Harus ditolak — periksa bahwa isi
      kunci tidak muncul di jawaban maupun di log.
- [ ] Buat symlink di dalam folder yang diizinkan menuju file di luar folder itu
      (di Windows: `mklink /J`), lalu minta membacanya. Harus ditolak.
- [ ] Ulangi dengan folder yang disinkronkan (OneDrive/Dropbox/iCloud), yang sering
      memakai reparse point. Catat apakah path dilaporkan berbeda dari yang dipilih.
- [ ] Matikan lagi lewat tombol yang sama, lalu ulangi langkah pertama. Harus kembali
      ditolak tanpa perlu restart, dan daftar folder harus hilang dari config.
- [ ] Rusak `config/api_keys.json` (tambahkan `{` di awal), jalankan ulang, lalu coba
      file di luar home. Harus tetap ditolak dan aplikasi tetap bisa dipakai.
- [ ] Coba minta asisten "memberi dirinya akses ke C:\". Ia tidak punya tool untuk
      itu; jawabannya harus menjelaskan bahwa Anda yang harus menekan tombolnya.

### Widget mengambang

- [ ] Buka drawer CONTROLS, tekan **FLOAT WIDGETS**. Caption harus keluar dari
      window dan muncul sebagai panel kecil tanpa bingkai.
- [ ] Pindah ke aplikasi lain (browser, editor). Caption harus tetap terlihat — di
      Windows/macOS/X11. Di Wayland, catat apakah ia tertutup, dan pastikan log
      menyebut alasannya.
- [ ] Ucapkan satu kalimat panjang. Caption mengambang harus tetap mengikuti teks.
- [ ] Tutup lalu buka lagi tombolnya. Caption harus kembali ke **posisi semula di
      dalam window**, bukan ke dasar panel.
- [ ] Geser caption ke sudut, matikan, nyalakan lagi. Ia harus muncul di tempat
      terakhir, bukan di pojok default.
- [ ] Cabut monitor kedua (atau ubah resolusi), lalu nyalakan caption yang terakhir
      berada di monitor itu. Ia harus muncul di layar yang masih ada.
- [ ] Tutup aplikasi saat caption masih mengambang, buka lagi, lalu nyalakan. Posisi
      terakhir harus diingat.
- [ ] Baca catatan kecil di bawah baris **FLOAT WIDGETS**. Catatan itu harus
      mengatakan bahwa baru teks ucapan yang bisa mengambang, dan tidak boleh
      terpotong di baris kedua atau tampak seperti tombol yang mati.
- [ ] Minta asisten mengambangkan kolom metrik atau avatar. **Belum didukung** —
      catat bila ia mengklaim bisa, dan pastikan tidak ada tombol yang
      menghasilkan apa-apa saat ditekan.
- [ ] Minta asisten mengambangkan window plugin (terminal trading, editor gambar).
      **Belum didukung** — catat bila ia mengklaim bisa. Langkah ini memastikan
      tidak ada klaim palsu.

### Satu tangan, satu tempat (gestur bare-hand → OS)

- [ ] Nyalakan kontrol tangan, lalu tekan **HAND → OS** di CONTROLS. Gerakkan
      tangan: **hanya kursor desktop** yang bergerak. Kartu di workspace tidak
      boleh ikut terseret — inilah bug yang diperbaiki.
- [ ] Masih dengan OS aktif, klik kembali ke jendela JARVIS. Kursor desktop
      harus membeku, dan gestur workspace harus **kembali bekerja**.
- [ ] Cubit dan tahan di area desktop, lalu tarik tangan keluar kamera.
      Tombol mouse harus lepas pada frame yang sama — desktop tidak boleh
      berubah menjadi seleksi seret yang tak bisa dihentikan.
- [ ] Cubit di workspace (JARVIS fokus) sambil OS aktif. Klik workspace harus
      tetap terjadi; desktop tidak boleh bergerak.
- [ ] Matikan kontrol tangan saat OS aktif, lalu nyalakan lagi. Log harus
      menyebut OS aktif sekali, dan gerakan tangan harus langsung sampai ke
      desktop.
- [ ] Pada sesi Wayland, tekan **HAND → OS**. Baris harus menyebut bahwa
      jendela tidak bisa selalu di atas — bukan berpura-pura.

### Dashboard layer

- [ ] Buka CONTROLS, tekan **DASBOR**. Papan harus menutupi seluruh jendela.
- [ ] Caption dan panel metrik harus ikut pindah ke papan, dan **tidak** ada
      salinan yang tertinggal di workspace.
- [ ] Ubah ukuran jendela saat papan terbuka. Papan harus mengikuti.
- [ ] Tekan **Esc**. Papan harus hilang, dan caption kembali ke posisi
      semula — bukan ke sudut kiri atas.
- [ ] Buka lagi, lalu tekan tombol **DASBOR** untuk keluar. Hasil yang sama.
- [ ] Buka lagi, lalu klik aplikasi lain. Papan harus ikut tertutup dan
      widget kembali.
- [ ] Saat papan tertutup, tekan Esc. Tidak boleh ada apa pun yang terjadi,
      dan Esc harus tetap menutup drawer/setup seperti biasa.
- [ ] Buka papan, lalu tutup aplikasi. Mulai ulang: papan **tidak** boleh
      terbuka sendiri.
- [ ] Pada plugin yang tidak punya widget (mis. `camera_preview`), papan harus
      tetap terbuka dengan tile yang ada dan menulis alasannya di log.

### Mikrofon: hilang, kembali, hilang lagi

- [ ] Cabut headset USB saat JARVIS mendengarkan. Log harus menyebut mikrofon
      berhenti dan akan dicoba lagi; aplikasi **tidak** boleh mati.
- [ ] Colok kembali. Harus muncul "Microphone found — listening again", dan HUD
      kembali ke LISTENING.
- [ ] Cabut dan colok **sekali lagi**. Pengumuman yang sama harus muncul lagi —
      inilah bug yang diperbaiki: dulu pemulihan kedua senyap.
- [ ] Nyalakan wake word, lalu cabut/colok mikrofon. HUD harus kembali ke
      SLEEPING, bukan LISTENING.
- [ ] Pada mesin tanpa mikrofon: mulai aplikasi, ketik sebuah perintah. Harus
      tetap dijawab, dan kalimat gagal hanya muncul **sekali**, bukan tiap dua
      detik.
- [ ] Matikan headset Bluetooth di tengah percakapan. Sesi harus bertahan dan
      mikrofon default harus diambil alih.

### Briefing pagi

- [ ] Mulai aplikasi tanpa menyapa apa pun. Sapaan harus mulai berbunyi dalam
      waktu kurang dari satu detik.
- [ ] Dengar sapaan, lalu cocokkan jam yang disebut dengan jam mesin.
- [ ] Setelah fase 2, bandingkan berita yang **dibacakan** dengan panel
      "NEWS" di layar. Tidak boleh ada judul yang tidak ada di panel.
- [ ] Matikan jaringan, mulai ulang. Briefing harus mengatakan berita tidak bisa
      diambil — bukan membacakan pesan error atau mengarang judul.
- [ ] Nonaktifkan plugin `morning_brief`, mulai ulang. Panel harus tetap muncul
      dengan berita saja, tanpa bagian kosong.
- [ ] Bicara dalam bahasa lain pada balasan pertama. Fase 2 harus mengikuti
      bahasa Anda, bukan bahasa yang diingat.
- [ ] Tanyakan sesuatu yang butuh `web_search` dan hasilnya kosong. Panel isi
      tidak boleh menampilkan pesan "No results" sebagai hasil.

### Prompt dan kemampuan yang dinyatakan

- [ ] Ganti `assistant_name` di config, mulai ulang, tanyakan "siapa kamu".
      Nama baru harus muncul, dan tidak pernah nama lama.
- [ ] Tanyakan "jam berapa sekarang". Jawabannya harus cocok dengan jam mesin.
- [ ] Tanyakan "apa saja yang bisa kamu lakukan". Daftar yang disebut harus
      sama dengan tool yang benar-benar terpasang (tidak ada tool hantu).
- [ ] Hapus/pindahkan satu plugin, mulai ulang, ulangi pertanyaan di atas.
      Tool itu harus hilang dari jawaban, bukan masih dijanjikan.
- [ ] Pada mesin tanpa mikrofon, tanyakan "apakah kamu bisa mendengar saya".
      Jawabannya harus menyatakan tidak bisa — bukan "saya tidak menyahut".
- [ ] Pada sesi Wayland, minta ia mengklik sesuatu. Ia harus menyebut
      keterbatasan platform, bukan mengaku sudah mengklik.

### Cincin pointer di desktop

- [ ] Di Windows, nyalakan kontrol tangan lalu tekan **HAND → OS**. Cincin cyan
      harus muncul **tepat di bawah kursor**, bukan di posisi lain.
- [ ] Gerakkan tangan. Cincin harus mengikuti kursor tanpa tertinggal — kalau ia
      bergerak sendiri ke tempat yang tidak pernah dikunjungi kursor, itu bug.
- [ ] Cubit dan tahan. Cincin harus membesar/menyala **selama ditahan**, bukan
      berkedip dua kali.
- [ ] Gerakkan tangan ke sudut layar. Cincin harus berhenti di posisi kursor yang
      dijepit margin, dan tetap sejajar dengan kursor.
- [ ] Klik tombol kecil di aplikasi lain (mis. tombol tutup tab browser). Cincin
      **tidak** boleh menghalangi klik itu.
- [ ] Beri fokus ke JARVIS. Cincin desktop harus **langsung hilang**.
- [ ] Munculkan konfirmasi, lalu gerakkan tangan. Cincin tidak boleh muncul.
- [ ] Matikan **HAND → OS**. Cincin harus hilang dan tidak tertinggal di layar.
- [ ] Tutup aplikasi saat cincin sedang tampil. Tidak boleh ada cincin yatim yang
      tertinggal di desktop.
- [ ] Ubah DPI layar ke 150%. Cincin harus tetap sejajar dengan kursor.

### Kebijakan reconnect

- [ ] Jalankan percakapan, lalu **cabut kabel jaringan** (atau matikan Wi-Fi) di
      tengah jawaban. Log harus menyebut "retrying in 3s", lalu 6, 12, 24, 48, dan
      berhenti di 60 — bukan langsung 60, dan bukan tanpa batas.
- [ ] Sambungkan kembali jaringan. Sesi harus pulih **pada model yang sama**.
      Kalau log menyebut "switching to …" padahal yang terjadi hanya kabel dicabut,
      itu bug yang sudah pernah ada — catat.
- [ ] Habiskan kuota satu model (atau pakai key dengan kuota rendah). Log harus
      menyebut nama model tujuan, dan percakapan harus lanjut di model berikutnya.
- [ ] Ganti suara dari pengaturan. Reconnect harus **seketika**, tanpa jeda dan
      tanpa baris peringatan.
- [ ] Masukkan API key yang salah, lalu jalankan. Harus muncul permintaan key baru,
      bukan percobaan berulang ke API.
- [ ] Biarkan satu percakapan berjalan lama sampai ada error yang tidak dikenal.
      Model **tidak** boleh turun; hanya boleh ada jeda 3 detik lalu mencoba lagi.

### Dokumen mengambang

- [ ] Buka editor kode atau panel trading, lalu tekan **FLOAT DOCUMENTS** di drawer
      CONTROLS. Window itu harus keluar dari area workspace dan muncul di desktop
      dengan ukuran dan posisi yang wajar — bukan layar penuh.
- [ ] Pindah ke aplikasi lain. Window itu harus tetap terlihat (Windows/macOS/X11).
      Di Wayland, catat bila ia tertutup, dan pastikan log menyebut alasannya.
- [ ] Tekan lagi. Window harus kembali ke area workspace, di posisi dan ukuran
      semula — **bukan** ke pojok kiri atas.
- [ ] Maximise dulu di dalam workspace, lalu keluarkan, lalu kembalikan. Ia harus
      kembali dalam keadaan maximised seperti semula.
- [ ] Edit sesuatu tanpa menyimpan, lalu tutup window yang mengambang lewat tombol
      tutupnya. Dialog "simpan?" harus tetap muncul.
- [ ] Edit sesuatu tanpa menyimpan, lalu matikan plugin pemilik window itu lewat
      panel plugin. Plugin **harus tetap AKTIF** dan log harus menjelaskan bahwa ada
      kerja yang belum disimpan.
- [ ] Simpan pekerjaannya, lalu matikan plugin itu. Window harus kembali ke workspace
      dan hilang, dan plugin benar-benar menjadi OFF.
- [ ] Buka konfirmasi order MT5. Pastikan tidak ada cara membuatnya mengambang, dan
      catat bila asisten mengklaim bisa — itu janji "konfirmasi sensitif memerlukan
      input fisik" yang dilanggar.
- [ ] Ubah manifest sebuah plugin agar berisi `"window": "float"`, muat ulang, lalu
      buka window-nya. Window **tidak** boleh mengambang sendiri; log boleh menyebut
      permintaan itu, dan hanya drawer yang boleh mewujudkannya.

### Tangan → OS

- [ ] Di Windows, nyalakan kontrol tangan dari panel workspace, lalu tekan
      **HAND → OS** di drawer CONTROLS. Gerakkan tangan: pointer Windows harus
      mengikuti.
- [ ] Periksa bahwa pointer **tidak** bisa mencapai empat sudut layar. Tombol tutup
      jendela harus tetap di luar jangkauan.
- [ ] Cubit dan tahan 0,35 detik: harus klik. Cubit singkat: **tidak** boleh klik.
- [ ] Cubit dan tahan, lalu tarik jendela ke tempat lain, lalu lepaskan. Lepas harus
      terjadi tepat saat jari membuka — bukan setelahnya.
- [ ] Cubit dan tahan, lalu **jauhkan tangan dari frame kamera**. Tombol mouse harus
      langsung lepas; desktop tidak boleh tertinggal dalam mode seret.
- [ ] Cubit dan tahan, lalu tekan **HAND → OS** untuk mematikannya. Tombol harus lepas
      juga.
- [ ] Klik ke window JARVIS (beri fokus), lalu gerakkan tangan. Pointer harus
      **berhenti** dan log harus menyebut alasannya.
- [ ] Minta konfirmasi apa pun hingga banner muncul, lalu gerakkan tangan. Pointer
      harus berhenti di frame itu juga — banner tidak boleh bisa ditekan dengan tangan.
- [ ] Pegang dua jari di depan kamera: harus menggulir, dan tidak boleh menggulir
      puluhan kali per detik.
- [ ] Gerakkan tangan sangat cepat melintasi frame (atau biarkan orang lain lewat).
      Pointer tidak boleh melompat; sampel harus dibuang.
- [ ] Minta asisten menjalankan shortcut (`Ctrl+W`, kunci layar) lewat gestur. Ia tidak
      punya kemampuan itu — catat bila ia mengklaim bisa.
- [ ] Tutup JARVIS saat tombol mouse sedang ditahan gestur. Desktop tidak boleh
      tertinggal dalam mode seret.

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
`tests/test_ssh_manager.py` cover vault/origin handling, isolated autofill logic,
tab lifecycle, and fake SSH transports. `tests/test_ssh_protocol.py` exercises
Paramiko over a local socketpair with a generated host key, including rejection
of an unknown key; no external server is involved. Kedua tool Qt itu **dihapus** bersama `ui/browser_read.py` dan
`ui/ssh_manager.py`; lihat `docs/mockups/NOT-IN-MOCKUP.md`. These checks do not establish visual fidelity, real
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

### Wajah animasi desktop

Pada desktop lebar, mode `face` menampilkan wajah holografis di tengah dengan
instance animasi HUD yang sama: kedipan, arah pandang, ekspresi status, serta
mulut berdasarkan audio/viseme pemutaran. Nama dan status mengikuti keadaan
aplikasi; panel asisten tidak perlu terbuka agar wajah terus diperbarui. Mode
baru default `face` hanya jika preferensi belum ada; pilihan `orb` atau `core`
yang tersimpan tetap dipertahankan. Layar sempit menyembunyikan dekorasi tengah
agar tidak menutupi jendela. Unit test memeriksa pemilihan mode, visibilitas,
pembaruan saat panel tersembunyi, rendering dengan stub Qt, serta animasi
wajah; smoke test Qt nyata juga mencakup pengambilan gambar desktop.

Visual ini adalah implementasi mesh holografis yang sudah ada, bukan model wajah
fotorealistis seperti gambar konsep. Permukaan desktop menginterpolasi warna
pencahayaan antar-vertex agar perbedaan segitiga lebih halus, sedangkan HUD asli
mempertahankan render sebelumnya; bentuk dan animasi masih menggunakan mesh yang
sama. Uji CI offscreen mencatat waktu render sintetis, bukan performa perangkat
pengguna. Hasil visual, komposit transparan, kinerja,
dan sinkronisasi suara masih perlu diperiksa pada Qt dan perangkat Windows
nyata; lingkungan pengujian lokal tidak memiliki dependensi Qt sistem.

### Gestur mendekatkan kedua tangan

Detektor clap menggunakan pendekatan cepat dua ujung telunjuk yang tetap
terlihat dan tidak mencubit; ini bukan deteksi suara tepuk atau pengenalan
telapak tangan secara penuh. Kehilangan tracking, modal, popup, fokus hilang,
dan cubitan membatalkan pengenalan. Jendela yang terlihat diminimalkan tanpa
menutup dokumen; menu Aplikasi menyediakan pemulihan batch, mempertahankan
status maximized sebelumnya dan tidak membuka jendela tersembunyi. Kamera atau
media dapat tetap aktif saat diminimalkan. Unit test memeriksa detektor dan
pemulihan; smoke Qt disiapkan, tetapi akurasi gesture, oklusi tangan, dan
pemulihan pada Windows/webcam nyata belum diverifikasi.

### Panel Asisten dan claw

Panel memiliki penanda asisten dan kartu tombol saran yang mengisi draft kosong
tanpa mengirim otomatis atau menimpa teks yang belum dikirim. Pesan pengguna dan
asisten memakai latar membulat dan alignment berbeda tanpa menafsirkan isi
sebagai HTML; teks tetap dipilih dan digulir dengan widget Qt asli. Pesan dengan
beberapa paragraf menggunakan satu latar. Keseluruhan tata letaknya belum
direplikasi persis dari mockup. Gesture claw memakai
heuristik jari melengkung, dwell 0,4 detik, dan hanya mengubah slider exploded
view pada canvas penampil model aktif yang memiliki beberapa komponen. Lepas,
hilangnya tracking, popup, atau dialog membatalkan aksi tanpa klik. Unit test
memeriksa klasifikasi pose; smoke Qt dengan sampel sintetis telah ditambahkan
tetapi belum dijalankan di lingkungan ini karena libGL.so.1 tidak tersedia.
Heuristik tersebut belum diuji pada webcam dan tidak menjamin bebas salah deteksi.

### Editor kode dan bantuan JARVIS

Editor memakai gutter nomor baris, pewarnaan sintaks ringan per baris untuk
berkas Python/JavaScript, dan status bahasa serta posisi kursor. Pewarnaan bukan
parser penuh (misalnya string multibaris); file tanpa ekstensi yang dikenal
masih teks polos. Setiap jendela editor kini mendukung beberapa tab file dan
tombol untuk file baru, buka, simpan, simpan sebagai, serta jalankan. Panel
project tree dapat dibuka lewat tombol proyek; folder dipilih pengguna secara
lokal dan tidak dibuka secara otomatis. Klik dua kali berkas membuka tab dengan
pembaca UTF-8 berbatas ukuran yang sama, tanpa otomatis mengirim isi ke JARVIS
atau menjalankannya. Tree tidak menampilkan symlink dan menolak target yang
sudah berubah menjadi di luar folder saat dibuka; ini bukan sandbox filesystem.
File yang sudah terbuka difokuskan kembali tanpa menggandakan tab atau menimpa
draft. Tampilan masih belum sama persis dengan konsep.

Plugin `code_editor` dapat membuka editor atau, setelah `workspace_control`
mencantumkan ID `doc-N`, meminta membaca dokumen editor aktif. Pengguna harus
menyetujui setiap pembacaan dan memeriksa rahasia karena isinya dapat dikirim
ke provider model. Hasil ditandai sebagai data tak tepercaya. Penggantian kode
memerlukan hash revisi yang terikat pada tab aktif, pratinjau diff dan persetujuan lokal;
perubahan dokumen saat menunggu membatalkan permintaan. Hasilnya dapat di-undo,
tidak otomatis disimpan maupun dijalankan. Batas bantuan 100 KB UTF-8; untuk
berkas lebih besar ditolak, bukan dikirim sebagian. Plugin harus diaktifkan
terlebih dahulu. Eksekusi tetap tidak di-sandbox dan memerlukan persetujuan
terpisah.

Unit test mencakup validasi, penolakan/persetujuan, perubahan selama dialog,
revisi kedaluwarsa, penanda data tak tepercaya dan warna sintaks. Smoke real Qt
untuk gutter/highlighter telah ditambahkan tetapi belum dijalankan di lingkungan
ini karena pustaka Qt sistem tidak tersedia. Belum diverifikasi dengan provider
model atau perangkat Windows nyata; pembungkus data tak tepercaya bukan jaminan
bahwa model akan mengabaikan semua instruksi dalam kode.

Unit test tab editor menggunakan stub Qt: pembukaan beberapa draft, pemisahan
path, penolakan nama file duplikat, konfirmasi perubahan yang belum disimpan,
dan perlindungan revisi antar-tab. Smoke test Qt nyata untuk pergantian dan
penutupan tab sudah ditambahkan; masih perlu dijalankan di Windows/Qt nyata.

### Penghapusan AI Image

Plugin `image_canvas`, generator Gemini-nya, tab AI Canvas, tujuan workspace
`ai_image`, dan item dock terkait telah dihapus. Permintaan lama untuk membuka
canvas ditolak, bukan dialihkan diam-diam ke editor kode. Editor gambar biasa
`image_editor` dan dokumen gambar pengguna tidak dihapus. Tes memeriksa
penemuan plugin, penolakan rute lama, menu dock, serta editor kode yang tetap
tersedia; pemeriksaan UI Qt nyata masih memerlukan perangkat dengan Qt sistem.

### Bantuan JARVIS pada SSH Manager

Mockup `design/jarvis-ssh-console-asistensi.png` menjadi acuan tata letak:
output monospasi lebih luas, input di bawah, kontrol salin/hapus dan izin
berbagi. Pengguna tetap membuka koneksi secara lokal dengan validasi known_hosts.
Setelah memilih tab SSH aktif, JARVIS dapat memeriksa status dan mengusulkan
satu perintah; setiap perintah menampilkan tujuan dan teks persisnya dalam
konfirmasi lokal default Tidak. Permintaan ditolak bila tab/sesi/draft berubah,
ada dialog lain, sesi sibuk, plugin dinonaktifkan, atau timeout. Respons saat
perintah dimulai bukan klaim bahwa eksekusi berhasil atau selesai.

Berbagi output default mati, harus disetujui pada masing-masing sesi dan dapat
dicabut. Hanya output yang diterima setelah izin diberikan disimpan untuk
asistensi (8.000 karakter terakhir); hapus output, cabut izin, atau disconnect
juga mengosongkan buffer. Output dapat memuat rahasia dan dapat dikirim ke
provider model; data yang sudah terkirim tidak dapat ditarik kembali. Output
remote dibungkus sebagai data tak tepercaya, bukan jaminan kebal prompt
injection. Sandi, passphrase dan lokasi kunci tidak dikembalikan ke model.
Bukan terminal interaktif; timeout/disconnect tidak menjamin proses server
berhenti.

Tes menggunakan request dan transport palsu memeriksa batas, persetujuan,
penolakan, sesi yang berganti, draft pengguna, pembatalan timeout, isolasi,
dan pencabutan. Smoke Qt nyata ditambahkan tetapi belum dijalankan di lingkungan
ini; tidak ada uji terhadap server SSH nyata, provider model, atau Windows.

### Penataan awal editor gambar

Aksi buka, undo dan simpan berada di atas; operasi gambar dan penambahan teks
berada pada panel vertikal yang dapat digulir di sebelah kanvas. Panel layer
masih berada di kanan. Smoke test Qt memeriksa tombol rotasi dan undo pada
gambar sintetis serta penerjemahan kontrol. Ini baru penataan awal, bukan
replika penuh mockup: toolbar memakai ikon vektor untuk operasi yang tersedia. Kuas dasar bekerja
pada gambar latar dengan ukuran dan warna yang dapat dipilih; layer teks tetap
terpisah dan satu sapuan dapat di-undo. Seleksi area dapat ditarik pada gambar
dan dipertahankan saat zoom; Crop membuka dialog dengan koordinat seleksi
untuk ditinjau sebelum diterapkan. Seleksi saja tidak mengubah gambar. Belum ada pengujian manual perangkat.
Slider zoom mengubah pratinjau dari 25–200% ukuran pas kanvas, dengan scroll
bila diperbesar; gambar dan layer asli tidak diubah. Ukuran render dibatasi
untuk mencegah alokasi berlebihan. Tes Qt memeriksa zoom, scroll, rotasi, undo
dan terjemahan dengan gambar sintetis, bukan pengujian manual perangkat.

Toolbar ikon diuji melalui Qt asli: ikon terisi, nama aksesibel dan tooltip
diterjemahkan, dan rotasi dapat dijalankan dengan keyboard. Tidak ada tombol
dekoratif untuk alat yang belum tersedia.

Smoke test Qt menggunakan gambar sintetis untuk drag seleksi, perubahan zoom,
pembatalan dan konfirmasi Crop, serta undo; dialog flatten tetap berlaku untuk
komposisi ber-layer. Pengujian ini tidak menggantikan uji manual perangkat.

Kuas diuji pada Qt offscreen dengan gambar sintetis: pemilihan warna dan
pembatalannya, ukuran, sapuan piksel, pemisahan layer teks, pergantian mode,
dan undo. Belum mencakup kuas lanjutan atau pengujian manual perangkat.

Tangkapan Qt sintetis editor gambar dibuat terpisah di CI agar dapat ditinjau
tanpa dokumen pengguna. Hasilnya menunjukkan rail ikon, kanvas, dan layer;
panel layer masih lebih sederhana daripada mockup. Kontrol warna dan ukuran
kuas dipindahkan ke baris kontekstual yang hanya muncul saat kuas aktif;
zoom dan aksi file tetap di toolbar utama. Ini bukan bukti kesetiaan visual penuh ataupun uji pada perangkat.

Tes Qt juga memeriksa visibilitas kontrol kuas dan bahwa warna serta ukuran
tetap tersimpan ketika beralih ke mode seleksi.

### Fondasi rotasi jendela (belum terintegrasi)

*(Tool di bagian ini sudah dihapus bersama jendela; teksnya disimpan sebagai riwayat.)*
Eksperimen terisolasi `tools/check_rotation_qt.py` menguji widget Qt biasa
di `QGraphicsProxyWidget` pada beberapa sudut: pemetaan koordinat, klik,
checkbox, fokus, pengetikan dan scroll via keyboard. Perhitungan selisih sudut
dua tangan diuji terpisah pada sampel sintetis. Keduanya **belum mengubah**
workspace `QMdiArea` atau menghubungkan rotasi ke gesture. Belum ada bukti
bahwa WebEngine, video/OpenGL, dialog/popup, siklus hidup jendela, aksesibilitas,
input gesture, dan perangkat Windows akan bekerja melalui proxy. Jangan
menganggap eksperimen ini implementasi rotasi interaktif bagi semua jendela.

Eksperimen tambahan `tools/check_rotation_editors_qt.py` menguji editor kode
JARVIS dan editor gambar yang sebenarnya dalam scene Qt terisolasi: pengetikan,
tab baru, penolakan penutupan draft (jawaban konfirmasi disimulasikan), drag
seleksi, rotasi gambar dan undo. Ini tidak menguji dialog persetujuan atau menu
popup yang nyata; tidak ada file pengguna, kode yang dijalankan, atau input OS.
Rotasi jendela workspace dan kontrol dua tangan tetap belum terintegrasi.

Sesuai keputusan pengguna, dialog **tidak ikut diputar**. Eksperimen
`tools/check_rotation_popups_qt.py` menempatkan dialog Ya/Tidak sintetis di
luar scene terputar sebagai dialog modal tegak dan memeriksa penolakan dengan
input langsung. Menu Qt diuji secara terpisah. Smoke test workspace menguji
bahwa dialog application-modal membatalkan gesture dan tidak memindahkan
jendela. Ini bukan uji dialog persetujuan JARVIS di workspace terputar; model
parenting dan siklus hidup untuk semua dialog nyata masih harus diintegrasikan
dan diuji. Konfirmasi sensitif tetap memerlukan tindakan pengguna lokal dan
tidak boleh disetujui dengan gesture. Rotasi workspace belum tersedia.

Sesuai keputusan pengguna, browser juga dikecualikan dari rotasi dan tetap
tegak, seperti dialog. Eksperimen WebEngine sintetis sebelumnya disimpan
sebagai referensi, tetapi tidak lagi dijalankan sebagai target rotasi di CI.
Kebijakan `rotation_allowed` menolak browser, dialog, dan jenis tidak dikenal;
kebijakan ini baru fondasi yang diuji, **belum dihubungkan** ke workspace yang
berputar. Integrasi kelak harus menerapkannya dengan identifikasi target tepercaya,
tanpa mengubah aturan keamanan, izin atau penyimpanan kredensial browser.

Layer teks pada editor gambar ditampilkan dari depan ke belakang; tombol
naik/turun mengubah urutan komposisi dan dapat di-undo tanpa menyimpan atau
meratakan layer. Background tetap selalu terlihat. Tes logika dan Qt offscreen
memeriksa urutan, kondisi batas, visibilitas, penghapusan dan undo; ini belum
mengubah format penyimpanan: Save as tetap mengekspor gambar yang diratakan.

Layer teks yang dipilih dapat diedit ulang: teks, posisi dan ukuran huruf.
Visibilitas dan urutan layer dipertahankan, perubahan dapat di-undo, dan
dialog yang dibatalkan atau data yang berubah selama dialog tidak menimpa
layer. Pengujian Qt offscreen menggunakan teks sintetis dan tidak membuktikan
penggunaan pada perangkat desktop sebenarnya.

Layer teks mendukung warna RGB per layer (default putih), termasuk saat
diedit ulang dan di-undo. Dialog warna dibatalkan tanpa mengubah pilihan;
komposisi dan ekspor menggunakan warna yang dipilih. Pemeriksaan Qt offscreen
mencakup warna pada piksel komposit sintetis, bukan uji perangkat fisik.

### Proyek editor gambar ber-layer

Buka proyek dan Simpan proyek menggunakan format lokal `.jimg` versi 1, yang
menyimpan background PNG dan layer teks (termasuk urutan, visibilitas, posisi,
ukuran dan warna). Ini bukan format PSD dan tidak menyimpan riwayat undo,
seleksi, atau layer kuas terpisah; sapuan kuas berada pada background. Ekspor
PNG/JPEG/BMP tetap diratakan dan tidak menandai perubahan layer yang belum
disimpan sebagai proyek sebagai tersimpan. Penyimpanan proyek memakai file
atomik; kegagalan tidak boleh merusak file tujuan yang sudah ada. Pembukaan
memeriksa versi, ukuran, dimensi dan isi sebelum mengganti dokumen aktif.

Tes model memeriksa round-trip dan data salah; smoke Qt CI memakai proyek dan
piksel sintetis untuk simpan, buka, pembatalan, file rusak, kegagalan simpan,
dan ekspor. Ini bukan pengujian perangkat atau format eksternal nyata.

### Perbandingan visual: desktop dan editor gambar

Capture sintetis desktop pada CI memperlihatkan susunan Files/editor kiri,
wajah tengah, asisten kanan dan dock seperti konsep, tetapi proporsi panel,
konten contoh, detail chrome dan wajah masih berbeda; ini bukan replika mockup.
Editor gambar sebelumnya memperlihatkan daftar layer polos dan label background
terpisah. Panel layer kini diberi permukaan bersama, ikon teks berwarna,
baris lebih mudah dibaca, dan thumbnail background aktual di bawah layer teks
(sesuai urutan komposisi, bukan dekorasi). Checkbox dan tindakan layer tetap
berfungsi; background tetap selalu terlihat. Ini masih penyelarasan bertahap,
bukan kesesuaian visual penuh dengan desain. Gambar CI sintetis tidak
membuktikan hasil pada monitor/DPI atau perangkat pengguna.

Panel percakapan disesuaikan lagi dengan konsep asisten: penanda visual
pengguna dan JARVIS digambar di luar bubble, tanpa menambahkan teks atau aksi
palsu. Pada panel sempit penanda disembunyikan agar ruang teks tetap tersedia;
seleksi, penyalinan, streaming dan scroll tetap memakai dokumen Qt asli.
Penanda ini bersifat ilustratif, bukan indikator koneksi atau status layanan.
Belum menyamai seluruh detail, proporsi, font atau ikon pada mockup.

Panel asisten: ukuran teks percakapan dan input ditingkatkan, dan saran tetap
terbuka seperti konsep tetapi dapat dilipat lewat keyboard untuk memberi lebih
banyak ruang percakapan. Melipat tidak mengirim perintah atau menghapus draft.
Capture desktop CI kini menggunakan percakapan sintetis beberapa paragraf
untuk meninjau proporsi; ini bukan percakapan pengguna dan bukan uji DPI nyata.

Pada Files, shortcut Proyek ditambahkan seperti konsep dan mengarah hanya ke
folder `Projects` di home lokal, bila tersedia. Tidak membuat atau membuka
folder secara otomatis: jika tidak ada, shortcut dinonaktifkan dan diperiksa
kembali saat jendela ditampilkan atau navigasi terjadi. Pilihan favorit mengikuti
riwayat Back/Forward; folder yang hilang menampilkan error dan tidak mengganti
lokasi aktif. Perbedaan visual lain pada Files masih ada.

### Penyelarasan awal browser

Referensi `design/proposed-graphite-browser.png` dibandingkan dengan capture Qt
browser kosong: sebelumnya tab menampilkan penanda kesalahan terjemahan dan
navigasi memakai tombol teks, sedangkan konsep memakai ikon. Tab kini memformat
nomornya dengan benar dan navigasi Back/Forward/Reload memakai ikon vektor,
label aksesibel dan tooltip yang diterjemahkan. Format konfirmasi Fill/Delete
juga diperbaiki agar origin dan username tampil tanpa penanda kesalahan. Aturan
vault, persetujuan, URL dan izin WebEngine tidak diubah. Capture CI menggunakan
alamat sintetik yang hanya diketik, tanpa memuat situs atau membaca kredensial;
ini bukan verifikasi situs nyata atau klaim kesesuaian penuh dengan mockup.

Bar tab browser kini memakai permukaan gelap dan garis tab aktif, dengan tombol
penutup vektor yang dapat dioperasikan lewat keyboard dan memiliki nama
aksesibel yang diterjemahkan. Tombol terikat pada identitas tab, bukan posisi,
sehingga penutupan tetap tepat setelah tab dipindah; sesi private per tab tetap
terpisah. Belum semua detail browser menyamai konsep, dan capture sintetis
bukan uji layanan atau browser nyata pada perangkat pengguna.

### Penyesuaian caption wajah desktop

Caption wajah sekarang memiliki nama, keterangan asisten dan status HUD yang
lebih jelas, seperti susunan konsep. Status tetap berasal dari HUD yang sama,
termasuk keadaan mute; teks keterangan tidak menyatakan bahwa mikrofon atau
layanan aktif. Tata letak dibatasi agar caption tidak bertumpuk dengan wajah
atau keluar dari stage. Ini bukan perubahan model 3D maupun wajah fotorealistis.
Tes geometri dan Qt offscreen memeriksa batas, bahasa dan status sintetis;
kecocokan visual, aksesibilitas dan performa perangkat tetap perlu pemeriksaan.

### Persetujuan tindakan umum

Gerbang `core.confirm` menolak permintaan baru secara atomik saat ada
persetujuan yang belum kedaluwarsa. Banner dan jawaban membawa ID permintaan
acak; jawaban, tampilan, atau penutupan yang terlambat tidak dapat menyetujui
atau menutup banner baru. Judul/detail yang melampaui batas tampilan ditolak,
bukan dipotong diam-diam. `tests/test_confirm.py` menguji konkurensi, identitas,
kedaluwarsa dan kegagalan callback; `tools/check_ambient_qt.py` menguji antrean
sinyal dan tombol dengan Qt offscreen. Ini bukan audit semua jalur persetujuan,
sandbox plugin, atau validasi interaksi pada perangkat nyata; gerbang MT5 dan
SSH memiliki mekanisme dan pengujiannya sendiri.

### Keandalan memori

Pembaruan, penghapusan dan ringkasan sesi diserialisasi dalam satu proses dan
ditulis melalui file sementara di direktori yang sama lalu `os.replace`. Jika
file memori rusak/tidak terbaca, operasi perubahan menolak menimpanya. Tes
mencakup penulisan bersamaan dan kegagalan penggantian; smoke Qt memeriksa pesan
kegagalan hapus. Ini bukan lock antarproses, enkripsi memori, jaminan pemulihan
setelah setiap kegagalan perangkat keras, atau pengujian pada perangkat nyata.

### Konten visual interaktif (tahap awal)

Plugin `visualize_data` menerima 2–48 pasangan label dan angka yang sudah
tersedia dari pengguna/hasil tool, bersama judul dan keterangan sumber. Nilai
harus terbatas dan hingga; tidak ada kode, URL, file, atau aksi yang dijalankan.
Waktu data tidak diada-adakan. Sumber adalah keterangan yang diberikan, **bukan**
sumber yang telah diverifikasi. UI menampilkan grafik garis dan tabel; pemilihan
titik lewat mouse, tombol panah atau tabel disinkronkan. Tombol bertanya hanya
menyiapkan draf berisi titik yang dipilih, tanpa menimpa draf yang ada atau
mengirim otomatis. Data dibungkus sebagai tak tepercaya; ini bukan jaminan
terhadap prompt injection. Pengguna meninjau dan mengirim draf sendiri.

Tes `tests/test_visual_content.py` mencakup validasi dan perhitungan posisi;
`tools/check_ambient_qt.py` menguji jalur worker, pemilihan, tabel, lokalisasi,
dan draf dengan Qt offscreen. CI mengambil gambar contoh sintetis untuk review.
Diagram lain, penyimpanan/bagikan, pengambilan data otomatis, dan kesesuaian
visual/DPI serta interaksi pada perangkat nyata belum diverifikasi atau belum
tersedia. Model lokal dengan anggaran tool kecil dapat tidak menawarkan plugin.

### Konten penjelasan, bukan hanya grafik

Plugin `present_content` menerima konten terbatas dalam tiga bentuk: kartu
konsep, langkah berurutan, atau linimasa. Ini adalah informasi interaktif,
bukan rencana yang otomatis dijalankan. Item dapat dipilih dengan mouse atau
keyboard untuk membaca detail dan menyiapkan pertanyaan pada kolom asisten;
draf lama tidak ditimpa dan tidak ada pengiriman otomatis. Judul, sumber dan
rincian ditampilkan sebagai teks biasa, tanpa menjalankan kode atau tautan.
Sumber hanyalah keterangan yang diberikan dan tidak otomatis diverifikasi;
tanggal kosong tetap tidak diketahui. Konten model dapat keliru dan penanda
untrusted bukan jaminan keamanan terhadap prompt injection.

`tests/test_narrative_content.py` memeriksa validasi dan pembatalan; CI menguji
jalur plugin hingga widget Qt offscreen dan menangkap contoh sintetis. Ini
belum menghasilkan semua jenis media, belum sinkron dengan setiap jawaban suara,
dan belum membuktikan kualitas pemilihan bentuk oleh provider nyata atau
penggunaan pada layar nyata. Tool dapat dihilangkan oleh provider beranggaran
kecil. Browser tetap tidak dikerjakan dalam tahap ini.

Tampilan pilihan kini memakai kartu berpratinjau untuk konsep, nomor untuk
langkah dan penanda linimasa untuk peristiwa. Pratinjau panjang dapat terpotong;
teks lengkap tetap tersedia di panel detail. Waktu peristiwa yang tidak diberikan
ditampilkan sebagai tidak diketahui, bukan diperkirakan. CI juga menguji pilihan
dengan mouse dan keyboard serta perubahan bahasa di Qt offscreen.

### Pemilihan visual dan batas tool model

Panduan visual ditambahkan ke instruksi model hanya bila tool yang bersangkutan
benar-benar ditawarkan setelah penyaringan dan anggaran. Model diminta memilih
bentuk yang sesuai, menghormati penolakan, dan tidak mengklaim tampilan berhasil
sebelum hasil tool mengonfirmasinya. Ini adalah panduan, bukan pemaksa atau
jaminan model akan memanggil tool maupun menyelaraskan tampilan dengan ucapan.

Untuk pipeline OpenAI-compatible, pengaturan lanjutan **Prioritize visual
content tools** bersifat opt-in dan perlu sambung ulang. Saat ada batas tool,
`present_content` lalu `visualize_data` diprioritaskan hanya jika aktif dan ada
pada daftar; tool lain, termasuk tool inti, dapat tergeser. Tool yang tidak
ditawarkan tetap dicatat dalam activity log. Pilihan ini tidak menaikkan
anggaran dan tidak mengaktifkan plugin yang dinonaktifkan. Tanpa batas, urutan
semula tetap berlaku. Ini bukan pemilihan tool berdasarkan permintaan per giliran:
prioritas berlaku sepanjang sesi. Seperti perilaku budget yang sudah ada, tool
pertama yang sendirian melebihi batas karakter tetap dapat lolos; batas jumlah
tool tetap berlaku. Model kecil mungkin tetap gagal memakai tool.

### Draf pertanyaan dari pilihan visual

Draf kini membawa salinan bagian yang dipilih, posisi/jumlah bagian, ringkasan
(jika ada), sumber dan waktu yang diberikan, serta konteks tetangga terbatas:
judul/waktu untuk konten penjelasan atau label/nilai untuk grafik. Tidak ada
rincian bagian lain atau seluruh dataset yang diam-diam ditambahkan. Semua
konteks itu terlihat di kolom masukan untuk diperiksa/diedit sebelum dikirim,
dibungkus sebagai data tak tepercaya dan tidak otomatis dikirim. Penanda ini
bukan sandbox, dan pengguna tetap dapat mengubahnya saat mengedit draf.

Draf yang sudah ada, termasuk hanya spasi, tidak diganti. Jika konteks lengkap
melampaui batas `QLineEdit` dalam unit UTF-16, tidak ada draf parsial yang
dimasukkan; pesan menjelaskan kegagalan. Uji unit meliputi batas pilihan,
tetangga, karakter emoji dan penanda berbahaya; uji Qt offscreen CI memeriksa
pengisian, batas input dan perlindungan draf untuk grafik serta ketiga bentuk
konten. Konteks ini adalah snapshot pada saat tombol ditekan, bukan sinkronisasi
pilihan secara langsung atau verifikasi kebenaran informasi.

Pada grafik maupun konten penjelasan, kolom pertanyaan opsional memungkinkan
pengguna menulis pertanyaan sendiri tanpa mengubah penanda konteks. Jika kosong,
pertanyaan penjelasan standar dipakai. Tombol tetap hanya membuat draf untuk
pemeriksaan di asisten, tidak mengirimnya. Saat pemilihan berubah, draf yang
sudah dibuat tidak berubah; pengguna harus mengosongkan atau mengirim draf itu
sebelum membuat snapshot baru. Pertanyaan yang ditulis tetap di kolom konten
jika pembuatan draf gagal atau bahasa UI diganti. Pertanyaan pengguna sengaja
berada di luar penanda untrusted; data tampilan tetap berada di dalamnya.

### Grafik batang untuk perbandingan

`visualize_data` kini menerima `chart_type` opsional: `bar` untuk perbandingan
kategori atau `line` untuk tren berurutan. Input lama tanpa tipe tetap memakai
garis. Pengguna dapat beralih antara garis, batang, dan tabel tanpa kehilangan
pilihan; draf pertanyaan menyertakan tipe grafik yang terakhir dipilih. Batang
menggunakan nol sebagai dasar untuk nilai positif maupun negatif, dan nol tidak
digambar sebagai batang bernilai non-nol. Tabel tetap menampilkan label dan
angka lengkap ketika label grafik disingkat atau terlalu banyak untuk digambar.

Uji geometri mencakup nilai campuran, nol, konstan dan nilai ekstrem dalam batas;
CI Qt offscreen menguji pergantian jenis, mouse pada batang termasuk nol,
keyboard, tabel dan draf. Pemilihan jenis oleh model tetap tidak dijamin benar;
pengguna dapat menggantinya. Angka dan sumber yang dikirim tool tidak diverifikasi.

### Batas antrean audio keluaran

Antrean potongan PCM menuju pemutar desktop dibatasi 200 potongan, masing-masing
maksimal 2.400 byte (sekitar 10 detik total pada 24 kHz, mono, 16-bit). Saat
penuh, penerimaan menunggu ruang: potongan tetap berurutan dan tidak diam-diam
dibuang. Tombol interrupt kini menjadwalkan pengosongan antrean dan pembatalan
pipeline pada event loop pemiliknya, bukan menyentuh `asyncio.Queue` dari thread
Qt; callback dari koneksi lama tidak mengganggu antrean koneksi pengganti. Jika
producer baru saja terbangun setelah interrupt, potongan lama dibuang sebelum
pemutar mendapat kesempatan membacanya.

Uji offline mencakup antrean penuh, FIFO, cancellation, interrupt lintas thread,
callback basi, serta jalur penerimaan sintetis yang membawa transkrip dan tool
call. Batas ini hanya pada antrean PCM pemutar, bukan ukuran frame individual,
event non-audio pipeline, frame individual provider, jaringan, buffer perangkat,
atau executor tool. Antrean PCM internal pipeline kini juga dibatasi seperti
dijelaskan di bawah.
Backpressure dapat menunda penerimaan transkrip, tool call dan akhir giliran
ketika pemutaran lambat; ini pilihan konservatif agar audio tidak hilang, bukan
nonblocking tool execution. Pemutaran yang sudah diserahkan ke perangkat belum
pasti berhenti seketika. Interupsi otomatis/barge-in, timeout dan pembatalan tool
belum diselesaikan. Penanganan batas interrupt pipeline lokal dijelaskan pada
bagian berikut. Tidak ada uji mikrofon, speaker, provider atau jaringan nyata
pada tahap ini.


### Batas interrupt pipeline lokal

Pipeline lokal mengirim penanda internal bernomor setelah semua event yang sudah
masuk antrean ketika interrupt ditekan. Penerima membuang audio lama sampai
penanda terbaru, bahkan bila ada akhir giliran lama sebelumnya; penanda lama
tidak dapat menyelesaikan interrupt yang lebih baru. Generasi yang dibatalkan
tidak lagi menghalangi giliran baru, dan giliran yang sudah menunggu dilanjutkan
setelah penanda. Penanda lokal tidak dihitung sebagai respons provider untuk
watchdog. Ini memperbaiki kasus status interrupt yang sebelumnya tidak pulih
ketika pembatalan tidak menghasilkan akhir giliran.

Uji sintetis menjalankan pipeline nyata, antrean pemutaran penuh, dua interrupt,
akhir giliran/transkrip/audio lama, dan giliran baru dengan audio baru. Ini
tidak membatalkan tool yang sudah berjalan atau membuktikan respons pada
provider/perangkat nyata. Respons Gemini Live tetap menggunakan batas giliran
yang dikirim server; jika batas itu tidak datang, kasus tersebut belum tertangani.


### Batas PCM pipeline lokal

Antrean event pipeline tetap membawa pesan kontrol tanpa membuangnya, tetapi
audio yang menunggu di antrean dibatasi 100 potongan maksimum 2.400 byte
(sekitar lima detik PCM). Blok TTS besar dipecah dan produser menunggu ruang.
Penerima melepaskan kapasitas saat mengambil setiap potongan; urutan audio,
transkrip, tool call dan penanda interrupt tetap mengikuti urutan event.
Penghentian dan interrupt diuji saat antrean penuh, termasuk blok TTS lebih
besar dari kapasitas dan pemberitahuan tool setelah ucapan pengantar.

Batas ini tidak mencakup blok yang sudah dialokasikan oleh provider, event
non-audio, buffer jaringan/perangkat, atau audio yang telah diambil penerima.
Backpressure juga dapat memperlambat pengiriman tool call; ini bukan solusi
untuk tool yang macet. Cancellation memerlukan provider kooperatif: kode atau
thread eksternal yang mengabaikan cancellation tidak dijamin berhenti. Uji
menggunakan provider sintetis, bukan TTS/provider atau perangkat nyata.

### Provider yang mengabaikan pembatalan

Pipeline memeriksa identitas generasi sebelum memproses event model, setelah
TTS, dan setelah menunggu kapasitas audio. Jika generasi sudah diganti atau
sesi ditutup, output terlambat tidak boleh menjadi transkrip, audio, tool call,
riwayat, atau akhir giliran baru. Uji menggunakan model dan TTS sintetis yang
sengaja menelan `CancelledError`, lalu mengembalikan output dan tool call lama.

Ini pagar untuk **output pipeline yang datang setelah generasi diganti**, bukan
jaminan menghentikan provider/thread eksternal. Tool call yang sudah dikeluarkan
sebelum interrupt dan tool yang sudah berjalan tidak otomatis dibatalkan;
tindakan eksternal tetap memerlukan mekanisme consent dan pembatalannya sendiri.

### Sinkronisasi awal ucapan dan visual

Pipeline lokal kini menempelkan teks yang benar-benar diserahkan ke TTS pada
potongan PCM pertama setiap segmen ucapan. Penanda ikut antrean audio dan
asisten menampilkan teks tersebut ketika pemutar memperkirakan segmen mulai
terdengar, bukan ketika model selesai menulis transkrip. Segmen berikutnya
tidak digabung ke batch sebelumnya; tampilan dibersihkan setelah antrean selesai.
Interrupt dan koneksi ulang mengganti epoch agar timer lama tidak memunculkan
teks basi. Teks polos hanya ditampilkan di JARVIS, tanpa markup, dan potongan
lebih dari 1.200 karakter ditandai terpotong.

Uji sintetis mencakup beberapa kalimat, TTS yang menghasilkan beberapa blok,
backpressure, urutan potongan dan perkiraan waktu playback; Qt offscreen menguji
penundaan, interrupt, timer basi, teks polos dan pergantian bahasa. Ini adalah
sinkronisasi **perkiraan per segmen** untuk pipeline lokal dengan TTS yang
menghasilkan PCM, bukan word-level alignment, tidak membuktikan suara benar-benar
terdengar pada perangkat, dan dapat berbeda akibat latensi perangkat/remote.
Gemini Live belum menyediakan pemetaan transkrip-ke-PCM yang dapat diandalkan di
jalur ini sehingga tidak diberi klaim sinkronisasi palsu. Konten kartu, langkah,
linimasa dan grafik juga belum otomatis berpindah mengikuti kalimat; tidak ada
pencocokan topik spekulatif yang dapat memilih konten salah. Pembaruan konten
terstruktur terikat giliran dan pengujian provider/perangkat nyata masih perlu.
