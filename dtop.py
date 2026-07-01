#!/usr/bin/env python3
"""
dtop - a btop-styled TUI to monitor and manage Docker containers.

Pure Python standard library. No third-party dependencies.
24-bit truecolor, braille graphs, rounded boxes, diff rendering.

Keys:
  Navigation : Up/Down j/k   PgUp/PgDn   Home/End g/G
  Sort       : o cycle field  O reverse
  View       : a all/running  / filter    i inspect   l/Enter logs
  Actions    : S start  T stop  R restart  P pause/unpause  K kill  D remove
  Misc       : ? help    q quit
"""

import os
import re
import sys
import json
import time
import select
import signal
import subprocess
import threading
import collections

__version__ = "0.1.0"

# ----------------------------------------------------------------------------
# Terminal helpers
# ----------------------------------------------------------------------------
try:
    import termios
    import tty
    HAVE_TTY = True
except ImportError:  # pragma: no cover
    HAVE_TTY = False

ESC = "\x1b"
CSI = ESC + "["
ALT_ON = CSI + "?1049h"
ALT_OFF = CSI + "?1049l"
CUR_HIDE = CSI + "?25l"
CUR_SHOW = CSI + "?25h"
CLEAR = CSI + "2J" + CSI + "H"
RESET = CSI + "0m"

HIST = 300  # history samples kept per metric


# ----------------------------------------------------------------------------
# Themes (btop-inspired). Each metric gets its own start->mid->end gradient,
# and each box a distinct title hue, for that high-contrast btop look.
# ----------------------------------------------------------------------------
# keys:
#   bg fg dim faint box border sel_bg sel_fg ok warn bad info accent title hdr
#   g_cpu g_mem g_down g_up      each = (start, mid, end)
THEMES = {
    "btop": {
        "bg": (0x0a, 0x0c, 0x12), "fg": (0xcc, 0xd2, 0xde),
        "dim": (0x71, 0x79, 0x8d), "faint": (0x2c, 0x33, 0x44),
        "box": (0x2f, 0x37, 0x49), "sel_bg": (0x1d, 0x33, 0x50),
        "sel_fg": (0xff, 0xff, 0xff), "accent": (0x66, 0xd9, 0xef),
        "title": (0x69, 0xf0, 0xb0), "hdr": (0x8f, 0xb8, 0xff),
        "ok": (0x4f, 0xe3, 0x7a), "warn": (0xf7, 0xd7, 0x3e),
        "bad": (0xff, 0x53, 0x4a), "info": (0x74, 0xc0, 0xff),
        "g_cpu": ((0x1e, 0xd7, 0x60), (0xf6, 0xd7, 0x32), (0xff, 0x38, 0x38)),
        "g_mem": ((0x2a, 0xd0, 0xc8), (0x53, 0x9b, 0xf6), (0xc9, 0x6a, 0xf2)),
        "g_down": ((0x2f, 0x6f, 0xd6), (0x5b, 0xc8, 0xff), (0x9d, 0xf0, 0xff)),
        "g_up": ((0xf0, 0x9a, 0x3a), (0xf7, 0x63, 0x5b), (0xff, 0x46, 0x8a)),
    },
    "gruvbox": {
        "bg": (0x1d, 0x20, 0x21), "fg": (0xeb, 0xdb, 0xb2),
        "dim": (0x92, 0x83, 0x74), "faint": (0x3c, 0x38, 0x36),
        "box": (0x50, 0x49, 0x45), "sel_bg": (0x3c, 0x38, 0x36),
        "sel_fg": (0xfb, 0xf1, 0xc7), "accent": (0x83, 0xa5, 0x98),
        "title": (0xb8, 0xbb, 0x26), "hdr": (0xfa, 0xbd, 0x2f),
        "ok": (0xb8, 0xbb, 0x26), "warn": (0xfa, 0xbd, 0x2f),
        "bad": (0xfb, 0x49, 0x34), "info": (0x83, 0xa5, 0x98),
        "g_cpu": ((0xb8, 0xbb, 0x26), (0xfa, 0xbd, 0x2f), (0xfb, 0x49, 0x34)),
        "g_mem": ((0x8e, 0xc0, 0x7c), (0x83, 0xa5, 0x98), (0xd3, 0x86, 0x9b)),
        "g_down": ((0x45, 0x85, 0x88), (0x83, 0xa5, 0x98), (0x8e, 0xc0, 0x7c)),
        "g_up": ((0xd6, 0x5d, 0x0e), (0xfe, 0x80, 0x19), (0xfb, 0x49, 0x34)),
    },
    "dracula": {
        "bg": (0x21, 0x22, 0x2c), "fg": (0xf8, 0xf8, 0xf2),
        "dim": (0x62, 0x72, 0xa4), "faint": (0x38, 0x3a, 0x4a),
        "box": (0x44, 0x47, 0x5a), "sel_bg": (0x44, 0x47, 0x5a),
        "sel_fg": (0xf8, 0xf8, 0xf2), "accent": (0x8b, 0xe9, 0xfd),
        "title": (0x50, 0xfa, 0x7b), "hdr": (0xbd, 0x93, 0xf9),
        "ok": (0x50, 0xfa, 0x7b), "warn": (0xf1, 0xfa, 0x8c),
        "bad": (0xff, 0x55, 0x55), "info": (0x8b, 0xe9, 0xfd),
        "g_cpu": ((0x50, 0xfa, 0x7b), (0xf1, 0xfa, 0x8c), (0xff, 0x55, 0x55)),
        "g_mem": ((0x8b, 0xe9, 0xfd), (0xbd, 0x93, 0xf9), (0xff, 0x79, 0xc6)),
        "g_down": ((0x62, 0x72, 0xa4), (0x8b, 0xe9, 0xfd), (0xf8, 0xf8, 0xf2)),
        "g_up": ((0xff, 0xb8, 0x6c), (0xff, 0x79, 0xc6), (0xff, 0x55, 0x55)),
    },
    "nord": {
        "bg": (0x2e, 0x34, 0x40), "fg": (0xe5, 0xe9, 0xf0),
        "dim": (0x7b, 0x88, 0x94), "faint": (0x3b, 0x42, 0x52),
        "box": (0x43, 0x4c, 0x5e), "sel_bg": (0x3b, 0x42, 0x52),
        "sel_fg": (0xec, 0xef, 0xf4), "accent": (0x88, 0xc0, 0xd0),
        "title": (0xa3, 0xbe, 0x8c), "hdr": (0x81, 0xa1, 0xc1),
        "ok": (0xa3, 0xbe, 0x8c), "warn": (0xeb, 0xcb, 0x8b),
        "bad": (0xbf, 0x61, 0x6a), "info": (0x88, 0xc0, 0xd0),
        "g_cpu": ((0xa3, 0xbe, 0x8c), (0xeb, 0xcb, 0x8b), (0xbf, 0x61, 0x6a)),
        "g_mem": ((0x8f, 0xbc, 0xbb), (0x81, 0xa1, 0xc1), (0xb4, 0x8e, 0xad)),
        "g_down": ((0x5e, 0x81, 0xac), (0x88, 0xc0, 0xd0), (0x8f, 0xbc, 0xbb)),
        "g_up": ((0xd0, 0x87, 0x70), (0xeb, 0xcb, 0x8b), (0xbf, 0x61, 0x6a)),
    },
    "tokyo-night": {
        "bg": (0x1a, 0x1b, 0x26), "fg": (0xc0, 0xca, 0xf5),
        "dim": (0x56, 0x5f, 0x89), "faint": (0x2a, 0x2e, 0x42),
        "box": (0x30, 0x35, 0x4f), "sel_bg": (0x28, 0x33, 0x57),
        "sel_fg": (0xc0, 0xca, 0xf5), "accent": (0x7d, 0xcf, 0xff),
        "title": (0x9e, 0xce, 0x6a), "hdr": (0x7a, 0xa2, 0xf7),
        "ok": (0x9e, 0xce, 0x6a), "warn": (0xe0, 0xaf, 0x68),
        "bad": (0xf7, 0x76, 0x8e), "info": (0x7d, 0xcf, 0xff),
        "g_cpu": ((0x9e, 0xce, 0x6a), (0xe0, 0xaf, 0x68), (0xf7, 0x76, 0x8e)),
        "g_mem": ((0x2a, 0xc3, 0xde), (0x7a, 0xa2, 0xf7), (0xbb, 0x9a, 0xf7)),
        "g_down": ((0x3d, 0x59, 0xa1), (0x7a, 0xa2, 0xf7), (0x7d, 0xcf, 0xff)),
        "g_up": ((0xff, 0x9e, 0x64), (0xf7, 0x76, 0x8e), (0xbb, 0x9a, 0xf7)),
    },
    "matrix": {
        "bg": (0x00, 0x08, 0x02), "fg": (0x3a, 0xf0, 0x62),
        "dim": (0x1f, 0x9e, 0x3f), "faint": (0x0c, 0x3d, 0x1a),
        "box": (0x15, 0x63, 0x2c), "sel_bg": (0x0c, 0x3d, 0x1a),
        "sel_fg": (0xd7, 0xff, 0xe0), "accent": (0x8f, 0xff, 0xa8),
        "title": (0x8f, 0xff, 0xa8), "hdr": (0x5a, 0xff, 0x82),
        "ok": (0x3a, 0xf0, 0x62), "warn": (0xd7, 0xff, 0x8f),
        "bad": (0xff, 0x99, 0x66), "info": (0x8f, 0xff, 0xa8),
        "g_cpu": ((0x0f, 0x8a, 0x2f), (0x33, 0xff, 0x66), (0xc9, 0xff, 0xd4)),
        "g_mem": ((0x0f, 0x8a, 0x2f), (0x33, 0xff, 0x66), (0xc9, 0xff, 0xd4)),
        "g_down": ((0x0f, 0x8a, 0x2f), (0x33, 0xff, 0x66), (0xc9, 0xff, 0xd4)),
        "g_up": ((0x0f, 0x8a, 0x2f), (0x33, 0xff, 0x66), (0xc9, 0xff, 0xd4)),
    },
}
THEME_ORDER = ["btop", "gruvbox", "dracula", "nord", "tokyo-night", "matrix"]


def _stops(triple):
    """(start, mid, end) -> a 4-point stop list with an extra hot top stop."""
    s, m, e = triple
    return [(0.0, s), (0.5, m), (1.0, e)]


class Theme:
    """Holds the *current* theme. set_theme() swaps these in place."""
    name = "btop"


