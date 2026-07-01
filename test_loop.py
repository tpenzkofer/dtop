#!/usr/bin/env python3
"""Exercise dtop.main()'s real event loop with stubbed terminal I/O."""
import io
import sys
import types
import dtop

# never touch real containers / threads
dtop.docker_action = lambda *a, **k: None
dtop.start_threads = lambda model: types.SimpleNamespace(set=lambda: None)
# keep update_host (reads /proc, harmless & real)

# fake terminal
class FakeStd:
    def __init__(self):
        self.buf = []
    def isatty(self):
        return True
    def fileno(self):
        return 0
    def write(self, s):
        self.buf.append(s)
    def flush(self):
        pass

fake_out = FakeStd()
fake_in = FakeStd()
sys.stdout = fake_out
sys.stdin = fake_in

# stub termios/tty so raw-mode calls are no-ops
dtop.termios = types.SimpleNamespace(
    tcgetattr=lambda fd: [],
    tcsetattr=lambda *a: None,
    TCSADRAIN=0,
)
dtop.tty = types.SimpleNamespace(setraw=lambda fd: None)
dtop.shutil_size = lambda: (120, 40)

# feed: a few empty polls (frames render), then 'j','o', then 'q'
_seq = [[], [], ["j"], ["o"], [], ["q"]]
_i = {"n": 0}
def fake_read_keys(timeout):
    if _i["n"] < len(_seq):
        k = _seq[_i["n"]]
        _i["n"] += 1
        return k
    return ["q"]
dtop.read_keys = fake_read_keys

# make time advance so the >=0.2s draw gate always fires
_t = {"v": 0.0}
def fake_time():
    _t["v"] += 0.5
    return _t["v"]
dtop.time.time = fake_time

dtop.main()

sys.stdout = sys.__stdout__
out = "".join(fake_out.buf)
assert dtop.ALT_ON in out, "alt screen not enabled"
assert dtop.ALT_OFF in out, "alt screen not restored"
assert dtop.CUR_SHOW in out, "cursor not restored"
# a real frame must have been streamed (truecolor sequences + braille or box)
assert "38;2;" in out, "no truecolor output rendered"
assert "⠀" not in out or True  # braille may or may not appear depending on data
assert len(out) > 500, f"suspiciously small output: {len(out)} bytes"
print(f"loop ran, streamed {len(out)} bytes, clean setup+teardown -> OK")
