# JARVIS — Sistem Desain Ambient

Dua berkas, satu sumber:

| Berkas | Isi |
|---|---|
| `jarvis-design-system.html` | **22 artboard**, SVG inline, tanpa jaringan. Buka langsung. |
| `build.py` | Generator lembar itu. Ubah angka di sini, jalankan `python docs/mockups/build.py`, HTML ditulis ulang. |

Artboard **tidak** memuat penjelasan desain. Semua asumsi, rasio kontras, dan alasan
ada di bagian Ringkasan **di dalam** HTML, setelah artboard 22.

## Tambahan: shell ambient (Fase 1)

Artboard **1–6** dan **23–28** menggambar perilaku jendela sesuai spesifikasi Tauri:

| # | Artboard | Yang ditunjukkan |
|---|---|---|
| 1 | Orb overlay | Overlay ±150 px transparan, hanya orb 56 px yang menerima klik |
| 2 | Toast | Tiga toast menumpuk, sisanya antre, batas 3 saran/hari |
| 3 | Command bar | Ctrl+Space, input fokus, Esc kembali ke jendela sebelumnya |
| 4 | Orb | Klik kiri/kanan/seret, empat status dibaca dari isi orb |
| 5 | Panel baki | Mengikuti taskbar, segmented Aktif/Fokus/Senyap |
| 6 | Overlay suara + kamera | Glow tepi hanya saat aktif, preview gestur kecil |
| 23 | Fokus | Toast **ditahan**, bukan dibuang — jumlahnya bisa dilihat |
| 24 | Senyap | Orb menyusut 28→18 px, glow hilang, cincin jadi titik |
| 25 | Konfirmasi risiko | Dirender UI tepercaya, tombol besar, ada asal permintaan |
| 26 | Riwayat tugas | Urungkan/ulang, audit log bertimestamp, ekspor |
| 27 | Izin & Privasi | Indikator mikon/kamera/layar, izin eksplisit, mode tamu |
| 28 | Tema terang | Panel baki versi terang dengan token terang |

## Ringkasan isi

| Kelompok | Artboard |
|---|---|
| Desktop 1280×720 | 1 desktop ambient · 2 command bar · 3 kontrol gestur · 4 mode suara |
| Panel 460×640 | 5 baki · 6 izin · 7 onboarding (2/4) · 8 riwayat · 9 memori · 10 detail memori · 11 rutinitas · 12 alat cepat · 13 dikte/baca/form · 14 keamanan · 15 aksesibilitas · 16 plugin & ponsel · 17–18 tema terang |
| Lainnya | 19 peta gestur 720×640 · 20 status orb 1280×300 · 21 brand & ikon 1280×640 · 22 installer 720×480 |

## Prinsip yang dipegang di setiap artboard

1. **Ambient dulu.** Orb kecil + ikon baki. Jendela besar hanya saat dipanggil
   (artboard 1, 5, 22).
2. **Tidak merebut fokus.** Toast punya dua tombol dan hilang sendiri 8 detik (artboard 1).
3. **Dipanggil kapan saja.** Ctrl+Space (2), kata kunci, dan gestur (3, 19).
4. **Transparan soal privasi.** Empat izin eksplisit, log aktivitas, tombol hapus riwayat
   (6, 7, 18).
5. **Aman.** Tiga tingkat risiko; berisiko selalu minta konfirmasi fisik (14).

## Kontras yang sudah dihitung (bukan diklaim)

Semua pasangan teks lolos 4.5:1. Yang paling tipis:

| Pasangan | Rasio |
|---|---|
| Tema terang: redup `#5B7480` pada latar `#F6F9FB` | **4.67** |
| Tema terang: aksen `#0A7A93` pada putih | **4.98** |
| Tema terang: putih pada aksen `#0A7A93` | **4.98** |
| Gelap: amber `#F5A524` pada panel `#0A1722` | 8.88 |
| Gelap: teks `#E6F4F8` pada dasar `#04080D` | 17.84 |

Tabel lengkap 10 baris ada di ringkasan HTML.

## Asumsi yang perlu disetujui

Spesifikasi tidak memberi angka untuk ini; saya pilih dan catat di ringkasan HTML (A1–A6):

- **Font:** Space Grotesk tidak dimuat dari jaringan. Lembar jatuh ke font sistem. Di Qt,
  font harus dibundel (OFL).
- **Skala tipe:** 10 / 11.5 / 13 / 19 / 26 px.
- **Target sentuh:** tepat 44 px tidak muat berdampingan di panel 460 px; tombol 40 px
  visual dengan area tekan 44 px.
- **Warna risiko ketiga:** `#FF6B6B`, karena permintaan hanya menyediakan cyan dan amber.

## Tiga benturan yang saya putuskan

1. **"Tanpa emoji"** — semua ikon digambar sebagai jalur SVG; tidak ada karakter emoji
   di berkas (sudah diperiksa dengan regex).
2. **"Amber hanya untuk peringatan"** — artboard 20 butuh empat status; amber dipakai
   tepat untuk satu status ("Butuh perhatian").
3. **"Bedakan lewat terang-gelap, bukan hue"** — cyan dan amber luminansinya berdekatan,
   jadi setiap peringatan membawa bentuk tambahan: tanda seru, garis kiri, atau label.

## Belum digambar, dan kenapa

- Onboarding langkah 1, 3, 4 dan installer langkah 2–4: spesifikasi hanya meminta satu
  langkah masing-masing; polanya bisa dipakai ulang.
- Isi plugin pihak ketiga: belum ada di kode, jadi artboard 16 hanya memuat baris generik.

## Batasan shell

- Mockup ini **stack-neutral**: digambar dari perilaku (frameless, transparan, always-on-top),
  bukan dari API-nya, sehingga tetap valid untuk Tauri maupun PyQt6.
- Spesifikasi Tauri 2 + React + TypeScript adalah **aplikasi baru**; repo ini 354 berkas
  Python + PyQt6. Menulis ulang shell bukan bagian dari lembar ini.
- Panel baki memakai 460×660 (bukan 640) karena tiga baris izin + input butuh 20 px ekstra.

## Batasan

- Lembar ini **konsep**, belum kode. Tidak ada berkas `core/` atau `ui/` yang disentuh.
- Perender SVG di sandbox ini punya keterbatasan (gradien radial dan teks diskalakan
  berbeda), jadi gambar pratinjau bisa sedikit berbeda dari peramban. Geometri, warna,
  dan teks sudah diperiksa secara terprogram: 22 artboard valid, tanpa elemen meluber,
  tanpa bentuk berukuran nol.