def set_theme(name):
    if name not in THEMES:
        name = "btop"
    t = THEMES[name]
    Theme.name = name
    for k in ("bg", "fg", "dim", "faint", "box", "sel_bg", "sel_fg",
              "accent", "title", "hdr", "ok", "warn", "bad", "info"):
        setattr(Theme, k, t[k])
    Theme.paused = t["warn"]
    Theme.box_hi = t["accent"]
    Theme.g_cpu = _stops(t["g_cpu"])
    Theme.g_mem = _stops(t["g_mem"])
    Theme.g_down = _stops(t["g_down"])
    Theme.g_up = _stops(t["g_up"])
    Theme.grad = Theme.g_cpu          # default gradient
    Theme.net_grad = Theme.g_down
    # per-box title hues = the vivid mid of each metric gradient
    Theme.c_cpu = t["g_cpu"][1]
    Theme.c_mem = t["g_mem"][1]
    Theme.c_net = t["g_down"][1]
    Theme.c_proc = t["g_up"][1]


def blend(a, b, f):
    """Mix color a toward b by fraction f (0..1)."""
    return (int(a[0] + (b[0] - a[0]) * f),
            int(a[1] + (b[1] - a[1]) * f),
            int(a[2] + (b[2] - a[2]) * f))


def gradient(t, stops=None):
    if stops is None:
        stops = Theme.grad
    if t <= 0:
        return stops[0][1]
    if t >= 1:
        return stops[-1][1]
    for i in range(1, len(stops)):
        p0, c0 = stops[i - 1]
        p1, c1 = stops[i]
        if t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0
            return (int(c0[0] + (c1[0] - c0[0]) * f),
                    int(c0[1] + (c1[1] - c0[1]) * f),
                    int(c0[2] + (c1[2] - c0[2]) * f))
    return stops[-1][1]


set_theme("btop")


CONFIG_PATH = os.path.expanduser("~/.config/dtop/config")


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                if line.startswith("theme=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def save_config(theme):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            f.write(f"theme={theme}\n")
    except OSError:
        pass


# ----------------------------------------------------------------------------
# Screen buffer with diff rendering
# ----------------------------------------------------------------------------
class Screen:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.ch = [[' '] * w for _ in range(h)]
        self.fgc = [[None] * w for _ in range(h)]
        self.bgc = [[None] * w for _ in range(h)]
        self.at = [[0] * w for _ in range(h)]
        self.clip = (0, 0, w - 1, h - 1)

    def put(self, x, y, text, fg=None, bg=None, attr=0, maxx=None):
        cx0, cy0, cx1, cy1 = self.clip
        if y < cy0 or y > cy1:
            return
        limit = cx1 + 1 if maxx is None else min(cx1 + 1, maxx)
        for c in text:
            cw = char_width(c)
            if cw == 0:
                continue
            if x + cw - 1 >= limit:
                break
            if x >= cx0:
                self.ch[y][x] = c
                self.fgc[y][x] = fg
                self.bgc[y][x] = bg
                self.at[y][x] = attr
                if cw == 2 and x + 1 <= cx1:
                    self.ch[y][x + 1] = WIDE_CONT
                    self.fgc[y][x + 1] = fg
                    self.bgc[y][x + 1] = bg
                    self.at[y][x + 1] = attr
            x += cw

    def set_clip(self, x, y, w, h):
        self.clip = (max(0, x), max(0, y),
                     min(self.w - 1, x + w - 1), min(self.h - 1, y + h - 1))

    def reset_clip(self):
        self.clip = (0, 0, self.w - 1, self.h - 1)

    def cell(self, x, y, c, fg=None, bg=None, attr=0):
        cx0, cy0, cx1, cy1 = self.clip
        if cx0 <= x <= cx1 and cy0 <= y <= cy1:
            self.ch[y][x] = c
            self.fgc[y][x] = fg
            self.bgc[y][x] = bg
            self.at[y][x] = attr

    def hline(self, x, y, w, ch, fg=None, bg=None):
        for i in range(w):
            self.cell(x + i, y, ch, fg, bg)

    def fill_bg(self, x, y, w, h, bg):
        cx0, cy0, cx1, cy1 = self.clip
        for j in range(h):
            for i in range(w):
                px, py = x + i, y + j
                if cx0 <= px <= cx1 and cy0 <= py <= cy1:
                    self.bgc[py][px] = bg

    def clear_region(self, x, y, w, h, bg=None, fg=None):
        """Blank out a rectangle: chars, fg, attr AND bg (opaque)."""
        for j in range(h):
            for i in range(w):
                self.cell(x + i, y + j, ' ', fg, bg, 0)

    def diff(self, prev):
        out = []
        lastx = lasty = -9
        cfg = cbg = cat = "INIT"
        for y in range(self.h):
            row = self.ch[y]
            for x in range(self.w):
                c = row[x]
                if c == WIDE_CONT:      # right half of a wide glyph: don't emit
                    continue
                fgv = self.fgc[y][x]
                bgv = self.bgc[y][x]
                atv = self.at[y][x]
                if prev is not None:
                    if (c == prev.ch[y][x] and fgv == prev.fgc[y][x]
                            and bgv == prev.bgc[y][x] and atv == prev.at[y][x]):
                        continue
                if not (y == lasty and x == lastx + 1):
                    out.append(f"{CSI}{y + 1};{x + 1}H")
                rfg = fgv if fgv else Theme.fg
                rbg = bgv if bgv else Theme.bg
                if (rfg, rbg, atv) != (cfg, cbg, cat):
                    seq = CSI + "0m"
                    if atv & 1:
                        seq += CSI + "1m"
                    if atv & 2:
                        seq += CSI + "2m"
                    seq += f"{CSI}38;2;{rfg[0]};{rfg[1]};{rfg[2]}m"
                    seq += f"{CSI}48;2;{rbg[0]};{rbg[1]};{rbg[2]}m"
                    out.append(seq)
                    cfg, cbg, cat = rfg, rbg, atv
                out.append(c)
                lastx, lasty = x, y
        return "".join(out)

    def to_lines(self):
        lines = []
        for y in range(self.h):
            parts = []
            cfg = cbg = cat = "INIT"
            for x in range(self.w):
                if self.ch[y][x] == WIDE_CONT:
                    continue
                fgv, bgv, atv = self.fgc[y][x], self.bgc[y][x], self.at[y][x]
                rfg = fgv if fgv else Theme.fg
                rbg = bgv if bgv else Theme.bg
                if (rfg, rbg, atv) != (cfg, cbg, cat):
                    seq = CSI + "0m"
                    if atv & 1:
                        seq += CSI + "1m"
                    if atv & 2:
                        seq += CSI + "2m"
                    seq += f"{CSI}38;2;{rfg[0]};{rfg[1]};{rfg[2]}m"
                    seq += f"{CSI}48;2;{rbg[0]};{rbg[1]};{rbg[2]}m"
                    parts.append(seq)
                    cfg, cbg, cat = rfg, rbg, atv
                parts.append(self.ch[y][x])
            parts.append(RESET)
            lines.append("".join(parts))
        return lines


# ----------------------------------------------------------------------------
# Drawing primitives
# ----------------------------------------------------------------------------
BOX = {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"}


def draw_box(scr, x, y, w, h, title="", color=None, tcolor=None,
             right=""):
    if w < 2 or h < 2:
        return
    if color is None:
        color = Theme.box
    if tcolor is None:
        tcolor = Theme.title
    scr.cell(x, y, BOX["tl"], color)
    scr.cell(x + w - 1, y, BOX["tr"], color)
    scr.cell(x, y + h - 1, BOX["bl"], color)
    scr.cell(x + w - 1, y + h - 1, BOX["br"], color)
    for i in range(1, w - 1):
        scr.cell(x + i, y, BOX["h"], color)
        scr.cell(x + i, y + h - 1, BOX["h"], color)
    for j in range(1, h - 1):
        scr.cell(x, y + j, BOX["v"], color)
        scr.cell(x + w - 1, y + j, BOX["v"], color)
    if title:
        t = f" {title} "
        scr.put(x + 2, y, t[:max(0, w - 4)], tcolor, attr=1)
    if right:
        rt = f" {right} "
        rx = x + w - 2 - len(rt)
        if rx > x + 2:
            scr.put(rx, y, rt, Theme.dim)


# braille dot bit values, columns: left rows 1,2,3,7 ; right rows 4,5,6,8
BR_LEFT = [0x01, 0x02, 0x04, 0x40]
BR_RIGHT = [0x08, 0x10, 0x20, 0x80]


def braille_graph(scr, x, y, w, h, series, maxval, stops=None,
                  bg=None):
    """Render a braille line/area graph into region (x,y,w,h)."""
    if w <= 0 or h <= 0:
        return
    if stops is None:
        stops = Theme.grad
    cols = w * 2
    rows = h * 4
    data = list(series)[-cols:]
    if len(data) < cols:
        data = [0.0] * (cols - len(data)) + data
    mv = maxval if maxval and maxval > 0 else 1.0
    # dot heights per column
    heights = []
    for v in data:
        f = v / mv
        if f < 0:
            f = 0
        if f > 1:
            f = 1
        heights.append(int(round(f * rows)))
    for cy in range(h):
        for cx in range(w):
            lc = cx * 2
            rc = cx * 2 + 1
            bits = 0
            top_filled = -1
            for r in range(4):
                dot_row = cy * 4 + r  # 0 = top
                dot_from_bottom = rows - 1 - dot_row
                if lc < cols and heights[lc] > dot_from_bottom:
                    bits |= BR_LEFT[r]
                if rc < cols and heights[rc] > dot_from_bottom:
                    bits |= BR_RIGHT[r]
            if bits:
                # color by vertical position in whole graph (flame look)
                vpos = 1.0 - (cy * 4) / max(1, rows - 1)
                col = gradient(vpos, stops)
                scr.cell(x + cx, y + cy, chr(0x2800 + bits), col, bg)
            elif bg is not None:
                scr.cell(x + cx, y + cy, ' ', None, bg)


BLOCKS = [' ', '▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']


def meter(scr, x, y, w, frac, stops=None, empty=None, bg=None):
    """Horizontal gradient meter bar of width w."""
    if w <= 0:
        return
    if stops is None:
        stops = Theme.grad
    if empty is None:
        empty = Theme.faint
    frac = max(0.0, min(1.0, frac))
    filled = frac * w
    full = int(filled)
    for i in range(w):
        t = (i + 0.5) / w
        if i < full:
            scr.cell(x + i, y, '█', gradient(t, stops), bg)
        elif i == full:
            rem = filled - full
            idx = int(rem * 8)
            if idx > 0:
                scr.cell(x + i, y, BLOCKS[idx], gradient(t, stops), bg)
            else:
                scr.cell(x + i, y, '─', empty, bg)
        else:
            scr.cell(x + i, y, '─', empty, bg)


def braille_spark(scr, x, y, w, series, maxval, stops=None, bg=None,
                  color_max=None):
    """One-row braille sparkline: 2 samples & 4 levels per cell.
    Height is scaled to `maxval` (pass a per-row peak to show shape);
    color is scaled to `color_max` (pass absolute capacity to show load).
    A faint baseline is drawn where the value is ~0."""
    if w <= 0:
        return
    if stops is None:
        stops = Theme.grad
    cols = w * 2
    data = list(series)[-cols:]
    if len(data) < cols:
        data = [0.0] * (cols - len(data)) + data
    mv = maxval if maxval and maxval > 0 else 1.0
    cmv = color_max if color_max and color_max > 0 else mv
    for cx in range(w):
        rawl = data[cx * 2]
        rawr = data[cx * 2 + 1]
        vl = max(0.0, min(1.0, rawl / mv))
        vr = max(0.0, min(1.0, rawr / mv))
        cv = max(0.0, min(1.0, max(rawl, rawr) / cmv))
        hl = int(round(vl * 4))
        hr = int(round(vr * 4))
        bits = 0
        for r in range(4):
            if (3 - r) < hl:
                bits |= BR_LEFT[r]
            if (3 - r) < hr:
                bits |= BR_RIGHT[r]
        if bits:
            scr.cell(x + cx, y, chr(0x2800 + bits), gradient(cv, stops), bg)
        else:
            scr.cell(x + cx, y, '⣀', Theme.faint, bg)  # baseline


# ----------------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------------
_UNITS = {'B': 1, 'kB': 1e3, 'KB': 1e3, 'MB': 1e6, 'GB': 1e9, 'TB': 1e12,
          'PB': 1e15, 'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3,
          'TiB': 1024**4, 'kiB': 1024}

_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][A-Za-z0-9]')


def clean_line(s):
    """Strip ANSI escapes, expand tabs and drop control chars so raw log
    output can't corrupt the screen buffer or spill past a panel."""
    s = _ANSI_RE.sub('', s).expandtabs(4)
    return ''.join(ch if ch >= ' ' else ' ' for ch in s)


# ranges of Unicode code points rendered two terminal columns wide
_WIDE_RANGES = (
    (0x1100, 0x115F), (0x2329, 0x232A), (0x2E80, 0x303E), (0x3041, 0x33FF),
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xA000, 0xA4CF), (0xAC00, 0xD7A3),
    (0xF900, 0xFAFF), (0xFE10, 0xFE19), (0xFE30, 0xFE6F), (0xFF00, 0xFF60),
    (0xFFE0, 0xFFE6), (0x1F000, 0x1FAFF), (0x20000, 0x3FFFD),
)
_ZERO_RANGES = ((0x0300, 0x036F), (0x200B, 0x200F), (0xFE00, 0xFE0F))
WIDE_CONT = '\x00'   # sentinel: right half of a double-width cell


