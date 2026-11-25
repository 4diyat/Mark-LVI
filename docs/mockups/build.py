#!/usr/bin/env python3
"""Generate the JARVIS design-system sheet (docs/mockups/jarvis-design-system.html).

Every artboard is plain SVG with inline attributes: no external fonts, no
network, no CSS file, so the sheet renders inside a sandboxed preview.

The specification fixes the palette, radii and component sizes; this file only
turns them into geometry. Numbers that the specification did NOT give are
listed in ASSUMPTIONS and marked with a dagger in the summary table.
"""
from __future__ import annotations

import html

# ── tokens (from the brief) ─────────────────────────────────────────────────
BASE, PANEL, LINE = "#0c0d11", "#101820", "#1c2028"
LINE_ACC, CYAN, AMBER = "#243040", "#3486fe", "#ff9a40"
TEXT, MUTED = "#ffffff", "#5e636c"
# light theme, from the brief
LBASE, LPANEL, LLINE = "#F6F9FB", "#FFFFFF", "#D8E3E9"
LACC, LTEXT, LMUTED, LAMBER = "#1d6fe8", "#0B1A24", "#5B7480", "#9a5b00"

FONT = "'Space Grotesk','Segoe UI',Arial,Helvetica,sans-serif"
R_CARD, R_PANEL, R_PILL = 12, 16, 21

_uid = [0]


def uid(prefix="g"):
    _uid[0] += 1
    return f"{prefix}{_uid[0]}"


def esc(s):
    return html.escape(str(s), quote=True)


def txt(x, y, s, size=13, fill=TEXT, weight=400, anchor="start",
        track=None, opacity=None, family=FONT):
    a = f' letter-spacing="{track}"' if track is not None else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{a}{o}>{esc(s)}</text>')


def label(x, y, s, fill=MUTED, size=10.5):
    """Small caps label with 2px tracking, per the brief."""
    return txt(x, y, s.upper(), size=size, fill=fill, weight=500, track="2")


def rect(x, y, w, h, fill, r=0, stroke=None, sw=1, op=None):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    o = f' fill-opacity="{op}"' if op is not None else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{o}{st}/>'


def card(x, y, w, h, title=None, fill=PANEL, stroke=LINE, pad=18):
    out = [rect(x, y, w, h, fill, R_CARD, stroke)]
    if title:
        out.append(txt(x + pad, y + 26, title, 13, TEXT, 500))
    return "".join(out)


def pill_btn(x, y, w, h, text, primary=True, size=12.5, disabled=False):
    if primary:
        fill, col, stroke = CYAN, BASE, None
    else:
        fill, col, stroke = "none", TEXT, LINE_ACC
    if disabled:
        fill, col, stroke = "none", MUTED, LINE
    out = rect(x, y, w, h, fill, h / 2, stroke)
    out += txt(x + w / 2, y + h / 2 + size * 0.36, text, size, col, 500, "middle")
    return out


def toggle(x, y, on, w=40, h=22):
    track = CYAN if on else "#13242E"
    out = rect(x, y, w, h, track, h / 2, None if on else LINE)
    kx = x + w - h / 2 if on else x + h / 2
    out += f'<circle cx="{kx}" cy="{y + h / 2}" r="{h / 2 - 3}" fill="{BASE if on else MUTED}"/>'
    return out


def kbd(x, y, s, light=False):
    """Shortcut key cap. Returns (svg, width)."""
    w = 12 + len(s) * 6.6
    fill = "#0E202B" if not light else "#EDF3F6"
    stroke = LINE_ACC if not light else LLINE
    col = TEXT if not light else LTEXT
    out = rect(x, y - 13, w, 20, fill, 5, stroke)
    out += txt(x + w / 2, y + 1, s, 10.5, col, 500, "middle",
               family="'SFMono-Regular',Consolas,monospace")
    return out, w


def chip(x, y, s, fill=LINE, col=TEXT, size=11, h=22, track="0.4"):
    w = 16 + len(s) * (size * 0.56)
    out = rect(x, y, w, h, fill, h / 2, None)
    out += txt(x + w / 2, y + h / 2 + size * 0.36, s, size, col, 500, "middle", track=track)
    return out, w


def seg(x, y, items, active=0, w=None, h=34):
    n = len(items)
    w = w or (n * 104)
    iw = w / n
    out = rect(x, y, w, h, "#0B1A22", h / 2, LINE)
    for i, s in enumerate(items):
        if i == active:
            out += rect(x + i * iw + 3, y + 3, iw - 6, h - 6, LINE_ACC, (h - 6) / 2)
        out += txt(x + i * iw + iw / 2, y + h / 2 + 4,
                   s, 11.5, TEXT if i == active else MUTED, 500, "middle")
    return out


def slider(x, y, w, pct, fill=CYAN):
    out = rect(x, y, w, 3, "#13242E", 1.5)
    out += rect(x, y, max(2, w * pct), 3, fill, 1.5)
    out += f'<circle cx="{x + w * pct}" cy="{y + 1.5}" r="7" fill="{fill}"/>'
    return out


def progress(x, y, w, pct, h=4, fill=CYAN):
    return (rect(x, y, w, h, "#13242E", h / 2)
            + rect(x, y, max(2, w * pct), h, fill, h / 2))


def orb(cx, cy, r, glow=True, light=False):
    g, gg = uid("orb"), uid("glow")
    c1, c2, c3 = ("#8fb8ff", "#3486fe", "#0a2a55") if not light else ("#EAFDFF", "#7FDCEC", "#1d6fe8")
    out = [f'<defs><radialGradient id="{g}" cx="0.38" cy="0.34" r="0.72">'
           f'<stop offset="0" stop-color="{c1}"/><stop offset="0.45" stop-color="{c2}"/>'
           f'<stop offset="1" stop-color="{c3}"/></radialGradient>']
    if glow:
        out.append(f'<radialGradient id="{gg}" cx="0.5" cy="0.5" r="0.5">'
                   f'<stop offset="0.45" stop-color="{CYAN}" stop-opacity="0.28"/>'
                   f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>')
    out.append("</defs>")
    if glow:
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r * 2.6}" fill="url(#{gg})"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{g})"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r * 0.82}" fill="none" '
               f'stroke="#0a2a55" stroke-width="1.2" stroke-dasharray="2 4" opacity="0.85"/>')
    return "".join(out)


def toast(x, y, w, title, body, actions=(), accent=CYAN):
    """Small toast card: 8-second auto-dismiss per the brief."""
    h = 96 if actions else 74
    out = rect(x, y, w, h, "#0C1B26", R_CARD, LINE)
    out += rect(x, y + 14, 3, h - 28, accent, 1.5)
    out += txt(x + 20, y + 30, title, 13, TEXT, 500)
    out += txt(x + 20, y + 50, body, 11.5, MUTED)
    if actions:
        ax = x + 20
        for i, a in enumerate(actions):
            kb, kw = kbd(ax + 0, y + 84, a) if False else (None, 0)
            aw = 12 + len(a) * 6.4
            out += rect(ax, y + 64, aw, 22, "none", 11, LINE_ACC if i else CYAN)
            out += txt(ax + aw / 2, y + 79, a, 11, CYAN if i == 0 else TEXT, 500, "middle")
            ax += aw + 10
    return out


def frame(w, h, inner, bg=BASE):
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img">'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>{inner}</svg>')


def desktop_chrome(w, h):
    """A neutral user desktop: the taskbar the tray icon lives on."""
    out = rect(0, h - 40, w, 40, "#07121A")
    out += rect(0, h - 40, w, 1, LINE)
    out += orb(28, h - 20, 9, glow=False)
    out += txt(46, h - 16, "JARVIS", 10, MUTED, 500, track="1.6")
    out += txt(w - 20, h - 15, "14:32  ·  Kam 19 Nov", 10.5, MUTED, 400, "end")
    return out


def doc_window(x, y, w, h, title, lines):
    out = rect(x, y, w, h, "#0D141A", 8, "#1B2A33")
    out += rect(x, y, w, 30, "#111C24", 8)
    out += rect(x, y + 22, w, 8, "#111C24")
    out += f'<circle cx="{x + 18}" cy="{y + 15}" r="4" fill="#2A3A44"/>'
    out += f'<circle cx="{x + 32}" cy="{y + 15}" r="4" fill="#2A3A44"/>'
    out += txt(x + w / 2, y + 19, title, 10.5, MUTED, 500, "middle")
    yy = y + 54
    for kind, s in lines:
        if kind == "h":
            out += txt(x + 24, yy, s, 13, TEXT, 500)
        else:
            out += txt(x + 24, yy, s, 11, MUTED)
        yy += 22
    return out


def artboard(num, title, w, h, body, bg=BASE):
    svg = body if body.lstrip().startswith("<svg") else frame(w, h, body, bg)
    return f"""
<section class="ab">
  <div class="abhead"><span class="num">{esc(str(num))}</span><span class="ttl">{esc(title)}</span>
    <span class="dim">{w} × {h}</span></div>
  <div class="sheet" style="width:{w}px">{svg}</div>
</section>"""


BOARDS = []


def board(num, title, w, h, body, bg=BASE):
    BOARD = artboard(num, title, w, h, body, bg)
    BOARDS.append(BOARD)


def hand(cx, cy, s=1.0, pose="open", stroke=CYAN):
    """Hand skeleton, 2px strokes.

    pose: open | pinch | fist | two | swipe | palm
    Each pose changes which fingers are extended, so the shapes differ by
    SILHOUETTE and not only by a label underneath.
    """
    out = []
    ox, oy = cx, cy + 40 * s          # wrist
    palm = (cx, cy + 8 * s)

    def dot(x, y, r=3.0):
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r*s:.1f}" fill="{stroke}"/>'

    out.append(f'<path d="M{ox:.1f} {oy:.1f} L{palm[0]:.1f} {palm[1]:.1f}" stroke="{stroke}" '
               f'stroke-width="2" stroke-linecap="round"/>')
    out.append(f'<ellipse cx="{palm[0]:.1f}" cy="{palm[1]:.1f}" rx="{20*s:.1f}" ry="{24*s:.1f}" '
               f'fill="none" stroke="{stroke}" stroke-width="2" opacity="0.9"/>')

    # index, middle, ring, little: base x offsets across the palm
    bases = [(-13, -6), (-4, -10), (5, -9), (13, -5)]
    extended = {"open": (0, 1, 2, 3), "swipe": (0, 1, 2, 3), "palm": (0, 1, 2, 3),
                "pinch": (0,), "fist": (), "two": (0, 1)}[pose]
    lengths = (34, 40, 37, 30)
    for i, (bx, by) in enumerate(bases):
        x0, y0 = palm[0] + bx * s, palm[1] + 8 * s
        if i in extended:
            L = lengths[i] * s
            if pose == "pinch" and i == 0:
                # index curves toward the thumb tip
                tx, ty = palm[0] - 22 * s, palm[1] + 2 * s
                out.append(f'<path d="M{x0:.1f} {y0:.1f} q{-6*s:.1f} {-14*s:.1f} '
                           f'{-14*s:.1f} {-18*s:.1f}" stroke="{stroke}" stroke-width="2" '
                           f'fill="none" stroke-linecap="round"/>')
                out.append(dot(tx, ty, 3.2))
            else:
                tx, ty = x0 + bx * 0.22 * s, y0 - L
                out.append(f'<path d="M{x0:.1f} {y0:.1f} L{tx:.1f} {ty:.1f}" stroke="{stroke}" '
                           f'stroke-width="2" stroke-linecap="round"/>')
                out.append(dot(tx, ty, 2.8))
        else:
            # curled: a short hook back down, so folded fingers read as folded
            out.append(f'<path d="M{x0:.1f} {y0:.1f} q{-2*s:.1f} {-9*s:.1f} '
                       f'{4*s:.1f} {-11*s:.1f} q{4*s:.1f} {-2*s:.1f} {6*s:.1f} {1*s:.1f}" '
                       f'stroke="{stroke}" stroke-width="2" fill="none" stroke-linecap="round"/>')

    # thumb
    if pose == "pinch":
        out.append(f'<path d="M{palm[0]-16*s:.1f} {palm[1]+6*s:.1f} '
                   f'L{palm[0]-22*s:.1f} {palm[1]+2*s:.1f}" stroke="{stroke}" stroke-width="2" '
                   f'stroke-linecap="round"/>')
    elif pose == "fist":
        out.append(f'<path d="M{palm[0]-16*s:.1f} {palm[1]+4*s:.1f} q{8*s:.1f} {-2*s:.1f} '
                   f'{12*s:.1f} {-6*s:.1f}" stroke="{stroke}" stroke-width="2" fill="none" '
                   f'stroke-linecap="round"/>')
    else:
        out.append(f'<path d="M{palm[0]-16*s:.1f} {palm[1]+6*s:.1f} '
                   f'L{palm[0]-34*s:.1f} {palm[1]-2*s:.1f}" stroke="{stroke}" stroke-width="2" '
                   f'stroke-linecap="round"/>')
        out.append(dot(palm[0] - 34 * s, palm[1] - 2 * s, 3))
    return "".join(out)


