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

Other verbs: ensure|status|stop|logs --name N ; gateway --spec FILE (internal).
State lives in ~/.local/state/shared-mcp/<name>/ (spec.json 0600, gateway.log).
Registers with `svc` (~/.config/svc/services.d) when that console exists.
"""
from __future__ import annotations

import http.client
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

VERSION = "0.1.0"
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


def stable_port(name: str) -> int:
    return 47800 + zlib.crc32(name.encode()) % 1000


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
    return h if h and h.get("name") == name else None


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
def label(name: str) -> str:
    return f"com.shared-mcp.{name}"


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
    for _ in range(20):                       # launchd holds a just-removed label briefly
        if _launchctl("print", f"{domain}/{lab}")[0] != 0:
            break
        time.sleep(0.25)
    logp = state_dir(name) / "gateway.log"
    argv = gateway_argv(spec)
    xml = "".join(f"<string>{a}</string>" for a in argv)
    path_env = os.pathsep.join(dict.fromkeys([str(venv_python().parent), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"] + os.environ.get("PATH", "").split(os.pathsep)))
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{lab}</string>
  <key>ProgramArguments</key><array>{xml}</array>
  <key>WorkingDirectory</key><string>{spec.get("cwd") or str(HOME)}</string>
  <key>ProcessType</key><string>Interactive</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>{logp}</string>
  <key>StandardErrorPath</key><string>{logp}</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>{path_env}</string>
    <key>HOME</key><string>{HOME}</string>
  </dict>
</dict></plist>
""")
    for i in range(10):                       # bootstrap right after bootout can fail with EIO
        rc, out = _launchctl("bootstrap", domain, str(plist))
        if rc == 0:
            break
        if i == 9:
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
ExecStart={' '.join(gateway_argv(spec))}
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


def stop_detached(name: str) -> None:
    pidf = state_dir(name) / "gateway.pid"
    try:
        pid = int(pidf.read_text())
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, 15)
    except Exception:  # noqa: BLE001
        pass
    pidf.unlink(missing_ok=True)


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
    me = f"{sys.executable} {Path(spec['launcher']).resolve()}"
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
            lines = logp.read_bytes().splitlines()[-2000:]
            logp.write_bytes(b"\n".join(lines) + b"\n")
    except OSError:
        pass