def char_width(ch):
    cp = ord(ch)
    if cp < 0x300:            # ASCII + Latin-1: always single width
        return 1
    for lo, hi in _ZERO_RANGES:
        if lo <= cp <= hi:
            return 0
    for lo, hi in _WIDE_RANGES:
        if lo <= cp <= hi:
            return 2
    return 1


def parse_size(s):
    if not s:
        return 0.0
    m = re.match(r'\s*([0-9.]+)\s*([A-Za-z]+)', s)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    return val * _UNITS.get(unit, 1)


def parse_pair(s):
    if not s or '/' not in s:
        return 0.0, 0.0
    a, b = s.split('/', 1)
    return parse_size(a), parse_size(b)


def parse_pct(s):
    try:
        return float(s.replace('%', '').strip())
    except (ValueError, AttributeError):
        return 0.0


def human_bytes(n):
    n = float(n)
    for unit in ('B', 'K', 'M', 'G', 'T', 'P'):
        if abs(n) < 1024.0:
            if unit == 'B':
                return f"{int(n)}{unit}"
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}E"


def human_rate(n):
    return human_bytes(n) + "/s"


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------
class Container:
    def __init__(self, cid):
        self.id = cid
        self.name = ""
        self.image = ""
        self.state = ""
        self.status = ""
        self.command = ""
        self.ports = ""
        self.created = ""
        self.networks = ""
        self.health = ""
        self.compose = ""
        # live stats
        self.cpu = 0.0
        self.mem_pct = 0.0
        self.mem_used = 0.0
        self.mem_limit = 0.0
        self.pids = 0
        self.net_rx = 0.0
        self.net_tx = 0.0
        self.blk_r = 0.0
        self.blk_w = 0.0
        self.net_rx_rate = 0.0
        self.net_tx_rate = 0.0
        self.blk_r_rate = 0.0
        self.blk_w_rate = 0.0
        self._prev_net = None
        self._prev_blk = None
        self._prev_t = None
        self.have_stats = False
        self.cpu_h = collections.deque(maxlen=HIST)
        self.mem_h = collections.deque(maxlen=HIST)
        self.rx_h = collections.deque(maxlen=HIST)
        self.tx_h = collections.deque(maxlen=HIST)

    def update_stats(self, d, now):
        self.cpu = parse_pct(d.get("CPUPerc", "0"))
        self.mem_pct = parse_pct(d.get("MemPerc", "0"))
        self.mem_used, self.mem_limit = parse_pair(d.get("MemUsage", ""))
        try:
            self.pids = int(d.get("PIDs", "0"))
        except ValueError:
            self.pids = 0
        rx, tx = parse_pair(d.get("NetIO", ""))
        br, bw = parse_pair(d.get("BlockIO", ""))
        if self._prev_t is not None:
            dt = now - self._prev_t
            if dt > 0:
                self.net_rx_rate = max(0.0, (rx - self._prev_net[0]) / dt)
                self.net_tx_rate = max(0.0, (tx - self._prev_net[1]) / dt)
                self.blk_r_rate = max(0.0, (br - self._prev_blk[0]) / dt)
                self.blk_w_rate = max(0.0, (bw - self._prev_blk[1]) / dt)
        self.net_rx, self.net_tx = rx, tx
        self.blk_r, self.blk_w = br, bw
        self._prev_net = (rx, tx)
        self._prev_blk = (br, bw)
        self._prev_t = now
        self.have_stats = True
        self.cpu_h.append(self.cpu)
        self.mem_h.append(self.mem_pct)
        self.rx_h.append(self.net_rx_rate)
        self.tx_h.append(self.net_tx_rate)


class Model:
    def __init__(self):
        self.lock = threading.Lock()
        self.conts = {}          # id -> Container
        self.order = []          # id list from ps
        self.docker_ver = ""
        self.host = ""
        self.n_images = 0
        self.err = ""
        # host metrics
        self.ncpu = os.cpu_count() or 1
        self.cpu_total = 0.0
        self.cpu_cores = []
        self.cpu_h = collections.deque(maxlen=HIST)
        self.mem_total = 0
        self.mem_used = 0
        self.mem_pct = 0.0
        self.mem_h = collections.deque(maxlen=HIST)
        self.swap_total = 0
        self.swap_used = 0
        self.load = (0.0, 0.0, 0.0)
        self._prev_cpu = None
        self._prev_cores = None

    def snapshot(self):
        with self.lock:
            return [self.conts[c] for c in self.order if c in self.conts]


