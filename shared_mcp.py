#!/usr/bin/env python3
"""shared-mcp — run a stdio MCP server ONCE per machine; every Claude Code session shares it.

Claude Code spawns a private copy of each stdio MCP server per session. With
many sessions that is many copies, and for a server that owns state (a database,
a lock) the copies fight. This file makes sharing the DEFAULT for a plugin while
staying safe on any machine:

    .mcp.json:  "command": "python3",
                "args": ["${CLAUDE_PLUGIN_ROOT}/shared_mcp.py", "connect", "--name", "my-server",
                         "--env", "MY_TOKEN", "--", "python3", "${CLAUDE_PLUGIN_ROOT}/server.py"]

`connect` (per session, stdlib only, ~12 MB):
  1. If a gateway for --name is already answering on this machine, bridge to it.
  2. Otherwise build a small venv (uv, or python -m venv) with the `mcp` package,
     register a background gateway (launchd on macOS, systemd --user on Linux,
     detached process elsewhere) that runs the ORIGINAL command exactly once and
     serves it over streamable HTTP on 127.0.0.1, wait for it, then bridge.
  3. If any of that is impossible (no venv, no network, odd OS) → exec the original
     command directly. Worst case is exactly today's behaviour, never a broken server.
  The bridge reconnects and replays when the gateway restarts (plugin upgrade, crash).

Flags on connect: --env KEY (forward a declared env var; repeatable), --port P, --cwd DIR,
  --serialize (one tool call at a time, for servers written for a single client),
  --per-session (keep the launcher but never share: cwd-dependent or browser-attached servers).
Other verbs: ensure|status|stop|logs --name N ; gateway --spec FILE (internal).
State lives in ~/.local/state/shared-mcp/<name>/ (spec.json 0600, gateway.log).
Registers with `svc` (~/.config/svc/services.d) when that console exists.
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import html as _html
import http.client
import json
import shlex
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

VERSION = "0.3.1"
HOME = Path.home()
STATE_ROOT = Path(os.environ.get("SHARED_MCP_STATE") or
                  (Path(os.environ["LOCALAPPDATA"]) / "shared-mcp" if os.name == "nt" and os.environ.get("LOCALAPPDATA")
                   else HOME / ".local" / "state" / "shared-mcp"))
VENV = STATE_ROOT / "venv"
MCP_REQUIREMENT = "mcp>=1.10,<2"
IS_MAC, IS_WIN = platform.system() == "Darwin", os.name == "nt"


def log(*a: object) -> None:
    print("[shared-mcp]", *a, file=sys.stderr, flush=True)


# ----------------------------------------------------------------- spec / paths
def state_dir(name: str) -> Path:
    d = STATE_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def owner_tag() -> str:
    """Per-user identity; two users on one machine share 127.0.0.1 and must not share gateways."""
    try:
        return f"{os.getuid()}"
    except AttributeError:                 # Windows
        return os.environ.get("USERNAME", "user")


def stable_port(name: str) -> int:
    return 47800 + zlib.crc32(f"{owner_tag()}:{name}{_SCOPE}".encode()) % 1000


def free_port_near(port: int, name: str) -> int:
    """If the hashed port is held by something that is not our gateway, walk forward to a free one."""
    import socket
    for candidate in range(port, port + 20):
        if gateway_ok(candidate, name):
            return candidate
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", candidate)) != 0:
                return candidate
    raise RuntimeError(f"no free loopback port near {port}")


def load_spec(name: str) -> dict | None:
    p = state_dir(name) / "spec.json"
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def save_spec(spec: dict) -> Path:
    p = state_dir(spec["name"]) / "spec.json"
    p.write_text(json.dumps(spec, indent=2) + "\n")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


# ----------------------------------------------------------------- health
def health(port: int, timeout: float = 1.5) -> dict | None:
    """The gateway's identity card, or None. Identity (name) is checked by callers so a
    foreign process on the port is never mistaken for ours."""
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        c.request("GET", "/health")
        r = c.getresponse()
        body = r.read()
        c.close()
        if r.status == 200:
            return json.loads(body)
    except Exception:  # noqa: BLE001
        return None
    return None


def gateway_ok(port: int, name: str) -> dict | None:
    h = health(port)
    return h if h and h.get("name") == name and str(h.get("owner")) == owner_tag() else None


def wait_ok(port: int, name: str, seconds: float) -> dict | None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        h = gateway_ok(port, name)
        if h:
            return h
        time.sleep(0.4)
    return None


# ----------------------------------------------------------------- venv
def ensure_venv() -> Path:
    py = venv_python()
    stamp = VENV / ".requirement"
    if py.exists() and stamp.exists() and stamp.read_text().strip() == MCP_REQUIREMENT:
        return py
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    with _Lock(STATE_ROOT / "venv.lock"):            # the venv is machine-wide: one builder at a time across names
        if py.exists() and stamp.exists() and stamp.read_text().strip() == MCP_REQUIREMENT:
            return py
        return _build_venv(py, stamp)


def _build_venv(py: Path, stamp: Path) -> Path:
    log(f"building gateway environment in {VENV} ({MCP_REQUIREMENT})")
    shutil.rmtree(VENV, ignore_errors=True)
    uv = shutil.which("uv")
    if uv:
        subprocess.run([uv, "venv", "-q", str(VENV)], check=True, stdout=sys.stderr, stderr=sys.stderr)
        subprocess.run([uv, "pip", "install", "-q", "--python", str(py), MCP_REQUIREMENT], check=True, stdout=sys.stderr, stderr=sys.stderr)
    else:
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True, stdout=sys.stderr, stderr=sys.stderr)
        subprocess.run([str(py), "-m", "pip", "install", "-q", MCP_REQUIREMENT], check=True, stdout=sys.stderr, stderr=sys.stderr)
    stamp.write_text(MCP_REQUIREMENT + "\n")
    return py


# ----------------------------------------------------------------- supervision
_SCOPE = "" if str(STATE_ROOT) == str(HOME / ".local" / "state" / "shared-mcp") else "." + hashlib.sha256(str(STATE_ROOT).encode()).hexdigest()[:6]


def label(name: str) -> str:
    return f"com.shared-mcp.{name}{_SCOPE}"


def gateway_argv(spec: dict) -> list[str]:
    return [str(venv_python()), str(Path(spec["launcher"]).resolve()), "gateway", "--spec", str(state_dir(spec["name"]) / "spec.json")]


def _launchctl(*args: str) -> tuple[int, str]:
    p = subprocess.run(["launchctl", *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def start_mac(spec: dict) -> None:
    name, lab = spec["name"], label(spec["name"])
    domain = f"gui/{os.getuid()}"
    plist = HOME / "Library" / "LaunchAgents" / f"{lab}.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    _launchctl("bootout", f"{domain}/{lab}")
    for _ in range(120):                      # graceful shutdown may take a while (in-flight calls); wait up to 30 s
        if _launchctl("print", f"{domain}/{lab}")[0] != 0:
            break
        time.sleep(0.25)
    logp = state_dir(name) / "gateway.log"
    argv = gateway_argv(spec)
    xml = "".join(f"<string>{_html.escape(a, quote=False)}</string>" for a in argv)
    path_env = spec.get("path") or os.environ.get("PATH", "/usr/bin:/bin")   # the session's PATH, venv NOT prepended
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{lab}</string>
  <key>ProgramArguments</key><array>{xml}</array>
  <key>WorkingDirectory</key><string>{_html.escape(spec.get("cwd") or str(HOME), quote=False)}</string>
  <key>ProcessType</key><string>Interactive</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>{logp}</string>
  <key>StandardErrorPath</key><string>{logp}</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>{_html.escape(path_env, quote=False)}</string>
    <key>HOME</key><string>{_html.escape(str(HOME), quote=False)}</string>
  </dict>
</dict></plist>
""")
    for i in range(20):                       # bootstrap right after bootout can fail with EIO
        rc, out = _launchctl("bootstrap", domain, str(plist))
        if rc == 0:
            break
        if i == 19:
            raise RuntimeError(f"launchctl bootstrap failed: {out.strip()}")
        time.sleep(0.5)
    _launchctl("kickstart", "-k", f"{domain}/{lab}")


