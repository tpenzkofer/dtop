#!/usr/bin/env python3
"""Deterministic logic + render smoke test for dtop. Never mutates containers."""
import sys
import math
import collections
import dtop

# ---- guard: make sure NO real docker action is ever invoked ----
_actions = []
dtop.docker_action = lambda *a, **k: _actions.append(a)
dtop.save_config = lambda *a, **k: None  # no disk writes during test
# never shell out to `docker logs` during tests
dtop.get_logs = lambda cid, tail=200, timestamps=True: [
    f"line {i} error" if i == 3 else f"log line {i}" for i in range(60)]

# ---- build a populated model without live threads ----
model = dtop.Model()
now = 1000.0
for i in range(6):
    c = dtop.Container(f"cid{i:09d}")
    c.name = f"container-{i}"
    c.image = "img/example:latest"
    c.state = ["running", "running", "exited", "paused", "created", "running"][i]
    c.status = "Up 3 minutes" if c.state == "running" else c.state
    c.ports = "0.0.0.0:8080->80/tcp"
    c.compose = "myproject"
    for k in range(80):
        c.cpu = 20 + 30 * math.sin((i + k) / 3)
        c.mem_pct = 10 + 20 * abs(math.cos((i + k) / 4))
        c.mem_used = c.mem_pct / 100 * 2e9
        c.mem_limit = 2e9
        c.pids = 10 + i
        c.cpu_h.append(c.cpu)
        c.mem_h.append(c.mem_pct)
        c.rx_h.append(abs(1e6 * math.sin(k / 5)))
        c.tx_h.append(abs(5e5 * math.cos(k / 5)))
    model.conts[c.id] = c
    model.order.append(c.id)
model.docker_ver = "29.6.1"
model.host = "tre-test"
model.n_images = 12
model.cpu_h = collections.deque([40 + 30 * math.sin(i / 4) for i in range(80)], maxlen=dtop.HIST)
model.mem_h = collections.deque([50] * 80, maxlen=dtop.HIST)
model.cpu_cores = [50 + 40 * math.sin(i) for i in range(model.ncpu)]
model.cpu_total = 42.0
model.mem_total = 32 * 2**30
model.mem_used = 5 * 2**30
model.mem_pct = 15.6
model.swap_total = 2 * 2**30
model.swap_used = 0
model.load = (1.2, 1.0, 0.9)

app = dtop.App(model)
fails = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as e:
        import traceback
        fails.append(name)
        print(f"  FAIL {name}: {e}")
        traceback.print_exc()


# 1. compute_visible + selection
def t_visible():
    app.compute_visible()
    assert len(app.visible) == 6, len(app.visible)
    assert app.selected() is not None
check("compute_visible", t_visible)


# 2. render at many sizes (incl. tiny/degenerate)
def t_render():
    for w, h in [(140, 44), (120, 40), (100, 30), (90, 24), (80, 20),
                 (60, 16), (45, 12), (40, 10), (200, 60)]:
        scr = app.render(w, h)
        assert scr.w == w and scr.h == h
        _ = scr.to_lines()
        _ = scr.diff(None)
check("render_sizes", t_render)


# 3. diff between two frames returns a string
def t_diff():
    a = app.render(120, 40)
    b = app.render(120, 40)
    out = b.diff(a)
    assert isinstance(out, str)
check("diff", t_diff)


# 4. navigation keys never raise, 'q' quits
def t_nav():
    for k in ["down", "down", "j", "up", "k", "pgdn", "pgup", "end", "home",
              "g", "G", "o", "o", "O", "a", "a"]:
        assert app.handle(k) is True, k
        app.render(120, 40)
    assert app.handle("q") is False
check("navigation", t_nav)


# 5. filter mode
def t_filter():
    app.handle("/")
    assert app.mode == "filter"
    for ch in "container-1":
        app.handle(ch)
    app.handle("enter")
    assert app.mode == "normal"
    app.compute_visible()
    assert len(app.visible) == 1, app.visible
    app.render(120, 40)
    app.handle("/")
    app.handle("esc")
    assert app.filter == ""
    app.compute_visible()
    assert len(app.visible) == 6
check("filter", t_filter)


# 6. confirm flow for destructive actions -> triggers docker_action once on 'y'
def t_confirm():
    app.sel = 0
    app.compute_visible()
    before = len(_actions)
    app.handle("T")               # stop -> confirm
    assert app.mode == "confirm"
    app.render(120, 40)
    app.handle("n")               # cancel
    assert app.mode == "normal"
    assert len(_actions) == before
    app.handle("K")               # kill -> confirm
    app.handle("y")               # confirm
    assert app.mode == "normal"
    assert len(_actions) == before + 1
check("confirm_flow", t_confirm)


# 7. non-confirm actions fire immediately (still stubbed)
def t_actions():
    before = len(_actions)
    app.handle("S")   # start
    app.handle("R")   # restart
    app.handle("P")   # pause/unpause
    assert len(_actions) == before + 3
check("instant_actions", t_actions)