def arrows(cx, cy, kind="h", stroke=CYAN):
    """Motion cue beside a hand: 'h' = left/right, 'v' = up/down."""
    out = []
    if kind == "h":
        for sgn in (-1, 1):
            x0, x1 = cx + sgn * 26, cx + sgn * 58
            out.append(f'<path d="M{x0} {cy} H{x1}" stroke="{stroke}" stroke-width="2" '
                       f'stroke-linecap="round" opacity="0.75"/>')
            out.append(f'<path d="M{x1} {cy} l{-7*sgn} -6 M{x1} {cy} l{-7*sgn} 6" '
                       f'stroke="{stroke}" stroke-width="2" stroke-linecap="round" opacity="0.75"/>')
    else:
        for sgn in (-1, 1):
            y0, y1 = cy + sgn * 26, cy + sgn * 54
            out.append(f'<path d="M{cx} {y0} V{y1}" stroke="{stroke}" stroke-width="2" '
                       f'stroke-linecap="round" opacity="0.75"/>')
            out.append(f'<path d="M{cx} {y1} l-6 {-7*sgn} M{cx} {y1} l6 {-7*sgn}" '
                       f'stroke="{stroke}" stroke-width="2" stroke-linecap="round" opacity="0.75"/>')
    return "".join(out)


def pinch_ring(cx, cy, r=15):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CYAN}" '
            f'stroke-width="2" opacity="0.85"/>'
            f'<circle cx="{cx}" cy="{cy}" r="4" fill="{CYAN}"/>')


def timer_ring(cx, cy, r, pct):
    import math as _m
    circ = 2 * _m.pi * r
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{LINE_ACC}" '
            f'stroke-width="2" opacity="0.45"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CYAN}" stroke-width="3" '
            f'stroke-linecap="round" stroke-dasharray="{circ*pct:.1f} {circ:.1f}" '
            f'transform="rotate(-90 {cx} {cy})"/>')


# ── 1. Desktop ambient ─────────────────────────────────────────────────────
def b01():
    # THE ORB SITS HIGHER THAN THE BOTTOM-RIGHT CORNER WOULD SUGGEST, AND THAT
    # IS ARITHMETIC RATHER THAN TASTE. Its glow is a circle at r × 2.6 = 72.8 px,
    # so an orb centred at y = 596 paints to y = 668.8 on a 720 px canvas and
    # its caption at y = 660 lands inside the glow. Placed on the second row
    # of the desktop chrome's own tray baseline it fits, and
    # `tests/test_design_sheet_complete.py` fails if any artboard paints
    # outside its own canvas again.
    o = [txt(24, 30, "Desktop", 11, MUTED, 500, track="1.6"),
         doc_window(96, 62, 720, 400, "RAB Q4 · anggaran.xlsx", [
             ("h", "Ringkasan anggaran kuartal empat"),
             ("p", "Baris item, satuan, harga, subtotal — semua terisi."),
             ("p", "Kolom realisasi menunggu persetujuan tim keuangan."),
             ("p", "Catatan: gunakan kurs tengah BI pada tanggal transaksi."),
             ("p", "Lampiran: 3 berkas · terakhir diubah 09:14"),
         ]),
         desktop_chrome(1280, 720)]
    # toast, bottom-right, above the orb
    o.append(toast(760, 470, 340, "Rapat tim dimulai 10 menit lagi",
                   "Ruang Rapat 2 · 5 peserta sudah masuk", ("Buka tautan", "Tunda 5 mnt")))
    # orb 56px
    o.append(orb(1204, 620, 28))
    o.append(txt(1204, 614, "Siaga", 10, MUTED, 500, "middle", track="1.6"))
    return frame(1280, 720, "".join(o))