def stop_mac(name: str) -> None:
    _launchctl("bootout", f"gui/{os.getuid()}/{label(name)}")
    (HOME / "Library" / "LaunchAgents" / f"{label(name)}.plist").unlink(missing_ok=True)


def _systemd_user_available() -> bool:
    return bool(shutil.which("systemctl")) and subprocess.run(["systemctl", "--user", "is-system-running"], capture_output=True).returncode in (0, 1)


def start_systemd(spec: dict) -> None:
    unit_dir = HOME / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit = unit_dir / f"shared-mcp-{spec['name']}.service"
    logp = state_dir(spec["name"]) / "gateway.log"
    unit.write_text(f"""[Unit]
Description=shared-mcp gateway: {spec['name']}
[Service]
ExecStart={' '.join(shlex.quote(a) for a in gateway_argv(spec))}
WorkingDirectory={spec.get('cwd') or HOME}
Restart=always
RestartSec=3
StandardOutput=append:{logp}
StandardError=append:{logp}
[Install]
WantedBy=default.target
""")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", unit.name], check=True)
    subprocess.run(["systemctl", "--user", "restart", unit.name], check=True)


def stop_systemd(name: str) -> None:
    unit = f"shared-mcp-{name}.service"
    subprocess.run(["systemctl", "--user", "disable", "--now", unit], capture_output=True)
    (HOME / ".config" / "systemd" / "user" / unit).unlink(missing_ok=True)


