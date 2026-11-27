"""Reproducible target-flow artboard for revision 1 (not a UI screenshot)."""
from PIL import Image, ImageDraw, ImageFont

W, H = 2700, 1550
im = Image.new('RGB', (W, H), '#0b111d')
d = ImageDraw.Draw(im)
font = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
bold = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def f(size, heavy=False):
    return ImageFont.truetype(bold if heavy else font, size)

def text(x, y, s, size=22, color='#e9f0fa', heavy=False):
    d.text((x, y), s, font=f(size, heavy), fill=color)

def arrow(x1, y, x2):
    d.line((x1, y, x2-8, y), fill='#71849c', width=3)
    d.polygon([(x2, y), (x2-10, y-6), (x2-10, y+6)], fill='#71849c')

colors = {'Pemicu': ('#213c61', '#70b8ff'), 'Proses': ('#153c40', '#5cdbc7'),
          'Keputusan': ('#51401f', '#f3c76e'), 'Error': ('#4a2530', '#ff8793'),
          'Hasil': ('#253a32', '#8cdb9d')}

def node(x, y, w, kind, lines):
    bg, accent = colors[kind]
    d.rounded_rectangle((x, y, x+w, y+128), radius=13, fill=bg, outline='#53667b', width=1)
    d.rounded_rectangle((x, y, x+5, y+128), radius=2, fill=accent)
    text(x+16, y+11, kind.upper(), 14, accent, True)
    for i, line in enumerate(lines):
        text(x+16, y+39+i*25, line, 19, heavy=(i == 0))

text(62, 45, 'REVISI 01  /  ALUR ANTARMUKA', 18, '#71b9fd', True)
text(62, 83, 'Empat jalur, satu artboard', 42, heavy=True)
text(62, 144, 'DIAGRAM TARGET — bukan tangkapan layar aplikasi; sebagian alur belum diterapkan.', 21, '#f3c76e')
text(62, 202, 'LEGENDA', 15, '#91a4bb', True)
x = 180
for label, (bg, accent) in colors.items():
    d.rounded_rectangle((x, 196, x+20, 216), radius=5, fill=bg, outline=accent)
    text(x+30, 196, label, 17)
    x += 185
text(1250, 196, '→ urutan utama     ↺ kembali / interupsi     |     kotak merah = kondisi gagal', 17, '#a6b8cc')

rows = [
 ('01', 'AMBIENT ORB + CHAT', 'Target: Mode Tamu belum tersedia; penyimpanan tidak dinonaktifkan.', [
  ('Pemicu', ['Tray / hotword', 'Masuk ke Idle']),
  ('Proses', ['Listening', 'Teks atau suara']),
  ('Proses', ['Intent & tool', 'Tentukan aksi']),
  ('Keputusan', ['Klasifikasi risiko', 'Sedang / tinggi:', 'konfirmasi']),
  ('Proses', ['Eksekusi', 'Speaking']),
  ('Hasil', ['Balasan / file', 'Tampil di chat']),
  ('Hasil', ['Riwayat & memori', 'Kecuali Tamu']),
  ('Error', ['Ditolak / gagal', 'Jangan eksekusi'])]),
 ('02', 'COMMAND BAR', 'Target: saran dan verifikasi warna belum terhubung ke eksekusi terklasifikasi.', [
  ('Pemicu', ['Hotkey', 'Buka bar']),
  ('Proses', ['Tulis / pilih', 'Saran perintah']),
  ('Keputusan', ['Verifikasi', 'Hijau: otomatis', 'Kuning: konfirmasi']),
  ('Proses', ['Jalankan', 'Setelah validasi']),
  ('Hasil', ['Hasil di chat', 'Status akurat']),
  ('Pemicu', ['Esc kapan saja', 'Tutup bar']),
  ('Hasil', ['Draf aman', '*Cek duplikasi', 'sebelum mencoba']),
  ('Error', ['Merah: gagal', 'Tampilkan alasan', 'Coba lagi*'])]),
 ('03', 'VOICE MODE', 'Target: izin mikrofon OS dan idle 8 detik belum ditegakkan.', [
  ('Pemicu', ['Mic / hotword', 'Mulai suara']),
  ('Keputusan', ['Izin mikrofon?', 'Belum → onboarding', 'langkah 2']),
  ('Proses', ['Listening', 'Terima suara']),
  ('Proses', ['STT', 'Transkripsi']),
  ('Proses', ['Thinking', 'Proses intent']),
  ('Proses', ['Speaking', 'Dengan caption']),
  ('Keputusan', ['Interupsi / diam', '↺ Listening', '8 detik → Idle']),
  ('Error', ['Izin ditolak', 'Beri petunjuk', 'jangan mendengar'])]),
 ('04', 'SECURITY & PERMISSIONS', 'Target: toggle global belum tersedia; counter hanya permintaan pada 50 entri audit terakhir.', [
  ('Pemicu', ['Permintaan tool', 'Akses dibutuhkan']),
  ('Proses', ['Klasifikasi', 'Risiko per aksi']),
  ('Keputusan', ['Cek toggle', 'Tanpa izin: blokir', 'Tinggi: konfirmasi']),
  ('Proses', ['Log aktivitas', 'Counter risiko']),
  ('Proses', ['Kontrol izin', 'Ubah toggle']),
  ('Keputusan', ['Ekspor / hapus', 'Konfirmasi', 'dua langkah']),
  ('Hasil', ['Hasil / log', 'Tampilkan status']),
  ('Error', ['Blokir / batal', 'Catat keputusan'])])]

for idx, (num, title, note, nodes) in enumerate(rows):
    y = 260 + idx*300
    d.rounded_rectangle((42, y, W-42, y+272), radius=18, fill='#111b2a', outline='#26384d', width=2)
    text(65, y+21, num, 19, '#68baff', True)
    text(113, y+17, title, 22, '#f2f6fc', True)
    text(65, y+54, note, 17, '#aabbd0')
    start, width, gap = 65, 295, 30
    for j, (kind, lines) in enumerate(nodes):
        nx = start + j*(width+gap)
        node(nx, y+100, width, kind, lines)
        if j < len(nodes)-2:
            arrow(nx+width+5, y+164, nx+width+gap-5)
    # A red failure is a branch, not a step which leads to execution.
    decision = next(j for j, n in enumerate(nodes) if n[0] == 'Keputusan')
    bx = start + decision*(width+gap) + width//2
    ex = start + 7*(width+gap) + width//2
    d.line((bx, y+228, bx, y+236, ex, y+236, ex, y+228), fill='#ff8793', width=2)
    d.polygon([(ex, y+228), (ex-5, y+234), (ex+5, y+234)], fill='#ff8793')
    text(65, y+244, 'Cabang merah: kondisi gagal / ditolak; jalur utama tidak melewati error.', 15, '#91a4bb')

text(62, 1490, 'Status implementasi dan batas verifikasi: lihat design/REVISI-1-STATUS.md', 18, '#b5c6d9')
im.save('design/snapshots/revisi-1-diagram-target.png')
