"""Custom-drawn outline icons (no emoji, no image assets).

Every icon is drawn into a ``tk.Canvas`` inside a square box of side ``s``
centred on ``(cx, cy)``.  All items carry ``tag`` so a widget can wipe and
redraw them when the theme changes.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable


def rounded_points(x1: float, y1: float, x2: float, y2: float, r: float) -> list[float]:
    """Polygon points for a rounded rectangle (use with smooth=True)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1,
        x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r,
        x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r,
        x1, y1,
    ]


def round_rect(c: tk.Canvas, x1, y1, x2, y2, r, **kw) -> int:
    return c.create_polygon(rounded_points(x1, y1, x2, y2, r), smooth=True, **kw)


def _line(c, pts, color, w, tag, **kw):
    return c.create_line(*pts, fill=color, width=w, capstyle="round", joinstyle="round", tags=tag, **kw)


def _box(cx, cy, s):
    return cx - s / 2, cy - s / 2


# ------------------------------------------------------------------ icons
def _dashboard(c, cx, cy, s, col, w, tag):
    x0, y0 = _box(cx, cy, s)
    g, u = s * 0.12, (s - s * 0.12 * 1) / 2 - s * 0.06
    for i in range(2):
        for j in range(2):
            a = x0 + s * 0.08 + i * (u + g)
            b = y0 + s * 0.08 + j * (u + g)
            h = u * (1.0 if (i + j) % 2 == 0 else 0.78)
            c.create_polygon(rounded_points(a, b, a + u, b + h, 2.5), smooth=True,
                             outline=col, fill="", width=w, tags=tag)


def _files(c, cx, cy, s, col, w, tag):
    x0, y0 = _box(cx, cy, s)
    l, r, t, b, f = x0 + s * .2, x0 + s * .8, y0 + s * .08, y0 + s * .92, s * .24
    _line(c, [l, t, r - f, t, r, t + f, r, b, l, b, l, t], col, w, tag)
    _line(c, [r - f, t, r - f, t + f, r, t + f], col, w, tag)
    _line(c, [l + s * .14, y0 + s * .56, r - s * .14, y0 + s * .56], col, w, tag)
    _line(c, [l + s * .14, y0 + s * .74, r - s * .26, y0 + s * .74], col, w, tag)


def _check_circle(c, cx, cy, s, col, w, tag):
    r = s * .42
    c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=w, tags=tag)
    _line(c, [cx - r * .45, cy + r * .02, cx - r * .1, cy + r * .38, cx + r * .5, cy - r * .32], col, w, tag)


def _alert(c, cx, cy, s, col, w, tag):
    top, bot, half = cy - s * .40, cy + s * .34, s * .46
    _line(c, [cx, top, cx + half, bot, cx - half, bot, cx, top], col, w, tag)
    _line(c, [cx, cy - s * .12, cx, cy + s * .1], col, w, tag)
    c.create_oval(cx - w * .6, cy + s * .2 - w * .6, cx + w * .6, cy + s * .2 + w * .6, fill=col, outline=col, tags=tag)


def _report(c, cx, cy, s, col, w, tag):
    x0, y0 = _box(cx, cy, s)
    _line(c, [x0 + s * .1, y0 + s * .1, x0 + s * .1, y0 + s * .9, x0 + s * .92, y0 + s * .9], col, w, tag)
    for i, h in enumerate((.35, .6, .45)):
        bx = x0 + s * (.28 + i * .24)
        c.create_polygon(rounded_points(bx, y0 + s * (.9 - h), bx + s * .14, y0 + s * .9, 1.5), smooth=True,
                         outline=col, fill="", width=w, tags=tag)


def _sun(c, cx, cy, s, col, w, tag):
    r = s * .2
    c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=w, tags=tag)
    for k in range(8):
        a = k * math.pi / 4
        _line(c, [cx + math.cos(a) * s * .33, cy + math.sin(a) * s * .33,
                  cx + math.cos(a) * s * .46, cy + math.sin(a) * s * .46], col, w, tag)


