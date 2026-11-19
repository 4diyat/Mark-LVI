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
| Editor kode/gambar dan penampil OBJ | Tes logika serta sebagian operasi Qt offscreen | Dialog file, font, gambar, penyimpanan dan penggunaan interaktif pada desktop pengguna |
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

Hand Board dan perintah kartunya telah dihapus: kontrol tangan bekerja langsung
pada jendela JARVIS. Catatan dan gambar menggunakan fitur catatan dan editor
gambar yang sudah ada; kartu sesi lama tidak dipersistenkan dan tidak dapat
dipindahkan. Penampil Model 3D dibuka lewat Aplikasi atau workspace_control,
dan menerima OBJ yang dipilih pengguna secara lokal. Ini hanya wireframe; yaw,
pitch, dan pemisahan komponen diatur dengan slider; claw satu tangan juga
mengatur pemisahan pada canvas model dengan beberapa komponen. Ini bukan
kontrol 3D dua tangan.
Memilih file menghentikan kontrol tangan sebelum dialog sistem terbuka.

`tests/test_workspace_transform.py` menguji geometri dengan sampel sintetis;
`tools/check_desktop_qt.py` memiliki smoke dua tangan di Qt offscreen untuk CI.
Keduanya bukan pengujian dengan webcam. Rotasi bebas jendela yang tetap
interaktif belum tersedia.

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