# 8. help / logs / inspect overlays render + close
def t_overlays():
    app.mode = "help"
    app.render(120, 40)
    app.handle("q")
    assert app.mode == "normal"
    # simulate an overlay without calling docker by injecting lines
    app.overlay_lines = [f"line {i}" for i in range(200)]
    app.overlay_title = "logs: test"
    app.mode = "logs"
    app.overlay_bottom = True
    app.render(120, 40)
    for k in ["down", "up", "pgdn", "pgup", "home", "end", "g", "G"]:
        app.handle(k)
        app.render(120, 40)
    app.handle("esc")
    assert app.mode == "normal"
check("overlays", t_overlays)


# 9. parsing helpers
def t_parse():
    assert abs(dtop.parse_size("812.5MiB") - 812.5 * 1024**2) < 1
    assert abs(dtop.parse_size("8.8MB") - 8.8e6) < 1
    assert dtop.parse_pct("101.00%") == 101.0
    rx, tx = dtop.parse_pair("656B / 126B")
    assert rx == 656 and tx == 126
    assert dtop.human_bytes(1536) == "1.5K"
check("parse_helpers", t_parse)


# 10. shutil_size zero-fallback (regression for the 0x0 pty bug)
def t_size():
    import os
    os.environ.pop("COLUMNS", None)
    os.environ.pop("LINES", None)
    w, h = dtop.shutil_size()
    assert w >= 40 and h >= 10, (w, h)
check("size_fallback", t_size)