def _moon(c, cx, cy, s, col, w, tag):
    """Filled crescent built from the part of the big circle outside a smaller one."""
    R = s * .42
    r2 = R * .82
    dx, dy = R * .5, -R * .42
    n = 72
    outer, inner = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        px, py = math.cos(a) * R, math.sin(a) * R
        outer.append((a, px, py, math.hypot(px - dx, py - dy) >= r2))
        qx, qy = dx + math.cos(a) * r2, dy + math.sin(a) * r2
        inner.append((a, qx, qy, math.hypot(qx, qy) <= R))

    def run(items):
        start = next((i for i in range(n) if items[i][3] and not items[i - 1][3]), 0)
        seq = [items[(start + k) % n] for k in range(n)]
        out = []
        for it in seq:
            if it[3]:
                out.append((it[1], it[2]))
            elif out:
                break
        return out

    o, q = run(outer), run(inner)
    if not o or not q:
        c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=col, width=w, tags=tag)
        return
    d1 = math.hypot(o[-1][0] - q[0][0], o[-1][1] - q[0][1])
    d2 = math.hypot(o[-1][0] - q[-1][0], o[-1][1] - q[-1][1])
    if d2 < d1:
        q.reverse()
    pts = []
    for x, y in o + q:
        pts += [cx + x, cy + y]
    c.create_polygon(*pts, fill=col, outline=col, width=1, tags=tag)


def _folder(c, cx, cy, s, col, w, tag):
    x0, y0 = _box(cx, cy, s)
    _line(c, [x0 + s * .08, y0 + s * .78, x0 + s * .08, y0 + s * .22, x0 + s * .38, y0 + s * .22,
              x0 + s * .5, y0 + s * .34, x0 + s * .92, y0 + s * .34, x0 + s * .92, y0 + s * .78,
              x0 + s * .08, y0 + s * .78], col, w, tag)


def _search(c, cx, cy, s, col, w, tag):
    r = s * .26
    ox, oy = cx - s * .08, cy - s * .08
    c.create_oval(ox - r, oy - r, ox + r, oy + r, outline=col, width=w, tags=tag)
    a = math.pi / 4
    _line(c, [ox + math.cos(a) * r, oy + math.sin(a) * r, cx + s * .4, cy + s * .4], col, w, tag)


def _info(c, cx, cy, s, col, w, tag):
    r = s * .42
    c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=w, tags=tag)
    _line(c, [cx, cy - s * .02, cx, cy + s * .2], col, w, tag)
    c.create_oval(cx - w * .6, cy - s * .2 - w * .6, cx + w * .6, cy - s * .2 + w * .6, fill=col, outline=col, tags=tag)


def _scan(c, cx, cy, s, col, w, tag):
    x0, y0 = _box(cx, cy, s)
    k, m = s * .26, s * .1
    for sx, sy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        px = x0 + m + sx * (s - 2 * m)
        py = y0 + m + sy * (s - 2 * m)
        dx, dy = (k if sx == 0 else -k), (k if sy == 0 else -k)
        _line(c, [px + dx, py, px, py, px, py + dy], col, w, tag)
    _line(c, [x0 + s * .24, cy, x0 + s * .76, cy], col, w, tag)


def _download(c, cx, cy, s, col, w, tag):
    x0, y0 = _box(cx, cy, s)
    _line(c, [cx, y0 + s * .12, cx, y0 + s * .62], col, w, tag)
    _line(c, [cx - s * .2, y0 + s * .44, cx, y0 + s * .66, cx + s * .2, y0 + s * .44], col, w, tag)
    _line(c, [x0 + s * .14, y0 + s * .72, x0 + s * .14, y0 + s * .88, x0 + s * .86, y0 + s * .88,
              x0 + s * .86, y0 + s * .72], col, w, tag)


def _close(c, cx, cy, s, col, w, tag):
    d = s * .26
    _line(c, [cx - d, cy - d, cx + d, cy + d], col, w, tag)
    _line(c, [cx - d, cy + d, cx + d, cy - d], col, w, tag)


def _arrow(c, cx, cy, s, col, w, tag):
    _line(c, [cx - s * .3, cy, cx + s * .3, cy], col, w, tag)
    _line(c, [cx + s * .1, cy - s * .2, cx + s * .3, cy, cx + s * .1, cy + s * .2], col, w, tag)


