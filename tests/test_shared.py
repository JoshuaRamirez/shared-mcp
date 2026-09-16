"""End-to-end: two bridges share one gateway; gateway restart is survived; stop cleans up."""
import json, os, subprocess, sys, time, threading
HERE = os.path.dirname(os.path.abspath(__file__)); KIT = os.path.join(HERE, "..", "shared_mcp.py")
sys.path.insert(0, os.path.join(HERE, "..")); import shared_mcp
VENV_PY = str(shared_mcp.ensure_venv()); NAME = "sm-test"
def bridge():
    env = {**os.environ, "SM_TEST_TOKEN": "secret-xyz"}
    return subprocess.Popen([sys.executable, KIT, "connect", "--name", NAME, "--env", "SM_TEST_TOKEN", "--", VENV_PY, os.path.join(HERE, "fixture_server.py")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
def rpc(p, msg, want_id=True, timeout=90):
    p.stdin.write((json.dumps(msg) + "\n").encode()); p.stdin.flush()
    if not want_id: return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line: raise RuntimeError("bridge closed stdout: " + p.stderr.read().decode()[-800:])
        m = json.loads(line)
        if m.get("id") == msg["id"]: return m
    raise TimeoutError
def init(p):
    r = rpc(p, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}})
    assert "result" in r, r; rpc(p, {"jsonrpc":"2.0","method":"notifications/initialized"}, want_id=False); return r["result"]["serverInfo"]["name"]
def call(p, i): 
    r = rpc(p, {"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":"counter","arguments":{}}}); assert "result" in r, r
    return r["result"]["content"][0]["text"]
def rss_mb(pid): return int(subprocess.run(["ps","-o","rss=","-p",str(pid)],capture_output=True,text=True).stdout.strip() or 0)/1024
ok = True
def check(cond, label):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + label)
subprocess.run([sys.executable, KIT, "stop", "--name", NAME], capture_output=True)
t0=time.time(); a = bridge(); srv = init(a); print(f"first bridge initialised in {time.time()-t0:.1f}s (cold gateway)"); check(srv=="fixture", f"server name via bridge = {srv}")
b = bridge(); init(b)
r1, r2, r3 = call(a, 10), call(b, 11), call(a, 12)
print("   ", r1, "|", r2, "|", r3)
check(r1.startswith("1 ") and r2.startswith("2 ") and r3.startswith("3 "), "counter continues across two bridges => ONE shared server process")
check("token=secret-xyz" in r1, "declared env var forwarded to the shared server")
check(len({x.split("pid=")[1].split()[0] for x in (r1,r2,r3)})==1, "same child pid for all calls")
print(f"    bridge RSS: {rss_mb(a.pid):.0f} MB / {rss_mb(b.pid):.0f} MB")
tl = rpc(a, {"jsonrpc":"2.0","id":13,"method":"tools/list"}); check([t["name"] for t in tl["result"]["tools"]]==["counter"], "tools/list forwarded")
# gateway restart underneath live bridges
spec = json.load(open(os.path.expanduser(f"~/.local/state/shared-mcp/{NAME}/spec.json")))
h = shared_mcp.health(spec["port"]); os.kill(h["pid"], 15); time.sleep(1)
t0=time.time(); r4 = call(a, 14); print(f"    after gateway kill: {r4} ({time.time()-t0:.1f}s)")
check(r4.startswith("1 "), "bridge reconnected to the restarted gateway (counter reset => new child) and replayed the call")
check(call(b, 15).startswith("2 "), "second bridge also reconnected")
a.stdin.close(); b.stdin.close(); a.wait(10); b.wait(10); check(a.returncode==0 and b.returncode==0, "bridges exit 0 on stdin EOF")
# in-place code change (same command path) must restart the gateway on the next connect
fx = os.path.join(HERE, "fixture_server.py"); src = open(fx).read()
open(fx, "w").write(src + "\n# touched by test\n")
try:
    c = bridge(); init(c)
    r5 = call(c, 20); print("    after in-place edit:", r5)
    check(r5.startswith("1 "), "in-place edit of the server file => gateway restarted (counter reset) although the command path was unchanged")
    c.stdin.close(); c.wait(10)
finally:
    open(fx, "w").write(src)
# svc descriptor + status + stop
desc = os.path.expanduser(f"~/.config/svc/services.d/com.shared-mcp.{NAME}.json"); check(os.path.exists(desc), "svc descriptor written")
st = subprocess.run([sys.executable, KIT, "status", "--name", NAME], capture_output=True, text=True); check(st.returncode==0 and '"running": true' in st.stdout, "status reports running")
subprocess.run([sys.executable, KIT, "stop", "--name", NAME], capture_output=True)
check(shared_mcp.health(spec["port"]) is None and not os.path.exists(desc), "stop: gateway gone and descriptor removed")
# fallback path: force daemon failure by pointing state at an unwritable dir
env = {**os.environ, "SHARED_MCP_STATE": "/dev/null/nope"}
p = subprocess.Popen([sys.executable, KIT, "connect", "--name", "sm-fallback", "--", VENV_PY, os.path.join(HERE, "fixture_server.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
try: check(init(p)=="fixture", "FALLBACK: when a daemon cannot be set up, the original stdio server runs directly")
except Exception as e: check(False, f"fallback: {e}")
p.kill()
import shutil  # cleanup state dirs the test created
for n in (NAME, "sm-fallback"): shutil.rmtree(os.path.expanduser(f"~/.local/state/shared-mcp/{n}"), ignore_errors=True)
print("ALL PASSED" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