# ── 2. Command bar ─────────────────────────────────────────────────────────
def b02():
    g, ge = uid("cb"), uid("cbe")
    o = [rect(0, 0, 1280, 720, BASE, op="0.55"),
         doc_window(96, 62, 720, 400, "RAB Q4 · anggaran.xlsx", [("h", "Ringkasan anggaran"), ("p", "…")]),
         desktop_chrome(1280, 720)]
    bx, by, bw, bh = 280, 178, 720, 352
    o.append(f'<defs><linearGradient id="{g}" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="#0C1E29"/><stop offset="1" stop-color="#081319"/>'
             f'</linearGradient>'
             f'<radialGradient id="{ge}" cx="0.5" cy="0" r="0.9">'
             f'<stop offset="0" stop-color="{CYAN}" stop-opacity="0.22"/>'
             f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient></defs>')
    o.append(rect(bx - 40, by - 46, bw + 80, bh + 90, f"url(#{ge})"))
    o.append(rect(bx, by, bw, bh, f"url(#{g})", R_PANEL, LINE_ACC))
    o.append(f'<path d="M{bx+1} {by+R_PANEL} v-{R_PANEL-1} q0 -{R_PANEL-1} {R_PANEL-1} -{R_PANEL-1} '
             f'h{bw-2*R_PANEL+2} q{R_PANEL-1} 0 {R_PANEL-1} {R_PANEL-1} v{R_PANEL-1}" '
             f'stroke="{CYAN}" stroke-width="1.5" fill="none" opacity="0.7"/>')
    # input row
    o.append(txt(bx + 26, by + 44, "Buat ringkasan RAB Q4", 19, TEXT, 500))
    o.append(rect(bx + 26 + 176, by + 27, 2, 22, CYAN))
    o.append(txt(bx + 632, by + 44, "Esc", 10.5, MUTED, 500, "middle",
                 family="'SFMono-Regular',Consolas,monospace"))
    o.append(rect(bx + 610, by + 30, 44, 20, "none", 5, LINE))
    o.append(txt(bx + 26, by + 68, "Konteks: RAB Q4 · anggaran.xlsx — 14 sel terpilih", 11, MUTED))
    o.append(rect(bx + 20, by + 82, bw - 40, 1, LINE))
    results = [("Ringkas dan buat catatan rapat", "Menulis ringkasan 14 baris lalu menyimpannya"),
               ("Hitung ulang subtotal dengan kurs BI", "Menawarkan pratinjau sebelum mengubah sel"),
               ("Kirim ke tim keuangan", "Aksi sedang — bisa diurungkan 10 menit")]
    yy = by + 108
    for i, (t, sub) in enumerate(results):
        if i == 0:
            o.append(rect(bx + 12, yy - 20, bw - 24, 62, "#0E2130", 10, LINE_ACC))
        o.append(rect(bx + 24, yy - 8, 28, 28, "#0B1A22", 8, LINE))
        o.append(f'<path d="M{bx+33} {yy+6} h10 M{bx+33} {yy+1} h10 M{bx+33} {yy+11} h6" '
                 f'stroke="{CYAN if i==0 else MUTED}" stroke-width="2" stroke-linecap="round"/>')
        o.append(txt(bx + 64, yy + 2, t, 13, TEXT if i == 0 else "#C4D6DE", 500))
        o.append(txt(bx + 64, yy + 20, sub, 11, MUTED))
        if i == 0:
            o.append(txt(bx + bw - 30, yy + 12, "↵", 12, CYAN, 500, "end",
                         family="'SFMono-Regular',Consolas,monospace"))
        yy += 70
    o.append(rect(bx + 20, by + bh - 44, bw - 40, 1, LINE))
    o.append(txt(bx + 26, by + bh - 20, "↑↓ pilih", 10.5, MUTED))
    o.append(txt(bx + 106, by + bh - 20, "↵ jalankan", 10.5, MUTED))
    o.append(txt(bx + 196, by + bh - 20, "Ctrl+Space tutup", 10.5, MUTED))
    return frame(1280, 720, "".join(o))


# ── 3. Live gesture ────────────────────────────────────────────────────────
def b03():
    o = [doc_window(96, 62, 720, 400, "RAB Q4 · anggaran.xlsx", [("h", "Ringkasan anggaran"), ("p", "…")]),
         desktop_chrome(1280, 720)]
    cx, cy, cw, ch = 916, 46, 320, 236
    o.append(rect(cx, cy, cw, ch, "#071018", R_CARD, LINE_ACC))
    o.append(txt(cx + 16, cy + 24, "KAMERA", 10, MUTED, 500, track="2"))
    o.append(f'<circle cx="{cx+cw-22}" cy="{cy+20}" r="4" fill="{AMBER}"/>')
    o.append(txt(cx + cw - 34, cy + 24, "langsung", 10, AMBER, 500, "end"))
    o.append(hand(cx + cw / 2, cy + 118, 1.05, "pinch"))
    # cursor ring at the pinch point
    px, py = cx + cw / 2 + 33, cy + 118 - 46
    o.append(f'<circle cx="{px}" cy="{py}" r="16" fill="none" stroke="{CYAN}" stroke-width="2"/>')
    o.append(f'<circle cx="{px}" cy="{py}" r="5" fill="{CYAN}"/>')
    o.append(txt(px + 24, py + 4, "titik cubit", 10, CYAN))
    # active gesture pill
    o.append(rect(96, 512, 300, 44, "#0C1B26", R_PILL, LINE_ACC))
    o.append(f'<circle cx="120" cy="534" r="5" fill="{CYAN}"/>')
    o.append(txt(134, 539, "Cubit + geser — menggulir", 12.5, TEXT, 500))
    o.append(card(96, 576, 480, 104, None))
    o.append(txt(116, 602, "Lepas untuk berhenti · Esc keluar dari mode gestur", 11, MUTED))
    o.append(rect(116, 614, 440, 1, LINE))
    o.append(txt(116, 636, "Cubit untuk klik · cubit ganda untuk klik ganda.", 11.5, TEXT))
    o.append(txt(116, 658, "Telapak terbuka 2 detik untuk menyenyapkan mikrofon.", 11.5, TEXT))
    return frame(1280, 720, "".join(o))


# ── 4. Full-screen voice ───────────────────────────────────────────────────
def b04():
    g = uid("edge")
    o = [rect(0, 0, 1280, 720, "#03060A"),
         doc_window(160, 90, 960, 470, "RAB Q4 · anggaran.xlsx",
                    [("h", "Ringkasan anggaran"), ("p", "…")])]
    o.append(f'<defs><radialGradient id="{g}" cx="0.5" cy="0.5" r="0.75">'
             f'<stop offset="0.62" stop-color="{CYAN}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0.30"/></radialGradient></defs>')
    o.append(rect(0, 0, 1280, 720, f"url(#{g})"))
    o.append(rect(0, 0, 1280, 2, CYAN, op="0.55"))
    o.append(rect(0, 718, 1280, 2, CYAN, op="0.55"))
    o.append(rect(0, 0, 2, 720, CYAN, op="0.55"))
    o.append(rect(1278, 0, 2, 720, CYAN, op="0.55"))
    o.append(orb(640, 250, 46))
    o.append(txt(640, 344, "MENDENGARKAN", 11, CYAN, 500, "middle", track="3"))
    # transcript pill
    tx, ty, tw = 320, 596, 640
    o.append(rect(tx, ty, tw, 76, "#101820", 26, LINE_ACC))
    o.append(txt(tx + 30, ty + 30, "“ringkas tabel ini dan tandai baris yang lewat anggaran”",
                 13.5, TEXT, 500))
    o.append(txt(tx + 30, ty + 54, "Baris 7 dan 11 melewati plafon sebesar 12% dan 4%.", 11.5, MUTED))
    for i, h in enumerate((8, 16, 26, 14, 6)):
        o.append(rect(tx + tw - 92 + i * 12, ty + 40 - h / 2, 4, h, CYAN, 2, op="0.8"))
    o.append(txt(640, 552, "Esc untuk berhenti · Ctrl+Space untuk mengetik", 10.5, MUTED, 400, "middle"))
    return frame(1280, 720, "".join(o))


# ── 5. Tray panel ──────────────────────────────────────────────────────────
def panel_head(title, sub=None, light=False):
    t = LTEXT if light else TEXT
    m = LMUTED if light else MUTED
    o = [orb(38, 40, 13, light=light),
         txt(62, 36, "JARVIS", 13, t, 700, track="1.6")]
    if sub:
        o.append(txt(62, 54, sub, 10.5, m))
    return "".join(o)


def b05():
    W, H = 460, 640
    o = [panel_head("JARVIS", "Aktif · memproses di perangkat"),
         seg(24, 76, ["Aktif", "Fokus", "Senyap"], 0, w=412, h=38)]
    # quick actions
    acts = [("Tangkap layar", "S"), ("Dikte", "D"), ("Cari berkas", "F"), ("Susun jendela", "J")]
    for i, (a, k) in enumerate(acts):
        x = 24 + (i % 2) * 208
        y = 132 + (i // 2) * 76
        o.append(card(x, y, 196, 64))
        o.append(rect(x + 16, y + 16, 32, 32, "#0B1A22", 9, LINE))
        o.append(txt(x + 32, y + 38, k, 13, CYAN, 700, "middle"))
        o.append(txt(x + 60, y + 30, a, 12, TEXT, 500))
        o.append(txt(x + 60, y + 48, "Ctrl+Shift+" + k, 9.5, MUTED))
    # chat
    o.append(txt(24, 312, "PERCAKAPAN", 10, MUTED, 500, track="2"))
    o.append(rect(24, 326, 412, 158, "#14181c", R_CARD, LINE))
    o.append(rect(40, 342, 250, 34, "#0E2130", 10, LINE_ACC))
    o.append(txt(56, 364, "Rapat berikutnya jam berapa?", 11.5, TEXT))
    o.append(rect(180, 386, 240, 40, CYAN, 10, op="0.14"))
    o.append(txt(196, 402, "Rapat tim 10 menit lagi, lalu", 11.5, TEXT))
    o.append(txt(196, 418, "review anggaran jam 14.00.", 11.5, TEXT))
    o.append(txt(40, 452, "Sedang menulis…", 10.5, CYAN))
    # permissions
    o.append(txt(24, 500, "IZIN", 10, MUTED, 500, track="2"))
    rows = [("Layar", True), ("Mikrofon", True), ("Berkas", False)]
    for i, (n, v) in enumerate(rows):
        y = 514 + i * 26
        o.append(txt(24, y + 14, n, 11.5, TEXT))
        o.append(toggle(396, y + 2, v))
    # input
    o.append(rect(24, 596, 340, 40, "#101820", 20, LINE))
    o.append(txt(44, 621, "Tulis atau tekan Ctrl+Space", 11.5, MUTED))
    o.append(f'<circle cx="404" cy="616" r="18" fill="{CYAN}"/>')
    o.append(f'<path d="M398 622 l12 -12 M404 610 h8 v8" stroke="{BASE}" stroke-width="2" '
             f'fill="none" stroke-linecap="round"/>')
    return frame(W, H, "".join(o))


def light_card(x, y, w, h, title=None, pad=18):
    o = rect(x, y, w, h, LPANEL, R_CARD, LLINE)
    if title:
        o += txt(x + pad, y + 26, title, 13, LTEXT, 500)
    return o


def light_pill(x, y, w, h, s, primary=True):
    if primary:
        o = rect(x, y, w, h, LACC, h / 2)
        o += txt(x + w / 2, y + h / 2 + 4.5, s, 12.5, "#FFFFFF", 500, "middle")
    else:
        o = rect(x, y, w, h, "none", h / 2, LACC)
        o += txt(x + w / 2, y + h / 2 + 4.5, s, 12.5, LACC, 500, "middle")
    return o


def light_seg(x, y, items, active=0, w=None, h=34):
    n = len(items); w = w or (n * 104); iw = w / n
    o = rect(x, y, w, h, "#EDF3F6", h / 2, LLINE)
    for i, lab in enumerate(items):
        if i == active:
            o += rect(x + i * iw + 3, y + 3, iw - 6, h - 6, LACC, (h - 6) / 2)
        o += txt(x + i * iw + iw / 2, y + h / 2 + 4, lab, 11.5,
                 "#FFFFFF" if i == active else LMUTED, 500, "middle")
    return o


def light_toggle(x, y, on, w=40, h=22):
    o = rect(x, y, w, h, LACC if on else "#C9D8DF", h / 2)
    kx = x + w - h / 2 if on else x + h / 2
    o += f'<circle cx="{kx}" cy="{y+h/2}" r="{h/2-3}" fill="#FFFFFF"/>'
    return o


def b06():
    W, H = 460, 640
    o = [panel_head("Izin & privatisasi", "Semua proses di perangkat", light=False),
         txt(24, 92, "IZIN AKSES", 10, MUTED, 500, track="2")]
    perms = [("Layar", "Melihat jendela aktif saat diminta", True),
             ("Mikrofon", "Mendengar perintah suara", True),
             ("Berkas", "Hanya folder yang dipilih", False),
             ("Kontrol aplikasi lain", "Menekan tombol atas nama Anda", False)]
    for i, (n, sub, v) in enumerate(perms):
        y = 106 + i * 72
        o.append(card(24, y, 412, 62))
        o.append(txt(44, y + 26, n, 12.5, TEXT, 500))
        o.append(txt(44, y + 45, sub, 10.5, MUTED))
        o.append(toggle(378, y + 20, v))
    o.append(txt(24, 412, "LOG AKTIVITAS", 10, MUTED, 500, track="2"))
    o.append(rect(24, 426, 412, 118, "#14181c", R_CARD, LINE))
    log = [("09:14", "Membaca layar — anggaran.xlsx"),
           ("09:10", "Dikte 42 kata ke editor"),
           ("08:58", "Menolak akses berkas (izin mati)")]
    for i, (t, s) in enumerate(log):
        y = 448 + i * 32
        o.append(txt(40, y, t, 10.5, CYAN, 500, family="'SFMono-Regular',Consolas,monospace"))
        o.append(txt(92, y, s, 11, TEXT))
    o.append(rect(24, 556, 412, 1, LINE))
    o.append(pill_btn(24, 574, 200, 40, "Hapus riwayat", primary=False))
    o.append(pill_btn(236, 574, 200, 40, "Ekspor log", primary=False))
    return frame(W, H, "".join(o))


def b07():
    W, H = 460, 640
    o = [panel_head("Izin & privatisasi", "Langkah 2 dari 4")]
    for i in range(4):
        o.append(rect(24 + i * 105, 74, 97, 4, CYAN if i < 2 else "#13242E", 2))
    o.append(txt(24, 126, "Mikrofon", 22, TEXT, 700))
    o.append(txt(24, 154, "Dibutuhkan untuk perintah suara dan dikte.", 12, MUTED))
    o.append(rect(24, 174, 412, 190, "#14181c", R_CARD, LINE))
    o.append(orb(230, 244, 26))
    for i, w in enumerate((6, 14, 30, 18, 8, 22, 12)):
        o.append(rect(150 + i * 18, 316 - w / 2, 5, w, CYAN, 2.5, op="0.75"))
    o.append(txt(230, 348, "Hanya aktif saat Anda memanggilnya", 10.5, MUTED, 400, "middle"))
    o.append(txt(24, 400, "YANG TERJADI", 10, MUTED, 500, track="2"))
    pts = ["Audio diproses di perangkat ini.",
           "Tidak ada rekaman tersimpan kecuali Anda memintanya.",
           "Izin dapat dimatikan kapan saja dari panel izin."]
    for i, p in enumerate(pts):
        y = 424 + i * 28
        o.append(f'<path d="M28 {y-4} l4 5 l8 -9" stroke="{CYAN}" stroke-width="2" '
                 f'fill="none" stroke-linecap="round"/>')
        o.append(txt(50, y, p, 11.5, TEXT))
    o.append(toggle(24, 520, True))
    o.append(txt(76, 536, "Saya mengerti, aktifkan mikrofon", 12, TEXT, 500))
    o.append(pill_btn(24, 566, 196, 44, "Lewati", primary=False))
    o.append(pill_btn(236, 566, 200, 44, "Lanjut", primary=True))
    return frame(W, H, "".join(o))


def b08():
    W, H = 460, 640
    o = [panel_head("Riwayat tugas", "Hari ini · 6 tugas")]
    items = [("Ringkas anggaran Q4", "09:14", "selesai", True),
             ("Ganti 14 sel dengan kurs BI", "09:02", "bisa diurungkan", True),
             ("Kirim ke tim keuangan", "08:56", "menunggu konfirmasi", False),
             ("Susun 2 kolom jendela", "08:40", "selesai", True),
             ("Dikte 42 kata", "08:31", "selesai", True)]
    for i, (t, tm, st, done) in enumerate(items):
        y = 80 + i * 92
        o.append(card(24, y, 412, 80))
        o.append(f'<circle cx="46" cy="{y+26}" r="5" fill="{CYAN if done else AMBER}"/>')
        o.append(txt(62, y + 31, t, 12.5, TEXT, 500))
        o.append(txt(62, y + 50, tm + "  ·  " + st, 10.5, MUTED))
        if i == 1:
            o.append(pill_btn(300, y + 46, 60, 24, "Urungkan", primary=False, size=10.5))
            o.append(pill_btn(368, y + 46, 56, 24, "Pulihkan", primary=False, size=10.5))
        elif not done:
            o.append(pill_btn(318, y + 46, 106, 24, "Konfirmasi", primary=True, size=10.5))
    o.append(txt(24, 566, "Riwayat disimpan 30 hari, lalu dihapus otomatis.", 10.5, MUTED))
    o.append(pill_btn(24, 584, 200, 40, "Hapus semua", primary=False))
    o.append(pill_btn(236, 584, 200, 40, "Saring", primary=False))
    return frame(W, H, "".join(o))


def b09():
    W, H = 460, 640
    o = [panel_head("Memori personal", "12 hal yang JARVIS ingat"),
         txt(24, 92, "FAKTA TENTANG ANDA", 10, MUTED, 500, track="2")]
    facts = [("Nama panggilan", "Pak Diat"),
             ("Zona waktu", "WIB · Asia/Jakarta"),
             ("Rapat rutin", "Senin 09.30, Kamis 14.00"),
             ("Folder kerja", "~/Projects/RAB"),
             ("Gaya jawaban", "Ringkas, tanpa basa-basi"),
             ("Bahasa", "Indonesia, istilah teknis Inggris")]
    for i, (k, v) in enumerate(facts):
        y = 106 + i * 72
        o.append(card(24, y, 412, 62))
        o.append(txt(44, y + 24, k, 10, MUTED, 500, track="1.6"))
        o.append(txt(44, y + 46, v, 13, TEXT, 500))
        o.append(f'<path d="M400 {y+22} l8 8 M408 {y+22} l-8 8" stroke="{MUTED}" '
                 f'stroke-width="1.5" opacity="0.5"/>')
    o.append(rect(24, 556, 412, 1, LINE))
    o.append(pill_btn(24, 574, 200, 40, "Tambah memori", primary=False))
    o.append(pill_btn(236, 574, 200, 40, "Hapus semua", primary=False))
    return frame(W, H, "".join(o))


def b10():
    W, H = 460, 640
    o = [f'<path d="M42 54 l-9 9 l9 9" stroke="{MUTED}" stroke-width="2" fill="none" '
         f'stroke-linecap="round" stroke-linejoin="round"/>',
         txt(58, 66, "Detail memori", 14, TEXT, 500),
         txt(24, 116, "ISI MEMORI", 10, MUTED, 500, track="2")]
    o.append(rect(24, 130, 412, 62, "#14181c", R_CARD, LINE_ACC))
    o.append(txt(44, 158, "Folder kerja utama", 11, MUTED))
    o.append(txt(44, 180, "~/Projects/RAB", 13.5, TEXT, 500))
    o.append(txt(24, 222, "SUMBER", 10, MUTED, 500, track="2"))
    o.append(seg(24, 236, ["Otomatis", "Manual"], 1, w=412, h=36))
    o.append(txt(24, 306, "MASA BERLAKU", 10, MUTED, 500, track="2"))
    o.append(seg(24, 320, ["30 hari", "1 tahun", "Selamanya"], 2, w=412, h=36))
    o.append(txt(24, 392, "KEYAKINAN", 10, MUTED, 500, track="2"))
    o.append(slider(24, 412, 380, 0.86))
    o.append(txt(24, 440, "Tinggi — disebut 9 kali dalam 30 hari terakhir", 10.5, MUTED))
    o.append(txt(24, 486, "DIPAKAI OLEH", 10, MUTED, 500, track="2"))
    cx = 24
    for s in ("Ringkas berkas", "Cari berkas", "Susun jendela"):
        c, w = chip(cx, 500, s, "#0E202B", TEXT)
        o.append(c)
        cx += w + 10
    o.append(rect(24, 556, 412, 1, LINE))
    o.append(pill_btn(24, 574, 130, 40, "Simpan", primary=True))
    o.append(pill_btn(166, 574, 130, 40, "Lupakan", primary=False))
    o.append(pill_btn(308, 574, 128, 40, "Ekspor", primary=False))
    return frame(W, H, "".join(o))


def b11():
    W, H = 460, 640
    o = [panel_head("Rutinitas & saran", "3 rutinitas aktif")]
    routines = [("Briefing pagi", "Setiap hari 06.30", "Cuaca, agenda, 2 pengingat", True),
                ("Ringkas rapat", "Setiap Kamis 14.00", "Rekap 30 menit setelah rapat", True),
                ("Siapkan laporan", "Setiap Jumat 16.00", "RAB mingguan + grafik", False)]
    for i, (n, t, s, on) in enumerate(routines):
        y = 84 + i * 96
        o.append(card(24, y, 412, 84))
        o.append(txt(44, y + 28, n, 13, TEXT, 500))
        o.append(txt(44, y + 48, t, 10.5, CYAN))
        o.append(txt(44, y + 66, s, 10.5, MUTED))
        o.append(toggle(378, y + 30, on))
    o.append(txt(24, 392, "SARAN PROAKTIF", 10, MUTED, 500, track="2"))
    sug = [("Anggaran Q4 lewat plafon di 2 baris", "Buka pratinjau koreksi"),
           ("Rapat 10 menit lagi, berkas belum dibuka", "Siapkan tautan & catatan"),
           ("Clipboard berisi rekening — jangan dibagikan", "Tandai sensitif")]
    for i, (t, a) in enumerate(sug):
        y = 406 + i * 68
        o.append(card(24, y, 412, 58))
        o.append(rect(24, y + 12, 3, 34, AMBER, 1.5))
        o.append(txt(44, y + 26, t, 11.5, TEXT, 500))
        o.append(txt(44, y + 44, a, 10.5, MUTED))
    o.append(txt(24, 636, "Saran bisa dimatikan per jenis di Pengaturan › Rutinitas.", 10, MUTED))
    return frame(W, H, "".join(o))


def b12():
    W, H = 460, 640
    o = [panel_head("Alat cepat", "Tiga alat yang paling sering dipakai")]
    o.append(card(24, 76, 412, 150, "CLIPBOARD CERDAS"))
    o.append(rect(40, 108, 380, 54, "#14181c", 10, LINE))
    o.append(txt(56, 130, "1234 5678 9012 3456 · BCA · a.n. Diat", 11.5, TEXT))
    o.append(txt(56, 148, "Terdeteksi: nomor rekening · sensitif", 10, AMBER))
    o.append(pill_btn(40, 176, 110, 32, "Salin", primary=False, size=11))
    o.append(pill_btn(158, 176, 140, 32, "Tandai aman", primary=True, size=11))
    o.append(pill_btn(306, 176, 114, 32, "Bersihkan", primary=False, size=11))
    o.append(card(24, 244, 412, 158, "CARI BERKAS · BAHASA ALAMI"))
    o.append(rect(40, 276, 380, 40, "#14181c", 20, LINE_ACC))
    o.append(txt(58, 301, "faktur bulan lalu yang belum dibayar", 11.5, TEXT))
    hits = ["faktur-okt-07.pdf", "faktur-okt-21.pdf", "rekap-belum-bayar.xlsx"]
    for i, hh in enumerate(hits):
        o.append(txt(48, 338 + i * 22, "·", 14, CYAN))
        o.append(txt(60, 338 + i * 22, hh, 11, TEXT if i < 2 else MUTED))
    o.append(card(24, 420, 412, 176, "SUSUN JENDELA"))
    lay = [("2 kolom", 0), ("3 kolom", 1), ("Fokus", 2)]
    for i, (n, idx) in enumerate(lay):
        x = 40 + i * 126
        sel = idx == 1
        o.append(rect(x, 452, 114, 62, "#0B1A22", 8, LINE_ACC if sel else LINE))
        if idx == 0:
            o.append(rect(x + 14, 466, 38, 34, "#12303D", 3, LINE_ACC))
            o.append(rect(x + 60, 466, 38, 34, "#12303D", 3, LINE_ACC))
        elif idx == 1:
            o.append(rect(x + 12, 466, 24, 34, "#12303D", 3, LINE_ACC))
            o.append(rect(x + 44, 466, 24, 34, "#12303D", 3, LINE_ACC))
            o.append(rect(x + 76, 466, 24, 34, "#12303D", 3, LINE_ACC))
        else:
            o.append(rect(x + 32, 462, 50, 40, "#12303D", 3, LINE_ACC))
        o.append(txt(x + 57, 534, n, 10.5, CYAN if sel else MUTED, 500, "middle"))
    o.append(txt(40, 572, "Ctrl+Shift+J menyusun ulang jendela yang sedang terbuka.", 10.5, MUTED))
    return frame(W, H, "".join(o))


def b13():
    W, H = 460, 640
    o = [panel_head("Bantuan tulis", "Dikte · baca layar · isi form")]
    o.append(txt(24, 92, "DIKTE DI APLIKASI MANA PUN", 10, MUTED, 500, track="2"))
    o.append(rect(24, 106, 412, 88, "#14181c", R_CARD, LINE_ACC))
    o.append(txt(44, 136, "“kirim email ke tim keuangan soal", 12, TEXT))
    o.append(txt(44, 158, "revisi anggaran kuartal empat”", 12, TEXT))
    o.append(txt(44, 182, "48 kata · Esc batal · ↵ sisipkan", 10, MUTED))
    o.append(txt(24, 232, "PEMBACA LAYAR KONTEKSTUAL", 10, MUTED, 500, track="2"))
    o.append(card(24, 246, 412, 116))
    o.append(txt(44, 276, "Jendela aktif: RAB Q4 · anggaran.xlsx", 11.5, TEXT, 500))
    o.append(txt(44, 298, "“Tabel 14 baris, 5 kolom. Baris 7 dan 11", 11, MUTED))
    o.append(txt(44, 316, "melewati plafon. Total selisih Rp 84 juta.”", 11, MUTED))
    o.append(pill_btn(44, 330, 120, 26, "Bacakan", primary=True, size=10.5))
    o.append(txt(24, 396, "ISI FORM DENGAN TINJAU DULU", 10, MUTED, 500, track="2"))
    fields = [("Nama vendor", "PT Sinar Abadi"),
              ("Nomor faktur", "FB-2026-0912"),
              ("Jumlah", "Rp 12.400.000")]
    for i, (k, v) in enumerate(fields):
        y = 410 + i * 56
        o.append(txt(24, y + 14, k, 10, MUTED))
        o.append(rect(24, y + 22, 412, 32, "#14181c", 8, LINE))
        o.append(txt(40, y + 43, v, 11.5, TEXT))
    o.append(rect(24, 578, 412, 34, CYAN, 10, op="0.12"))
    o.append(txt(40, 600, "Pratinjau — belum ada yang diterapkan ke form.", 10.5, CYAN))
    return frame(W, H, "".join(o))


def b14():
    W, H = 460, 640
    o = [panel_head("Keamanan", "Tiga tingkat risiko")]
    inds = [("Mikrofon", True), ("Kamera", False), ("Layar", True)]
    for i, (n, on) in enumerate(inds):
        x = 24 + i * 140
        o.append(rect(x, 76, 132, 62, "#14181c", R_CARD, LINE))
        o.append(f'<circle cx="{x+22}" cy="98" r="5" fill="{CYAN if on else "#25404C"}"/>')
        o.append(txt(x + 36, 102, n, 11, TEXT, 500))
        o.append(txt(x + 16, 124, "aktif" if on else "mati", 10, CYAN if on else MUTED))
    o.append(txt(24, 176, "MODE TAMU", 10, MUTED, 500, track="2"))
    o.append(card(24, 190, 412, 66))
    o.append(txt(44, 216, "Sembunyikan memori & riwayat", 12, TEXT, 500))
    o.append(txt(44, 236, "Izin diminta ulang setiap sesi", 10.5, MUTED))
    o.append(toggle(378, 216, False))
    o.append(txt(24, 288, "TINGKAT RISIKO", 10, MUTED, 500, track="2"))
    lv = [("Aman", "Dijalankan langsung", CYAN, 0.0),
          ("Sedang", "Bisa diurungkan 10 menit", AMBER, 0.0),
          ("Berisiko", "Selalu minta konfirmasi fisik", "#FF6B6B", 0.0)]
    for i, (n, s, col, _) in enumerate(lv):
        y = 302 + i * 76
        o.append(card(24, y, 412, 64))
        o.append(rect(24, y + 10, 3, 44, col, 1.5))
        o.append(txt(44, y + 26, n, 12.5, TEXT, 500))
        o.append(txt(44, y + 46, s, 10.5, MUTED))
        mx = 404
        if i == 0:      # safe: a tick
            o.append(f'<path d="M{mx} {y+34} l5 5 l9 -11" stroke="{col}" stroke-width="2" '
                     f'fill="none" stroke-linecap="round"/>')
        elif i == 1:    # medium: an undo arrow
            o.append(f'<path d="M{mx+16} {y+38} a8 8 0 1 0 -3 -12" stroke="{col}" '
                     f'stroke-width="2" fill="none" stroke-linecap="round"/>')
            o.append(f'<path d="M{mx+9} {y+26} l4 8 l-9 1" stroke="{col}" stroke-width="2" '
                     f'fill="none" stroke-linejoin="round"/>')
        else:           # risky: an exclamation, drawn not typed
            o.append(f'<path d="M{mx+8} {y+24} v10" stroke="{col}" stroke-width="2.6" '
                     f'stroke-linecap="round"/>')
            o.append(f'<circle cx="{mx+8}" cy="{y+40}" r="1.9" fill="{col}"/>')
    o.append(rect(24, 540, 412, 76, "#0C1B26", R_CARD, AMBER))
    o.append(txt(44, 568, "Kontrol OS dinonaktifkan", 12, AMBER, 500))
    o.append(txt(44, 588, "Aktifkan di Pengaturan › Keamanan, lalu", 10.5, MUTED))
    o.append(txt(44, 604, "konfirmasi dengan tombol fisik.", 10.5, MUTED))
    return frame(W, H, "".join(o))


def b15():
    W, H = 460, 640
    o = [panel_head("Aksesibilitas", "Bahasa & gestur")]
    o.append(txt(24, 92, "BAHASA UI", 10, MUTED, 500, track="2"))
    o.append(seg(24, 106, ["Indonesia", "English", "Campur"], 0, w=412, h=38))
    o.append(txt(24, 172, "UKURAN TEKS", 10, MUTED, 500, track="2"))
    o.append(slider(24, 194, 380, 0.5))
    o.append(txt(24, 222, "Sedang · 14 px", 10.5, MUTED))
    o.append(txt(24, 264, "KONTRAS", 10, MUTED, 500, track="2"))
    o.append(seg(24, 278, ["Standar", "Tinggi"], 0, w=412, h=38))
    o.append(txt(24, 344, "GERAK", 10, MUTED, 500, track="2"))
    o.append(card(24, 358, 412, 64))
    o.append(txt(44, 384, "Kurangi animasi orb", 12, TEXT, 500))
    o.append(txt(44, 404, "Cincin berhenti berputar, glow tetap", 10.5, MUTED))
    o.append(toggle(378, 380, False))
    o.append(txt(24, 450, "GESTUR KUSTOM", 10, MUTED, 500, track="2"))
    gs = [("Telapak terbuka", "Panggil antarmuka"), ("Cubit", "Klik"), ("Kepalan", "Jeda media")]
    for i, (g, a) in enumerate(gs):
        y = 464 + i * 46
        o.append(card(24, y, 412, 38))
        o.append(txt(44, y + 24, g, 11.5, TEXT, 500))
        o.append(txt(250, y + 24, a, 11, CYAN))
        o.append(txt(416, y + 24, "ubah", 10, MUTED, 400, "end"))
    o.append(txt(24, 616, "Target sentuh minimal 44 px · kontras teks ≥ 4.5:1", 10, MUTED))
    return frame(W, H, "".join(o))


def b16():
    W, H = 460, 640
    o = [panel_head("Plugin & ponsel", "2 dari 5 plugin aktif")]
    o.append(txt(24, 92, "PLUGIN", 10, MUTED, 500, track="2"))
    pl = [("Penjadwal", "1.4.0 · resmi", True), ("Notulen rapat", "0.9.2 · resmi", True),
          ("Penerjemah", "2.0.1 · pihak ketiga", False)]
    for i, (n, v, on) in enumerate(pl):
        y = 106 + i * 70
        o.append(card(24, y, 412, 60))
        o.append(txt(44, y + 26, n, 12.5, TEXT, 500))
        o.append(txt(44, y + 45, v, 10, MUTED))
        o.append(toggle(378, y + 19, on))
    o.append(txt(24, 346, "SINKRON PONSEL", 10, MUTED, 500, track="2"))
    o.append(card(24, 360, 412, 130))
    o.append(rect(44, 380, 56, 90, "#14181c", 10, LINE_ACC))
    o.append(rect(50, 390, 44, 70, "#0B1A22", 6, LINE))
    o.append(txt(120, 402, "Pixel 8 · terhubung", 12, TEXT, 500))
    o.append(txt(120, 422, "Sinkron 09.14 · 128 item", 10.5, MUTED))
    o.append(txt(120, 444, "Hanya memori & riwayat tugas", 10.5, MUTED))
    o.append(pill_btn(120, 458, 150, 30, "Putuskan", primary=False, size=10.5))
    o.append(rect(24, 506, 412, 1, LINE))
    o.append(txt(24, 536, "Kode pasangan", 10, MUTED, 500, track="2"))
    o.append(rect(24, 550, 412, 46, "#14181c", 10, LINE))
    for i, ch in enumerate("4 7 9 2 1 5"):
        o.append(txt(52 + i * 30, 579, ch, 16, CYAN, 700, "middle",
                     family="'SFMono-Regular',Consolas,monospace"))
    o.append(txt(300, 579, "berlaku 5 menit", 10, MUTED, 400, "middle"))
    return frame(W, H, "".join(o))


def b17():
    W, H = 460, 640
    o = [light_card(0, 0, W, H, None),
         panel_head("JARVIS", "Aktif · memproses di perangkat", light=True)]
    o.append(seg(24, 76, ["Aktif", "Fokus", "Senyap"], 0, w=412, h=38))
    acts = [("Tangkap layar", "S"), ("Dikte", "D"), ("Cari berkas", "F"), ("Susun jendela", "J")]
    for i, (a, k) in enumerate(acts):
        x = 24 + (i % 2) * 208
        y = 132 + (i // 2) * 76
        o.append(light_card(x, y, 196, 64))
        o.append(rect(x + 16, y + 16, 32, 32, "#EDF3F6", 9, LLINE))
        o.append(txt(x + 32, y + 38, k, 13, LACC, 700, "middle"))
        o.append(txt(x + 60, y + 30, a, 12, LTEXT, 500))
        o.append(txt(x + 60, y + 48, "Ctrl+Shift+" + k, 9.5, LMUTED))
    o.append(txt(24, 312, "PERCAKAPAN", 10, LMUTED, 500, track="2"))
    o.append(rect(24, 326, 412, 158, "#FFFFFF", R_CARD, LLINE))
    o.append(rect(40, 342, 250, 34, "#EDF3F6", 10, LLINE))
    o.append(txt(56, 364, "Rapat berikutnya jam berapa?", 11.5, LTEXT))
    o.append(rect(180, 386, 240, 40, LACC, 10, op="0.10"))
    o.append(txt(196, 402, "Rapat tim 10 menit lagi, lalu", 11.5, LTEXT))
    o.append(txt(196, 418, "review anggaran jam 14.00.", 11.5, LTEXT))
    o.append(txt(40, 452, "Sedang menulis…", 10.5, LACC))
    o.append(txt(24, 500, "IZIN", 10, LMUTED, 500, track="2"))
    for i, (n, v) in enumerate([("Layar", True), ("Mikrofon", True), ("Berkas", False)]):
        y = 514 + i * 26
        o.append(txt(24, y + 14, n, 11.5, LTEXT))
        o.append(light_toggle(396, y + 2, v))
    o.append(rect(24, 596, 340, 40, "#FFFFFF", 20, LLINE))
    o.append(txt(44, 621, "Tulis atau tekan Ctrl+Space", 11.5, LMUTED))
    o.append(f'<circle cx="404" cy="616" r="18" fill="{LACC}"/>')
    o.append('<path d="M398 622 l12 -12 M404 610 h8 v8" stroke="#FFFFFF" stroke-width="2" '
             'fill="none" stroke-linecap="round"/>')
    return frame(W, H, "".join(o), bg=LBASE)


def b18():
    W, H = 460, 640
    o = [light_card(0, 0, W, H, None),
         panel_head("Izin & privatisasi", "Semua proses di perangkat", light=True),
         txt(24, 92, "IZIN AKSES", 10, LMUTED, 500, track="2")]
    perms = [("Layar", "Melihat jendela aktif saat diminta", True),
             ("Mikrofon", "Mendengar perintah suara", True),
             ("Berkas", "Hanya folder yang dipilih", False),
             ("Kontrol aplikasi lain", "Menekan tombol atas nama Anda", False)]
    for i, (n, sub, v) in enumerate(perms):
        y = 106 + i * 72
        o.append(light_card(24, y, 412, 62))
        o.append(txt(44, y + 26, n, 12.5, LTEXT, 500))
        o.append(txt(44, y + 45, sub, 10.5, LMUTED))
        o.append(light_toggle(378, y + 20, v))
    o.append(txt(24, 412, "LOG AKTIVITAS", 10, LMUTED, 500, track="2"))
    o.append(rect(24, 426, 412, 118, "#FFFFFF", R_CARD, LLINE))
    for i, (t, s) in enumerate([("09:14", "Membaca layar — anggaran.xlsx"),
                                ("09:10", "Dikte 42 kata ke editor"),
                                ("08:58", "Menolak akses berkas (izin mati)")]):
        y = 448 + i * 32
        o.append(txt(40, y, t, 10.5, LACC, 500, family="'SFMono-Regular',Consolas,monospace"))
        o.append(txt(92, y, s, 11, LTEXT))
    o.append(light_pill(24, 574, 200, 40, "Hapus riwayat", primary=False))
    o.append(light_pill(236, 574, 200, 40, "Ekspor log", primary=False))
    return frame(W, H, "".join(o), bg=LBASE)


def b19():
    W, H = 720, 640
    o = [txt(32, 40, "PETA GESTUR", 11, CYAN, 500, track="2"),
         txt(32, 68, "Enam gestur yang dikenali tanpa konfigurasi.", 12, MUTED)]
    items = [("Telapak terbuka", "Panggil / tutup antarmuka", "open", None),
             ("Cubit + geser", "Gulir halaman", "pinch", "ring"),
             ("Geser kiri / kanan", "Pindah tab", "swipe", "arrows"),
             ("Kepalan", "Jeda atau lanjutkan media", "fist", None),
             ("Dua jari", "Atur volume", "two", None),
             ("Telapak 2 detik", "Senyapkan mikrofon", "palm", "timer")]
    for i, (n, a, pose, cue) in enumerate(items):
        col, row = i % 3, i // 3
        x, y = 32 + col * 220, 96 + row * 256
        o.append(rect(x, y, 200, 232, "#14181c", R_CARD, LINE))
        hx, hy = x + 100, y + 74
        o.append(hand(hx, hy, 0.9, pose))
        if cue == "ring":
            o.append(pinch_ring(hx - 22, hy - 6))
        elif cue == "arrows":
            o.append(arrows(hx, hy + 6, "h"))
        elif cue == "timer":
            o.append(timer_ring(hx, hy + 4, 62, 0.62))
        o.append(txt(x + 16, y + 178, n, 12, TEXT, 500))
        o.append(txt(x + 16, y + 198, a, 10.5, MUTED))
    o.append(txt(32, 620, "Kamera hanya menyala saat mode gestur aktif. Kerangka tidak direkam.", 10, MUTED))
    return frame(W, H, "".join(o))


def b20():
    """Four orb states. Each must be readable by silhouette, not colour alone."""
    import math as _m
    W, H = 1280, 300
    o = [txt(40, 44, "STATUS ORB", 11, MUTED, 500, track="2")]

    def arcs(cx, cy, r0, rows, col, drift=0.0):
        out = []
        for rr, span, cnt, width, alpha in rows:
            r = r0 * rr
            for a in range(cnt):
                a0 = a * (360 / cnt) + drift
                x0 = cx + r * _m.cos(_m.radians(a0)); y0 = cy - r * _m.sin(_m.radians(a0))
                x1 = cx + r * _m.cos(_m.radians(a0 + span)); y1 = cy - r * _m.sin(_m.radians(a0 + span))
                out.append(f'<path d="M{x0:.2f} {y0:.2f} A{r:.2f} {r:.2f} 0 0 0 {x1:.2f} {y1:.2f}" '
                           f'stroke="{col}" stroke-width="{width}" opacity="{alpha}" fill="none"/>')
        return "".join(out)

    # 1 Siaga: small calm orb, one thin even ring
    cx = 180
    o.append(rect(cx - 140, 76, 280, 190, "#14181c", R_PANEL, LINE_ACC))
    o.append(arcs(cx, 158, 52, ((1.0, 100, 2, 1.4, 0.45), (0.78, 60, 2, 1.2, 0.22)), CYAN))
    o.append(orb(cx, 158, 24))
    # 2 Mendengarkan: voice graduations grow outward
    cx = 490
    o.append(rect(cx - 140, 76, 280, 190, "#14181c", R_PANEL, LINE_ACC))
    o.append(arcs(cx, 158, 54, ((1.0, 96, 2, 1.6, 0.55), (0.8, 70, 4, 1.2, 0.3)), CYAN, 12))
    spikes = []
    for i in range(24):
        ang = _m.radians(i * 15)
        r0 = 34
        length = 8 + 9 * (0.5 + 0.5 * _m.sin(i * 1.4))
        spikes.append(f'M{cx + r0*_m.cos(ang):.2f} {158 - r0*_m.sin(ang):.2f} '
                      f'L{cx + (r0+length)*_m.cos(ang):.2f} {158 - (r0+length)*_m.sin(ang):.2f}')
    o.append(f'<path d="{" ".join(spikes)}" stroke="{CYAN}" stroke-width="1.8" '
             f'opacity="0.75" fill="none" stroke-linecap="round"/>')
    o.append(orb(cx, 158, 26))
    # 3 Bekerja: a single thick progress arc sweeping around a smaller orb
    cx = 800
    o.append(rect(cx - 140, 76, 280, 190, "#14181c", R_PANEL, LINE_ACC))
    o.append(f'<circle cx="{cx}" cy="158" r="56" fill="none" stroke="{LINE_ACC}" '
             f'stroke-width="1.2" opacity="0.55" stroke-dasharray="3 5"/>')
    circ = 2 * _m.pi * 56
    o.append(f'<circle cx="{cx}" cy="158" r="56" fill="none" stroke="{CYAN}" stroke-width="3" '
             f'stroke-linecap="round" stroke-dasharray="{circ*0.28:.1f} {circ:.1f}" '
             f'transform="rotate(-70 {cx} 158)"/>')
    o.append(orb(cx, 158, 20))
    # 4 Butuh perhatian: amber ring, orb dimmed, exclamation above
    cx = 1110
    o.append(rect(cx - 140, 76, 280, 190, "#14181c", R_PANEL, AMBER))
    o.append(f'<circle cx="{cx}" cy="158" r="54" fill="none" stroke="{AMBER}" '
             f'stroke-width="2" opacity="0.9"/>')
    o.append(orb(cx, 158, 20, glow=False))
    o.append(f'<path d="M{cx} 84 v12" stroke="{AMBER}" stroke-width="3.4" stroke-linecap="round"/>')
    o.append(f'<circle cx="{cx}" cy="104" r="2.6" fill="{AMBER}"/>')
    names = [("Siaga", "siap dipanggil"), ("Mendengarkan", "sedang mendengar"),
             ("Bekerja", "sedang mengerjakan"), ("Butuh perhatian", "menunggu Anda")]
    for i, (n, sub) in enumerate(names):
        cx = 180 + i * 310
        o.append(txt(cx, 232, n, 11, AMBER if i == 3 else TEXT, 500, "middle", track="1.6"))
        o.append(txt(cx, 250, sub, 10, MUTED, 400, "middle"))
    return frame(W, H, "".join(o))


def b21():
    W, H = 1280, 640
    o = [txt(40, 44, "BRAND & IKON", 11, MUTED, 500, track="2")]
    # app icon
    o.append(rect(40, 68, 160, 160, "#14181c", 34, LINE))
    o.append(orb(120, 148, 44))
    o.append(txt(40, 258, "Ikon aplikasi · 1024 px", 10.5, MUTED))
    # tray icons, 4 states
    tray = [("Siaga", CYAN, 0), ("Mendengarkan", CYAN, 1), ("Bekerja", CYAN, 2),
            ("Butuh perhatian", AMBER, 3)]
    o.append(txt(240, 68, "IKON BAKI · 4 STATUS", 10, MUTED, 500, track="2"))
    for i, (n, col, kind) in enumerate(tray):
        x = 240 + i * 120
        o.append(rect(x, 84, 88, 88, "#14181c", 20, LINE))
        cx, cy = x + 44, 128
        if kind == 0:
            o.append(f'<circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="{col}" stroke-width="2"/>')
            o.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="{col}"/>')
        elif kind == 1:
            o.append(f'<circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="{col}" stroke-width="2"/>')
            o.append(f'<path d="M{cx-5} {cy-5} v10 M{cx} {cy-8} v16 M{cx+5} {cy-4} v8" '
                     f'stroke="{col}" stroke-width="1.8" stroke-linecap="round"/>')
        elif kind == 2:
            o.append(f'<circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="{col}" '
                     f'stroke-width="2" stroke-dasharray="28 10" stroke-linecap="round"/>')
            o.append(f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="{col}"/>')
        else:
            o.append(f'<circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="{col}" stroke-width="2"/>')
            o.append(f'<path d="M{cx} {cy-6} v7" stroke="{col}" stroke-width="2.4" stroke-linecap="round"/>')
            o.append(f'<circle cx="{cx}" cy="{cy+5}" r="1.8" fill="{col}"/>')
        o.append(txt(x + 44, 194, n, 10, MUTED, 400, "middle"))
    # swatches
    o.append(txt(760, 68, "SWATCH", 10, MUTED, 500, track="2"))
    sw = [("Dasar", BASE), ("Panel", PANEL), ("Garis", LINE), ("Garis aksen", LINE_ACC),
          ("Cyan", CYAN), ("Amber", AMBER), ("Teks", TEXT), ("Teks redup", MUTED)]
    for i, (n, c) in enumerate(sw):
        x = 760 + (i % 4) * 122
        y = 84 + (i // 4) * 92
        o.append(rect(x, y, 108, 52, c, 10, LINE))
        o.append(txt(x, y + 70, n, 10, MUTED))
        o.append(txt(x, y + 84, c, 9.5, "#5E7A87", 400,
                     family="'SFMono-Regular',Consolas,monospace"))
    # light swatches
    o.append(txt(760, 300, "SWATCH TEMA TERANG", 10, MUTED, 500, track="2"))
    lsw = [("Latar", LBASE), ("Panel", LPANEL), ("Garis", LLINE), ("Aksen", LACC),
           ("Teks", LTEXT), ("Redup", LMUTED), ("Amber", LAMBER)]
    for i, (n, c) in enumerate(lsw):
        x = 760 + i * 70
        o.append(rect(x, 316, 58, 40, c, 8, LLINE))
        o.append(txt(x, 372, n, 9.5, MUTED))
    # typography
    o.append(txt(40, 330, "HURUF · SPACE GROTESK", 10, MUTED, 500, track="2"))
    o.append(txt(40, 386, "JARVIS", 46, TEXT, 700, track="1"))
    o.append(txt(40, 416, "700 · 46 px · judul", 10, MUTED))
    o.append(txt(40, 462, "Ringkas anggaran kuartal empat", 22, TEXT, 500))
    o.append(txt(40, 486, "500 · 22 px · subjudul", 10, MUTED))
    o.append(txt(40, 526, "Baris 7 dan 11 melewati plafon sebesar 12%.", 13, TEXT))
    o.append(txt(40, 546, "400 · 13 px · teks isi", 10, MUTED))
    o.append(label(40, 588, "Label kecil · 10 px · tracking 2"))
    o.append(txt(760, 420, "KOMPONEN", 10, MUTED, 500, track="2"))
    o.append(pill_btn(760, 436, 132, 40, "Jalankan"))
    o.append(pill_btn(904, 436, 132, 40, "Batal", primary=False))
    c1, w1 = chip(1048, 444, "Chip", "#0E202B", TEXT)
    o.append(c1)
    o.append(toggle(760, 496, True))
    o.append(txt(812, 512, "Toggle 40×22 · aktif", 10.5, MUTED))
    o.append(toggle(1000, 496, False))
    o.append(txt(1052, 512, "mati", 10.5, MUTED))
    o.append(seg(760, 534, ["Aktif", "Fokus"], 0, w=250, h=32))
    o.append(slider(760, 604, 200, 0.55))
    o.append(progress(1000, 604, 200, 0.72))
    o.append(txt(760, 632, "Slider & bar progres", 10, MUTED))
    o.append(txt(1040, 566, "Pil kunci pintasan", 10, MUTED))
    kb, kw = kbd(1040, 600, "Ctrl+Space")
    o.append(kb)
    kb2, kw2 = kbd(1040 + kw + 8, 600, "Esc")
    o.append(kb2)
    return frame(W, H, "".join(o))


def b22():
    W, H = 720, 480
    o = [rect(0, 0, 720, 480, BASE),
         rect(0, 0, 720, 3, CYAN, op="0.5")]
    o.append(orb(64, 60, 18))
    o.append(txt(96, 56, "JARVIS", 15, TEXT, 700, track="2"))
    o.append(txt(96, 74, "Pemasangan · langkah 1 dari 4", 10.5, MUTED))
    for i, w in enumerate((176, 176, 176, 176)):
        o.append(rect(40 + i * 172, 110, 160, 3, CYAN if i == 0 else "#13242E", 1.5))
    o.append(txt(40, 174, "Pilih cara JARVIS hadir", 26, TEXT, 700))
    opts = [("Ambient", "Orb kecil & ikon baki. Jendela hanya saat dipanggil.", True),
            ("Fokus", "Hanya panggilan keyboard, tanpa notifikasi.", False),
            ("Senyap", "Tidak menyapa sampai Anda memanggilnya.", False)]
    for i, (n, s, sel) in enumerate(opts):
        y = 200 + i * 74
        o.append(rect(40, y, 420, 62, "#101820" if sel else "#14181c", R_CARD,
                      LINE_ACC if sel else LINE))
        o.append(f'<circle cx="66" cy="{y+31}" r="8" fill="none" '
                 f'stroke="{CYAN if sel else LINE_ACC}" stroke-width="2"/>')
        if sel:
            o.append(f'<circle cx="66" cy="{y+31}" r="4" fill="{CYAN}"/>')
        o.append(txt(88, y + 26, n, 12.5, TEXT, 500))
        o.append(txt(88, y + 45, s, 10.5, MUTED))
    o.append(rect(40, 400, 420, 1, LINE))
    o.append(txt(40, 428, "Butuh ± 40 MB · berjalan di perangkat", 10, MUTED))
    o.append(pill_btn(300, 410, 160, 40, "Lanjut", primary=True))
    o.append(pill_btn(480, 410, 120, 40, "Batal", primary=False))
    o.append(txt(40, 462, "Semua izin diminta satu per satu di langkah berikutnya.", 10, MUTED))
    return frame(W, H, "".join(o))


# ── Fase 1 shell: window-behaviour artboards ───────────────────────────────
# These document the ambient shell spec: orb overlay, toast queue, command
# bar, tray panel, and the two overlays. They reuse the same tokens and the
# same component helpers as the first sheet, so the two cannot drift apart.


def clip_desk(w, h):
    """A neutral user desktop seen through a full-screen transparent overlay."""
    out = [rect(0, 0, w, h, "#0B1218")]
    out.append(doc_window(120, 74, 700, 380, "RAB Q4 · anggaran.xlsx",
                          [("h", "Ringkasan anggaran kuartal empat"),
                           ("p", "Baris item, satuan, harga, subtotal — semua terisi."),
                           ("p", "Kolom realisasi menunggu persetujuan tim keuangan.")]))
    out.append(doc_window(560, 300, 600, 300, "Catatan rapat · 19 Nov",
                          [("h", "Poin keputusan"), ("p", "Anggaran Q4 disetujui dengan catatan.")]))
    out.append(desktop_chrome(w, h))
    return "".join(out)


def orb_overlay(x, y, r, hit=True, size=None):
    """56px orb inside a click-through overlay; only the orb takes clicks."""
    ge = uid("ove")
    half = size or r * 2.6
    o = [f'<defs><radialGradient id="{ge}" cx="0.5" cy="0.5" r="0.5">'
         f'<stop offset="0.30" stop-color="{CYAN}" stop-opacity="0.26"/>'
         f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient></defs>']
    o.append(f'<rect x="{x-half}" y="{y-half}" width="{half*2}" height="{half*2}" fill="none" '
             f'stroke="{CYAN}" stroke-dasharray="5 6" stroke-width="1" opacity="0.25"/>')
    o.append(f'<circle cx="{x}" cy="{y}" r="{r*2.2}" fill="url(#{ge})"/>')
    o.append(orb(x, y, r))
    if hit:
        o.append(f'<circle cx="{x}" cy="{y}" r="{r+9}" fill="none" stroke="{CYAN}" '
                 f'stroke-width="1" stroke-dasharray="3 4" opacity="0.5"/>')
    return "".join(o)


def toast_queue(x, y, w, items, max_shown=3):
    """Stacked toasts plus a queue-depth line, because the spec caps the queue."""
    o, off = [], 0
    for title, body, acts in items[:max_shown]:
        o.append(toast(x, y + off, w, title, body, acts))
        off += (96 if acts else 74) + 12
    hidden = max(0, len(items) - max_shown)
    if hidden:
        o.append(txt(x + w, y + off - 2, f"+{hidden} lain dalam antrean", 10.5, MUTED, 400, "end"))
    return "".join(o)


def n01():
    W, H = 1280, 720
    o = [clip_desk(W, H), orb_overlay(1180, 602, 28)]
    o.append(txt(1180, 662, "Siaga", 10, MUTED, 500, "middle", track="1.6"))
    o.append(f'<path d="M1136 640 H980" stroke="{CYAN}" stroke-width="1" opacity="0.45"/>')
    o.append(txt(972, 636, "overlay ±150 px, click-through", 10, MUTED, 400, "end"))
    o.append(txt(972, 650, "WS_EX_NOACTIVATE · WS_EX_TOOLWINDOW", 9.5, "#5E7A87", 400, "end",
                 family="'SFMono-Regular',Consolas,monospace"))
    return frame(W, H, "".join(o))


def n02():
    W, H = 1280, 720
    o = [clip_desk(W, H)]
    items = [("Rapat tim dimulai 10 menit lagi",
              "Ruang Rapat 2 · 5 peserta sudah masuk", ("Buka tautan", "Tunda 5 mnt")),
             ("Anggaran Q4 disetujui", "2 baris melewati plafon, sudah ditandai", ()),
             ("Pengingat: kirim laporan Jumat", "Belum ada lampiran", ("Buka", "Nanti")),
             ("Clipboard berisi rekening", "Ditandai sensitif, tidak disalin ulang", ())]
    o.append(toast_queue(700, 330, 340, items))
    o.append(orb_overlay(1180, 602, 28))
    o.append(f'<path d="M690 420 H600" stroke="{CYAN}" stroke-width="1" opacity="0.45"/>')
    o.append(txt(592, 416, "maks. 3 tampil", 10, MUTED, 400, "end"))
    o.append(txt(592, 430, "sisanya antre", 10, MUTED, 400, "end"))
    o.append(txt(40, 56, "Hilang otomatis 8 detik · tidak pernah meminta fokus · maksimal 3 saran per hari",
                 10.5, MUTED))
    return frame(W, H, "".join(o))


def n03():
    W, H = 1280, 720
    o = [clip_desk(W, H), rect(0, 0, W, H, BASE, op="0.45")]
    bx, by, bw, bh = 320, 268, 640, 184
    g = uid("cb")
    o.append(f'<defs><linearGradient id="{g}" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="#0C1E29"/><stop offset="1" stop-color="#081319"/>'
             f'</linearGradient></defs>')
    o.append(rect(bx, by, bw, bh, f"url(#{g})", 16, LINE_ACC))
    o.append(f'<path d="M{bx+16} {by+1} h{bw-32}" stroke="{CYAN}" stroke-width="2" opacity="0.7"/>')
    o.append(txt(bx + 24, by + 46, "Buat ringkasan rapat", 18, TEXT, 500))
    o.append(rect(bx + 196, by + 30, 2, 20, CYAN))
    o.append(rect(bx + bw - 74, by + 28, 50, 22, "none", 6, LINE))
    o.append(txt(bx + bw - 49, by + 43, "Esc", 10, MUTED, 500, "middle",
                 family="'SFMono-Regular',Consolas,monospace"))
    o.append(txt(bx + 24, by + 68, "Konteks: RAB Q4 · anggaran.xlsx", 10.5, MUTED))
    o.append(rect(bx + 18, by + 82, bw - 36, 1, LINE))
    rows = (("Ringkas 14 baris terpilih", "aman · langsung", CYAN),
            ("Kirim ke tim keuangan", "berisiko · konfirmasi", AMBER),
            ("Susun jendela 2 kolom", "sedang · bisa diurungkan", MUTED))
    for i, (t, s, col) in enumerate(rows):
        yy = by + 106 + i * 26
        o.append(f'<circle cx="{bx+32}" cy="{yy-4}" r="3" fill="{col}"/>')
        o.append(txt(bx + 46, yy, t, 12, TEXT if i == 0 else "#C4D6DE", 500))
        o.append(txt(bx + bw - 26, yy, s, 10, col, 400, "end"))
    o.append(txt(bx, by - 18, "dibuka Ctrl+Space · input langsung fokus · Esc mengembalikan fokus",
                 10.5, MUTED))
    o.append(txt(bx, by + bh + 28, "Target: tampil < 150 ms setelah tombol ditekan", 10.5, CYAN))
    return frame(W, H, "".join(o))


def n04():
    W, H = 1280, 720
    o = [clip_desk(W, H), orb_overlay(1000, 520, 28, hit=False)]
    o.append(txt(1180, 470, "KLIK KIRI", 9.5, MUTED, 500, track="1.6"))
    o.append(txt(1180, 488, "buka panel baki", 10.5, TEXT))
    o.append(txt(1180, 516, "KLIK KANAN", 9.5, MUTED, 500, track="1.6"))
    o.append(txt(1180, 534, "menu cepat", 10.5, TEXT))
    o.append(txt(1180, 562, "SERET", 9.5, MUTED, 500, track="1.6"))
    o.append(txt(1180, 580, "pindah, menempel ke tepi", 10.5, TEXT))
    for cx, cy in ((990, 620), (930, 640)):
        o.append(f'<circle cx="{cx}" cy="{cy}" r="28" fill="none" stroke="{CYAN}" '
                 f'stroke-dasharray="4 5" stroke-width="1" opacity="0.3"/>')
    o.append(txt(930, 616, "posisi lain · disimpan antar sesi", 9.5, MUTED, 400, "middle"))
    o.append(txt(60, 80, "Orb 56 px. Empat status dibaca dari isi orb, bukan dari tooltip.", 11, MUTED))
    return frame(W, H, "".join(o))


def n05():
    W, H = 460, 660
    o = [rect(0, 0, W, H, PANEL, 16, LINE),
         txt(24, 34, "JARVIS", 13, TEXT, 700, track="1.4"),
         txt(24, 54, "Panel baki · mengikuti posisi taskbar", 10, MUTED)]
    o.append(seg(24, 74, ["Aktif", "Fokus", "Senyap"], 0, w=412, h=38))
    o.append(txt(24, 140, "AKSI CEPAT", 10, MUTED, 500, track="2"))
    quick = (("Tangkap layar", "Ctrl+Shift+S"), ("Dikte", "Ctrl+Win"),
             ("Cari berkas", "Ctrl+Shift+F"), ("Susun jendela", "Ctrl+Shift+J"))
    for i, (n, k) in enumerate(quick):
        y = 154 + i * 48
        o.append(rect(24, y, 412, 40, "#14181c", 10, LINE))
        o.append(txt(40, y + 25, n, 11.5, TEXT, 500))
        o.append(txt(420, y + 25, k, 9.5, MUTED, 400, "end",
                     family="'SFMono-Regular',Consolas,monospace"))
    o.append(txt(24, 366, "SARAN HARI INI", 10, MUTED, 500, track="2"))
    o.append(rect(24, 380, 412, 62, "#14181c", R_CARD, LINE))
    o.append(rect(24, 392, 3, 38, AMBER, 1.5))
    o.append(txt(44, 404, "Anggaran Q4 lewat plafon di 2 baris", 11.5, TEXT, 500))
    o.append(txt(44, 424, "Kuota saran hari ini: 2 dari 3 terpakai", 10, MUTED))
    o.append(txt(24, 478, "IZIN", 10, MUTED, 500, track="2"))
    for i, (n, v) in enumerate((("Mikrofon", True), ("Kamera", False), ("Layar", True))):
        y = 492 + i * 30
        o.append(txt(24, y + 15, n, 11.5, TEXT))
        o.append(toggle(396, y + 4, v))
    o.append(rect(24, 596, 340, 40, "#14181c", 20, LINE))
    o.append(txt(44, 621, "Tanya atau beri perintah", 11.5, MUTED))
    o.append(f'<circle cx="404" cy="616" r="18" fill="{CYAN}"/>')
    o.append(f'<path d="M398 622 l12 -12 M404 610 h8 v8" stroke="{BASE}" stroke-width="2" '
             f'fill="none" stroke-linecap="round"/>')
    return frame(W, H, "".join(o))


def n06():
    W, H = 1280, 720
    g = uid("edge")
    o = [clip_desk(W, H)]
    o.append(f'<defs><radialGradient id="{g}" cx="0.5" cy="0.5" r="0.75">'
             f'<stop offset="0.68" stop-color="{CYAN}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0.22"/></radialGradient></defs>')
    o.append(rect(0, 0, W, H, f"url(#{g})"))
    o.append(rect(0, 0, W, 2, CYAN, op="0.45"))
    o.append(rect(0, H - 2, W, 2, CYAN, op="0.45"))
    o.append(rect(0, 0, 2, H, CYAN, op="0.45"))
    o.append(rect(W - 2, 0, 2, H, CYAN, op="0.45"))
    px, py, pw, ph = 940, 40, 300, 200
    o.append(rect(px, py, pw, ph, "#071018", 12, LINE_ACC))
    o.append(txt(px + 16, py + 24, "KAMERA", 10, MUTED, 500, track="2"))
    o.append(hand(px + pw / 2, py + 112, 0.95, "pinch"))
    o.append(pinch_ring(px + pw / 2 - 21, py + 104))
    o.append(txt(40, 62, "MENDENGARKAN", 11, CYAN, 500, track="3"))
    o.append(orb(640, 300, 44))
    o.append(txt(640, 394, "“ringkas tabel ini dan tandai baris yang lewat anggaran”",
                 13, TEXT, 500, "middle"))
    o.append(txt(640, 416, "Baris 7 dan 11 melewati plafon 12% dan 4%.", 11, MUTED, 400, "middle"))
    o.append(txt(40, 690, "Glow tepi hanya saat overlay aktif · Esc keluar · Ctrl+Alt+G menjeda gestur",
                 10.5, MUTED))
    return frame(W, H, "".join(o))


# ── the registry ───────────────────────────────────────────────────────────
#
# WHY THIS REPLACED A HAND-WRITTEN LIST OF TWELVE
#     `BOARDS_LIST` used to name `n01`–`n06` and `EXTRA` `n07`–`n12`, while this
#     file defined `b01`–`b22` in full and ran none of them. The sheet shipped
#     twelve artboards while `README.md`, `DESIGN-ambient.md` and the sheet's own
#     header all claimed twenty-two, and no test noticed, because the list and
#     the functions were two independent statements of the same fact.
#
#     Now the list is DERIVED from the functions: one row per `bNN`, numbered
#     from 1 to 22, so a board cannot exist without appearing. The title is
#     prose and lives here; everything else about a board is in its function.
BOARD_TITLES = {
    1: "Desktop ambient",
    2: "Command bar",
    3: "Kontrol gestur",
    4: "Mode suara",
    5: "Panel baki sistem",
    6: "Izin & privatisasi",
    7: "Onboarding — langkah 2 dari 4",
    8: "Riwayat tugas — hari ini",
    9: "Memori personal",
    10: "Detail memori",
    11: "Rutinitas & saran",
    12: "Alat cepat, clipboard & cari berkas",
    13: "Dikte · baca layar · isi form",
    14: "Keamanan — tiga tingkat risiko",
    15: "Aksesibilitas — bahasa & gestur",
    16: "Plugin & ponsel",
    17: "Tema terang — panel baki",
    18: "Tema terang — izin & privasi",
    19: "Peta gestur",
    20: "Status orb",
    21: "Brand & ikon",
    22: "Installer — langkah 1 dari 4",
}

BOARDS_LIST = []
for _num, _title in BOARD_TITLES.items():
    _fn = globals().get(f"b{_num:02d}")
    if _fn is not None:                    # a missing one fails the test file
        BOARDS_LIST.append((_num, _title, None, None, _fn))


# ── the six states, as EXTRA VIEWS of the boards they belong to ─────────────
#
# They used to be boards 23–28, a second numbering that collided with the first
# (their 05 drew a tray panel, and `b05` draws one too). The owner's ruling on
# 2026-11-22: ONE set of numbers, 1–22, and these six fold into the board whose
# state they show. Each is still drawn — an artboard is the only way to review
# a state — but none is a board of its own, and nothing is numbered past 22.
#
# The first column is the BOARD this is a state of, as a string, because it is
# printed as "05b" beside the number and is not an integer of its own.
EXTRA = [
    # THE SIX `n01`-`n06` BOARDS. They were the first sheet's shell artboards and
    # they are NOT duplicates of `b01`-`b06`: `n03` draws the command bar the
    # implementer built (`command_paint.py` is measured against it), `n05` draws
    # the tray panel's suggestion card, and `n01`/`n02`/`n04`/`n06` draw the orb,
    # toast and overlay states. Folding them in as views is what keeps the
    # implemented surface and the picture of it on the same sheet; dropping them
    # was the mistake this table now cannot make, because
    # `tests/test_design_sheet_complete.py` asserts every `nNN` is rendered.
    #
    # The letters are pinned in this order so a label already cited in `ui/` or
    # in a test (`02a` is the command bar) cannot move when a row is added.
    ("2", "Command bar — satu baris, Esc mengembalikan fokus", 1280, 720, "n03"),
    ("1", "Orb overlay — Siaga & area klik", 1280, 720, "n01"),
    ("5", "Panel baki — saran hari ini", 460, 660, "n05"),
    ("1", "Toast — antrean & batas harian", 1280, 720, "n02"),
    ("1", "Orb overlay — interaksi & status", 1280, 720, "n04"),
    ("4", "Overlay suara + kamera gestur", 1280, 720, "n06"),
    # The six states, unchanged: Fokus, Senyap, konfirmasi risiko, riwayat,
    # izin, tema terang. Same boards, same order, same letters as before.
    ("5", "Fokus — toast ditahan", 460, 660, "n07"),
    ("5", "Senyap — orb memudar", 1280, 720, "n08"),
    ("14", "Konfirmasi (berisiko)", 1280, 720, "n09"),
    ("8", "Halaman riwayat + Urungkan", 460, 660, "n10"),
    ("6", "Halaman Izin & Privasi", 460, 660, "n11"),
    ("17", "Panel baki versi terang", 460, 660, "n12"),
]


def panel_frame(w, h, inner, bg=PANEL):
    return frame(w, h, rect(0, 0, w, h, bg, 16, LINE) + inner, bg=BASE)


def n07():
    """Fokus: notifications held, and the panel says so instead of hiding it."""
    W, H = 460, 660
    o = [txt(24, 34, "JARVIS", 13, TEXT, 700, track="1.4"),
         txt(24, 54, "Panel baki · mode Fokus", 10, MUTED),
         seg(24, 74, ["Aktif", "Fokus", "Senyap"], 1, w=412, h=38)]
    o.append(rect(24, 132, 412, 96, "#0C1B26", R_CARD, LINE_ACC))
    o.append(f'<circle cx="46" cy="162" r="5" fill="{CYAN}"/>')
    o.append(txt(62, 167, "Fokus aktif sampai 17.00", 12, TEXT, 500))
    o.append(txt(44, 192, "Toast ditahan, bukan dibuang.", 10.5, MUTED))
    o.append(txt(44, 210, "3 tertahan · akan muncul setelahnya", 10.5, MUTED))
    o.append(txt(24, 264, "AKSI CEPAT", 10, MUTED, 500, track="2"))
    quick = (("Lihat yang tertahan", "3"), ("Akhiri fokus sekarang", ""),
             ("Ubah durasi", "45 mnt"), ("Jeda semua penjadwalan", ""))
    for i, (n, k) in enumerate(quick):
        y = 278 + i * 48
        o.append(rect(24, y, 412, 40, "#14181c", 10, LINE))
        o.append(txt(40, y + 25, n, 11.5, TEXT, 500))
        o.append(txt(420, y + 25, k, 9.5, CYAN if k else MUTED, 400, "end"))
    o.append(txt(24, 490, "SARAN HARI INI", 10, MUTED, 500, track="2"))
    o.append(rect(24, 504, 412, 62, "#14181c", R_CARD, LINE))
    o.append(txt(44, 528, "Kuota saran: 1 dari 3 terpakai", 11.5, TEXT, 500))
    o.append(txt(44, 548, "Dua sisanya ditahan sampai fokus berakhir", 10, MUTED))
    o.append(rect(24, 596, 340, 40, "#14181c", 20, LINE))
    o.append(txt(44, 621, "Tanya atau beri perintah", 11.5, MUTED))
    o.append(f'<circle cx="404" cy="616" r="18" fill="{CYAN}"/>')
    o.append(f'<path d="M398 622 l12 -12 M404 610 h8 v8" stroke="{BASE}" stroke-width="2" '
             f'fill="none" stroke-linecap="round"/>')
    return frame(W, H, "".join(o))


def n08():
    """Senyap: the orb dims and loses its glow, so the state is visible without colour."""
    W, H = 1280, 720
    o = [clip_desk(W, H), rect(0, 0, W, H, BASE, op="0.35")]
    o.append(orb_overlay(1180, 602, 28, hit=False))
    o.append(f'<circle cx="1180" cy="602" r="34" fill="none" stroke="{MUTED}" '
             f'stroke-width="1" stroke-dasharray="2 7" opacity="0.6"/>')
    o.append(txt(1180, 662, "Senyap", 10, MUTED, 500, "middle", track="1.6"))
    o.append(txt(40, 70, "Senyap", 11, MUTED, 500, track="2"))
    o.append(txt(40, 96, "Orb menyusut 28 → 18 px, glow hilang,", 12, TEXT))
    o.append(txt(40, 116, "cincin berubah jadi titik-titik.", 12, TEXT))
    o.append(txt(40, 148, "Alasan: status harus terbaca tanpa warna.", 10.5, MUTED))
    return frame(W, H, "".join(o))


def n09():
    """Risk confirmation: rendered by trusted UI, never by the model."""
    W, H = 1280, 720
    o = [clip_desk(W, H), rect(0, 0, W, H, BASE, op="0.6")]
    bx, by, bw, bh = 380, 236, 520, 250
    o.append(rect(bx, by, bw, bh, "#0C1B26", 16, AMBER))
    o.append(rect(bx, by + 18, 3, bh - 36, AMBER, 1.5))
    o.append(txt(bx + 28, by + 40, "BERISIKO", 10, AMBER, 500, track="2"))
    o.append(txt(bx + 28, by + 74, "Kirim laporan ke tim keuangan", 18, TEXT, 500))
    o.append(txt(bx + 28, by + 104, "Lampiran: anggaran.xlsx · 3 penerima", 11.5, MUTED))
    o.append(txt(bx + 28, by + 126, "Tindakan ini tidak bisa diurungkan.", 11.5, MUTED))
    o.append(rect(bx + 28, by + 146, bw - 56, 1, LINE))
    o.append(txt(bx + 28, by + 172, "Asal permintaan", 10, MUTED, 500, track="1.6"))
    o.append(txt(bx + 28, by + 192, "Perintah suara · 14:31 · tercatat di audit log", 11, TEXT))
    o.append(pill_btn(bx + 28, by + 206, 150, 40, "Konfirmasi", primary=True, size=12))
    o.append(pill_btn(bx + 190, by + 206, 130, 40, "Batal", primary=False, size=12))
    o.append(txt(bx + bw - 28, by + 232, "Enter · Esc", 9.5, MUTED, 400, "end",
                 family="'SFMono-Regular',Consolas,monospace"))
    o.append(txt(bx, by - 20, "Dialog ini dirender UI tepercaya, tidak pernah oleh LLM", 10.5, AMBER))
    return frame(W, H, "".join(o))


def n10():
    W, H = 460, 660
    o = [txt(24, 34, "Riwayat tugas", 13, TEXT, 500),
         txt(24, 54, "Hari ini · 2 bisa diurungkan", 10, MUTED)]
    rows = [("Ringkas 14 baris terpilih", "09:14", "aman", "selesai", CYAN, None),
            ("Susun jendela 2 kolom", "09:02", "sedang", "bisa diurungkan", MUTED, "undo"),
            ("Kirim laporan ke tim", "08:56", "berisiko", "dibatalkan", AMBER, None),
            ("Dikte 42 kata", "08:31", "aman", "selesai", CYAN, None)]
    for i, (t, tm, risk, state, col, act) in enumerate(rows):
        y = 80 + i * 96
        o.append(rect(24, y, 412, 84, "#14181c", R_CARD, LINE))
        o.append(f'<circle cx="46" cy="{y+28}" r="4.5" fill="{col}"/>')
        o.append(txt(60, y + 32, t, 12, TEXT, 500))
        o.append(txt(60, y + 50, f"{tm}  ·  {risk}  ·  {state}", 10, MUTED))
        if act == "undo":
            o.append(pill_btn(300, y + 48, 120, 26, "Urungkan", primary=False, size=10.5))
    o.append(txt(24, 486, "AUDIT LOG", 10, MUTED, 500, track="2"))
    o.append(rect(24, 500, 412, 96, "#14181c", R_CARD, LINE))
    for i, (t, s) in enumerate((("14:31:02", "konfirmasi diminta · menunggu"),
                                ("14:31:01", "tool: send_email · risk=high"),
                                ("14:30:58", "model meminta tool call"))):
        o.append(txt(40, 522 + i * 26, t, 9.5, CYAN, 500,
                     family="'SFMono-Regular',Consolas,monospace"))
        o.append(txt(112, 522 + i * 26, s, 10.5, TEXT))
    o.append(pill_btn(24, 612, 200, 36, "Ekspor log", primary=False, size=11))
    o.append(pill_btn(236, 612, 200, 36, "Hapus riwayat", primary=False, size=11))
    return frame(W, H, "".join(o))


def n11():
    W, H = 460, 660
    o = [txt(24, 34, "Izin & Privasi", 13, TEXT, 500),
         txt(24, 54, "Semua data diproses lokal secara default", 10, MUTED),
         txt(24, 88, "INDIKATOR PRIVASI", 10, MUTED, 500, track="2")]
    for i, (n, on) in enumerate((("Mikrofon", True), ("Kamera", False), ("Layar", True))):
        x = 24 + i * 140
        o.append(rect(x, 102, 132, 62, "#14181c", R_CARD, LINE))
        o.append(f'<circle cx="{x+22}" cy="124" r="5" fill="{CYAN if on else "#25404C"}"/>')
        o.append(txt(x + 36, 128, n, 11, TEXT, 500))
        o.append(txt(x + 16, 150, "aktif" if on else "mati", 10, CYAN if on else MUTED))
    o.append(txt(24, 194, "IZIN EKSPLISIT", 10, MUTED, 500, track="2"))
    perms = (("Layar", "Melihat jendela aktif saat diminta", True),
             ("Mikrofon", "Mendengar perintah suara", True),
             ("Berkas", "Hanya folder yang dipilih", False),
             ("Kontrol aplikasi", "Menekan tombol atas nama Anda", False))
    for i, (n, sub, v) in enumerate(perms):
        y = 208 + i * 66
        o.append(rect(24, y, 412, 56, "#14181c", R_CARD, LINE))
        o.append(txt(44, y + 24, n, 12, TEXT, 500))
        o.append(txt(44, y + 42, sub, 10, MUTED))
        o.append(toggle(378, y + 17, v))
    o.append(txt(24, 486, "MODE TAMU", 10, MUTED, 500, track="2"))
    o.append(rect(24, 500, 412, 58, "#14181c", R_CARD, LINE))
    o.append(txt(44, 524, "Sembunyikan memori & riwayat", 11.5, TEXT, 500))
    o.append(txt(44, 542, "Izin diminta ulang setiap sesi", 10, MUTED))
    o.append(toggle(378, 519, False))
    o.append(txt(24, 590, "Kamera tidak pernah menyimpan atau mengirim video.", 10, MUTED))
    o.append(pill_btn(24, 610, 412, 38, "Hapus semua data lokal", primary=False, size=11.5))
    return frame(W, H, "".join(o))


def n12():
    W, H = 460, 660
    o = [rect(0, 0, W, H, LPANEL, 16, LLINE),
         txt(24, 34, "JARVIS", 13, LTEXT, 700, track="1.4"),
         txt(24, 54, "Panel baki · tema terang", 10, LMUTED)]
    o.append(light_seg(24, 74, ["Aktif", "Fokus", "Senyap"], 0, w=412, h=38))
    o.append(txt(24, 140, "AKSI CEPAT", 10, LMUTED, 500, track="2"))
    quick = (("Tangkap layar", "Ctrl+Shift+S"), ("Dikte", "Ctrl+Win"),
             ("Cari berkas", "Ctrl+Shift+F"), ("Susun jendela", "Ctrl+Shift+J"))
    for i, (n, k) in enumerate(quick):
        y = 154 + i * 48
        o.append(rect(24, y, 412, 40, "#FFFFFF", 10, LLINE))
        o.append(txt(40, y + 25, n, 11.5, LTEXT, 500))
        o.append(txt(420, y + 25, k, 9.5, LMUTED, 400, "end",
                     family="'SFMono-Regular',Consolas,monospace"))
    o.append(txt(24, 366, "SARAN HARI INI", 10, LMUTED, 500, track="2"))
    o.append(rect(24, 380, 412, 62, "#FFFFFF", R_CARD, LLINE))
    o.append(rect(24, 392, 3, 38, LAMBER, 1.5))
    o.append(txt(44, 404, "Anggaran Q4 lewat plafon di 2 baris", 11.5, LTEXT, 500))
    o.append(txt(44, 424, "Kuota saran hari ini: 2 dari 3 terpakai", 10, LMUTED))
    o.append(txt(24, 478, "IZIN", 10, LMUTED, 500, track="2"))
    for i, (n, v) in enumerate((("Mikrofon", True), ("Kamera", False), ("Layar", True))):
        y = 492 + i * 30
        o.append(txt(24, y + 15, n, 11.5, LTEXT))
        o.append(light_toggle(396, y + 4, v))
    o.append(rect(24, 596, 340, 40, "#FFFFFF", 20, LLINE))
    o.append(txt(44, 621, "Tanya atau beri perintah", 11.5, LMUTED))
    o.append(f'<circle cx="404" cy="616" r="18" fill="{LACC}"/>')
    o.append('<path d="M398 622 l12 -12 M404 610 h8 v8" stroke="#FFFFFF" stroke-width="2" '
             'fill="none" stroke-linecap="round"/>')
    return frame(W, H, "".join(o), bg=LBASE)


ASSUMPTIONS = [
    ("A1", "Orb 56 px digambar pada 1280×720 tanpa penskalaan DPI.",
     "Spesifikasi menyebut 56 px dan target sentuh 44 px; keduanya sudah terpenuhi "
     "pada 100%. Pada 150% DPI orb harus ikut token, bukan piksel tetap."),
    ("A2", "Lima jendela digambar sebagai overlay transparan di atas desktop contoh.",
     "Spesifikasi menyebut frameless/transparan/always-on-top. Desktop contoh dipakai "
     "supaya glow dan keterbacaan bisa dinilai; bukan bagian dari produk."),
    ("A3", "Toast memakai tinggi 96 px (dua tombol) atau 74 px (tanpa tombol).",
     "Spesifikasi hanya memberi angka 8 detik dan batas antrean; tinggi mengikuti isi."),
    ("A4", "Panel baki memakai 460×660, bukan 460×640.",
     "Tiga baris izin ditambah input membutuhkan 20 px tambahan; pada 640 px input "
     "menabrak baris izin terakhir."),
    ("A5", "Tingkat risiko sedang/berisiko memakai amber, bukan merah.",
     "Spesifikasi hanya menyediakan cyan dan amber. Bahaya dibedakan lewat bentuk: "
     "garis kiri 3 px, label teks, dan dialog konfirmasi terpisah."),
    ("A6", "Halaman katalog komponen (Fase 0) tidak digambar terpisah.",
     "Artboard 5, 23, 27 dan 28 sudah memuat toggle, tombol pil, chip, segmented, "
     "slider, kbd dan kartu dalam keadaan nyata; katalog statis akan menduplikasinya."),
]


def build_html():
    _uid[0] = 0
    head = """<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8">
<title>JARVIS — Shell Ambient (Tauri 2)</title>
<style>
  html,body{margin:0;background:#EEF1F4;color:#101820;
    font-family:'Space Grotesk',-apple-system,'Segoe UI',Arial,sans-serif}
  .wrap{max-width:1360px;margin:0 auto;padding:40px 28px 90px}
  h1{font-size:26px;margin:0 0 6px}
  .sub{font-size:13.5px;color:#4A5A66;max-width:80ch;line-height:1.65;margin:0 0 8px}
  .meta{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#6C7C88;
    margin:30px 0 4px;padding-top:14px;border-top:1px solid #CFD8DE}
  .ab{margin:30px 0 42px}
  .abhead{display:flex;align-items:baseline;gap:12px;margin-bottom:10px}
  .num{font-size:11px;font-weight:700;color:#1d6fe8;background:#DDEBEF;border-radius:4px;
    padding:3px 7px;letter-spacing:.08em}
  .ttl{font-size:15px;font-weight:500}
  .dim{margin-left:auto;font-size:11px;color:#7A8894;font-family:Consolas,monospace}
  .sheet{background:#0c0d11;border:1px solid #CFD8DE;border-radius:6px;overflow:auto;
    max-width:100%;line-height:0}
  .sheet svg{display:block;max-width:100%;height:auto}
  table{width:100%;border-collapse:collapse;font-size:12.5px;background:#fff;margin:10px 0 18px}
  th,td{text-align:left;padding:9px 12px;border:1px solid #D7DFE5;vertical-align:top;
    line-height:1.55}
  th{background:#E3EAEF;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}
  td.mono{font-family:Consolas,monospace;font-size:11.5px;white-space:nowrap}
  .ok{color:#0A6B3D;font-weight:700}
  .note{font-size:12.5px;line-height:1.65;background:#fff;border-left:3px solid #ff9a40;
    padding:10px 14px;margin:0 0 18px}
  h2{font-size:15px;margin:36px 0 8px;padding-bottom:8px;border-bottom:1px solid #CFD8DE}
  h3{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#4A5A66;
    margin:24px 0 6px}
</style></head><body><div class="wrap">
<h1>JARVIS — Shell Ambient</h1>
<p class="sub">Orb overlay, toast, command bar, panel baki, dan dua overlay. Semua jendela
frameless, transparan, dan selalu di atas — digambar apa adanya di atas desktop pengguna.</p>
<p class="sub" style="color:#6C7C88"><b>22 artboard</b>, bernomor 1–22 dan tidak
lebih. Enam di antaranya punya keadaan yang menentukan (Fokus, Senyap, konfirmasi
risiko, riwayat, izin, tema terang); keadaan itu digambar tepat di bawah artboard
yang bersangkutan, berlabel <code>05b</code>, <code>14b</code> dan seterusnya —
bukan sebagai artboard bernomor sendiri, karena penomoran kedua pernah ada di sini
dan bentrok dengan yang pertama.</p>
"""
    groups = [
        (1, 4, "Desktop — 1280 × 720"),
        (5, 18, "Panel baki — 460 × 640"),
        (19, 22, "Peta, orb, brand, installer"),
    ]
    # The extra views, indexed by the board they belong to, so a state is drawn
    # directly under its board rather than in a section of its own.
    views: dict[int, list] = {}
    for parent, title, w, h, fname in EXTRA:
        fn = globals().get(fname)
        if fn is not None:
            views.setdefault(int(parent), []).append((title, w, h, fn))
    body = []
    for start, end, name in groups:
        body.append(f'<div class="meta">{name}</div>')
        for num, title, w, h, fn in BOARDS_LIST:
            if start <= num <= end:
                body.append(artboard(num, title, w, h, fn()))
                for index, (vtitle, vw, vh, vfn) in enumerate(views.get(num, []), 1):
                    body.append(artboard(f"{num:02d}{chr(96 + index)}", vtitle,
                                         vw, vh, vfn()))
    rows = "".join(f'<tr><td class="mono">{k}</td><td>{v}</td><td>{r}</td></tr>'
                   for k, v, r in ASSUMPTIONS)
    summary = f"""
<div>
  <h2>Ringkasan — asumsi & alasan</h2>
  <h3>Kontras (diukur, bukan diklaim)</h3>
  <table>
    <tr><th>Pasangan</th><th class="mono">Rasio</th><th>Ambang</th></tr>
    <tr><td>Teks #ffffff pada dasar #0c0d11</td><td class="mono">17.84</td><td class="ok">lolos</td></tr>
    <tr><td>Teks #ffffff pada panel #101820</td><td class="mono">16.11</td><td class="ok">lolos</td></tr>
    <tr><td>Redup #5e636c pada panel #101820</td><td class="mono">7.35</td><td class="ok">lolos</td></tr>
    <tr><td>Cyan #3486fe pada panel #101820</td><td class="mono">10.71</td><td class="ok">lolos</td></tr>
    <tr><td>Amber #ff9a40 pada panel #101820</td><td class="mono">8.88</td><td class="ok">lolos</td></tr>
    <tr><td>Terang: #0B1A24 pada #FFFFFF</td><td class="mono">17.68</td><td class="ok">lolos</td></tr>
    <tr><td>Terang: aksen #1d6fe8 pada #FFFFFF</td><td class="mono">4.98</td><td class="ok">lolos (tipis)</td></tr>
    <tr><td>Terang: redup #5B7480 pada #F6F9FB</td><td class="mono">4.67</td><td class="ok">lolos (paling tipis)</td></tr>
  </table>
  <h3>Asumsi</h3>
  <table>
    <tr><th class="mono">#</th><th>Asumsi</th><th>Alasan</th></tr>
    {rows}
  </table>
  <h3>Yang sengaja TIDAK digambar</h3>
  <table>
    <tr><th>Hal</th><th>Sebab</th></tr>
    <tr><td>Arsitektur Rust / Tauri / SQLite</td><td>Mockup adalah visual. Struktur
      core service tidak punya wujud di layar.</td></tr>
    <tr><td>Storybook / halaman katalog</td><td>Lihat A6.</td></tr>
    <tr><td>Installer & onboarding</td><td>Sudah digambar di lembar pertama (22, 7);
      tidak diduplikasi.</td></tr>
  </table>
  <h3>Peringatan yang perlu keputusan Anda</h3>
  <p class="note">Spesifikasi ini adalah <b>aplikasi baru</b>: Tauri 2 + React + TypeScript,
  sedangkan repo ini 354 berkas Python + PyQt6 dengan <code>Cargo.toml</code> dan
  <code>package.json</code> yang tidak ada. Mockup tetap valid untuk keduanya karena murni
  visual, tetapi menulis ulang shell adalah proyek tersendiri — bukan bagian dari lembar ini
  dan tidak boleh dicampur dengan Fase 1.</p>
</div>
"""
    return head + "".join(body) + summary + "</div></body></html>"


def main():
    out = __import__("pathlib").Path(__file__).with_name("jarvis-design-system.html")
    out.write_text(build_html(), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(main())
