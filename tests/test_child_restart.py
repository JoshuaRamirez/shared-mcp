"""End-to-end: the gateway's child dies under live bridges; the gateway restarts it on the SAME
port within one cycle and the bridges read again (it used to fail to rebind its own port with
Errno 48 and loop every 60 s until the gateway itself was restarted)."""
import json, os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); KIT = os.path.join(HERE, "..", "shared_mcp.py")
sys.path.insert(0, os.path.join(HERE, "..")); import shared_mcp
VENV_PY = str(shared_mcp.ensure_venv()); NAME = "sm-child-test"
ok = True
def check(cond, label):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + label)
def bridge():
    p = subprocess.Popen([sys.executable, KIT, "connect", "--name", NAME, "--", VENV_PY, os.path.join(HERE, "fixture_server.py")],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    _reader(p); return p
import queue, threading
_queues = {}
def _reader(p):
    q = _queues[p.pid] = queue.Queue()
    def run():
        for line in iter(p.stdout.readline, b""):
            try: q.put(json.loads(line))
            except ValueError: pass
    threading.Thread(target=run, daemon=True).start()
def rpc(p, msg, timeout=30):
    p.stdin.write((json.dumps(msg) + "\n").encode()); p.stdin.flush()
    if "id" not in msg: return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try: m = _queues[p.pid].get(timeout=max(0.05, deadline - time.time()))
        except queue.Empty: break
        if m.get("id") == msg["id"]: return m
    return {}
def init(p):
    assert "result" in rpc(p, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}, 120)
    rpc(p, {"jsonrpc":"2.0","method":"notifications/initialized"})
def call(p, i):
    r = rpc(p, {"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":"counter","arguments":{}}}, 10)
    return r.get("result", {}).get("content", [{}])[0].get("text", "") if "result" in r else ""
def call_until(p, i, seconds):
    """A session that keeps asking: the first reply carrying a counter, or ''."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        t = call(p, i); i += 1
        if t and "pid=" in t: return t
        time.sleep(0.5)
    return ""

subprocess.run([sys.executable, KIT, "stop", "--name", NAME], capture_output=True)
a = b = None
try:
    a, b = bridge(), bridge(); init(a); init(b)
    r1 = call(a, 10); child = int(re.search(r"pid=(\d+)", r1).group(1))
    spec = json.load(open(os.path.expanduser(f"~/.local/state/shared-mcp/{NAME}/spec.json")))
    gw = shared_mcp.health(spec["port"])
    check(r1.startswith("1 "), f"first read through the gateway: {r1}")
    os.kill(child, 9)
    t0 = time.time()
    # One cycle: the gateway's first restart comes 2 s after the cycle ends; give it that, its
    # child's start-up and one bridge reconnect, well under the 60 s backoff the bug fell into.
    ra = call_until(a, 100, 40); rb = call_until(b, 200, 20); dt = time.time() - t0
    print(f"    after child kill: {ra} | {rb} ({dt:.1f}s)")
    new = re.search(r"pid=(\d+)", ra)
    check(bool(new) and int(new.group(1)) != child, "a new child answers after the old one was killed")
    check(bool(rb) and "pid=" in rb, "the second session reads too")
    check(dt < 40, f"recovered within one cycle ({dt:.1f}s)")
    h = shared_mcp.health(spec["port"])
    check(bool(h) and gw and h.get("pid") == gw.get("pid"), "same gateway process, same port: the child restarted in place")
    check(bool(h) and h.get("child_restarts", 0) >= 1, f"health counts the restart ({h and h.get('child_restarts')})")
    # Stopping the gateway stops its child too: no orphan keeps what the child holds.
    nowchild = int(new.group(1)) if new else None
    subprocess.run([sys.executable, KIT, "stop", "--name", NAME], capture_output=True)
    alive = False
    for _ in range(20):
        try: os.kill(nowchild, 0); alive = True
        except (OSError, TypeError): alive = False; break
        time.sleep(0.25)
    check(nowchild and not alive, "stopping the gateway stops its child (no orphan)")
finally:
    for p in (a, b):
        if p:
            try: p.stdin.close(); p.wait(10)
            except Exception: p.kill()
    subprocess.run([sys.executable, KIT, "stop", "--name", NAME], capture_output=True)
    import shutil
    if not ok:
        lg = os.path.expanduser(f"~/.local/state/shared-mcp/{NAME}/gateway.log")
        if os.path.exists(lg): print("    gateway.log tail:\n      " + "\n      ".join(open(lg).read().splitlines()[-25:]))
    shutil.rmtree(os.path.expanduser(f"~/.local/state/shared-mcp/{NAME}"), ignore_errors=True)
print("ALL PASSED" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
