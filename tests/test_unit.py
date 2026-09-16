"""Fast, gateway-free tests for the bridge's failure paths and the lock (review findings)."""
import io, json, os, sys, tempfile, threading, time, types
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["SHARED_MCP_STATE"] = tempfile.mkdtemp(prefix="sm-unit-")
import shared_mcp as k
ok = True
def check(c, label):
    global ok; ok &= bool(c); print(("ok   " if c else "FAIL ") + label)

# --- 1. unreachable gateway + failing ensure: handle() must emit a JSON-RPC error and never raise
k.wait_ok = lambda port, name, seconds: None
k.gateway_ok = lambda port, name: None
k.service_alive = lambda name: False
def boom(*a, **kw): raise RuntimeError("no daemon here")
k.ensure = boom
spec = {"name": "unit", "port": 1, "command": ["x"], "env": {}, "launcher": __file__}   # port 1: nothing listens
b = k.Bridge(spec); out = io.BytesIO(); b.emit = lambda o: out.write((json.dumps(o) + "\n").encode())
t0 = time.time(); b.handle({"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}}); dt = time.time() - t0
msgs = [json.loads(l) for l in out.getvalue().splitlines()]
check(any(m.get("id") == 7 and "error" in m for m in msgs), f"unreachable gateway: client gets a -32000 error, no exception ({dt:.1f}s)")
check(b.init_done.is_set() and not b.init_inflight, "failed initialize releases pipelined messages (init_done set, inflight cleared)")
# --- 2. reconnect() never raises even when everything inside fails
k.gateway_ok = lambda port, name: {"name": name}
b.sid = "s"; b._session_alive = lambda: (_ for _ in ()).throw(OSError("boom"))
try: b.reconnect(); check(True, "reconnect() swallows internal failures")
except Exception as e: check(False, f"reconnect raised {e!r}")
# --- 3. port is read live from the spec (ensure may move it)
spec["port"] = 4242; check(b.port == 4242, "bridge follows spec['port'] after a move")
# --- 4. lock: waiter that gives up does not remove the holder's lock; stale lock is claimed atomically
import pathlib
lp = pathlib.Path(os.environ["SHARED_MCP_STATE"]) / "t.lock"
with k._Lock(lp, wait_s=0.3) as holder:
    with k._Lock(lp, wait_s=0.3) as waiter:
        check(holder.held and not waiter.held, "second acquirer times out unheld")
    check(lp.exists(), "timed-out waiter did not remove the holder's lock")
check(not lp.exists(), "holder released its lock")
lp.mkdir(); os.utime(lp, (time.time() - 700, time.time() - 700))
with k._Lock(lp, wait_s=2) as l2: check(l2.held, "stale (10 min) lock is claimed by rename and re-taken")
# --- 5. identity: declared command, not the session's resolution; explicit --port honoured
sp = k.build_spec({"name": "u", "port": "50500"}, ["python3", "-m", "nothing"])
check(sp["command"][0] == "python3" and sp["resolved_exe"] and sp["port"] == 50500 and sp["port_explicit"], "spec keeps declared command, records resolved exe separately, honours --port")
# --- 6. free_port_near raises instead of returning a busy port
k.gateway_ok = lambda port, name: None            # undo the stub from test 2
import socket
srvs = []
try:
    base = 47000
    for p in range(base, base + 20):
        s_ = socket.socket(); s_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s_.bind(("127.0.0.1", p)); s_.listen(1); srvs.append(s_)
    try: k.free_port_near(base, "u"); check(False, "free_port_near returned a busy port")
    except RuntimeError: check(True, "free_port_near raises when 20 consecutive ports are busy")
finally:
    for s_ in srvs: s_.close()

# --- 7. replay policy: a mid-request failure on a side-effecting call is reported once, never replayed;
#        the same failure on an idempotent call is retried; a pre-dispatch refusal is retried for both
import socket
k.wait_ok = lambda port, name, seconds: None; k.gateway_ok = lambda port, name: None; k.service_alive = lambda name: False
def mk(exc):
    b2 = k.Bridge({"name": "unit", "port": 1, "command": ["x"], "env": {}, "launcher": __file__}); calls = {"n": 0}
    def post(msg): calls["n"] += 1; raise exc
    b2.post = post; b2.reconnect = lambda: None; got = []; b2.emit = got.append
    return b2, calls, got
b2, calls, got = mk(socket.timeout("timed out"))
b2.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "t", "arguments": {}}})
check(calls["n"] == 1 and len(got) == 1 and "not replayed" in got[0]["error"]["message"], "tools/call + mid-request timeout: posted once, one explicit error, no replay")
b2, calls, got = mk(socket.timeout("timed out"))
b2.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
check(calls["n"] == 3 and len(got) == 1, "tools/list + mid-request timeout: retried to 3 attempts, then one error")
b2, calls, got = mk(ConnectionRefusedError("refused"))
b2.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "t", "arguments": {}}})
check(calls["n"] == 3 and len(got) == 1 and "unreachable" in got[0]["error"]["message"], "tools/call + connection refused (pre-dispatch): retried 3x, then 'unreachable' error")
print("ALL PASSED" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