def ensure(spec: dict, wait: float = 60) -> dict:
    """Make the gateway for spec run with THIS spec; returns its health card or raises."""
    name, port = spec["name"], spec["port"]
    current = load_spec(name)
    running = gateway_ok(port, name)
    same = current and current.get("command") == spec["command"] and current.get("env") == spec["env"] and current.get("launcher") == spec["launcher"]
    if running and same:
        return running
    if running and not same:
        log(f"gateway '{name}' runs an older definition; restarting with the current one")
    else:
        log(f"starting gateway '{name}' on 127.0.0.1:{port}")
    ensure_venv()
    rotate_log(name)
    save_spec(spec)
    start_gateway(spec)
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
        self.spec, self.port, self.name = spec, spec["port"], spec["name"]
        self.sid: str | None = None
        self.init_params: dict | None = None
        self.out_lock, self.conn_lock = threading.Lock(), threading.Lock()

    def emit(self, obj: dict) -> None:
        with self.out_lock:
            sys.stdout.buffer.write(json.dumps(obj, separators=(",", ":")).encode() + b"\n")
            sys.stdout.buffer.flush()

    def post(self, msg: dict) -> tuple[int, dict, list[dict]]:
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=600)
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
                    parsed = json.loads(body)
                    msgs.extend(parsed if isinstance(parsed, list) else [parsed])
        else:
            r.read()
        c.close()
        return r.status, headers, msgs

    def reconnect(self) -> None:
        with self.conn_lock:
            if gateway_ok(self.port, self.name) and self.sid and self._session_alive():
                return
            log("gateway connection lost; reconnecting")
            self.sid = None
            if not wait_ok(self.port, self.name, 10):
                try:
                    ensure(self.spec)
                except Exception as e:  # noqa: BLE001
                    log(f"could not revive gateway: {e}")
                    wait_ok(self.port, self.name, 60)
            if self.init_params is not None:
                st, hdrs, _ = self.post({"jsonrpc": "2.0", "id": "shared-mcp-reinit", "method": "initialize", "params": self.init_params})
                if st == 200:
                    self.sid = hdrs.get("mcp-session-id")
                    self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
                    log("reconnected")

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
        for attempt in range(3):
            try:
                status, headers, msgs = self.post(msg)
                if status == 404 and self.sid and not is_init:
                    raise ConnectionError("session terminated")
                if status in (200, 202):
                    if is_init and status == 200:
                        self.sid = headers.get("mcp-session-id")
                    for m in msgs:
                        self.emit(m)
                    return
                if "id" in msg:
                    self.emit({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": f"gateway returned HTTP {status}"}})
                return
            except (ConnectionError, OSError, http.client.HTTPException) as e:
                if attempt == 2:
                    if "id" in msg:
                        self.emit({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": f"shared-mcp gateway unreachable: {e}"}})
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
        params = StdioServerParameters(command=spec["command"][0], args=spec["command"][1:],
                                       env={**os.environ, **spec.get("env", {})}, cwd=spec.get("cwd") or None)
        async with stdio_client(params, errlog=sys.stderr) as (read, write):
            async with ClientSession(read, write) as up:
                init = await up.initialize()
                srv: Server = Server(init.serverInfo.name, instructions=init.instructions)
                caps = init.capabilities
                if caps.tools is not None:
                    @srv.list_tools()
                    async def _lt() -> list[types.Tool]:
                        return (await up.list_tools()).tools

                    @srv.call_tool(validate_input=False)
                    async def _ct(n: str, a: dict | None) -> types.CallToolResult:
                        return await up.call_tool(n, a or {})
                if caps.prompts is not None:
                    @srv.list_prompts()
                    async def _lp() -> list[types.Prompt]:
                        return (await up.list_prompts()).prompts

                    @srv.get_prompt()
                    async def _gp(n: str, a: dict[str, str] | None) -> types.GetPromptResult:
                        return await up.get_prompt(n, a)
                if caps.resources is not None:
                    @srv.list_resources()
                    async def _lr() -> list[types.Resource]:
                        return (await up.list_resources()).resources

                    @srv.read_resource()
                    async def _rr(uri):
                        res = await up.read_resource(uri)
                        return [types.ReadResourceContents(content=getattr(c, "text", None) or getattr(c, "blob", ""), mime_type=c.mimeType) for c in res.contents]

                mgr = StreamableHTTPSessionManager(app=srv, stateless=False)

                async def health_ep(_req):
                    return JSONResponse({"name": name, "version": VERSION, "server": init.serverInfo.name,
                                         "uptime_s": int(time.time() - started), "child_restarts": child_info["restarts"],
                                         "spec": spec_path, "pid": os.getpid()})

                @contextlib.asynccontextmanager
                async def lifespan(_app):
                    async with mgr.run():
                        yield

                class _Mcp:                      # exact-path ASGI endpoint (Mount would 307 "/mcp" -> "/mcp/")
                    async def __call__(self, scope, receive, send):
                        await mgr.handle_request(scope, receive, send)

                app = Starlette(routes=[Route("/health", health_ep), Route("/mcp", _Mcp(), methods=["GET", "POST", "DELETE"])], lifespan=lifespan)
                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
                log(f"gateway '{name}' serving {init.serverInfo.name} on http://127.0.0.1:{port}/mcp (child restarts: {child_info['restarts']})")

                async def watchdog() -> None:
                    while not server.should_exit:
                        await anyio.sleep(15)
                        try:
                            with anyio.fail_after(10):
                                await up.send_ping()
                        except Exception as e:  # noqa: BLE001
                            log(f"child server stopped answering ({type(e).__name__}); restarting it")
                            server.should_exit = True
                            return

                async with anyio.create_task_group() as tg:
                    tg.start_soon(watchdog)
                    await server.serve()
                    tg.cancel_scope.cancel()
                if server.should_exit and not _got_signal["v"]:
                    raise RuntimeError("child restart requested")

    _got_signal = {"v": False}

    async def main() -> None:
        while True:
            try:
                await serve_once()
                return                          # clean shutdown (signal)
            except (KeyboardInterrupt, asyncio.CancelledError):
                return
            except BaseException as e:  # noqa: BLE001
                log(f"gateway '{name}' cycle ended: {type(e).__name__}: {str(e)[:200]} — restarting child in 2s")
                await asyncio.sleep(2)

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


def build_spec(opts: dict, command: list[str]) -> dict:
    name = opts.get("name") or Path(command[-1]).stem
    return {"name": name, "command": command, "cwd": opts.get("cwd") or os.getcwd(),
            "env": {k: os.environ[k] for k in opts.get("env", []) if k in os.environ},
            "port": int(opts.get("port") or stable_port(name)), "launcher": str(Path(__file__).resolve()), "version": VERSION}


def exec_original(command: list[str]) -> None:
    log(f"falling back to a plain per-session server: {' '.join(command)}")
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
        spec = build_spec(opts, rest)
        if os.environ.get("SHARED_MCP_DISABLE") == "1":
            exec_original(rest)
        try:
            ensure(spec)
        except Exception as e:  # noqa: BLE001
            log(f"cannot share '{spec['name']}' on this machine: {e}")
            exec_original(rest)
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