def _guitar_glyph(c, cx, cy, s, col, w, tag, hole=None):
    """Filled guitar silhouette, rotated 45 degrees (neck towards the top right)."""
    u = (math.cos(-math.pi / 4), math.sin(-math.pi / 4))
    n = (-u[1], u[0])

    def P(t, d=0.0):
        return cx + (u[0] * t + n[0] * d) * s, cy + (u[1] * t + n[1] * d) * s

    def disc(t, r):
        x, y = P(t)
        c.create_oval(x - r * s, y - r * s, x + r * s, y + r * s, fill=col, outline=col, tags=tag)

    disc(-0.20, 0.215)       # lower bout
    disc(0.0, 0.155)         # upper bout
    x1, y1 = P(0.02)
    x2, y2 = P(0.40)
    c.create_line(x1, y1, x2, y2, fill=col, width=max(2.0, s * .085), capstyle="butt", tags=tag)
    head = [P(0.38, -0.075), P(0.38, 0.075), P(0.50, 0.085), P(0.50, -0.065)]
    c.create_polygon(*[v for p in head for v in p], fill=col, outline=col, tags=tag)
    hx, hy = P(-0.16)
    rr = s * .06
    c.create_oval(hx - rr, hy - rr, hx + rr, hy + rr, fill=hole or "", outline=hole or col, width=1, tags=tag)


ICONS: dict[str, Callable] = {
    "dashboard": _dashboard, "files": _files, "match": _check_circle, "problems": _alert,
    "reports": _report, "sun": _sun, "moon": _moon, "folder": _folder, "search": _search,
    "info": _info, "scan": _scan, "download": _download, "close": _close, "arrow": _arrow,
    "guitar": _guitar_glyph,
}


def draw_icon(c: tk.Canvas, name: str, cx: float, cy: float, size: float, color: str,
              width: float = 1.7, tag: str = "icon", **kw) -> None:
    fn = ICONS[name]
    if name == "guitar":
        fn(c, cx, cy, size, color, width, tag, **kw)
    else:
        fn(c, cx, cy, size, color, width, tag)


def draw_logo(c: tk.Canvas, cx: float, cy: float, size: float, badge: str, glyph: str,
              tag: str = "logo") -> None:
    """The Guitar app mark: a violet rounded badge with a white guitar silhouette."""
    h = size / 2
    round_rect(c, cx - h, cy - h, cx + h, cy + h, size * .28, fill=badge, outline="", tags=tag)
    draw_icon(c, "guitar", cx, cy + size * .02, size * .86, glyph, tag=tag, hole=badge)


def make_app_icon(root, size: int = 64) -> tk.PhotoImage:
    """Small window icon rendered pixel by pixel (no external assets)."""
    img = tk.PhotoImage(master=root, width=size, height=size)
    s = float(size)
    u = (math.cos(-math.pi / 4), math.sin(-math.pi / 4))
    n = (-u[1], u[0])
    bg, fg = "#8B5CF6", "#FFFFFF"
    rows = []
    r_c = s * .28
    for y in range(size):
        row = []
        for x in range(size):
            px, py = x + .5, y + .5
            dx, dy = abs(px - s / 2) - (s / 2 - r_c), abs(py - s / 2) - (s / 2 - r_c)
            inside = (max(dx, 0) ** 2 + max(dy, 0) ** 2) ** .5 <= r_c if (dx > 0 and dy > 0) else (dx <= r_c and dy <= r_c)
            if not inside:
                row.append("#100C19")
                continue
            rx, ry = (px - s / 2) / (s * .86), (py - s / 2 - s * .02) / (s * .86)
            t = rx * u[0] + ry * u[1]
            d = rx * n[0] + ry * n[1]
            hit = ((t + .20) ** 2 + d ** 2 <= .215 ** 2) or (t ** 2 + d ** 2 <= .155 ** 2) \
                or (.02 <= t <= .40 and abs(d) <= .045) or (.38 <= t <= .50 and abs(d) <= .08)
            hole = ((t + .16) ** 2 + d ** 2) <= .06 ** 2
            row.append(bg if hole else (fg if hit else bg))
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    return img