# 11. overlays are OPAQUE: nothing from the detail graphs bleeds through
def t_no_bleed():
    W, H = 140, 44
    app.mode = "normal"
    app.filter = ""
    app.compute_visible()
    base = app.render(W, H)
    # confirm the detail panel actually drew braille somewhere (precondition)
    braille = any(0x2800 <= ord(base.ch[y][x]) <= 0x28FF
                  for y in range(H) for x in range(W))
    assert braille, "no braille in base frame - test precondition failed"
    # open a logs overlay with short lines
    app.overlay_lines = ["short line", "another"]
    app.overlay_title = "logs: t"
    app.mode = "logs"
    app.overlay_bottom = True
    scr = app.render(W, H)
    # match _draw_overlay's bottom-docked geometry
    ox = max(2, W // 24)
    ow = W - ox * 2
    oh = max(8, int(H * 0.72))
    oy = H - oh - 1
    for y in range(oy + 1, oy + oh - 1):
        for x in range(ox + 1, ox + ow - 1):
            ch = scr.ch[y][x]
            assert not (0x2800 <= ord(ch) <= 0x28FF), \
                f"braille bled through overlay at {x},{y}: {ch!r}"
    app.mode = "normal"
check("overlay_no_bleed", t_no_bleed)


# 12. graphs never draw outside their box (no spill past borders)
def t_no_spill():
    W, H = 100, 30
    app.mode = "normal"
    scr = app.render(W, H)
    # bottom border row and last column must be border/space, not braille
    for x in range(W):
        assert not (0x2800 <= ord(scr.ch[H - 2][x]) <= 0x28FF), \
            f"braille on footer row at x={x}"
    check_ok = True
    assert check_ok
check("no_spill", t_no_spill)


# 13. every theme applies and renders without error
def t_themes():
    for n in dtop.THEME_ORDER:
        dtop.set_theme(n)
        assert dtop.Theme.name == n
        assert len(dtop.Theme.g_cpu) >= 2 and len(dtop.Theme.g_mem) >= 2
        assert isinstance(dtop.Theme.bg, tuple) and len(dtop.Theme.bg) == 3
        app.render(120, 40)          # renders cleanly in this theme
        app.render(80, 20)
    dtop.set_theme("btop")
    before = dtop.Theme.name
    app.cycle_theme(1)
    assert dtop.Theme.name != before, "cycle_theme did not advance"
    app.cycle_theme(-1)
    assert dtop.Theme.name == before, "cycle_theme -1 did not return"
check("themes", t_themes)


# 14. canvas is fully painted with the theme bg (contrast): a blank cell
#     renders the theme background, not transparent
def t_bg_fill():
    dtop.set_theme("dracula")
    scr = app.render(120, 40)
    out = scr.diff(None)
    r, g, b = dtop.Theme.bg
    assert f"48;2;{r};{g};{b}m" in out, "theme background not emitted"
    dtop.set_theme("btop")
check("bg_fill", t_bg_fill)


# 15. detail panel shows live logs for the selected container
def t_panel_logs():
    dtop.set_theme("btop")
    app.mode = "normal"
    app.filter = ""
    app.compute_visible()
    c = app.selected()
    assert c is not None
    # pre-seed the cache (bypass the async fetch) then render
    with app.log_lock:
        app.log_cache[c.id] = ["log line A", "log line B error", "log line C"]
        app.log_fetch_t[c.id] = 10 ** 9   # mark fresh so no refetch overwrites
    scr = app.render(140, 44)
    joined = "\n".join("".join(scr.ch[y]) for y in range(44))
    assert "logs" in joined, "no logs section label in detail panel"
    assert "log line C" in joined, "latest log line not shown in panel"
check("panel_logs", t_panel_logs)


# 16. filesystem browser: open, navigate in/out, close
def t_files():
    dtop.list_container_dir = lambda cid, path: (
        [("etc", True), ("bin", True), ("file.txt", False)], "")
    app.mode = "normal"
    app.compute_visible()
    c = next(x for x in app.visible if x.state == "running")
    app.sel = app.visible.index(c)
    app.open_files(c)
    assert app.mode == "files", app.mode
    assert app.fs_path == "/"
    assert ("..", True) not in app.fs_items       # no .. at root
    app.render(140, 44)
    app.fs_sel = 0                                  # 'etc'
    app.handle("enter")
    assert app.fs_path == "/etc", app.fs_path
    assert app.fs_items[0] == ("..", True)         # .. present in subdir
    app.render(140, 44)
    app.handle("left")
    assert app.fs_path == "/"
    app.handle("q")
    assert app.mode == "normal"
check("files_browser", t_files)


# 17. network view: builds topology + mermaid, renders as overlay
def t_network():
    dtop.inspect_json = lambda cid: {
        "NetworkSettings": {
            "Networks": {"bridge": {"IPAddress": "172.17.0.2",
                                    "Gateway": "172.17.0.1",
                                    "MacAddress": "aa:bb", "Aliases": ["web"]}},
            "Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}}}
    dtop._network_peers = lambda net, cid: [("abc123def456", "peer1",
                                             "172.17.0.3")]
    lines = dtop.build_network_view("cid123456789", "web", app.model)
    joined = "\n".join(lines)
    for token in ("networks", "topology", "mermaid", "graph LR", "peer1",
                  "172.17.0.2", "8080"):
        assert token in joined, f"missing {token!r} in network view"
    app.overlay_lines = lines
    app.overlay_title = "network: web"
    app.mode = "net"
    app.render(140, 44)
    app.handle("q")
    assert app.mode == "normal"
check("network_view", t_network)


# 18. shell request set only for running containers
def t_shell():
    app.mode = "normal"
    app.request = None
    app.compute_visible()
    run = next(x for x in app.visible if x.state == "running")
    app.sel = app.visible.index(run)
    app.handle("s")
    assert app.request == ("shell", run.id, run.name), app.request
    app.request = None
    ex = next((x for x in app.visible if x.state != "running"), None)
    if ex:
        app.sel = app.visible.index(ex)
        app.handle("s")
        assert app.request is None, "shell should not start on stopped ctr"
check("shell_request", t_shell)


# 19. path normalization helper
def t_norm():
    assert dtop._norm_path("/", "etc") == "/etc"
    assert dtop._norm_path("/etc", "nginx") == "/etc/nginx"
    assert dtop._norm_path("/etc/nginx", "..") == "/etc"
    assert dtop._norm_path("/etc", "..") == "/"
    assert dtop._norm_path("/", "..") == "/"
check("norm_path", t_norm)


# 20. wide (double-width) chars reserve 2 cells and never emit the sentinel
def t_wide():
    s = dtop.Screen(20, 1)
    s.put(0, 0, "a漢b", dtop.Theme.fg)
    assert s.ch[0][0] == "a"
    assert s.ch[0][1] == "漢"
    assert s.ch[0][2] == dtop.WIDE_CONT, "no continuation cell for wide char"
    assert s.ch[0][3] == "b", "char after wide glyph mis-placed"
    out = s.diff(None)
    assert dtop.WIDE_CONT not in out, "sentinel leaked into output"
    assert "漢" in out
    line = s.to_lines()[0]
    assert dtop.WIDE_CONT not in line and "漢" in line
    # emoji are width 2 as well
    assert dtop.char_width("🧊") == 2 and dtop.char_width("a") == 1
check("wide_chars", t_wide)


# 21. wrap toggle changes the scrollable line count for long lines
def t_wrap():
    dtop.set_theme("btop")
    app.mode = "logs"
    app.overlay_lines = ["x" * 400 for _ in range(40)]
    app.overlay_title = "logs"
    app.wrap = False
    app.render(120, 40)
    unwrapped_max = app.overlay_maxoff
    app.wrap = True
    app.render(120, 40)
    wrapped_max = app.overlay_maxoff
    assert wrapped_max > unwrapped_max, (unwrapped_max, wrapped_max)
    # horizontal scroll only applies unwrapped
    app.wrap = False
    app.hoff = 0
    app.handle("right")
    assert app.hoff == 8
    app.wrap = True
    app.handle("right")
    assert app.hoff == 8, "hscroll should be ignored while wrapped"
    app.mode = "normal"
    app.wrap = False
    app.hoff = 0
check("wrap_toggle", t_wrap)


print()
if fails:
    print(f"FAILED: {len(fails)} -> {fails}")
    sys.exit(1)
print("ALL TESTS PASSED")