# ----------------------------------------------------------------------------
# Collectors (threads)
# ----------------------------------------------------------------------------
def run_json_lines(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except Exception as e:
        return None, str(e)
    if p.returncode != 0:
        return None, (p.stderr.strip() or f"exit {p.returncode}")
    out = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out, ""


def ps_loop(model, stop):
    while not stop.is_set():
        rows, err = run_json_lines(
            ["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"])
        with model.lock:
            if err:
                model.err = err
            elif rows is not None:
                model.err = ""
                seen = []
                for r in rows:
                    cid = r.get("ID", "")[:12]
                    if not cid:
                        continue
                    seen.append(cid)
                    c = model.conts.get(cid)
                    if c is None:
                        c = Container(cid)
                        model.conts[cid] = c
                    c.name = r.get("Names", "")
                    c.image = r.get("Image", "")
                    c.state = r.get("State", "")
                    c.status = r.get("Status", "")
                    c.command = r.get("Command", "").strip('"')
                    c.ports = r.get("Ports", "")
                    c.created = r.get("CreatedAt", "")
                    c.networks = r.get("Networks", "")
                    c.health = r.get("HealthStatus", "")
                    labels = r.get("Labels", "")
                    m = re.search(r'com\.docker\.compose\.project=([^,]+)',
                                  labels)
                    c.compose = m.group(1) if m else ""
                model.order = seen
                # drop removed
                for cid in list(model.conts):
                    if cid not in seen:
                        del model.conts[cid]
        stop.wait(2.0)


def stats_loop(model, stop):
    while not stop.is_set():
        rows, err = run_json_lines(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"])
        now = time.time()
        if rows is not None:
            with model.lock:
                for r in rows:
                    cid = r.get("ID", "")[:12]
                    c = model.conts.get(cid)
                    if c is None:
                        c = Container(cid)
                        c.name = r.get("Name", "")
                        model.conts[cid] = c
                    c.update_stats(r, now)
                # zero out stats for non-running to avoid stale graphs
                running_ids = {r.get("ID", "")[:12] for r in rows}
                for cid, c in model.conts.items():
                    if cid not in running_ids and c.state != "running":
                        c.cpu = 0.0
        stop.wait(0.3)


def meta_loop(model, stop):
    while not stop.is_set():
        try:
            p = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=10)
            ver = p.stdout.strip()
        except Exception:
            ver = ""
        try:
            pi = subprocess.run(["docker", "images", "-q"],
                                capture_output=True, text=True, timeout=10)
            nimg = len([x for x in pi.stdout.splitlines() if x.strip()])
        except Exception:
            nimg = 0
        host = os.uname().nodename if hasattr(os, "uname") else ""
        with model.lock:
            model.docker_ver = ver
            model.n_images = nimg
            model.host = host
        stop.wait(10.0)


def read_proc_stat():
    cores = {}
    total = None
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("cpu"):
                    parts = line.split()
                    name = parts[0]
                    vals = list(map(int, parts[1:8]))
                    idle = vals[3] + vals[4]
                    tot = sum(vals)
                    if name == "cpu":
                        total = (idle, tot)
                    else:
                        cores[name] = (idle, tot)
    except OSError:
        pass
    return total, cores


def update_host(model):
    total, cores = read_proc_stat()
    with model.lock:
        if total and model._prev_cpu:
            di = total[0] - model._prev_cpu[0]
            dt = total[1] - model._prev_cpu[1]
            if dt > 0:
                model.cpu_total = max(0.0, min(100.0, 100.0 * (1 - di / dt)))
                model.cpu_h.append(model.cpu_total)
        model._prev_cpu = total
        if cores and model._prev_cores:
            usage = []
            for k in sorted(cores, key=lambda s: int(s[3:])):
                if k in model._prev_cores:
                    di = cores[k][0] - model._prev_cores[k][0]
                    dt = cores[k][1] - model._prev_cores[k][1]
                    usage.append(max(0.0, min(100.0, 100.0 * (1 - di / dt)))
                                 if dt > 0 else 0.0)
            model.cpu_cores = usage
        model._prev_cores = cores
        # memory
        try:
            mem = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    mem[k] = int(v.strip().split()[0]) * 1024
            model.mem_total = mem.get("MemTotal", 0)
            avail = mem.get("MemAvailable", mem.get("MemFree", 0))
            model.mem_used = model.mem_total - avail
            model.mem_pct = (100.0 * model.mem_used / model.mem_total
                             if model.mem_total else 0.0)
            model.mem_h.append(model.mem_pct)
            model.swap_total = mem.get("SwapTotal", 0)
            model.swap_used = model.swap_total - mem.get("SwapFree", 0)
        except OSError:
            pass
        try:
            model.load = os.getloadavg()
        except (OSError, AttributeError):
            pass


# ----------------------------------------------------------------------------
# Docker actions
# ----------------------------------------------------------------------------
def docker_action(action, cid, name, toast):
    def run():
        args = {
            "start": ["docker", "start", cid],
            "stop": ["docker", "stop", cid],
            "restart": ["docker", "restart", cid],
            "pause": ["docker", "pause", cid],
            "unpause": ["docker", "unpause", cid],
            "kill": ["docker", "kill", cid],
            "remove": ["docker", "rm", "-f", cid],
        }[action]
        try:
            p = subprocess.run(args, capture_output=True, text=True,
                               timeout=60)
            if p.returncode == 0:
                toast(f"{action} {name}: ok", Theme.ok)
            else:
                toast(f"{action} {name}: {p.stderr.strip()[:60]}", Theme.bad)
        except Exception as e:
            toast(f"{action} {name}: {e}", Theme.bad)
    threading.Thread(target=run, daemon=True).start()


def get_logs(cid, tail=500, timestamps=True):
    args = ["docker", "logs", "--tail", str(tail)]
    if timestamps:
        args.append("--timestamps")
    args.append(cid)
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=20)
        text = p.stdout + p.stderr
        return text.splitlines() or ["(no output)"]
    except Exception as e:
        return [f"error: {e}"]


def get_inspect(cid):
    try:
        p = subprocess.run(["docker", "inspect", cid],
                           capture_output=True, text=True, timeout=20)
        return p.stdout.splitlines() or ["(empty)"]
    except Exception as e:
        return [f"error: {e}"]


def inspect_json(cid):
    try:
        p = subprocess.run(["docker", "inspect", cid],
                           capture_output=True, text=True, timeout=20)
        data = json.loads(p.stdout)
        return data[0] if data else None
    except Exception:
        return None


def list_container_dir(cid, path):
    """Return (entries, error). Each entry is (name, is_dir). Uses `ls`
    inside the container; degrades gracefully if ls is absent."""
    script = ("LC_ALL=C ls -Ap --group-directories-first -- %s 2>/dev/null "
              "|| LC_ALL=C ls -Ap -- %s") % (_shq(path), _shq(path))
    try:
        p = subprocess.run(["docker", "exec", cid, "sh", "-c", script],
                           capture_output=True, text=True, timeout=15)
    except Exception as e:
        return [], str(e)
    if p.returncode != 0:
        err = p.stderr.strip() or "cannot read directory"
        return [], err
    entries = []
    for line in p.stdout.splitlines():
        if not line:
            continue
        is_dir = line.endswith("/")
        name = line[:-1] if is_dir else line
        entries.append((name, is_dir))
    return entries, ""


def _shq(s):
    return "'" + s.replace("'", "'\\''") + "'"


def _norm_path(base, name):
    if name == "..":
        if base in ("/", ""):
            return "/"
        return "/" + "/".join(base.strip("/").split("/")[:-1])
    joined = (base.rstrip("/") + "/" + name) if base != "/" else "/" + name
    return joined or "/"


def build_network_view(cid, name, model):
    """Build scrollable lines describing the container's network setup,
    an ASCII topology, and a copy-pasteable Mermaid diagram."""
    info = inspect_json(cid)
    lines = []
    if not info:
        return ["(could not inspect container)"]
    ns = info.get("NetworkSettings", {}) or {}
    nets = ns.get("Networks", {}) or {}
    ports = ns.get("Ports", {}) or {}

    lines.append(f"container : {name}")
    lines.append(f"id        : {cid}")
    lines.append("")

    # gather peers per network via `docker network inspect`
    peers_by_net = {}
    for net in nets:
        peers_by_net[net] = _network_peers(net, cid)

    lines.append("── networks ──")
    for net, ncfg in nets.items():
        ip = ncfg.get("IPAddress") or "-"
        gw = ncfg.get("Gateway") or "-"
        mac = ncfg.get("MacAddress") or "-"
        aliases = ncfg.get("Aliases") or []
        lines.append(f"● {net}")
        lines.append(f"    ip {ip}   gw {gw}   mac {mac}")
        if aliases:
            lines.append(f"    aliases: {', '.join(aliases)}")
        peers = peers_by_net.get(net, [])
        others = [p for p in peers if p[0] != cid[:12]]
        if others:
            lines.append(f"    peers ({len(others)}):")
            for pid, pname, pip in others:
                lines.append(f"      ├ {pname}  {pip}")
        lines.append("")

    # ports
    pub = []
    for cport, binds in (ports or {}).items():
        if binds:
            for b in binds:
                hip = b.get("HostIp", "")
                hport = b.get("HostPort", "")
                pub.append(f"{hip}:{hport} → {cport}")
        else:
            pub.append(f"(exposed) {cport}")
    lines.append("── ports ──")
    lines.extend(["  " + p for p in pub] or ["  (none published)"])
    lines.append("")

    # ASCII topology
    lines.append("── topology ──")
    short = name if len(name) <= 22 else name[:21] + "…"
    for net, ncfg in nets.items():
        ip = ncfg.get("IPAddress") or "-"
        lines.append(f"  [{short}] ─({ip})─ «{net}»")
        for pid, pname, pip in peers_by_net.get(net, []):
            if pid == cid[:12]:
                continue
            lines.append(f"        «{net}» ─({pip})─ [{pname}]")
    lines.append("")

    # Mermaid diagram (copy/paste into any mermaid renderer)
    lines.append("── mermaid ──")
    lines.append("graph LR")
    node_self = "C_" + re.sub(r'\W', '_', cid[:12])
    lines.append(f'  {node_self}["🧊 {name}"]')
    seen_nodes = set()
    for i, (net, ncfg) in enumerate(nets.items()):
        nnode = f"N{i}"
        lines.append(f'  {nnode}(["🌐 {net}"])')
        ip = ncfg.get("IPAddress") or ""
        lines.append(f'  {node_self} -->|"{ip}"| {nnode}')
        for pid, pname, pip in peers_by_net.get(net, []):
            if pid == cid[:12]:
                continue
            pnode = "P_" + re.sub(r'\W', '_', pid)
            if pnode not in seen_nodes:
                lines.append(f'  {pnode}["{pname}"]')
                seen_nodes.add(pnode)
            lines.append(f'  {nnode} -->|"{pip}"| {pnode}')
    return lines


def _network_peers(net, self_cid):
    """Return [(short_id, name, ipv4), ...] for containers on `net`."""
    try:
        p = subprocess.run(["docker", "network", "inspect", net],
                           capture_output=True, text=True, timeout=15)
        data = json.loads(p.stdout)
    except Exception:
        return []
    if not data:
        return []
    out = []
    for full_id, c in (data[0].get("Containers") or {}).items():
        ip = (c.get("IPv4Address") or "").split("/")[0] or "-"
        out.append((full_id[:12], c.get("Name", full_id[:12]), ip))
    out.sort(key=lambda t: t[1])
    return out


# ----------------------------------------------------------------------------
# Input
# ----------------------------------------------------------------------------
KEY_MAP = {
    "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
    "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left",
    "\x1b[5~": "pgup", "\x1b[6~": "pgdn",
    "\x1b[H": "home", "\x1b[F": "end", "\x1b[1~": "home", "\x1b[4~": "end",
    "\r": "enter", "\n": "enter", "\x7f": "bksp", "\x08": "bksp",
    "\x1b": "esc", "\t": "tab",
}


def read_keys(timeout):
    r, _, _ = select.select([sys.stdin.fileno()], [], [], timeout)
    if not r:
        return []
    try:
        data = os.read(sys.stdin.fileno(), 1024).decode("utf-8", "replace")
    except OSError:
        return []
    keys = []
    i = 0
    while i < len(data):
        if data[i] == "\x1b":
            matched = None
            for length in (4, 3, 2):
                chunk = data[i:i + length]
                if chunk in KEY_MAP:
                    matched = (KEY_MAP[chunk], length)
                    break
            if matched:
                keys.append(matched[0])
                i += matched[1]
                continue
            keys.append("esc")
            i += 1
            continue
        ch = data[i]
        keys.append(KEY_MAP.get(ch, ch))
        i += 1
    return keys


# ----------------------------------------------------------------------------
# Sorting
# ----------------------------------------------------------------------------
SORT_FIELDS = [
    ("cpu", lambda c: c.cpu),
    ("mem", lambda c: c.mem_pct),
    ("name", lambda c: c.name.lower()),
    ("state", lambda c: c.state),
    ("net", lambda c: c.net_rx_rate + c.net_tx_rate),
    ("pids", lambda c: c.pids),
]


def state_color(state):
    return {"running": Theme.ok, "exited": Theme.bad, "paused": Theme.paused,
            "restarting": Theme.warn, "created": Theme.info,
            "dead": Theme.bad}.get(state, Theme.dim)