def start_detached(spec: dict) -> None:
    """No service manager: detached process + pid file. `ensure` restarts it when dead."""
    stop_detached(spec["name"])
    logp = state_dir(spec["name"]) / "gateway.log"
    kw: dict = {"stdout": open(logp, "ab"), "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL, "cwd": spec.get("cwd") or None}
    if IS_WIN:
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen(gateway_argv(spec), **kw)
    (state_dir(spec["name"]) / "gateway.pid").write_text(str(p.pid))


def _pid_is_gateway(pid: int) -> bool:
    """A pid file can go stale and the OS can reuse the number; only trust a pid whose
    command line is one of our gateways."""
    try:
        if IS_WIN:
            out = subprocess.run(["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"], capture_output=True, text=True).stdout
        else:
            out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
        return "shared_mcp.py" in out and "gateway" in out
    except Exception:  # noqa: BLE001
        return False


def stop_detached(name: str) -> None:
    pidf = state_dir(name) / "gateway.pid"
    try:
        pid = int(pidf.read_text())
        if not _pid_is_gateway(pid):
            raise ProcessLookupError(pid)
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, 15)
    except Exception:  # noqa: BLE001
        pass
    pidf.unlink(missing_ok=True)


def service_alive(name: str) -> bool:
    """Is a gateway process registered and alive (even if not yet answering)? Used to wait
    for a starting gateway instead of tearing it down and starting again."""
    try:
        if IS_MAC:
            rc, out = _launchctl("print", f"gui/{os.getuid()}/{label(name)}")
            return rc == 0 and re.search(r"^\s*pid = \d+", out, re.M) is not None
        if not IS_WIN and _systemd_user_available():
            return subprocess.run(["systemctl", "--user", "is-active", "--quiet", f"shared-mcp-{name}.service"]).returncode == 0
        pid = int((state_dir(name) / "gateway.pid").read_text())
        os.kill(pid, 0)
        return _pid_is_gateway(pid)
    except Exception:  # noqa: BLE001
        return False


def start_gateway(spec: dict) -> None:
    if IS_MAC:
        start_mac(spec)
    elif not IS_WIN and _systemd_user_available():
        start_systemd(spec)
    else:
        start_detached(spec)


def stop_gateway(name: str) -> None:
    if IS_MAC:
        stop_mac(name)
    elif not IS_WIN and _systemd_user_available():
        stop_systemd(name)
    stop_detached(name)
    spec = load_spec(name)
    if spec:
        for _ in range(20):
            if not health(spec["port"]):
                break
            time.sleep(0.25)
    desc = HOME / ".config" / "svc" / "services.d" / f"{label(name)}.json"
    desc.unlink(missing_ok=True)


def write_svc_descriptor(spec: dict) -> None:
    d = HOME / ".config" / "svc" / "services.d"
    if not d.is_dir():
        return
    me = f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(spec['launcher']).resolve()))}"
    (d / f"{label(spec['name'])}.json").write_text(json.dumps({
        "label": label(spec["name"]), "name": f"mcp-{spec['name']}",
        "purpose": f"shared-mcp gateway for the '{spec['name']}' MCP server: runs `{' '.join(spec['command'])}` once and serves it to every Claude session over HTTP.",
        "source": str(Path(spec["launcher"]).resolve().parent), "docs": str(Path(spec["launcher"]).resolve()),
        "health": {"url": f"http://127.0.0.1:{spec['port']}/health", "expect": [200]},
        "manage": {"status": f"{me} status --name {spec['name']}", "logs": f"{me} logs --name {spec['name']}",
                   "stop": f"{me} stop --name {spec['name']}", "start": f"{me} ensure --name {spec['name']}",
                   "restart": f"{me} stop --name {spec['name']} && {me} ensure --name {spec['name']}"},
        "registered_at": time.strftime("%Y-%m-%d"),
    }, indent=2) + "\n")


def rotate_log(name: str) -> None:
    logp = state_dir(name) / "gateway.log"
    try:
        if logp.stat().st_size > 5_000_000:
            with open(logp, "rb") as fh:
                fh.seek(-2_000_000, os.SEEK_END)
                tail = fh.read().split(b"\n", 1)[-1]
            logp.write_bytes(tail)
    except OSError:
        pass


_HELD_LOCKS: set = set()


def _release_held_locks() -> None:
    for pth in list(_HELD_LOCKS):
        try: Path(pth).rmdir()
        except OSError: pass


atexit.register(_release_held_locks)


class _Lock:
    """mkdir lock so sessions restored in a batch do not race the bootstrap.
    Holders refresh the mtime between long steps (touch()); a lock idle for 10 minutes is
    stale and is claimed atomically by rename. A waiter that gives up proceeds WITHOUT the
    lock and never removes someone else's."""
    def __init__(self, path: Path, wait_s: float = 300):
        self.path, self.wait_s, self.held = path, wait_s, False
    def touch(self):
        if self.held:
            try: os.utime(self.path)
            except OSError: pass
    def __enter__(self):
        deadline = time.time() + self.wait_s
        while time.time() < deadline:
            try:
                self.path.mkdir(); self.held = True; _HELD_LOCKS.add(str(self.path)); return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 600:
                        stale = self.path.with_name(f"{self.path.name}.stale.{os.getpid()}")
                        os.rename(self.path, stale)      # atomic: exactly one waiter wins the claim
                        stale.rmdir(); continue
                except OSError:
                    pass
                time.sleep(0.25)
        log(f"could not take {self.path.name} within {self.wait_s:.0f}s; proceeding unlocked")
        return self
    def __exit__(self, *a):
        if self.held:
            _HELD_LOCKS.discard(str(self.path))
            try: self.path.rmdir()
            except OSError: pass


