"""Exercise the 'no service manager' supervision path (Linux without systemd, Windows) on this
machine by forcing the kit off launchd: detached process + pid file, ensure, health, stop."""
import json, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["SHARED_MCP_STATE"] = tempfile.mkdtemp(prefix="sm-detached-")   # scoped label/port: never touches production
import shared_mcp as k
k.IS_MAC = False; k._systemd_user_available = lambda: False               # -> start_detached / stop_detached
k.VENV = k.Path(os.path.expanduser("~/.local/state/shared-mcp/venv"))       # reuse the built venv (test speed)
k.STATE_ROOT.mkdir(parents=True, exist_ok=True)
ok = True
def check(c, label):
    global ok; ok &= bool(c); print(("ok   " if c else "FAIL ") + label)
py = str(k.venv_python()); fixture = os.path.join(HERE, "fixture_server.py")
spec = k.build_spec({"name": "sm-detached"}, [py, fixture])
t0 = time.time(); h = k.ensure(spec, wait=60); dt = time.time() - t0
check(h and h.get("name") == "sm-detached", f"detached gateway came up via pid file in {dt:.1f}s")
pidf = k.state_dir("sm-detached") / "gateway.pid"
check(pidf.exists() and k.service_alive("sm-detached"), "pid file written and service_alive() sees the process")
check(not (k.HOME / "Library/LaunchAgents" / f"{k.label('sm-detached')}.plist").exists(), "no launchd plist was created on this path")
# ensure again: healthy + same -> no restart (pid unchanged)
pid1 = int(pidf.read_text()); k.ensure(spec); check(int(pidf.read_text()) == pid1, "second ensure is a no-op on a healthy detached gateway")
# kill the process: no supervisor restarts it, but ensure must revive it
os.kill(pid1, 9); time.sleep(1)
check(not k.gateway_ok(spec["port"], "sm-detached"), "after SIGKILL nothing restarts it (no service manager) — expected")
h2 = k.ensure(spec, wait=60); check(h2 is not None and int(pidf.read_text()) != pid1, "ensure revives the dead detached gateway with a new pid")
k.stop_gateway("sm-detached"); time.sleep(0.5)
check(not k.gateway_ok(spec["port"], "sm-detached") and not pidf.exists(), "stop: process gone, pid file removed")
import shutil; shutil.rmtree(os.environ["SHARED_MCP_STATE"], ignore_errors=True)
print("ALL PASSED" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