# ----------------------------------------------------------------------------
# The application
# ----------------------------------------------------------------------------
class App:
    def __init__(self, model):
        self.model = model
        self.sel = 0
        self.top = 0            # scroll offset for table
        self.sort_i = 0
        self.reverse = True
        self.show_all = True
        self.filter = ""
        self.mode = "normal"   # normal | filter | confirm | logs | inspect | help
        self.confirm = None    # (action, cid, name)
        self.overlay_lines = []
        self.overlay_off = 0
        self.overlay_maxoff = 0
        self.overlay_title = ""
        self.wrap = False        # wrap long lines in text overlays
        self.hoff = 0            # horizontal scroll when unwrapped
        self.toast_msg = ""
        self.toast_col = None
        self.toast_t = 0
        self.prev_screen = None
        self.visible = []
        self.force_redraw = False
        # live panel logs cache (fetched off the render thread)
        self.log_lock = threading.Lock()
        self.log_cache = {}      # cid -> list[str]
        self.log_fetch_t = {}    # cid -> monotonic ts of last fetch
        self.log_fetching = set()
        # filesystem browser state
        self.fs_cid = None
        self.fs_name = ""
        self.fs_path = "/"
        self.fs_items = []       # [(name, is_dir)]
        self.fs_sel = 0
        self.fs_off = 0
        self.fs_err = ""
        # request for the main loop to perform a terminal-suspending action
        self.request = None      # ("shell", cid, name) etc.

    def ensure_panel_logs(self, cid, tail=200, interval=2.0):
        """Kick off a background log fetch for cid if stale/missing."""
        now = time.monotonic()
        with self.log_lock:
            if cid in self.log_fetching:
                return
            last = self.log_fetch_t.get(cid, 0)
            if cid in self.log_cache and now - last < interval:
                return
            self.log_fetching.add(cid)

        def run():
            lines = get_logs(cid, tail=tail, timestamps=False)
            with self.log_lock:
                self.log_cache[cid] = lines
                self.log_fetch_t[cid] = time.monotonic()
                self.log_fetching.discard(cid)
        threading.Thread(target=run, daemon=True).start()

    def panel_logs(self, cid):
        with self.log_lock:
            return self.log_cache.get(cid)

    def set_toast(self, msg, col=None):
        self.toast_msg = msg
        self.toast_col = col if col else Theme.accent
        self.toast_t = time.time()

    def cycle_theme(self, step):
        i = THEME_ORDER.index(Theme.name) if Theme.name in THEME_ORDER else 0
        name = THEME_ORDER[(i + step) % len(THEME_ORDER)]
        set_theme(name)
        save_config(name)
        self.force_redraw = True
        self.set_toast(f"theme: {name}", Theme.title)

    # -- data view -------------------------------------------------------
    def compute_visible(self):
        conts = self.model.snapshot()
        if not self.show_all:
            conts = [c for c in conts if c.state == "running"]
        if self.filter:
            f = self.filter.lower()
            conts = [c for c in conts if f in c.name.lower()
                     or f in c.image.lower() or f in c.id.lower()
                     or f in c.compose.lower()]
        name, keyf = SORT_FIELDS[self.sort_i]
        conts.sort(key=keyf, reverse=self.reverse)
        self.visible = conts
        if self.sel >= len(conts):
            self.sel = max(0, len(conts) - 1)
        return conts

    def selected(self):
        if 0 <= self.sel < len(self.visible):
            return self.visible[self.sel]
        return None

    # -- input -----------------------------------------------------------
    def handle(self, key):
        if self.mode == "filter":
            self._handle_filter(key)
            return True
        if self.mode == "confirm":
            self._handle_confirm(key)
            return True
        if self.mode == "files":
            self._handle_files(key)
            return True
        if self.mode in ("logs", "inspect", "help", "net"):
            self._handle_overlay(key)
            return True
        return self._handle_normal(key)

    def _handle_normal(self, key):
        n = len(self.visible)
        if key in ("q",):
            return False
        elif key in ("up", "k"):
            self.sel = max(0, self.sel - 1)
        elif key in ("down", "j"):
            self.sel = min(n - 1, self.sel + 1) if n else 0
        elif key == "pgup":
            self.sel = max(0, self.sel - 10)
        elif key == "pgdn":
            self.sel = min(n - 1, self.sel + 10) if n else 0
        elif key in ("home", "g"):
            self.sel = 0
        elif key in ("end", "G"):
            self.sel = max(0, n - 1)
        elif key == "o":
            self.sort_i = (self.sort_i + 1) % len(SORT_FIELDS)
        elif key == "O":
            self.reverse = not self.reverse
        elif key == "t":
            self.cycle_theme(1)
        elif key == "a":
            self.show_all = not self.show_all
        elif key == "/":
            self.mode = "filter"
        elif key in ("l", "enter"):
            c = self.selected()
            if c:
                self.overlay_lines = get_logs(c.id)
                self.overlay_off = max(0, len(self.overlay_lines) - 1)
                self.overlay_title = f"logs: {c.name}"
                self.mode = "logs"
                self.overlay_bottom = True
        elif key == "i":
            c = self.selected()
            if c:
                self.overlay_lines = get_inspect(c.id)
                self.overlay_off = 0
                self.overlay_title = f"inspect: {c.name}"
                self.mode = "inspect"
                self.overlay_bottom = False
        elif key == "n":
            c = self.selected()
            if c:
                self.overlay_lines = build_network_view(c.id, c.name,
                                                        self.model)
                self.overlay_off = 0
                self.overlay_title = f"network: {c.name}"
                self.mode = "net"
                self.overlay_bottom = False
        elif key == "f":
            c = self.selected()
            if c:
                self.open_files(c)
        elif key == "s":
            c = self.selected()
            if c and c.state == "running":
                self.request = ("shell", c.id, c.name)
            elif c:
                self.set_toast("shell: container not running", Theme.warn)
        elif key == "?":
            self.mode = "help"
        elif key in ("S", "T", "R", "P", "K", "D"):
            self._action_key(key)
        return True

    # -- filesystem browser ---------------------------------------------
    def open_files(self, c):
        if c.state != "running":
            self.set_toast("files: container not running", Theme.warn)
            return
        self.fs_cid = c.id
        self.fs_name = c.name
        self.fs_path = "/"
        self.fs_sel = 0
        self.fs_off = 0
        self._load_fs()
        self.mode = "files"

    def _load_fs(self):
        items, err = list_container_dir(self.fs_cid, self.fs_path)
        self.fs_err = err
        if self.fs_path != "/":
            items = [("..", True)] + items
        self.fs_items = items
        self.fs_sel = min(self.fs_sel, max(0, len(items) - 1))
        self.fs_off = 0

    def _handle_files(self, key):
        n = len(self.fs_items)
        if key in ("esc", "q", "f"):
            self.mode = "normal"
        elif key in ("up", "k"):
            self.fs_sel = max(0, self.fs_sel - 1)
        elif key in ("down", "j"):
            self.fs_sel = min(n - 1, self.fs_sel + 1) if n else 0
        elif key == "pgup":
            self.fs_sel = max(0, self.fs_sel - 15)
        elif key == "pgdn":
            self.fs_sel = min(n - 1, self.fs_sel + 15) if n else 0
        elif key in ("home", "g"):
            self.fs_sel = 0
        elif key in ("end", "G"):
            self.fs_sel = max(0, n - 1)
        elif key in ("left", "bksp"):
            if self.fs_path != "/":
                self.fs_path = _norm_path(self.fs_path, "..")
                self.fs_sel = 0
                self._load_fs()
        elif key in ("enter", "right"):
            if 0 <= self.fs_sel < n:
                name, is_dir = self.fs_items[self.fs_sel]
                if is_dir:
                    self.fs_path = _norm_path(self.fs_path, name)
                    self.fs_sel = 0
                    self._load_fs()
        elif key == "s":  # shell into container at current path
            self.request = ("shell", self.fs_cid, self.fs_name)
            self.mode = "normal"

    def _action_key(self, key):
        c = self.selected()
        if not c:
            return
        if key == "S":
            docker_action("start", c.id, c.name, self.set_toast)
        elif key == "R":
            docker_action("restart", c.id, c.name, self.set_toast)
        elif key == "P":
            act = "unpause" if c.state == "paused" else "pause"
            docker_action(act, c.id, c.name, self.set_toast)
        elif key == "T":
            self.confirm = ("stop", c.id, c.name)
            self.mode = "confirm"
        elif key == "K":
            self.confirm = ("kill", c.id, c.name)
            self.mode = "confirm"
        elif key == "D":
            self.confirm = ("remove", c.id, c.name)
            self.mode = "confirm"

    def _handle_filter(self, key):
        if key == "enter":
            self.mode = "normal"
        elif key == "esc":
            self.filter = ""
            self.mode = "normal"
        elif key == "bksp":
            self.filter = self.filter[:-1]
        elif len(key) == 1 and key.isprintable():
            self.filter += key

    def _handle_confirm(self, key):
        if key in ("y", "Y", "enter"):
            action, cid, name = self.confirm
            docker_action(action, cid, name, self.set_toast)
            self.mode = "normal"
            self.confirm = None
        elif key in ("n", "N", "esc", "q"):
            self.mode = "normal"
            self.confirm = None

    def _handle_overlay(self, key):
        page = 20
        toggle = {"logs": "l", "inspect": "i", "net": "n"}.get(self.mode)
        if key in ("esc", "q") or (toggle and key == toggle):
            self.mode = "normal"
        elif key in ("up", "k"):
            self.overlay_off -= 1
        elif key in ("down", "j"):
            self.overlay_off += 1
        elif key == "pgup":
            self.overlay_off -= page
        elif key == "pgdn":
            self.overlay_off += page
        elif key in ("home", "g"):
            self.overlay_off = 0
            self.hoff = 0
        elif key in ("end", "G"):
            self.overlay_off = 10 ** 9        # clamped in render
        elif key == "w" and self.mode != "help":
            self.wrap = not self.wrap
            self.hoff = 0
        elif key == "left" and not self.wrap:
            self.hoff = max(0, self.hoff - 8)
        elif key == "right" and not self.wrap:
            self.hoff += 8
        elif key == "r" and self.mode in ("logs", "inspect", "net"):
            c = self.selected()
            if c:
                if self.mode == "logs":
                    self.overlay_lines = get_logs(c.id)
                    self.overlay_off = 10 ** 9
                elif self.mode == "inspect":
                    self.overlay_lines = get_inspect(c.id)
                else:
                    self.overlay_lines = build_network_view(c.id, c.name,
                                                            self.model)
        self.overlay_off = max(0, min(self.overlay_off, self.overlay_maxoff))

    # -- rendering -------------------------------------------------------
    def render(self, w, h):
        scr = Screen(w, h)
        self.compute_visible()
        self._draw_header(scr, w)
        host_h = 9 if h >= 26 else 7
        if h < 18:
            host_h = 0
        if host_h:
            self._draw_host(scr, 0, 1, w, host_h)
        main_y = 1 + host_h
        avail = h - main_y - 1                 # rows between host and footer
        # persistent full-width logs panel across the bottom
        logs_h = 0
        if avail >= 16:
            logs_h = max(6, min(14, avail // 3))
        main_h = avail - logs_h
        # split the upper area into table + detail
        detail_w = 0
        if w >= 90:
            detail_w = max(34, int(w * 0.36))
        table_w = w - detail_w
        self._draw_table(scr, 0, main_y, table_w, main_h)
        if detail_w:
            self._draw_detail(scr, table_w, main_y, detail_w, main_h)
        if logs_h:
            self._draw_logs_panel(scr, 0, main_y + main_h, w, logs_h)
        self._draw_footer(scr, w, h)
        if self.mode in ("logs", "inspect", "help", "net"):
            self._draw_overlay(scr, w, h)
        if self.mode == "files":
            self._draw_files(scr, w, h)
        if self.mode == "confirm":
            self._draw_confirm(scr, w, h)
        return scr

    def _draw_header(self, scr, w):
        m = self.model
        scr.put(1, 0, "▟▙ dtop", Theme.title, attr=1)
        running = sum(1 for c in m.snapshot() if c.state == "running")
        total = len(m.snapshot())
        info = f"docker {m.docker_ver}  {m.host}"
        scr.put(11, 0, info, Theme.dim)
        stat = f"containers {running}/{total}  images {m.n_images}"
        scr.put(11 + len(info) + 2, 0, stat, Theme.hdr)
        clk = time.strftime("%H:%M:%S")
        scr.put(w - len(clk) - 1, 0, clk, Theme.accent, attr=1)
        thm = f"◈ {Theme.name}"
        tx = w - len(clk) - 3 - len(thm)
        scr.put(tx, 0, thm, Theme.c_proc)
        if m.err:
            e = f"⚠ {m.err}"[:max(0, tx - 12)]
            scr.put(tx - 2 - len(e), 0, e, Theme.bad)

    def _draw_host(self, scr, x, y, w, h):
        m = self.model
        cpu_w = int(w * 0.6)
        mem_w = w - cpu_w
        # ---- CPU box ----
        draw_box(scr, x, y, cpu_w, h, "cpu", tcolor=Theme.c_cpu,
                 right=f"{m.cpu_total:4.1f}%  load {m.load[0]:.2f}")
        scr.set_clip(x + 1, y + 1, cpu_w - 2, h - 2)
        inner_x = x + 2
        inner_w = cpu_w - 4
        # per-core mini bars on left, graph on right
        cores = m.cpu_cores
        ncols = 2 if len(cores) > 4 else 1
        core_area = min(len(cores), (h - 2) * ncols)
        label_w = 16
        for idx in range(core_area):
            col = idx % ncols
            row = idx // ncols
            cx = inner_x + col * (label_w + 8)
            cy = y + 1 + row
            if cy >= y + h - 1:
                break
            frac = cores[idx] / 100.0
            scr.put(cx, cy, f"c{idx}", Theme.dim)
            meter(scr, cx + 3, cy, 8, frac)
            scr.put(cx + 12, cy, f"{cores[idx]:3.0f}%",
                    gradient(frac))
        # big cpu graph on the right portion
        gx = inner_x + ncols * (label_w + 8)
        gw = x + cpu_w - 2 - gx
        if gw > 8:
            braille_graph(scr, gx, y + 1, gw, h - 2, m.cpu_h, 100.0,
                          Theme.g_cpu)
        scr.reset_clip()
        # ---- MEM box ----
        mx = x + cpu_w
        draw_box(scr, mx, y, mem_w, h, "mem", tcolor=Theme.c_mem,
                 right=f"{human_bytes(m.mem_used)}/{human_bytes(m.mem_total)}")
        scr.set_clip(mx + 1, y + 1, mem_w - 2, h - 2)
        ix = mx + 2
        iw = mem_w - 4
        scr.put(ix, y + 1, "RAM", Theme.hdr)
        meter(scr, ix + 4, y + 1, iw - 12, m.mem_pct / 100.0, Theme.g_mem)
        scr.put(ix + iw - 6, y + 1, f"{m.mem_pct:4.1f}%",
                gradient(m.mem_pct / 100, Theme.g_mem))
        if m.swap_total:
            sp = 100.0 * m.swap_used / m.swap_total
            scr.put(ix, y + 2, "SWP", Theme.hdr)
            meter(scr, ix + 4, y + 2, iw - 12, sp / 100.0, Theme.g_mem)
            scr.put(ix + iw - 6, y + 2, f"{sp:4.1f}%",
                    gradient(sp / 100, Theme.g_mem))
        if h - 2 >= 4:
            braille_graph(scr, ix, y + 3, iw, h - 4, m.mem_h, 100.0, Theme.g_mem)
        scr.reset_clip()

    def _draw_table(self, scr, x, y, w, h):
        title = f"containers  sort:{SORT_FIELDS[self.sort_i][0]}"
        title += "▼" if self.reverse else "▲"
        if not self.show_all:
            title += " [running]"
        if self.filter:
            title += f" /{self.filter}"
        draw_box(scr, x, y, w, h, title, tcolor=Theme.c_proc,
                 right=f"{len(self.visible)}")
        scr.set_clip(x + 1, y + 1, w - 2, h - 2)
        ix = x + 1
        iw = w - 2
        rows_h = h - 3
        hy = y + 1
        cx = ix + 1              # state dot
        name_x = cx + 2         # name start
        ncpu = self.model.ncpu

        # right-aligned columns (label, width); dropped as width shrinks.
        # CPU%/MEM% become gradient meter+value bars when there's room.
        meter_cols = iw > 62
        cw = 12 if meter_cols else 6
        rcols = [("CPU%", cw), ("MEM%", cw)]
        if iw > 78:
            rcols.append(("MEM", 10))
        if iw > 92:
            rcols.append(("NET↓", 10))
        if iw > 100:
            rcols.append(("PIDS", 5))
        gap = 1
        rblock = sum(wd for _, wd in rcols) + gap * (len(rcols) - 1)
        rx0 = ix + iw - rblock                  # first col of right block
        longest = max((len(c.name) for c in self.visible), default=8)
        name_w = max(10, min(longest, 34))
        graph_x = name_x + name_w + 1
        graph_w = rx0 - 2 - graph_x
        if graph_w < 6:                          # not worth a graph -> grow name
            graph_w = 0
            name_w = max(8, rx0 - 2 - name_x)

        # header row
        scr.put(name_x, hy, "NAME"[:name_w], Theme.hdr, attr=1)
        if graph_w >= 6:
            scr.put(graph_x, hy, "cpu history"[:graph_w], Theme.faint)
        colx = rx0
        for lbl, wd in rcols:
            if lbl in ("CPU%", "MEM%") and wd >= 11:
                scr.put(colx, hy, lbl, Theme.hdr, attr=1)
            else:
                scr.put(colx, hy, lbl.rjust(wd), Theme.hdr, attr=1)
            colx += wd + gap
        scr.hline(ix, hy + 1, iw, "─", Theme.faint)

        # scroll window
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + rows_h:
            self.top = self.sel - rows_h + 1
        self.top = max(0, min(self.top, max(0, len(self.visible) - rows_h)))

        for r in range(rows_h):
            idx = self.top + r
            if idx >= len(self.visible):
                break
            c = self.visible[idx]
            ry = hy + 2 + r
            selected = (idx == self.sel)
            bg = Theme.sel_bg if selected else None
            if bg:
                scr.fill_bg(ix, ry, iw, 1, bg)
            sc = state_color(c.state)
            dot = "▶" if c.state == "running" else (
                "⏸" if c.state == "paused" else "■")
            scr.cell(cx, ry, dot, sc, bg)
            scr.put(name_x, ry, c.name[:name_w],
                    Theme.sel_fg if selected else Theme.fg, bg,
                    attr=1 if selected else 0)
            if graph_w >= 6 and c.cpu_h:
                peak = max(max(c.cpu_h), 10.0)   # autoscale shape to own peak
                braille_spark(scr, graph_x, ry, graph_w, c.cpu_h, peak,
                              Theme.g_cpu, bg, color_max=100.0 * ncpu)
            colx = rx0
            for lbl, wd in rcols:
                if lbl in ("CPU%", "MEM%"):
                    if lbl == "CPU%":
                        frac = min(1.0, c.cpu / (100.0 * ncpu))
                        stops = Theme.g_cpu
                        val = f"{c.cpu:.1f}"
                    else:
                        frac = c.mem_pct / 100.0
                        stops = Theme.g_mem
                        val = f"{c.mem_pct:.1f}"
                    if wd >= 11:
                        mw = wd - 6
                        meter(scr, colx, ry, mw, frac, stops, bg=bg)
                        scr.put(colx + mw + 1, ry, val.rjust(5),
                                gradient(frac, stops), bg)
                    else:
                        scr.put(colx, ry, val.rjust(wd),
                                gradient(frac, stops), bg)
                elif lbl == "MEM":
                    scr.put(colx, ry, human_bytes(c.mem_used).rjust(wd),
                            Theme.fg, bg)
                elif lbl == "NET↓":
                    scr.put(colx, ry, human_rate(c.net_rx_rate).rjust(wd),
                            Theme.info, bg)
                else:  # PIDS
                    scr.put(colx, ry, str(c.pids).rjust(wd), Theme.dim, bg)
                colx += wd + gap
        if not self.visible:
            scr.put(name_x, hy + 3, "no containers", Theme.dim)
        scr.reset_clip()

    def _draw_detail(self, scr, x, y, w, h):
        c = self.selected()
        title = "detail"
        draw_box(scr, x, y, w, h, title, color=Theme.box_hi,
                 tcolor=Theme.c_net)
        scr.set_clip(x + 1, y + 1, w - 2, h - 2)
        if not c:
            scr.put(x + 2, y + 1, "select a container", Theme.dim)
            scr.reset_clip()
            return
        ix = x + 2
        iw = w - 4
        yy = y + 1
        sc = state_color(c.state)
        scr.put(ix, yy, c.name[:iw], Theme.accent, attr=1); yy += 1
        scr.put(ix, yy, f"{c.state}", sc, attr=1)
        scr.put(ix + len(c.state) + 1, yy, f"{c.status}"[:iw - len(c.state) - 1],
                Theme.dim); yy += 1
        scr.put(ix, yy, f"id    {c.id}", Theme.dim); yy += 1
        scr.put(ix, yy, f"image {c.image}"[:iw], Theme.fg); yy += 1
        if c.compose:
            scr.put(ix, yy, f"proj  {c.compose}"[:iw], Theme.dim); yy += 1
        if c.ports:
            scr.put(ix, yy, f"ports {c.ports}"[:iw], Theme.info); yy += 1
        yy += 1
        # --- CPU / MEM / NET braille graphs fill the remaining detail area ---
        avail = y + h - 1 - yy
        if avail >= 18:
            gh, nh = 5, 4
        elif avail >= 14:
            gh, nh = 4, 3
        elif avail >= 10:
            gh, nh = 3, 2
        elif avail >= 7:
            gh, nh = 2, 1
        else:
            gh, nh = 0, 0

        ncpu = self.model.ncpu
        if gh > 0:
            scr.put(ix, yy, f"CPU {c.cpu:.1f}%", Theme.c_cpu, attr=1)
            meter(scr, ix + 11, yy, iw - 11,
                  min(1.0, c.cpu / (100.0 * ncpu)), Theme.g_cpu)
            yy += 1
            braille_graph(scr, ix, yy, iw, gh, c.cpu_h, 100.0 * ncpu,
                          Theme.g_cpu)
            yy += gh
            scr.put(ix, yy, f"MEM {c.mem_pct:.1f}%", Theme.c_mem, attr=1)
            meter(scr, ix + 11, yy, iw - 11, c.mem_pct / 100.0, Theme.g_mem)
            yy += 1
            braille_graph(scr, ix, yy, iw, gh, c.mem_h, 100.0, Theme.g_mem)
            yy += gh
            # NET (download+upload split, each its own gradient)
            maxr = max([1.0] + list(c.rx_h) + list(c.tx_h))
            scr.put(ix, yy, "NET", Theme.c_net, attr=1)
            scr.put(ix + 4, yy, f"↓{human_rate(c.net_rx_rate)}"[:iw - 20],
                    gradient(0.5, Theme.g_down))
            up_lbl = f"↑{human_rate(c.net_tx_rate)}"
            scr.put(ix + iw - len(up_lbl), yy, up_lbl, gradient(0.5, Theme.g_up))
            yy += 1
            body = y + h - 1 - yy            # graph net into all leftover rows
            if body >= 4:
                half = body // 2
                braille_graph(scr, ix, yy, iw, half, c.rx_h, maxr, Theme.g_down)
                braille_graph(scr, ix, yy + half, iw, body - half, c.tx_h,
                              maxr, Theme.g_up)
            elif body > 0:
                braille_graph(scr, ix, yy, iw, body, c.rx_h, maxr, Theme.g_down)
        scr.reset_clip()

    def _draw_logs_panel(self, scr, x, y, w, h):
        """Full-width live logs panel across the bottom for the selected ctr."""
        c = self.selected()
        name = c.name if c else "—"
        draw_box(scr, x, y, w, h, f"logs: {name}", color=Theme.box,
                 tcolor=Theme.c_proc, right="l = full view")
        scr.set_clip(x + 1, y + 1, w - 2, h - 2)
        ix = x + 2
        iw = w - 4
        rows = h - 2
        if not c:
            scr.put(ix, y + 1, "select a container", Theme.dim)
            scr.reset_clip()
            return
        self.ensure_panel_logs(c.id)
        lines = self.panel_logs(c.id)
        if lines is None:
            scr.put(ix, y + 1, "loading…", Theme.dim)
            scr.reset_clip()
            return
        for i, ln in enumerate(lines[-rows:]):
            low = ln.lower()
            if any(k in low for k in ("error", "exception", "fatal",
                                      "panic", "traceback")):
                col = Theme.bad
            elif "warn" in low:
                col = Theme.warn
            else:
                col = Theme.fg
            scr.put(ix, y + 1 + i, clean_line(ln)[:iw], col)
        scr.reset_clip()

    def _draw_footer(self, scr, w, h):
        y = h - 1
        if time.time() - self.toast_t < 4 and self.toast_msg:
            scr.put(1, y, f" {self.toast_msg} ", self.toast_col, attr=1)
            return
        if self.mode == "filter":
            scr.put(1, y, f" filter: {self.filter}", Theme.accent, attr=1)
            scr.cell(1 + 9 + len(self.filter), y, "█", Theme.accent)
            return
        keys = ("↑↓ nav  o sort  / filter  l logs  s shell  f files  "
                "n net  i inspect  S/T/R/P/K/D actions  t theme  "
                "? help  q quit")
        scr.put(1, y, keys[:w - 2], Theme.dim)

    def _draw_overlay(self, scr, w, h):
        BG = blend(Theme.bg, Theme.box, 0.30)  # subtly raised panel
        scr.reset_clip()
        if self.mode == "help":
            ox = max(2, w // 12)
            oy = max(1, h // 12)
            ow = w - ox * 2
            oh = h - oy * 2
            scr.clear_region(ox, oy, ow, oh, BG)
            self._draw_help(scr, ox, oy, ow, oh)
            return
        # large, bottom-docked window (logs/inspect/net)
        ox = max(2, w // 24)
        ow = w - ox * 2
        oh = max(8, int(h * 0.72))
        oy = h - oh - 1
        if oy < 1:
            oy, oh = 1, h - 2
        text_w = ow - 2
        scr.clear_region(ox, oy, ow, oh, BG)
        wrap_lbl = "wrap:on" if self.wrap else "wrap:off"
        draw_box(scr, ox, oy, ow, oh, self.overlay_title, color=Theme.box_hi,
                 tcolor=Theme.c_net,
                 right=f"w {wrap_lbl}  ←→ scroll  r refresh  q close")
        view_h = oh - 2

        # build display lines (wrapped or raw)
        raw = [clean_line(s) for s in self.overlay_lines]
        if self.wrap:
            disp = []
            for s in raw:
                if s == "":
                    disp.append("")
                while len(s) > text_w:
                    disp.append(s[:text_w])
                    s = s[text_w:]
                disp.append(s)
        else:
            disp = raw
        maxoff = max(0, len(disp) - view_h)
        self.overlay_maxoff = maxoff
        if getattr(self, "overlay_bottom", False):
            self.overlay_off = maxoff
            self.overlay_bottom = False
        off = max(0, min(self.overlay_off, maxoff))
        self.overlay_off = off
        hoff = 0 if self.wrap else self.hoff

        scr.set_clip(ox + 1, oy + 1, text_w, view_h)
        for i in range(view_h):
            li = off + i
            if li >= len(disp):
                break
            line = disp[li]
            if hoff:
                line = line[hoff:]
            scr.put(ox + 1, oy + 1 + i, line[:text_w], Theme.fg, BG)
        scr.reset_clip()
        # scrollbar (on the right border)
        if len(disp) > view_h:
            frac = off / maxoff if maxoff else 0
            sb = oy + 1 + int(frac * (view_h - 1))
            scr.cell(ox + ow - 1, sb, "█", Theme.accent)

    def _draw_files(self, scr, w, h):
        BG = blend(Theme.bg, Theme.box, 0.30)
        ox = max(2, w // 10)
        oy = max(1, h // 10)
        ow = w - ox * 2
        oh = h - oy * 2
        scr.reset_clip()
        scr.clear_region(ox, oy, ow, oh, BG)
        title = f"files: {self.fs_name}"
        draw_box(scr, ox, oy, ow, oh, title, color=Theme.box_hi,
                 tcolor=Theme.c_proc,
                 right="↑↓ nav  ⏎ open  ← up  s shell  q close")
        scr.set_clip(ox + 1, oy + 1, ow - 2, oh - 2)
        # path breadcrumb
        scr.put(ox + 2, oy + 1, ("path " + self.fs_path)[:ow - 4],
                Theme.accent, BG)
        view_y = oy + 3
        view_h = oh - 4
        if self.fs_err:
            scr.put(ox + 2, view_y, ("⚠ " + self.fs_err)[:ow - 4], Theme.bad, BG)
            scr.reset_clip()
            return
        if not self.fs_items:
            scr.put(ox + 2, view_y, "(empty)", Theme.dim, BG)
            scr.reset_clip()
            return
        # keep selection in view
        if self.fs_sel < self.fs_off:
            self.fs_off = self.fs_sel
        elif self.fs_sel >= self.fs_off + view_h:
            self.fs_off = self.fs_sel - view_h + 1
        for i in range(view_h):
            idx = self.fs_off + i
            if idx >= len(self.fs_items):
                break
            name, is_dir = self.fs_items[idx]
            ry = view_y + i
            sel = (idx == self.fs_sel)
            rbg = Theme.sel_bg if sel else BG
            if sel:
                scr.fill_bg(ox + 1, ry, ow - 2, 1, rbg)
            icon = "▸ " if is_dir else "  "
            col = (Theme.accent if is_dir else Theme.fg)
            if sel:
                col = Theme.sel_fg
            label = icon + name + ("/" if is_dir else "")
            scr.put(ox + 2, ry, label[:ow - 4], col, rbg,
                    attr=1 if (sel or is_dir) else 0)
        # scrollbar
        if len(self.fs_items) > view_h:
            frac = self.fs_off / max(1, len(self.fs_items) - view_h)
            sb = view_y + int(frac * (view_h - 1))
            scr.cell(ox + ow - 1, sb, "█", Theme.accent)
        scr.reset_clip()

    def _draw_help(self, scr, x, y, w, h):
        draw_box(scr, x, y, w, h, "help — dtop", color=Theme.box_hi,
                 right="q close")
        scr.set_clip(x + 1, y + 1, w - 2, h - 2)
        rows = [
            ("Navigation", ""),
            ("  ↑ / k  ↓ / j", "move selection"),
            ("  PgUp / PgDn", "jump 10 rows"),
            ("  Home/g  End/G", "first / last"),
            ("View", ""),
            ("  o", "cycle sort field"),
            ("  O", "reverse sort order"),
            ("  a", "toggle all / running-only"),
            ("  /", "filter by name/image/project"),
            ("  l / Enter", "view logs (r to refresh)"),
            ("  i", "inspect (docker inspect JSON)"),
            ("Explore", ""),
            ("  s", "shell into container (exec sh/bash)"),
            ("  f", "browse container filesystem"),
            ("  n", "network setup + mermaid diagram"),
            ("Actions", ""),
            ("  S", "start container"),
            ("  T", "stop container (confirm)"),
            ("  R", "restart container"),
            ("  P", "pause / unpause toggle"),
            ("  K", "kill container (confirm)"),
            ("  D", "remove -f container (confirm)"),
            ("Other", ""),
            ("  t", "cycle color theme (saved to config)"),
            ("  ?", "this help"),
            ("  q", "quit"),
        ]
        yy = y + 1
        for k, v in rows:
            if yy >= y + h - 1:
                break
            if v == "":
                scr.put(x + 2, yy, k, Theme.title, attr=1)
            else:
                scr.put(x + 3, yy, k, Theme.accent)
                scr.put(x + 22, yy, v, Theme.fg)
            yy += 1
        scr.reset_clip()

    def _draw_confirm(self, scr, w, h):
        action, cid, name = self.confirm
        msg = f"{action} '{name}' ?"
        bw = max(40, len(msg) + 8)
        bh = 5
        bx = (w - bw) // 2
        by = (h - bh) // 2
        cbg = blend(Theme.bg, Theme.bad, 0.28)
        scr.reset_clip()
        scr.clear_region(bx, by, bw, bh, cbg)
        draw_box(scr, bx, by, bw, bh, "confirm", color=Theme.bad,
                 tcolor=Theme.bad)
        scr.put(bx + 3, by + 1, msg, Theme.fg, cbg, attr=1)
        scr.put(bx + 3, by + 3, "y", Theme.ok, cbg, attr=1)
        scr.put(bx + 4, by + 3, " yes   ", Theme.fg, cbg)
        scr.put(bx + 11, by + 3, "n", Theme.bad, cbg, attr=1)
        scr.put(bx + 12, by + 3, " no", Theme.fg, cbg)


# ----------------------------------------------------------------------------
# Main loops
# ----------------------------------------------------------------------------
def start_threads(model):
    stop = threading.Event()
    threads = [
        threading.Thread(target=ps_loop, args=(model, stop), daemon=True),
        threading.Thread(target=stats_loop, args=(model, stop), daemon=True),
        threading.Thread(target=meta_loop, args=(model, stop), daemon=True),
    ]
    for t in threads:
        t.start()
    return stop


def selftest():
    model = Model()
    rows, err = run_json_lines(
        ["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"])
    now = time.time()
    if rows:
        seen = []
        for r in rows:
            cid = r.get("ID", "")[:12]
            seen.append(cid)
            c = Container(cid)
            c.name = r.get("Names", "")
            c.image = r.get("Image", "")
            c.state = r.get("State", "")
            c.status = r.get("Status", "")
            c.ports = r.get("Ports", "")
            labels = r.get("Labels", "")
            m = re.search(r'com\.docker\.compose\.project=([^,]+)', labels)
            c.compose = m.group(1) if m else ""
            model.conts[cid] = c
        model.order = seen
    srows, _ = run_json_lines(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}"])
    if srows:
        for r in srows:
            cid = r.get("ID", "")[:12]
            c = model.conts.get(cid)
            if c:
                for k in range(20):
                    c.update_stats(r, now + k * 0.5)
                # fake some variation
                import math
                c.cpu_h = collections.deque(
                    [c.cpu * (0.6 + 0.4 * math.sin(i / 3)) for i in range(60)],
                    maxlen=HIST)
                c.mem_h = collections.deque(
                    [c.mem_pct * (0.7 + 0.3 * math.cos(i / 4)) for i in range(60)],
                    maxlen=HIST)
                c.rx_h = collections.deque(
                    [abs(1000 * math.sin(i / 5)) for i in range(60)], maxlen=HIST)
    update_host(model)
    time.sleep(0.2)
    update_host(model)
    import math
    model.cpu_h = collections.deque(
        [40 + 30 * math.sin(i / 4) for i in range(80)], maxlen=HIST)
    model.mem_h = collections.deque(
        [model.mem_pct] * 80, maxlen=HIST)
    model.cpu_cores = [50 + 40 * math.sin(i) for i in range(model.ncpu)]
    model.docker_ver = "test"
    model.host = os.uname().nodename
    app = App(model)
    app.compute_visible()
    sel = app.selected()
    if sel:                      # warm the panel-logs cache synchronously
        app.log_cache[sel.id] = get_logs(sel.id, tail=60, timestamps=False)
        app.log_fetch_t[sel.id] = time.monotonic()
    w = int(os.environ.get("COLUMNS", 130))
    h = int(os.environ.get("LINES", 42))
    scr = app.render(w, h)
    sys.stdout.write("\n".join(scr.to_lines()) + RESET + "\n")


def apply_cli_theme():
    """Resolve theme from --theme flag, else saved config, else default."""
    name = None
    for i, a in enumerate(sys.argv):
        if a == "--theme" and i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
        elif a.startswith("--theme="):
            name = a.split("=", 1)[1]
    if name is None:
        name = load_config()
    if name:
        set_theme(name)
        return name in THEMES
    return True


def run_interactive_shell(fd, old_termios, cid, name):
    """Drop out of the TUI, exec an interactive shell in the container,
    then hand control back to the caller (which restores the TUI)."""
    # leave raw mode + alt screen so the child owns the real terminal
    sys.stdout.write(RESET + CUR_SHOW + ALT_OFF)
    sys.stdout.flush()
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_termios)
    except Exception:
        pass
    os.system("clear")
    print(f"\x1b[1;36m▟▙ dtop\x1b[0m  shell into "
          f"\x1b[1m{name}\x1b[0m ({cid})   —  type 'exit' to return\n")
    # prefer bash, fall back to sh
    script = ("if command -v bash >/dev/null 2>&1; then exec bash; "
              "else exec sh; fi")
    try:
        subprocess.call(["docker", "exec", "-it", cid, "sh", "-c", script])
    except Exception as e:
        print(f"shell error: {e}")
        try:
            input("press enter to return…")
        except EOFError:
            pass
    # re-enter raw mode + alt screen (caller repaints)
    try:
        tty.setraw(fd)
    except Exception:
        pass
    sys.stdout.write(ALT_ON + CUR_HIDE)
    sys.stdout.flush()


USAGE = """dtop {ver} - a btop-styled TUI to monitor & manage Docker containers

usage: dtop [options]

options:
  --theme NAME     start with a color theme ({themes})
  --list-themes    list available themes and exit
  --selftest       render one frame to stdout and exit (no TTY needed)
  --version        print version and exit
  -h, --help       show this help and exit

In-app keys: press ? for the full list. q to quit.
Config (persisted theme) lives at ~/.config/dtop/config.
""".format(ver=__version__, themes="/".join(THEME_ORDER))


def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print(USAGE)
        return
    if "--version" in sys.argv:
        print(f"dtop {__version__}")
        return
    if "--list-themes" in sys.argv:
        for n in THEME_ORDER:
            print(n + ("  (current)" if n == (load_config() or "btop") else ""))
        return
    ok = apply_cli_theme()
    if "--selftest" in sys.argv or "--once" in sys.argv:
        selftest()
        return
    if not ok:
        sys.stderr.write(f"dtop: unknown theme; options: "
                         f"{', '.join(THEME_ORDER)}\n")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write("dtop: needs an interactive terminal "
                         "(try --selftest to render one frame)\n")
        sys.exit(1)

    model = Model()
    stop = start_threads(model)
    app = App(model)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    resize_flag = {"v": True}

    def on_winch(signum, frame):
        resize_flag["v"] = True
    try:
        signal.signal(signal.SIGWINCH, on_winch)
    except (ValueError, AttributeError):
        pass

    try:
        tty.setraw(fd)
        bg = Theme.bg
        sys.stdout.write(ALT_ON + CUR_HIDE
                         + f"{CSI}48;2;{bg[0]};{bg[1]};{bg[2]}m" + CLEAR)
        sys.stdout.flush()
        prev_screen = None
        last_host = 0.0
        last_draw = 0.0
        w, h = shutil_size()
        running = True
        while running:
            keys = read_keys(0.12)
            for k in keys:
                if k == "\x03":  # Ctrl-C
                    running = False
                    break
                if not app.handle(k):
                    running = False
                    break
            if not running:
                break
            # terminal-suspending requests (e.g. shell into a container)
            if app.request:
                kind, cid, name = app.request
                app.request = None
                if kind == "shell":
                    run_interactive_shell(fd, old, cid, name)
                    prev_screen = None
                    bg = Theme.bg
                    sys.stdout.write(f"{CSI}48;2;{bg[0]};{bg[1]};{bg[2]}m"
                                     + CLEAR)
                    app.set_toast(f"exited shell: {name}", Theme.accent)
            now = time.time()
            if now - last_host >= 1.0:
                update_host(model)
                last_host = now
            if resize_flag["v"]:
                w, h = shutil_size()
                resize_flag["v"] = False
                prev_screen = None
                sys.stdout.write(CLEAR)
            if app.force_redraw:
                app.force_redraw = False
                prev_screen = None
                # repaint terminal bg to the new theme, then clear
                bg = Theme.bg
                sys.stdout.write(f"{CSI}48;2;{bg[0]};{bg[1]};{bg[2]}m" + CLEAR)
            if now - last_draw >= 0.2 or keys:
                if w >= 40 and h >= 10:
                    scr = app.render(w, h)
                    out = scr.diff(prev_screen)
                    if out:
                        sys.stdout.write(out)
                        sys.stdout.flush()
                    prev_screen = scr
                else:
                    sys.stdout.write(CLEAR + "terminal too small")
                    sys.stdout.flush()
                    prev_screen = None
                last_draw = now
    finally:
        stop.set()
        sys.stdout.write(RESET + CUR_SHOW + ALT_OFF)
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def shutil_size():
    cols = lines = 0
    try:
        sz = os.get_terminal_size()
        cols, lines = sz.columns, sz.lines
    except OSError:
        pass
    if cols <= 0:
        cols = int(os.environ.get("COLUMNS", 0) or 0)
    if lines <= 0:
        lines = int(os.environ.get("LINES", 0) or 0)
    return (cols or 80), (lines or 24)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write(RESET + CUR_SHOW + ALT_OFF)