def _flapping(name: str, spec: dict) -> bool:
    """True if this exact definition was replaced by another within the last 10 minutes —
    two sessions declaring different env/commands would otherwise restart the gateway forever."""
    hist_p = state_dir(name) / "spec-history.json"
    key = json.dumps([spec["command"], spec["env"], spec.get("fingerprint"), spec.get("launcher")], sort_keys=True)
    try:
        hist = json.loads(hist_p.read_text())
    except Exception:  # noqa: BLE001
        hist = []
    now = time.time()
    hist = [h for h in hist if now - h["t"] < 600][-6:]
    seen_recently = any(h["k"] == key for h in hist) and any(h["k"] != key for h in hist)
    hist.append({"k": key, "t": now})
    hist_p.write_text(json.dumps(hist))
    return seen_recently


def ensure(spec: dict, wait: float = 60, restart_ok: bool = True) -> dict:
    """restart_ok=False (bridges reconnecting): revive a dead gateway, adopt a live one, never
    replace a live one — a still-open old session must not downgrade an upgraded gateway."""
    with _Lock(state_dir(spec["name"]) / "ensure.lock") as lk:
        return _ensure_locked(spec, wait, restart_ok, lk)


def _ensure_locked(spec: dict, wait: float, restart_ok: bool, lk: "_Lock") -> dict:
    """Make the gateway for spec run with THIS spec; returns its health card or raises."""
    name = spec["name"]
    current = load_spec(name)
    if not restart_ok and current and Path(current.get("launcher", "")).exists():
        # A reconnecting bridge revives with the NEWEST definition on disk, never its own
        # possibly-stale one (an old session must not downgrade an upgrade). Port follows.
        spec.clear(); spec.update(current)
    if current and current.get("port") and not spec.get("port_explicit"):
        spec["port"] = current["port"]                          # keep the port a running gateway already uses
    if not Path(spec.get("launcher", "")).exists():
        raise RuntimeError(f"launcher {spec.get('launcher')} no longer exists (plugin removed or upgraded); start a new session")
    running = gateway_ok(spec["port"], name)
    if not running and service_alive(name):
        # Registered and alive but not answering yet: STARTING (child init, restart backoff) —
        # or stuck (port taken, uvicorn cannot bind). Give it a bounded grace, then treat as dead.
        running = wait_ok(spec["port"], name, min(wait, 20))
    if not running:
        spec["port"] = free_port_near(spec["port"], name)      # hashed port held by a stranger? step forward
    port = spec["port"]
    same = (current and all(current.get(k) == spec.get(k) for k in ("command", "env", "launcher", "fingerprint", "serialize", "cwd")))
    if running and same:
        return running
    if running and not restart_ok:
        return running                                          # a live gateway wins over a reconnecting old bridge
    if running and not spec.get("resolved", True):
        # This session's PATH cannot even find the executable; a healthy gateway started by a
        # better-equipped session must not be replaced by a definition that cannot run.
        log(f"gateway '{name}' is healthy; keeping it (this session cannot resolve {spec['command'][0]!r})")
        return running
    if running and not same and _flapping(name, spec):
        log(f"gateway '{name}': sessions disagree about its definition (env or command); keeping the running one. "
            f"Give each variant its own --name, or align the declared env.")
        return running
    if running and not same:
        why = "code changed" if current and current.get("command") == spec["command"] and current.get("env") == spec["env"] else "definition changed"
        log(f"gateway '{name}': {why}; restarting with the current version")
    elif current is None:
        log(f"first run for '{name}': installing a shared background service so every Claude session uses ONE "
            f"copy of this server. It creates {STATE_ROOT}/venv and {state_dir(name)}, listens on 127.0.0.1:{port} only, "
            f"and is kept alive by {'launchd' if IS_MAC else 'systemd --user' if (not IS_WIN and _systemd_user_available()) else 'a detached process'}. "
            f"Opt out: SHARED_MCP_DISABLE=1, or `python3 {Path(__file__).name} stop --name {name}`.")
    else:
        log(f"starting gateway '{name}' on 127.0.0.1:{port}")
    ensure_venv(); lk.touch()
    rotate_log(name)
    save_spec(spec)
    try:
        start_gateway(spec); lk.touch()
    except Exception as e:  # noqa: BLE001
        # e.g. bootstrap raced a graceful shutdown; if a gateway is alive anyway, adopt it
        # rather than falling back to a private copy that would fight the shared one.
        h = wait_ok(port, name, 30)
        if h:
            log(f"start_gateway failed ({e}) but a gateway is answering; adopting it")
            return h
        raise
    write_svc_descriptor(spec)
    h = wait_ok(port, name, wait)
    if not h:
        raise RuntimeError(f"gateway '{name}' did not answer on 127.0.0.1:{port} within {wait:.0f}s — see {state_dir(name) / 'gateway.log'}")
    return h


# ----------------------------------------------------------------- bridge (stdlib)
class Bridge:
    """stdin/stdout JSON-RPC <-> streamable HTTP. One thread per client message.
    Reconnects (re-initialize with the client's own initialize params) and replays
    the message when the gateway has restarted."""

    def __init__(self, spec: dict):
        self.spec, self.name = spec, spec["name"]
        self.sid: str | None = None
        self.init_params: dict | None = None
        self.out_lock, self.conn_lock = threading.Lock(), threading.Lock()
        self.init_done = threading.Event()      # set once an initialize round-trip completes
        self.init_inflight = False              # only then do pipelined messages wait for it

    @property
    def port(self) -> int:                      # live: ensure() may move the gateway's port
        return self.spec["port"]

    def emit(self, obj: dict) -> None:
        with self.out_lock:
            sys.stdout.buffer.write(json.dumps(obj, separators=(",", ":")).encode() + b"\n")
            sys.stdout.buffer.flush()

    IDEMPOTENT = ("initialize", "tools/list", "prompts/list", "resources/list", "resources/templates/list", "resources/read", "prompts/get", "ping", "server/discover")
    CALL_TIMEOUT = float(os.environ.get("SHARED_MCP_CALL_TIMEOUT", "3600"))

    def post(self, msg: dict) -> tuple[int, dict, list[dict]]:
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.CALL_TIMEOUT)
        hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.sid:
            hdrs["Mcp-Session-Id"] = self.sid
        c.request("POST", "/mcp", body=json.dumps(msg).encode(), headers=hdrs)
        r = c.getresponse()
        headers = {k.lower(): v for k, v in r.getheaders()}
        msgs: list[dict] = []
        ctype = headers.get("content-type", "")
        if r.status == 200:
            if ctype.startswith("text/event-stream"):
                data: list[bytes] = []
                for raw in r:
                    line = raw.rstrip(b"\r\n")
                    if line.startswith(b"data:"):
                        data.append(line[5:].strip())
                    elif line == b"" and data:
                        try:
                            msgs.append(json.loads(b"\n".join(data)))
                        except ValueError:
                            pass
                        data = []
                if data:
                    try:
                        msgs.append(json.loads(b"\n".join(data)))
                    except ValueError:
                        pass
            else:
                body = r.read()
                if body.strip():
                    try:
                        parsed = json.loads(body)
                        msgs.extend(parsed if isinstance(parsed, list) else [parsed])
                    except ValueError:
                        pass
        else:
            body = r.read()
            if ctype.startswith("application/json") and body.strip():
                try:
                    parsed = json.loads(body)
                    msgs.extend(parsed if isinstance(parsed, list) else [parsed])
                except ValueError:
                    pass
        c.close()
        return r.status, headers, msgs

    def reconnect(self) -> None:
        """Never raises. Revives or waits for the gateway, then re-initializes if the client had."""
        with self.conn_lock:
            try:
                if gateway_ok(self.port, self.name) and self.sid and self._session_alive():
                    return
                log("gateway connection lost; reconnecting")
                self.sid = None
                grace = 45 if service_alive(self.name) else 10       # a starting gateway deserves patience
                if not wait_ok(self.port, self.name, grace):
                    try:
                        ensure(self.spec, restart_ok=False)              # revive/adopt only; never replace a live one
                    except Exception as e:  # noqa: BLE001
                        log(f"could not revive gateway: {e}")
                        wait_ok(self.port, self.name, 60)
                if self.init_params is not None and gateway_ok(self.port, self.name):
                    st, hdrs, _ = self.post({"jsonrpc": "2.0", "id": "shared-mcp-reinit", "method": "initialize", "params": self.init_params})
                    if st == 200:
                        self.sid = hdrs.get("mcp-session-id")
                        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
                        log("reconnected")
            except Exception as e:  # noqa: BLE001
                log(f"reconnect attempt failed: {type(e).__name__}: {e}")
            finally:
                self.init_done.set(); self.init_inflight = False     # never leave pipelined messages parked

    def _session_alive(self) -> bool:
        try:
            st, _, _ = self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return st in (200, 202)
        except Exception:  # noqa: BLE001
            return False

    def handle(self, msg: dict) -> None:
        is_init = msg.get("method") == "initialize"
        if is_init:
            self.init_params = msg.get("params") or {}
            self.init_inflight = True
        elif self.init_inflight and not self.init_done.is_set():
            self.init_done.wait(60)              # a client may pipeline messages right after initialize
        # A 2026-07-28 client never sends initialize and the server issues no session id;
        # nothing above engages and every message is simply forwarded — stateless by default.
        for attempt in range(3):
            try:
                status, headers, msgs = self.post(msg)
                if status == 404 and self.sid and not is_init:
                    raise ConnectionError("session terminated")
                if status in (200, 202):
                    if is_init and status == 200:
                        self.sid = headers.get("mcp-session-id")   # None for a sessionless server
                    if is_init:
                        self.init_done.set(); self.init_inflight = False
                    for m in msgs:
                        self.emit(m)
                    return
                if is_init:
                    self.init_done.set(); self.init_inflight = False   # failed handshake must not park later messages
                jsonrpc = [m for m in msgs if isinstance(m, dict) and m.get("jsonrpc") == "2.0"]
                if jsonrpc:                       # e.g. a JSON-RPC error carried on a 4xx (2026-07-28 style)
                    for m in jsonrpc:
                        self.emit(m)
                elif "id" in msg:
                    self.emit({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": f"gateway returned HTTP {status}"}})
                return
            except (ConnectionError, OSError, http.client.HTTPException, ValueError) as e:
                # Replay is safe only if the request cannot have executed: connection refused,
                # or a terminated session (rejected before dispatch). A timeout or a reset
                # mid-stream on a side-effecting call is reported, never replayed.
                pre_dispatch = isinstance(e, ConnectionRefusedError) or "session terminated" in str(e)
                idempotent = msg.get("method") in self.IDEMPOTENT or msg.get("method", "").startswith("notifications/")
                if attempt == 2 or not (pre_dispatch or idempotent):
                    self.reconnect() if not pre_dispatch else None
                    if is_init:
                        self.init_done.set(); self.init_inflight = False
                    if "id" in msg:
                        why = "gateway unreachable" if pre_dispatch else "connection lost mid-request; not replayed (the call may have run once)"
                        self.emit({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": f"shared-mcp: {why}: {e}"}})
                    return
                self.reconnect()

    def run(self) -> int:
        stdin = sys.stdin.buffer
        threads: list[threading.Thread] = []
        while True:
            line = stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            t = threading.Thread(target=self.handle, args=(msg,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=5)
        if self.sid:
            try:
                c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
                c.request("DELETE", "/mcp", headers={"Mcp-Session-Id": self.sid})
                c.getresponse().read()
                c.close()
            except Exception:  # noqa: BLE001
                pass
        return 0


# ----------------------------------------------------------------- gateway (runs in venv)
def run_gateway(spec_path: str) -> int:
    import asyncio
    import contextlib

    import anyio
    import uvicorn
    from mcp import ClientSession, types
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.server import Server
    from mcp.server.lowlevel.helper_types import ReadResourceContents
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    spec = json.loads(Path(spec_path).read_text())
    name, port = spec["name"], spec["port"]
    started = time.time()
    child_info: dict = {"pid": None, "restarts": -1}

    async def serve_once() -> None:
        child_info["restarts"] += 1
        child_env = {**os.environ, **spec.get("env", {})}
        if spec.get("path"):
            child_env["PATH"] = spec["path"]
        exe = spec.get("resolved_exe") or spec["command"][0]
        params = StdioServerParameters(command=exe, args=spec["command"][1:], env=child_env, cwd=spec.get("cwd") or None)
        async with stdio_client(params, errlog=sys.stderr) as (read, write):
            async with ClientSession(read, write) as up:
                init = await up.initialize()
                srv: Server = Server(init.serverInfo.name, instructions=init.instructions)
                caps = init.capabilities
                call_lock = anyio.Lock() if spec.get("serialize") else None
                inflight = {"n": 0, "last_done": time.time()}

                async def guarded(coro):
                    """Every upstream request goes through here: counts in-flight work (the watchdog
                    stays quiet while the child is busy) and, with --serialize, one at a time."""
                    inflight["n"] += 1
                    try:
                        if call_lock is None:
                            return await coro
                        async with call_lock:
                            return await coro
                    finally:
                        inflight["n"] -= 1
                        inflight["last_done"] = time.time()

                if caps.tools is not None:
                    @srv.list_tools()
                    async def _lt() -> list[types.Tool]:
                        return (await guarded(up.list_tools())).tools

                    @srv.call_tool(validate_input=False)
                    async def _ct(n: str, a: dict | None) -> types.CallToolResult:
                        return await guarded(up.call_tool(n, a or {}))
                if caps.prompts is not None:
                    @srv.list_prompts()
                    async def _lp() -> list[types.Prompt]:
                        return (await guarded(up.list_prompts())).prompts

                    @srv.get_prompt()
                    async def _gp(n: str, a: dict[str, str] | None) -> types.GetPromptResult:
                        return await guarded(up.get_prompt(n, a))
                if caps.resources is not None:
                    @srv.list_resources()
                    async def _lr() -> list[types.Resource]:
                        return (await guarded(up.list_resources())).resources

                    @srv.read_resource()
                    async def _rr(uri):
                        res = await guarded(up.read_resource(uri))
                        out = []
                        for c in res.contents:
                            if isinstance(c, types.BlobResourceContents):
                                out.append(ReadResourceContents(content=base64.b64decode(c.blob), mime_type=c.mimeType))
                            else:
                                out.append(ReadResourceContents(content=c.text, mime_type=c.mimeType))
                        return out

                mgr = StreamableHTTPSessionManager(app=srv, stateless=False)
                try:
                    tools_snapshot = [{"name": t.name, "description": t.description or ""} for t in (await up.list_tools()).tools] if caps.tools is not None else []
                except Exception:  # noqa: BLE001
                    tools_snapshot = []

                async def health_ep(_req):
                    return JSONResponse({"name": name, "owner": owner_tag(), "version": VERSION, "server": init.serverInfo.name,
                                         "uptime_s": int(time.time() - started), "child_restarts": child_info["restarts"],
                                         "spec": spec_path, "pid": os.getpid()})

                async def server_card(_req):
                    # MCP Server Card (SEP-2127, in review as of 2026-09): a description of the
                    # server that can be read without connecting. Shape follows the registry
                    # server.json schema the SEP builds on. Served at the SEP's path and a short alias.
                    return JSONResponse({
                        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-10-17/server.schema.json",
                        "name": f"local.shared-mcp/{name}",
                        "title": init.serverInfo.name,
                        "description": f"Shared local instance of the '{init.serverInfo.name}' MCP server, hosted by shared-mcp {VERSION} for every Claude Code session on this machine.",
                        "version": getattr(init.serverInfo, "version", None) or "0",
                        "supportedProtocolVersions": [init.protocolVersion],
                        "remotes": [{"type": "streamable-http", "url": f"http://127.0.0.1:{port}/mcp"}],
                        "capabilities": caps.model_dump(exclude_none=True),
                        "tools": tools_snapshot,
                        "_meta": {"local.shared-mcp": {"gateway_version": VERSION, "child_restarts": child_info["restarts"],
                                                       "uptime_s": int(time.time() - started), "health": f"http://127.0.0.1:{port}/health"}},
                    })

                @contextlib.asynccontextmanager
                async def lifespan(_app):
                    async with mgr.run():
                        yield

                class _Mcp:                      # exact-path ASGI endpoint (Mount would 307 "/mcp" -> "/mcp/")
                    async def __call__(self, scope, receive, send):
                        await mgr.handle_request(scope, receive, send)

                app = Starlette(routes=[Route("/health", health_ep),
                                        Route("/.well-known/mcp/server-cards.json", server_card), Route("/.well-known/mcp.json", server_card),
                                        Route("/mcp", _Mcp(), methods=["GET", "POST", "DELETE"])], lifespan=lifespan)
                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
                log(f"gateway '{name}' serving {init.serverInfo.name} on http://127.0.0.1:{port}/mcp (child restarts: {child_info['restarts']})")

                async def watchdog() -> None:
                    # Liveness = "an ordinary RPC gets ANY reply". The 2026-07-28 spec removed
                    # `ping`; tools/list exists in every generation, and an error reply still
                    # proves the child is alive. Only silence / a broken pipe means dead.
                    from mcp.shared.exceptions import McpError
                    misses = 0
                    while not server.should_exit:
                        await anyio.sleep(30)
                        if inflight["n"] and time.time() - inflight["last_done"] < 600:
                            continue                        # busy child (a long sync tool) is not a dead child —
                                                            # but nothing completing for 10 min is, so probe anyway
                        try:
                            with anyio.fail_after(60):
                                await up.list_tools()
                            misses = 0
                        except McpError:
                            misses = 0
                        except Exception as e:  # noqa: BLE001
                            misses += 1
                            if misses >= 2:                 # two consecutive silences (~3 min) before restart
                                log(f"child server stopped answering ({type(e).__name__}) twice; restarting it")
                                server.should_exit = True
                                return

                async with anyio.create_task_group() as tg:
                    tg.start_soon(watchdog)
                    await server.serve()
                    tg.cancel_scope.cancel()
                if server.should_exit:
                    raise RuntimeError("child restart requested")

    async def main() -> None:
        delay = 2.0
        while True:
            t0 = time.time()
            try:
                await serve_once()
                return                          # clean shutdown (signal)
            except (KeyboardInterrupt, asyncio.CancelledError):
                return
            except SystemExit as e:                          # uvicorn could not bind: exit so the supervisor/ensure can move the port
                log(f"gateway '{name}' exiting: {e} (port busy?)")
                raise
            except BaseException as e:  # noqa: BLE001
                # Backoff: at login the child's dependencies (a database, a network) may not be up yet.
                if time.time() - t0 > 120:
                    delay = 2.0                             # it ran a while: a fresh failure, start over
                log(f"gateway '{name}' cycle ended: {type(e).__name__}: {str(e)[:200]} — restarting child in {delay:.0f}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)

    asyncio.run(main())
    return 0


# ----------------------------------------------------------------- CLI
def parse(argv: list[str]) -> tuple[str, dict, list[str]]:
    if not argv:
        print(__doc__)
        sys.exit(2)
    verb, opts, rest = argv[0], {}, []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--":
            rest = argv[i + 1:]
            break
        if a.startswith("--"):
            key = a[2:]
            if key in ("env",):
                opts.setdefault(key, []).append(argv[i + 1])
                i += 2
            elif key in ("name", "port", "spec", "cwd", "n"):
                opts[key] = argv[i + 1]
                i += 2
            else:
                opts[key] = True
                i += 1
        else:
            rest.append(a)
            i += 1
    return verb, opts, rest


def fingerprint(command: list[str], launcher: Path, cwd: str | None = None) -> str:
    """Content identity of what the gateway would run, so an in-place update (a
    directory-source marketplace, or a server you edit) restarts the gateway even
    though the command path is unchanged. Combines: the plugin's declared version
    (nearest .claude-plugin/plugin.json above the launcher), the hash of the first
    argument that is an existing file (the entry script), and the launcher's own hash."""
    h = hashlib.sha256()
    for parent in [launcher.parent, *launcher.parents]:
        pj = parent / ".claude-plugin" / "plugin.json"
        if pj.is_file():
            try:
                h.update(("plugin:" + str(json.loads(pj.read_text()).get("version"))).encode())
            except Exception:  # noqa: BLE001
                h.update(pj.read_bytes())
            break
    for a in command[1:]:
        pa = Path(a) if os.path.isabs(a) else Path(cwd or os.getcwd()) / a
        if pa.is_file():
            h.update(pa.read_bytes())
            break
    if launcher.is_file():
        h.update(launcher.read_bytes())
    return h.hexdigest()[:16]


def build_spec(opts: dict, command: list[str]) -> dict:
    name = opts.get("name")
    if not name:                                  # derive something unique, not just a basename
        stem = next((Path(a).stem for a in reversed(command) if not a.startswith("-")), "server")
        name = f"{stem}-{zlib.crc32(' '.join(command).encode()):08x}"[:40]
        log(f"no --name given; using '{name}' (give plugins an explicit --name)")
    # Resolve the executable NOW, with the session's PATH: the gateway runs under a
    # service manager whose PATH differs, and its own venv must never shadow `python3`.
    resolved = shutil.which(command[0])
    return {"name": name, "command": list(command), "resolved_exe": resolved, "resolved": bool(resolved),
            "port_explicit": bool(opts.get("port")),
            "path": os.environ.get("PATH", ""), "cwd": opts.get("cwd") or os.getcwd(),
            "fingerprint": fingerprint(list(command), Path(__file__).resolve(), opts.get("cwd") or os.getcwd()),
            "serialize": bool(opts.get("serialize")),
            "env": {k: os.environ[k] for k in opts.get("env", []) if k in os.environ},
            "port": int(opts.get("port") or stable_port(name)), "launcher": str(Path(__file__).resolve()), "version": VERSION}


def exec_original(command: list[str], cwd: str | None = None) -> None:
    log(f"falling back to a plain per-session server: {' '.join(command)}")
    if cwd:
        try: os.chdir(cwd)
        except OSError as e: log(f"could not chdir to {cwd}: {e}")
    if IS_WIN:
        sys.exit(subprocess.call(command))
    os.execvp(command[0], command)


def main(argv: list[str]) -> int:
    verb, opts, rest = parse(argv)
    if verb == "gateway":
        return run_gateway(opts["spec"])
    if verb == "connect":
        if not rest:
            log("connect needs the original command after `--`")
            return 2
        if os.environ.get("SHARED_MCP_DISABLE") == "1" or opts.get("per-session"):
            exec_original(rest, opts.get("cwd"))    # --per-session: uniform launcher, but this server must not be shared
        try:                                    # anything that fails before the bridge exists falls back to plain stdio
            spec = build_spec(opts, rest)
            ensure(spec)
        except Exception as e:  # noqa: BLE001
            log(f"cannot share {opts.get('name') or rest[-1]!r} on this machine: {e}")
            exec_original(rest, opts.get("cwd"))
        return Bridge(spec).run()
    name = opts.get("name")
    if not name:
        log(f"{verb} needs --name")
        return 2
    spec = load_spec(name)
    if verb == "ensure":
        if not spec:
            log(f"no spec for '{name}' yet; it is created on first connect")
            return 1
        if not Path(spec["launcher"]).exists():
            log(f"launcher {spec['launcher']} no longer exists (plugin removed?); run `stop --name {name}`")
            return 1
        h = ensure(spec)
        print(json.dumps(h, indent=2))
        return 0
    if verb == "status":
        h = gateway_ok(spec["port"], name) if spec else None
        print(json.dumps({"name": name, "port": spec and spec["port"], "running": bool(h), "health": h, "spec": spec and str(state_dir(name) / "spec.json")}, indent=2))
        return 0 if h else 1
    if verb == "stop":
        stop_gateway(name)
        print(f"stopped gateway '{name}'")
        return 0
    if verb == "logs":
        p = state_dir(name) / "gateway.log"
        os.execvp("tail", ["tail", "-n", str(opts.get("n", 60)), str(p)]) if not IS_WIN else print(p.read_text()[-8000:])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
