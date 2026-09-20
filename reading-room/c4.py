#!/usr/bin/env python3
"""The C4 model of the shared-MCP system.

One registry of elements (Level 1 context -> Level 4 code), one registry of diagrams
that place those elements, and one registry of use cases that name the elements they
exercise. Everything else in this file is derived from those three: the SVG drawings,
the traceability tables, and the structural checks.

The point of the arrangement: nothing is drawn that is not an element, no element below
Level 1 exists without a parent element, and no diagram below Level 1 exists without a
parent diagram that draws its focus. `check()` proves those properties at build time and
`generate.py` prints the result into the reading room, so a drawing cannot quietly drift
away from the model it claims to zoom into.
"""
from roomlib import E

# --------------------------------------------------------------------------- elements
# id -> kind, name, tech, note, parent (an element id, or None at Level 1), level
EL: dict[str, dict] = {}


def el(id_, level, kind, name, tech="", note="", parent=None):
    EL[id_] = dict(id=id_, level=level, kind=kind, name=name, tech=tech, note=note, parent=parent)
    return id_


# ---- Level 1: the context -------------------------------------------------
el("p.owner", 1, "person", "Machine owner", "one person, one Mac",
   "Runs Claude Code all day; owns every background process it leaves behind.")
el("p.author", 1, "person", "Plugin author / installer", "publishes or installs a plugin",
   "Ships an MCP server inside a Claude Code plugin, for machines they will never see.")
el("sys.mcp", 1, "system", "Shared MCP", "the system in scope",
   "Makes each plugin's MCP server run once per machine instead of once per session, "
   "keeps it supervised and visible, and degrades to the old behaviour when it cannot.")
el("ext.session", 1, "external", "Claude Code session", "N concurrent per machine",
   "Spawns the server named in .mcp.json and speaks JSON-RPC to it over stdio.")
el("ext.server", 1, "external", "Original MCP server", "the plugin's own program; stdio",
   "Unmodified. Often owns single-writer state, which is why N copies fight.")
el("ext.launchd", 1, "external", "OS service manager", "launchd · systemd --user · none",
   "Starts the service at login and restarts it when it exits.")
el("ext.store", 1, "external", "Server-owned state", "SQLite · Neo4j · files",
   "What the original server reads and writes. One writer is the whole point.")
el("ext.market", 1, "external", "Plugin marketplace", "git repo · directory source",
   "Installs and upgrades the plugin that carries the launcher.")

# ---- Level 2: the containers ---------------------------------------------
el("c.bridge", 2, "container", "Bridge", "python3, standard library only · ~26 MB · one per session per server",
   "Reads stdio JSON-RPC, posts it to the gateway, writes replies back. Before it starts "
   "relaying it guarantees the gateway exists. Thread per message.", "sys.mcp")
el("c.gateway", 2, "container", "Gateway", "python3 + mcp/starlette/uvicorn in a venv · one per server per machine",
   "Runs the original server once and serves it as streamable HTTP on 127.0.0.1 only.", "sys.mcp")
el("c.agent", 2, "container", "Service definition", "plist · systemd unit · pid file",
   "~/Library/LaunchAgents/com.shared-mcp.<owner>.<name>.plist — what the machine's service manager is given "
   "so the gateway survives logout, crash and reboot.", "sys.mcp")
el("c.state", 2, "store", "Kit state", "one directory per server",
   "~/.local/state/shared-mcp/<name>/ — spec.json (0600, holds forwarded secrets), ensure.lock, "
   "gateway.log (5 MB cap), spec-history.json.", "sys.mcp")
el("c.venv", 2, "store", "Gateway runtime", "one virtualenv per machine",
   "~/.local/state/shared-mcp/venv — rebuilt when the pinned requirements change, under a machine-wide lock.", "sys.mcp")
el("c.console", 2, "container", "svc console", "python3 CLI · ~/.local/bin/svc",
   "The one place the owner sees everything launchd runs for them: list, show, logs, health, doctor, prune.", "sys.mcp")
el("c.desc", 2, "store", "svc descriptors", "one file per service",
   "~/.config/svc/services.d/ — the only authored facts about a service: purpose, source, health probe. "
   "Written by the daemon itself when it starts.", "sys.mcp")
el("c.room", 2, "container", "Reading room", "generate.py -> index.html · pre-commit hook + daily agent",
   "This page. Prose authored, evidence derived from the live machine at build time.", "sys.mcp")
el("c.specvault", 2, "container", "spec-vault graph daemon", "daemon.sh + proxy.py + server.py --transport http",
   "The bespoke sibling that predates the kit and still runs: same shape, its own code.", "sys.mcp")
el("c.repo", 2, "container", "Kit source + vendor", "~/Developer/shared-mcp · shared_mcp.py · vendor.sh",
   "One canonical file, stamped byte-identically into each plugin root. Fixes flow outward by re-vendoring.", "sys.mcp")

# ---- Level 3: components of the bridge container --------------------------
el("b.parse", 3, "component", "parse() / main()", "CLI front",
   "Splits the verb and flags from the original command after `--`; routes connect / gateway / ensure / status / stop / logs.", "c.bridge")
el("b.spec", 3, "component", "build_spec()", "identity",
   "Resolves the executable with THIS session's PATH, hashes a stable port from the name, "
   "captures only the --env vars declared, records cwd and the launcher path.", "c.bridge")
el("b.fp", 3, "component", "fingerprint()", "content identity",
   "plugin.json version + entry-script bytes + launcher bytes, so an in-place edit restarts the gateway "
   "even when the command path never changed.", "c.bridge")
el("b.ensure", 3, "component", "ensure() / _ensure_locked()", "the decision",
   "Start, adopt, restart or keep the gateway. The only writer of spec.json.", "c.bridge")
el("b.lock", 3, "component", "_Lock", "mutual exclusion",
   "mkdir lock with a heartbeat, atomic stale claim by rename, atexit release; never removes a live owner's lock.", "c.bridge")
el("b.venv", 3, "component", "ensure_venv()", "runtime build",
   "Builds the shared venv once, under a machine-wide lock, keyed by a requirements stamp.", "c.bridge")
el("b.sup", 3, "component", "start_gateway() + back-ends", "supervision adapters",
   "start_mac (launchd, ProcessType Interactive) · start_systemd · start_detached, plus service_alive() and stop.", "c.bridge")
el("b.rotate", 3, "component", "rotate_log()", "housekeeping",
   "Streaming truncate of gateway.log at 5 MB before each start.", "c.bridge")
el("b.desc", 3, "component", "write_svc_descriptor()", "self-registration",
   "Writes the svc descriptor, but only if the console's directory already exists — the kit never installs the console.", "c.bridge")
el("b.bridge", 3, "component", "Bridge", "the relay",
   "run() reads stdin and starts a thread per message; handle() sends, classifies failures and decides replay; "
   "post() speaks streamable HTTP; reconnect() revives the gateway without ever raising.", "c.bridge")
el("b.fallback", 3, "component", "exec_original()", "the floor",
   "execvp the original command. Reached by SHARED_MCP_DISABLE=1, --per-session, or any failure before the bridge exists.", "c.bridge")

# ---- Level 3: components of the gateway container -------------------------
el("g.main", 3, "component", "main() restart loop", "supervision of the child",
   "Exponential backoff 2 s -> 60 s, reset after a cycle that lasted; re-raises a bind failure so the port can move.", "c.gateway")
el("g.serve", 3, "component", "serve_once()", "one child lifetime",
   "Spawns the original command over stdio, initializes it, builds the proxy from its declared capabilities, serves until the child dies.", "c.gateway")
el("g.proxy", 3, "component", "capability proxies", "tools · prompts · resources",
   "Registered only for capabilities the child declared; forwards verbatim and converts blob resources back to bytes.", "c.gateway")
el("g.guard", 3, "component", "guarded()", "concurrency",
   "Counts in-flight work so the watchdog stays quiet while the child is busy; takes one lock per call under --serialize.", "c.gateway")
el("g.watch", 3, "component", "watchdog()", "liveness",
   "An ordinary tools/list every 30 s. Any reply, including an error, proves life; two silences restart the child.", "c.gateway")
el("g.http", 3, "component", "Starlette routes", "127.0.0.1 only",
   "/mcp as an exact path (a mount would 307-redirect), /health, and the server card path.", "c.gateway")
el("g.card", 3, "component", "server_card()", "SEP-2127, in review",
   "Serves a server card at /.well-known/mcp/server-cards.json so a client can read the server without connecting.", "c.gateway")

# ---- Level 3: components of the svc console -------------------------------
el("s.inv", 3, "component", "inventory()", "derived every run",
   "launchd labels x plists x the process table x listening ports. Nothing is remembered, so nothing can rot.", "c.console")
el("s.membrane", 3, "component", "parse_launchctl_print()", "with classify() and ownership() — the membrane",
   "The only code that understands launchctl's output shape, pinned by recorded fixtures.", "c.console")
el("s.desc", 3, "component", "load_descriptors()", "authored facts",
   "Reads the descriptors: purpose, source directory, health probe — the things launchd cannot know.", "c.console")
el("s.health", 3, "component", "health()", "probe",
   "Runs the descriptor's probe and reports ok / fail / unknown.", "c.console")
el("s.doctor", 3, "component", "doctor()", "rules",
   "Unregistered service, log bloat, no probe, dead but loaded, source directory gone.", "c.console")
el("s.control", 3, "component", "cmd_control()", "verified control",
   "start / stop / restart, then re-derives the state to prove the verb actually took effect.", "c.console")
el("s.prune", 3, "component", "cmd_prune()", "dry run by default",
   "Reports reclaimable log bytes; --go acts; --install registers the daily 03:30 agent.", "c.console")
el("s.selftest", 3, "component", "cmd_selftest()", "membrane fixtures",
   "Replays recorded launchctl output and plists against expected.json.", "c.console")

# ---- Level 3: components of the spec-vault daemon -------------------------
el("v.daemon", 3, "component", "daemon.sh", "bash manager",
   "connect = ensure + exec proxy. Builds a venv keyed by a requirements hash, writes the launchd agent, "
   "compares a recorded version, waits for the port, writes the svc descriptor.", "c.specvault")
el("v.proxy", 3, "component", "proxy.py", "mcp-library bridge · ~38 MB",
   "One owning task holds the upstream connection; a job queue feeds it; it reconnects and replays, "
   "and a watchdog abandons a call when the daemon stops answering mid-request.", "c.specvault")
el("v.server", 3, "component", "server.py (http mode)", "FastMCP streamable HTTP",
   "The graph server itself, serving 127.0.0.1:47765 — native HTTP, so it needs no gateway wrapper.", "c.specvault")
el("v.sig", 3, "component", "_handle_shutdown()", "the crash fix",
   "The SIGTERM handler that used to abort the interpreter on every Claude quit.", "c.specvault")

# ---- Level 4: Bridge.handle, the replay decision --------------------------
el("r.gate", 4, "code", "initialize gate", "handle(), first block",
   "An initialize is remembered and marked in flight; anything pipelined behind it waits up to 60 s for the handshake. "
   "A 2026-07-28 client sends no initialize, so nothing engages.", "b.bridge")
el("r.post", 4, "code", "post()", "attempt 1 of 3",
   "POST /mcp with the session id if one was ever issued; parse JSON or the SSE stream.", "b.bridge")
el("r.ok", 4, "code", "200 / 202 -> emit", "success",
   "Capture the session id on an initialize, write every reply to stdout, return.", "b.bridge")
el("r.http", 4, "code", "other status", "error, not failure",
   "A JSON-RPC error carried on a 4xx is forwarded as-is; otherwise synthesize -32000 with the HTTP status.", "b.bridge")
el("r.class", 4, "code", "classify the exception", "the safety rule",
   "pre_dispatch = connection refused, or a 404 for a session the gateway no longer has. "
   "idempotent = a read method or a notification.", "b.bridge")
el("r.replay", 4, "code", "reconnect + replay", "only when provably safe",
   "Revive or wait for the gateway, re-initialize with the client's own params, send the same message again.", "b.bridge")
el("r.report", 4, "code", "report, never replay", "the honest path",
   "A timeout or a reset mid-stream on a side-effecting call returns -32000 'not replayed (the call may have run once)'.", "b.bridge")

# ---- Level 4: _ensure_locked, the start/keep decision ---------------------
el("e.newest", 4, "code", "newest spec wins", "reconnecting bridge only",
   "restart_ok=False: adopt the newest definition on disk rather than this session's own, "
   "so a still-open old session cannot downgrade an upgraded gateway.", "b.ensure")
el("e.probe", 4, "code", "is it answering?", "health + service state",
   "gateway_ok on the port; if the service is registered but silent, a bounded grace for a starting child.", "b.ensure")
el("e.port", 4, "code", "move the port", "stranger on the hashed port",
   "Nothing answering as us: step forward to a free port near the hashed one.", "b.ensure")
el("e.same", 4, "code", "same definition?", "command · env · launcher · fingerprint · serialize · cwd",
   "All six equal means the running gateway already is what this session wants.", "b.ensure")
el("e.keep", 4, "code", "keep the live one", "four reasons",
   "Identical; or a reconnecting bridge; or this session cannot resolve the executable; or sessions are flapping "
   "between two definitions within ten minutes.", "b.ensure")
el("e.start", 4, "code", "start it", "venv, rotate, save, register",
   "Build the venv, rotate the log, write spec.json, hand the definition to the service manager, "
   "adopt a gateway that answers anyway if registration raced, then wait for health.", "b.ensure")

# ---- Level 4: the gateway watchdog and child restart ----------------------
el("w.sleep", 4, "code", "every 30 s", "loop head", "Wakes while the HTTP server is still meant to run.", "g.watch")
el("w.busy", 4, "code", "busy child?", "in-flight counter",
   "Work in flight and something completed within 10 minutes: stay quiet. A long synchronous tool is not a dead server — "
   "but ten minutes with nothing completing is, so probe anyway.", "g.watch")
el("w.probe", 4, "code", "tools/list, 60 s cap", "an ordinary RPC",
   "ping was removed by the 2026-07-28 spec and some servers reject it; tools/list exists in every generation.", "g.watch")
el("w.reply", 4, "code", "any reply = alive", "including McpError",
   "An error reply proves the child is answering. This one line ended a 2,813-restart loop.", "g.watch")
el("w.miss", 4, "code", "two silences", "~3 minutes",
   "One miss can be a slow moment; two consecutive silences mean the child is gone.", "g.watch")
el("w.restart", 4, "code", "restart the child", "back to main()",
   "Stop the HTTP server, raise, and let the backoff loop spawn a fresh child.", "g.watch")

# ---- Level 4: the SIGTERM handler, before and after -----------------------
el("x.sysexit", 4, "code", "sys.exit(0) in the handler", "before",
   "Raises SystemExit, which starts interpreter finalization from inside a signal handler.", "v.sig")
el("x.join", 4, "code", "wait_for_thread_shutdown()", "before",
   "Finalization joins the MCP library's non-daemon stdin reader, which is blocked in read() holding the buffer lock.", "v.sig")
el("x.abort", 4, "code", "abort() / SIGABRT", "before",
   "The reader wakes into a finalizing interpreter, is parked, and the main thread aborts: "
   "'could not acquire lock for <_io.BufferedReader name=<stdin>> at interpreter shutdown'.", "v.sig")
el("x.reentry", 4, "code", "re-entry guard", "after",
   "A second signal during cleanup leaves immediately instead of racing the first.", "v.sig")
el("x.cleanup", 4, "code", "remove pid file, close DB", "after",
   "The two cleanups run here, each guarded, instead of being left to interpreter finalization.", "v.sig")
el("x.osexit", 4, "code", "os._exit(0)", "after",
   "Leaves without finalization and without the join. Exit 0 in under a second, in all three signal orders.", "v.sig")


# --------------------------------------------------------------------------- drawing
KIND = {
    "person":    dict(fill="#e4edf3", stroke="#1d5b73", ink="#11212e", tag="Person"),
    "system":    dict(fill="#1d5b73", stroke="#11212e", ink="#ffffff", tag="Software System"),
    "external":  dict(fill="#eceae3", stroke="#8a8578", ink="#3a4d5c", tag="External"),
    "container": dict(fill="#e5f1ea", stroke="#0f5132", ink="#11212e", tag="Container"),
    "store":     dict(fill="#f6efe1", stroke="#9a5b1e", ink="#11212e", tag="Store"),
    "component": dict(fill="#ffffff", stroke="#3a4d5c", ink="#11212e", tag="Component"),
    "code":      dict(fill="#eef1f0", stroke="#3a4d5c", ink="#11212e", tag="Code"),
}
ARROW = "#3a4d5c"
LSZ, LCH, LLH = 10.2, 5.25, 11.6          # label font size, mean character width, line height
VW = 1000                                  # every drawing is this wide; the page scales it down


def _wrap(t: str, n: int) -> list[str]:
    words = []
    for w in t.split():                      # a path with no spaces still has to fit the box
        while len(w) > n:
            words.append(w[:n]); w = w[n:]
        words.append(w)
    out, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= n or not cur:
            cur = (cur + " " + w).strip()
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def _note_lines(e, note, w):
    return _wrap(note if note is not None else e["note"], max(12, int((w - 26) / 5.6)))


def _tech_lines(e, w):
    return _wrap(e["tech"], max(10, int((w - 26) / 5.6))) if e["tech"] else []


def _box_h(e, note, w):
    return 26 + 16 + 13 * len(_tech_lines(e, w)) + 13 * len(_note_lines(e, note, w)) + 12


def _box(e, x, y, w, h, note=None):
    k = KIND[e["kind"]]
    ink, sub = k["ink"], ("#cfe0e6" if e["kind"] == "system" else "#5f7a88")
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{k["fill"]}" stroke="{k["stroke"]}" stroke-width="1.5"/>',
         f'<text x="{x+13}" y="{y+17}" font-size="9.5" letter-spacing=".08em" fill="{sub}">{E(k["tag"].upper())}</text>',
         f'<text x="{x+w-11}" y="{y+17}" font-size="9.5" text-anchor="end" font-family="ui-monospace,Menlo,monospace" fill="{sub}">{E(e["id"])}</text>']
    yy = y + 36
    s.append(f'<text x="{x+13}" y="{yy}" font-size="13.5" font-weight="700" fill="{ink}">{E(e["name"])}</text>')
    for ln in _tech_lines(e, w):
        yy += 13
        s.append(f'<text x="{x+13}" y="{yy}" font-size="10.5" font-style="italic" fill="{sub}">{E(ln)}</text>')
    yy += 16
    for ln in _note_lines(e, note, w):
        s.append(f'<text x="{x+13}" y="{yy}" font-size="11" fill="{ink}" opacity=".92">{E(ln)}</text>')
        yy += 13
    return "".join(s)


# ---- grid -----------------------------------------------------------------
def cols(n, gap=96, m=14, W=VW):
    """n columns across the drawing. The gap is not decoration: it is where edge labels go,
    so it is never smaller than a short phrase."""
    w = (W - 2 * m - gap * (n - 1)) / n
    return [(round(m + i * (w + gap)), round(w)) for i in range(n)]


def bx(id_, col, row, span=1, note=None):
    return dict(id=id_, col=col, row=row, span=span, note=note)


def layout(d, live=None):
    """Rows are as tall as their tallest box, so nothing can collide vertically; columns are fixed,
    so nothing can collide horizontally. Every coordinate on every drawing comes from here."""
    C, vg, y0 = d["cols"], d.get("vgap", 46), d.get("y0", 30)
    def geom(b):
        x, w = C[b["col"]]
        if b.get("span", 1) > 1:
            x2, w2 = C[b["col"] + b["span"] - 1]
            w = x2 + w2 - x
        return x, w
    nrows = max(b["row"] for b in d["boxes"]) + 1
    hs = []
    for r in range(nrows):
        h = 0
        for b in d["boxes"]:
            if b["row"] == r:
                note = b["note"].format(**live) if (b["note"] and live) else b["note"]
                h = max(h, _box_h(EL[b["id"]], note, geom(b)[1]))
        hs.append(h)
    ys, y = [], y0
    for r in range(nrows):
        ys.append(y); y += hs[r] + vg
    R = {}
    for b in d["boxes"]:
        x, w = geom(b)
        R[b["id"]] = (x, ys[b["row"]], w, hs[b["row"]])
    return R, ys, hs, y - vg


def cxx(r): return r[0] + r[2] / 2
def cyy(r): return r[1] + r[3] / 2


def band(R, f, t):
    a, b = R[f], R[t]
    return (a[1] + a[3] + b[1]) / 2 if b[1] > a[1] else (b[1] + b[3] + a[1]) / 2


def down(R, f, t, dxf=0, dxt=0):
    a, b, y = R[f], R[t], band(R, f, t)
    return [(cxx(a) + dxf, a[1] + a[3]), (cxx(a) + dxf, y), (cxx(b) + dxt, y), (cxx(b) + dxt, b[1])]


def up(R, f, t, dxf=0, dxt=0):
    a, b, y = R[f], R[t], band(R, f, t)
    return [(cxx(a) + dxf, a[1]), (cxx(a) + dxf, y), (cxx(b) + dxt, y), (cxx(b) + dxt, b[1] + b[3])]


def gutter(R, f, t, x, side="l"):
    """Along a vertical lane beside the boxes: the only way back up a column."""
    a, b = R[f], R[t]
    ax = a[0] if side == "l" else a[0] + a[2]
    bx_ = b[0] if side == "l" else b[0] + b[2]
    return [(ax, cyy(a)), (x, cyy(a)), (x, cyy(b)), (bx_, cyy(b))]


def _auto(a, b):
    ax, ay, aw, ah = a; bx_, by, bw, bh = b
    ox0, ox1 = max(ax, bx_), min(ax + aw, bx_ + bw)
    oy0, oy1 = max(ay, by), min(ay + ah, by + bh)
    if ox1 - ox0 > 24:
        x = (ox0 + ox1) / 2
        return [(x, ay + ah), (x, by)] if by >= ay + ah else [(x, ay), (x, by + bh)]
    if oy1 - oy0 > 24:
        y = (oy0 + oy1) / 2
        return [(ax + aw, y), (bx_, y)] if bx_ >= ax + aw else [(ax, y), (bx_ + bw, y)]
    y, x = ay + ah / 2, bx_ + bw / 2
    return [(ax + aw if bx_ > ax else ax, y), (x, y), (x, by + bh if by < ay else by)]


def _label(x, y, text, rot=False, size=LSZ):
    t = (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" fill="#11212e" stroke="#f6f4ee" '
         f'stroke-width="3.4" paint-order="stroke" stroke-linejoin="round">{E(text)}</text>')
    return f'<g transform="rotate(-90 {x} {y})">{t}</g>' if rot else t


def _label_geom(pts, ed):
    """Where a label goes and the box it occupies, so check() can prove it lands in a gap.

    On a horizontal connector the label is wrapped to the width of the gap it spans — the gap is the
    only place guaranteed to be empty. On a vertical connector it sits in the band between two rows,
    which is empty across the whole drawing, so it can stay on one line."""
    i = max(range(len(pts) - 1), key=lambda j: abs(pts[j][0] - pts[j + 1][0]) + abs(pts[j][1] - pts[j + 1][1]))
    (x0, y0), (x1, y1) = pts[i], pts[i + 1]
    if ed.get("rot"):
        cx, cy = ed.get("lpos") or ((x0 + x1) / 2, (y0 + y1) / 2)
        w = len(ed["l"]) * LCH
        return [ed["l"]], cx + 4, cy + w / 2, (cx - LLH / 2, cy - w / 2, LLH, w)
    horiz = abs(x1 - x0) >= abs(y1 - y0)
    if horiz:
        cx, avail = (x0 + x1) / 2, max(46, abs(x1 - x0) - 6)
    else:
        cx, avail = x0, ed.get("lw", 240)
    lines = _wrap(ed["l"], max(7, int(avail / LCH)))
    w = max(len(ln) for ln in lines) * LCH
    H = LLH * len(lines)
    top = (min(y0, y1) - 7 - H) if horiz else ((y0 + y1) / 2 - H / 2)
    return lines, cx, top + 9, (cx - w / 2, top, w, H)


def epts(d, R, ed):
    p = ed.get("pts")
    return (p(R) if callable(p) else p) if p else _auto(R[ed["f"]], R[ed["t"]])


def render(d, live=None) -> str:
    R, ys, hs, bottom = layout(d, live)
    h = bottom + d.get("vpad", 28)
    mk = f'arw-{d["id"]}'
    s = [f'<svg viewBox="0 0 {VW} {h}" xmlns="http://www.w3.org/2000/svg" font-family="ui-sans-serif,system-ui,sans-serif">',
         f'<defs><marker id="{mk}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         f'<path d="M0 0L10 5L0 10z" fill="{ARROW}"/></marker></defs>']
    for (c0, c1, r0, r1, lbl, pad) in d.get("bounds", []):
        x = d["cols"][c0][0] - pad; w = d["cols"][c1][0] + d["cols"][c1][1] + pad - x
        y = ys[r0] - pad; bh = ys[r1] + hs[r1] + pad - y
        s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{bh}" rx="14" fill="none" stroke="#9aa7ae" stroke-width="1.3" stroke-dasharray="7 5"/>')
        s.append(f'<text x="{x+16}" y="{y-7}" font-size="10.5" letter-spacing=".07em" fill="#5f7a88">{E(lbl.upper())}</text>')
    for (tx, trow, size, anchor, txt) in d.get("texts", []):
        s.append(f'<text x="{tx}" y="{ys[trow]-26}" font-size="{size}" font-weight="700" text-anchor="{anchor}" fill="#11212e">{E(txt)}</text>')
    for b in d["boxes"]:
        note = b["note"].format(**live) if (b["note"] and live) else b["note"]
        s.append(_box(EL[b["id"]], *R[b["id"]], note))
    labels = []
    for ed in d.get("edges", []):
        pts = epts(d, R, ed)
        dash = ' stroke-dasharray="6 4"' if ed.get("dash") else ""
        s.append(f'<path d="M' + "L".join(f"{x} {y}" for x, y in pts) + f'" fill="none" stroke="{ARROW}" stroke-width="1.6"{dash}'
                 f' marker-end="url(#{mk})"' + (f' marker-start="url(#{mk})"' if ed.get("both") else "") + "/>")
        if ed.get("l"):
            lines, lx, ly, _bb = _label_geom(pts, ed)
            labels += [_label(lx, ly + k * LLH, ln, ed.get("rot")) for k, ln in enumerate(lines)]
    s += labels
    s.append("</svg>")
    return "".join(s)


def render_seq(d, live=None) -> str:
    """Lane diagram: containers across the top, numbered messages down."""
    C = d["cols"]
    lanes = [(b["id"], *C[b["col"]]) for b in d["boxes"]]
    hh = max(_box_h(EL[i], b["note"], w) for (i, x, w), b in zip(lanes, d["boxes"]))
    off = max(0, (14 + hh + 34) - d["steps"][0]["y"])      # the first message starts below the lanes
    h = d["steps"][-1]["y"] + off + 40
    mk = f'arw-{d["id"]}'
    s = [f'<svg viewBox="0 0 {VW} {h}" xmlns="http://www.w3.org/2000/svg" font-family="ui-sans-serif,system-ui,sans-serif">',
         f'<defs><marker id="{mk}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         f'<path d="M0 0L10 5L0 10z" fill="{ARROW}"/></marker></defs>']
    X = {}
    for (i, x, w), b in zip(lanes, d["boxes"]):
        s.append(_box(EL[i], x, 14, w, hh, b["note"]))
        X[i] = x + w / 2
        s.append(f'<path d="M{x+w/2} {14+hh}V{h-14}" stroke="#b9c3c8" stroke-width="1.2" stroke-dasharray="4 5" fill="none"/>')
    for st in d["steps"]:
        y, f_, t_ = st["y"] + off, st["f"], st["t"]
        if f_ == t_:
            x = X[f_]
            s.append(f'<path d="M{x} {y}h46v26h-40" fill="none" stroke="{ARROW}" stroke-width="1.6" marker-end="url(#{mk})"/>')
            s.append(f'<text x="{x+56}" y="{y+18}" font-size="11.5" fill="#11212e">{E(st["l"])}</text>')
        else:
            x0, x1 = X[f_], X[t_]
            x1 += -7 if x1 > x0 else 7
            s.append(f'<path d="M{x0} {y}H{x1}" fill="none" stroke="{ARROW}" stroke-width="1.6"'
                     + (' stroke-dasharray="6 4"' if st.get("dash") else "") + f' marker-end="url(#{mk})"/>')
            s.append(_label((x0 + x1) / 2, y - 7, st["l"], size=11.5))
    s.append("</svg>")
    return "".join(s)


# --------------------------------------------------------------------------- diagrams
G3, G4, G4b, G3w, G2, G5 = cols(3, 118), cols(4, 96), cols(4, 72), cols(3, 92), cols(2, 150), cols(5, 46)
D: list[dict] = []


def dg(**kw):
    D.append(kw)
    return kw


def _bot(R, pad=36):
    return max(r[1] + r[3] for r in R.values()) + pad


dg(id="C1", level=1, kind="context", parent=None, focus=None, cols=G3, vgap=60,
   title="System context — Shared MCP on one machine",
   shows="The system, the two people it serves, and the four things it must live with: the sessions that call it, "
         "the original server it hosts, the machine's service manager, and the marketplace that delivers it.",
   boxes=[bx("p.owner", 0, 0), bx("p.author", 2, 0),
          bx("ext.session", 0, 1), bx("sys.mcp", 1, 1), bx("ext.market", 2, 1),
          bx("ext.launchd", 0, 2), bx("ext.server", 1, 2), bx("ext.store", 2, 2)],
   edges=[dict(f="ext.session", t="sys.mcp", l="stdio JSON-RPC"),
          dict(f="ext.market", t="sys.mcp", l="installs · upgrades"),
          dict(f="ext.server", t="ext.store", l="single writer"),
          dict(f="sys.mcp", t="ext.server", l="runs exactly one, over stdio"),
          dict(f="sys.mcp", t="ext.launchd", both=True, l="registers · supervised by",
               pts=lambda R: down(R, "sys.mcp", "ext.launchd", dxf=-70)),
          dict(f="p.owner", t="sys.mcp", l="svc list · show · logs · doctor",
               pts=lambda R: down(R, "p.owner", "sys.mcp", dxt=-46)),
          dict(f="p.author", t="sys.mcp", l="vendors one file into the plugin",
               pts=lambda R: down(R, "p.author", "sys.mcp", dxt=46))])

dg(id="C2", level=2, kind="container", parent="C1", focus="sys.mcp", cols=G4, vgap=56, vpad=74,
   title="Containers — the request path",
   shows="Everything a tool call passes through, and the containers that keep the gateway alive. The dashed line "
         "along the bottom is the floor: when none of this can work, the session gets the plain per-session server "
         "it would have had anyway.",
   bounds=[(1, 2, 0, 3, "Shared MCP", 16)],
   boxes=[bx("c.agent", 1, 0, 2), bx("ext.launchd", 3, 0),
          bx("ext.session", 0, 1), bx("c.bridge", 1, 1), bx("c.gateway", 2, 1), bx("ext.server", 3, 1),
          bx("c.state", 1, 2), bx("c.venv", 2, 2), bx("ext.store", 3, 2),
          bx("c.specvault", 1, 3, 2)],
   edges=[dict(f="ext.session", t="c.bridge", l="stdio JSON-RPC"),
          dict(f="c.bridge", t="c.gateway", l="POST /mcp · 127.0.0.1:<port>"),
          dict(f="c.gateway", t="ext.server", l="spawns once · stdio"),
          dict(f="ext.server", t="ext.store", l="reads / writes"),
          dict(f="c.bridge", t="c.agent", l="registers it"),
          dict(f="c.agent", t="ext.launchd", l="plist / unit / pid file"),
          dict(f="ext.launchd", t="c.gateway", l="starts at login · restarts on exit",
               pts=lambda R: down(R, "ext.launchd", "c.gateway")),
          dict(f="c.bridge", t="c.state", l="writes spec.json"),
          dict(f="c.gateway", t="c.venv", l="runs in"),
          dict(f="c.gateway", t="c.state", l="reads it · appends gateway.log",
               pts=lambda R: down(R, "c.gateway", "c.state", dxf=-40, dxt=40)),
          dict(f="ext.session", t="c.specvault", l="stdio (its own bridge)",
               pts=lambda R: [(cxx(R["ext.session"]), R["ext.session"][1] + R["ext.session"][3]),
                              (cxx(R["ext.session"]), cyy(R["c.specvault"])), (R["c.specvault"][0], cyy(R["c.specvault"]))]),
          dict(f="ext.session", t="ext.server", dash=True,
               l="fallback: the launcher execs the original — Claude Code's old behaviour",
               pts=lambda R: [(cxx(R["ext.session"]) + 44, R["ext.session"][1] + R["ext.session"][3]),
                              (cxx(R["ext.session"]) + 44, _bot(R)), (767, _bot(R)),
                              (767, cyy(R["ext.server"]) + 42), (R["ext.server"][0], cyy(R["ext.server"]) + 42)])])

dg(id="C2M", level=2, kind="container", parent="C1", focus="sys.mcp", cols=G3, vgap=56, vpad=74,
   title="Containers — the management and evidence plane",
   shows="The same system seen by its owner rather than by a session: what is running, what it is for, and how the "
         "account of it is kept honest.",
   bounds=[(1, 2, 0, 2, "Shared MCP", 16)],
   boxes=[bx("ext.launchd", 0, 0), bx("c.room", 1, 0, 2),
          bx("p.owner", 0, 1), bx("c.console", 1, 1), bx("c.desc", 2, 1),
          bx("ext.market", 0, 2), bx("c.repo", 1, 2),
          bx("c.bridge", 2, 2, 1, "Writes the descriptor when it starts a gateway — and only if the console's directory already exists.")],
   edges=[dict(f="p.owner", t="c.console", l="svc list · show · logs · doctor"),
          dict(f="c.console", t="c.desc", l="reads purpose, source, probe"),
          dict(f="c.room", t="c.console", l="live evidence"),
          dict(f="c.console", t="ext.launchd", l="launchctl print / bootout / kickstart",
               pts=lambda R: up(R, "c.console", "ext.launchd", dxf=70)),
          dict(f="c.bridge", t="c.desc", l="writes its own descriptor"),
          dict(f="c.repo", t="ext.market", l="vendored copies published"),
          dict(f="ext.market", t="c.bridge", l="installs the plugin carrying the launcher",
               pts=lambda R: [(cxx(R["ext.market"]), R["ext.market"][1] + R["ext.market"][3]),
                              (cxx(R["ext.market"]), _bot(R)), (cxx(R["c.bridge"]), _bot(R)),
                              (cxx(R["c.bridge"]), R["c.bridge"][1] + R["c.bridge"][3])])])

dg(id="C2D", level=2, kind="dynamic", parent="C1", focus="sys.mcp", seq=True, cols=G5,
   title="Dynamic — cold start, from an empty machine to the first tool call",
   shows="The order of events the first time a session asks for a server that is not running yet. Steps 3 to 7 "
         "happen once per machine; every later session joins at step 8.",
   boxes=[bx("ext.session", 0, 0, 1, "One of N."), bx("c.bridge", 1, 0, 1, "This session's."),
          bx("ext.launchd", 2, 0, 1, "The machine's."), bx("c.gateway", 3, 0, 1, "One per server."),
          bx("ext.server", 4, 0, 1, "The plugin's own.")],
   steps=[dict(y=150, f="ext.session", t="c.bridge", l="1 · spawn `connect --name X -- <original>`"),
          dict(y=196, f="c.bridge", t="c.bridge", l="2 · build_spec: resolve the exe with THIS PATH, hash the port, fingerprint"),
          dict(y=254, f="c.bridge", t="c.gateway", l="3 · GET /health — nothing answers"),
          dict(y=300, f="c.bridge", t="ext.launchd", l="4 · write the plist, bootstrap it"),
          dict(y=346, f="ext.launchd", t="c.gateway", l="5 · start (ProcessType Interactive)"),
          dict(y=392, f="c.gateway", t="ext.server", l="6 · spawn the original · initialize"),
          dict(y=438, f="c.gateway", t="c.bridge", l="7 · /health returns name + owner: adopt it"),
          dict(y=484, f="ext.session", t="c.bridge", l="8 · initialize"),
          dict(y=530, f="c.bridge", t="c.gateway", l="9 · POST /mcp initialize → Mcp-Session-Id"),
          dict(y=576, f="c.bridge", t="ext.server", dash=True, l="10 · tools/call, forwarded verbatim through the gateway's proxy")])

dg(id="C2P", level=2, kind="deployment", parent="C1", focus="sys.mcp", cols=cols(3, 80), vgap=52, y0=76,
   title="Deployment — one Mac, right now",
   shows="Where the containers actually sit on this machine, with the counts read from the process table when this "
         "page was generated.",
   bounds=[(0, 2, 0, 2, "MacBook · macOS · one user account", 30),
           (0, 0, 0, 1, "Claude Code sessions", 12),
           (1, 2, 0, 0, "launchd user domain · com.shared-mcp.<owner>.*", 12),
           (0, 2, 2, 2, "filesystem · ~/.local", 12)],
   boxes=[bx("c.bridge", 0, 0, 1, "{bridges} running now: one per session per server, ~26 MB each, standard library only."),
          bx("c.gateway", 1, 0, 1, "{gateways} gateways, each on its own hashed loopback port in 47800-48799."),
          bx("ext.server", 2, 0, 1, "One child per gateway — the plugin's own program, unmodified."),
          bx("c.specvault", 0, 1, 1, "proxy.py, one per session, on the mcp library (~38 MB)."),
          bx("c.state", 0, 2), bx("c.venv", 1, 2), bx("c.desc", 2, 2)],
   edges=[dict(f="c.bridge", t="c.gateway", l="HTTP over loopback"),
          dict(f="c.gateway", t="ext.server", l="stdio")])

dg(id="C3B", level=3, kind="component", parent="C2", focus="c.bridge", cols=G3w, vgap=48,
   title="Components — the bridge process (shared_mcp.py connect)",
   shows="One process with two phases. The middle column is the sequence, top to bottom; the right column is what "
         "each step uses. Everything above the last box runs once, before a single byte is relayed.",
   bounds=[(1, 2, 0, 5, "Bridge process — one per session", 16)],
   boxes=[bx("ext.session", 0, 0), bx("b.parse", 1, 0), bx("b.fallback", 2, 0),
          bx("b.spec", 1, 1), bx("b.fp", 2, 1),
          bx("b.ensure", 1, 2), bx("b.lock", 2, 2),
          bx("b.venv", 1, 3), bx("b.rotate", 2, 3),
          bx("ext.launchd", 0, 4), bx("b.sup", 1, 4), bx("b.desc", 2, 4),
          bx("c.gateway", 0, 5), bx("b.bridge", 1, 5, 2)],
   edges=[dict(f="ext.session", t="b.parse", l="argv + stdio"),
          dict(f="b.parse", t="b.fallback", dash=True, l="DISABLE=1 · --per-session"),
          dict(f="b.parse", t="b.spec", l="connect"),
          dict(f="b.spec", t="b.fp", l="content identity"),
          dict(f="b.spec", t="b.ensure", l="the spec"),
          dict(f="b.ensure", t="b.lock", l="one session at a time"),
          dict(f="b.ensure", t="b.venv", l="1 · build the runtime"),
          dict(f="b.venv", t="b.rotate", l="2 · rotate the log"),
          dict(f="b.venv", t="b.sup", l="3 · register and start"),
          dict(f="b.sup", t="b.desc", l="4 · write the descriptor"),
          dict(f="b.sup", t="ext.launchd", l="bootstrap"),
          dict(f="b.sup", t="b.bridge", l="gateway guaranteed — now relay"),
          dict(f="b.bridge", t="c.gateway", l="POST /mcp")])

dg(id="C3G", level=3, kind="component", parent="C2", focus="c.gateway", cols=G3w, vgap=48,
   title="Components — the gateway process (shared_mcp.py gateway)",
   shows="The half of the kit that runs under the service manager: one child, one HTTP surface, and a liveness rule "
         "that survives servers which refuse to be pinged.",
   bounds=[(1, 2, 0, 4, "Gateway process — one per server, per machine", 26)],
   boxes=[bx("c.state", 0, 0, 1, "The definition it runs."), bx("g.main", 1, 0, 2),
          bx("ext.server", 0, 1, 1, "The plugin's own program."), bx("g.serve", 1, 1, 2),
          bx("c.bridge", 0, 2, 1, "Every session's."), bx("g.http", 1, 2), bx("g.proxy", 2, 2),
          bx("g.card", 1, 3), bx("g.guard", 2, 3),
          bx("g.watch", 1, 4, 2)],
   edges=[dict(f="g.main", t="c.state", l="spec.json"),
          dict(f="g.main", t="g.serve", l="restart loop · backoff 2 s → 60 s"),
          dict(f="g.serve", t="ext.server", l="spawn · initialize"),
          dict(f="g.serve", t="g.http", l="serve"),
          dict(f="g.serve", t="g.proxy", l="build from declared capabilities"),
          dict(f="c.bridge", t="g.http", l="POST /mcp"),
          dict(f="g.card", t="g.http", l="route"),
          dict(f="g.guard", t="g.proxy", l="wraps every call"),
          dict(f="g.watch", t="g.guard", l="reads the in-flight counter"),
          dict(f="g.watch", t="g.main", l="two silences: restart the child", rot=True,
               pts=lambda R: gutter(R, "g.watch", "g.main", G3w[1][0] - 9))])

dg(id="C3S", level=3, kind="component", parent="C2M", focus="c.console", cols=G4b, vgap=48,
   title="Components — the svc console",
   shows="Why the list cannot rot: everything except purpose, source and probe is re-derived from launchd, the "
         "process table and the filesystem on every single run.",
   bounds=[(1, 2, 0, 4, "svc console", 24)],
   boxes=[bx("s.membrane", 1, 0), bx("s.desc", 2, 0), bx("c.desc", 3, 0, 1, "purpose · source · probe"),
          bx("s.inv", 1, 1, 2), bx("ext.launchd", 3, 1, 1, "the user domain"),
          bx("s.doctor", 1, 2), bx("s.health", 2, 2), bx("c.gateway", 3, 2, 1, "the probed service"),
          bx("p.owner", 0, 3), bx("s.control", 1, 3), bx("s.prune", 2, 3),
          bx("s.selftest", 1, 4, 2)],
   edges=[dict(f="s.membrane", t="s.inv", l="parsed shapes"),
          dict(f="s.desc", t="s.inv", l="merged in"),
          dict(f="s.desc", t="c.desc", l="reads"),
          dict(f="s.inv", t="ext.launchd", l="launchctl print"),
          dict(f="s.inv", t="s.doctor", l="rules run over it"),
          dict(f="s.inv", t="s.health", l="one row per service"),
          dict(f="s.health", t="c.gateway", l="probe"),
          dict(f="p.owner", t="s.control", l="the verbs"),
          dict(f="s.inv", t="s.control", l="each verb re-derives", rot=True,
               pts=lambda R: gutter(R, "s.inv", "s.control", G4b[1][0] - 9)),
          dict(f="s.selftest", t="s.membrane", l="pins its output shapes", rot=True,
               pts=lambda R: gutter(R, "s.selftest", "s.membrane", G4b[2][0] + G4b[2][1] + 9, "r"))])

dg(id="C3V", level=3, kind="component", parent="C2", focus="c.specvault", cols=G4b, vgap=48,
   title="Components — the spec-vault graph daemon",
   shows="The same four jobs as the kit — supervise, bridge, serve, shut down cleanly — written before the kit "
         "existed, and kept because it works and the graph server speaks HTTP natively.",
   bounds=[(1, 2, 0, 2, "spec-vault graph daemon", 14)],
   boxes=[bx("ext.session", 0, 0), bx("v.daemon", 1, 0, 2), bx("ext.launchd", 3, 0, 1, "com.spec-vault.graph-server"),
          bx("v.proxy", 1, 1), bx("v.server", 2, 1), bx("ext.store", 3, 1, 1, "the graph database"),
          bx("v.sig", 1, 2, 2)],
   edges=[dict(f="ext.session", t="v.daemon", l="connect"),
          dict(f="v.daemon", t="ext.launchd", l="writes + bootstraps it"),
          dict(f="v.daemon", t="v.proxy", l="exec — same process"),
          dict(f="v.proxy", t="v.server", l="port 47765"),
          dict(f="v.server", t="ext.store", l="reads / writes"),
          dict(f="v.server", t="v.sig", l="SIGTERM / SIGINT"),
          dict(f="ext.launchd", t="v.server", l="starts it", pts=lambda R: down(R, "ext.launchd", "v.server"))])

dg(id="C4R", level=4, kind="code", parent="C3B", focus="b.bridge", cols=G3w, vgap=48,
   title="Code — Bridge.handle: send, classify, and the one rule about replay",
   shows="The decision that keeps a shared server honest. A reply that never arrived is not the same thing as a "
         "call that never ran, and only the first can be sent again.",
   boxes=[bx("ext.session", 0, 0, 1, "One JSON-RPC message; one thread per message."), bx("r.gate", 1, 0, 2),
          bx("r.post", 1, 1, 2),
          bx("r.ok", 0, 2), bx("r.http", 1, 2), bx("r.class", 2, 2),
          bx("r.report", 1, 3), bx("r.replay", 2, 3)],
   edges=[dict(f="ext.session", t="r.gate", l="stdin"),
          dict(f="r.gate", t="r.post", l="forward it"),
          dict(f="r.post", t="r.http", l="4xx / 5xx"),
          dict(f="r.post", t="r.class", l="the socket failed"),
          dict(f="r.post", t="r.ok", l="200 / 202",
               pts=lambda R: [(R["r.post"][0] + 24, R["r.post"][1] + R["r.post"][3]),
                              (R["r.post"][0] + 24, band(R, "r.post", "r.ok")),
                              (cxx(R["r.ok"]), band(R, "r.post", "r.ok")), (cxx(R["r.ok"]), R["r.ok"][1])]),
          dict(f="r.class", t="r.replay", l="pre-dispatch OR idempotent"),
          dict(f="r.class", t="r.report", l="anything else, or attempt 3",
               pts=lambda R: down(R, "r.class", "r.report")),
          dict(f="r.replay", t="r.post", l="retry the same message", rot=True,
               pts=lambda R: gutter(R, "r.replay", "r.post", G3w[2][0] + G3w[2][1] + 8, "r"))])

dg(id="C4E", level=4, kind="code", parent="C3B", focus="b.ensure", cols=G3w, vgap=48, vpad=74,
   title="Code — _ensure_locked: start, adopt, restart, or keep",
   shows="Four sessions with four opinions have to converge on one gateway. Every branch that ends in 'keep' is "
         "there because a real session once tried to replace a gateway that was better than its own.",
   boxes=[bx("e.newest", 1, 0, 2),
          bx("e.port", 0, 1), bx("e.probe", 1, 1, 2),
          bx("e.same", 1, 2), bx("e.keep", 2, 2),
          bx("c.gateway", 0, 3, 1, "Answering on its port, identifying itself by name and owner."), bx("e.start", 1, 3)],
   edges=[dict(f="e.newest", t="e.probe", l="restart_ok=False only"),
          dict(f="e.probe", t="e.port", l="silent"),
          dict(f="e.probe", t="e.same", l="answering"),
          dict(f="e.same", t="e.keep", l="yes — or one of three other reasons"),
          dict(f="e.same", t="e.start", l="no"),
          dict(f="e.start", t="c.gateway", l="wait for health"),
          dict(f="e.keep", t="c.gateway", l="return the one that is already right",
               pts=lambda R: [(cxx(R["e.keep"]), R["e.keep"][1] + R["e.keep"][3]), (cxx(R["e.keep"]), _bot(R)),
                              (cxx(R["c.gateway"]), _bot(R)), (cxx(R["c.gateway"]), R["c.gateway"][1] + R["c.gateway"][3])])])

dg(id="C4W", level=4, kind="code", parent="C3G", focus="g.watch", cols=G3w, vgap=48,
   title="Code — the gateway watchdog: what counts as a dead child",
   shows="Three real incidents are compiled into this loop: a server that rejects ping, a tool that runs for eight "
         "minutes, and a child that dies without saying so.",
   boxes=[bx("w.sleep", 1, 0), bx("g.main", 2, 0, 1, "The backoff loop that spawns a fresh child."),
          bx("w.busy", 1, 1),
          bx("w.reply", 0, 2), bx("w.probe", 1, 2),
          bx("w.miss", 1, 3), bx("w.restart", 2, 3)],
   edges=[dict(f="w.sleep", t="w.busy", l="tick"),
          dict(f="w.busy", t="w.probe", l="idle — or 10 min with nothing completing"),
          dict(f="w.busy", t="w.sleep", l="busy: stay quiet", pts=lambda R: up(R, "w.busy", "w.sleep", dxf=-64, dxt=-64)),
          dict(f="w.probe", t="w.reply", l="any reply"),
          dict(f="w.probe", t="w.miss", l="silence"),
          dict(f="w.reply", t="w.sleep", l="misses = 0",
               pts=lambda R: [(cxx(R["w.reply"]), R["w.reply"][1]), (cxx(R["w.reply"]), cyy(R["w.sleep"])),
                              (R["w.sleep"][0], cyy(R["w.sleep"]))]),
          dict(f="w.miss", t="w.restart", l="the second one in a row"),
          dict(f="w.restart", t="g.main", l="raise")])

dg(id="C4X", level=4, kind="code", parent="C3V", focus="v.sig", cols=G2, vgap=48, y0=64,
   title="Code — the SIGTERM handler, before and after",
   shows="The defect the whole system grew out of: a handler that asked a finalizing interpreter to join a thread "
         "that could never be joined.",
   texts=[(219, 0, 14, "middle", "Before — SIGABRT on every quit"), (780, 0, 14, "middle", "After — exit 0 in under a second")],
   boxes=[bx("x.sysexit", 0, 0), bx("x.reentry", 1, 0),
          bx("x.join", 0, 1), bx("x.cleanup", 1, 1),
          bx("x.abort", 0, 2), bx("x.osexit", 1, 2)],
   edges=[dict(f="x.sysexit", t="x.join", l="SystemExit"),
          dict(f="x.join", t="x.abort", l="the join never returns"),
          dict(f="x.reentry", t="x.cleanup", l="first signal"),
          dict(f="x.cleanup", t="x.osexit", l="always")])
# --------------------------------------------------------------------------- use cases (the "+1")
UC: list[dict] = []


def uc(id_, name, actor, note, els):
    UC.append(dict(id=id_, name=name, actor=actor, note=note, els=els))


uc("U1", "A session starts and gets its tools", "Claude Code session",
   "The ordinary case, a dozen times a day.",
   ["ext.session", "c.bridge", "b.parse", "b.spec", "b.fp", "b.ensure", "e.probe", "e.same", "e.keep",
    "c.gateway", "g.http", "g.proxy", "r.gate", "r.post", "r.ok", "ext.server"])
uc("U2", "The first session on a cold machine", "Claude Code session",
   "Nothing is running; the service has to be created before a single tool can be listed.",
   ["ext.session", "c.bridge", "b.ensure", "e.start", "b.venv", "b.rotate", "b.sup", "b.desc", "c.agent",
    "ext.launchd", "c.gateway", "g.main", "g.serve", "c.state", "c.venv", "c.desc", "ext.server"])
uc("U3", "A second session joins the running server", "Claude Code session",
   "The whole point: one server, many clients, one writer.",
   ["ext.session", "c.bridge", "b.ensure", "e.same", "e.keep", "c.gateway", "g.guard", "ext.server", "ext.store"])
uc("U4", "The server gets a new version", "Plugin author / marketplace",
   "A new install path, or the same path with new bytes — both must reach every session.",
   ["ext.market", "c.repo", "b.fp", "b.spec", "b.ensure", "e.same", "e.start", "c.gateway", "g.main", "c.state"])
uc("U5", "The gateway restarts under a call in flight", "the machine",
   "The failure that decides whether a shared server can be trusted with side effects.",
   ["ext.session", "c.bridge", "b.bridge", "r.post", "r.class", "r.replay", "r.report", "c.gateway",
    "g.watch", "w.probe", "w.reply", "w.miss", "w.restart", "g.main", "ext.server"])
uc("U6", "The owner audits and controls the daemons", "Machine owner",
   "What turns a dark daemon into a service someone can support.",
   ["p.owner", "c.console", "s.inv", "s.membrane", "s.desc", "s.health", "s.doctor", "s.control", "s.prune",
    "c.desc", "ext.launchd", "c.gateway", "c.room"])
uc("U7", "The machine cannot host a shared service", "Plugin installer",
   "Someone else's Windows box, a locked-down laptop, or an explicit opt-out.",
   ["p.author", "ext.session", "c.bridge", "b.parse", "b.fallback", "ext.server"])
uc("U8", "Everything quits", "Machine owner",
   "Where this began: the crash dialog on every quit.",
   ["ext.session", "c.bridge", "b.bridge", "c.specvault", "v.proxy", "v.server", "v.sig",
    "x.sysexit", "x.join", "x.abort", "x.reentry", "x.cleanup", "x.osexit"])


# --------------------------------------------------------------------------- derived indexes
def placements(d):
    return d["boxes"]


def drawn_in(eid):
    return [d["id"] for d in D if any(b["id"] == eid for b in placements(d))]


def zoomed_by(eid):
    return [d["id"] for d in D if d.get("focus") == eid]


def ucs_of(eid):
    return [u["id"] for u in UC if eid in u["els"]]


def children_of(did):
    return [d["id"] for d in D if d.get("parent") == did]


def uc_diagrams(u):
    return sorted({d["id"] for d in D for b in placements(d) if b["id"] in u["els"]},
                  key=lambda i: [x["id"] for x in D].index(i))


def _rects(d):
    R, _ys, _hs, _bot = layout(d)
    return [(i, *r) for i, r in R.items()]


def check() -> list[tuple[str, bool, str]]:
    """Structural properties of the set. generate.py prints the result into the room."""
    res = []
    bad = [f"{i} -> {e['parent']}" for i, e in EL.items()
           if e["level"] > 1 and (e["parent"] not in EL or EL[e["parent"]]["level"] != e["level"] - 1)]
    res.append(("Every element below Level 1 has a parent element exactly one level up",
                not bad, "; ".join(bad) or f"{sum(1 for e in EL.values() if e['level'] > 1)} elements checked"))

    orphan = [i for i in EL if not drawn_in(i)]
    res.append(("Every element is drawn on at least one diagram", not orphan,
                "; ".join(orphan) or f"{len(EL)} elements, {sum(len(placements(d)) for d in D)} placements"))

    bad = []
    for d in D:
        if d.get("parent"):
            par = next(x for x in D if x["id"] == d["parent"])
            if d["focus"] not in [b["id"] for b in placements(par)]:
                bad.append(f"{d['id']} focus {d['focus']} not drawn on {par['id']}")
    res.append(("Every diagram below Level 1 zooms into an element its parent diagram draws",
                not bad, "; ".join(bad) or f"{sum(1 for d in D if d.get('parent'))} diagrams checked"))

    bad = []
    for d in D:
        for b in placements(d):
            e = EL[b["id"]]
            if e["level"] > d["level"]:
                bad.append(f"{d['id']} draws {e['id']} (L{e['level']})")
            elif e["level"] == d["level"] and d.get("focus") and e["parent"] != d["focus"]:
                bad.append(f"{d['id']} draws {e['id']}, whose parent is {e['parent']}, not {d['focus']}")
    res.append(("No diagram draws below its own level, and its own-level elements are all children of its focus",
                not bad, "; ".join(bad) or f"{sum(len(placements(x)) for x in D)} placements checked"))

    counts = [sum(1 for d in D if d["level"] == n) for n in (1, 2, 3, 4)]
    res.append(("The set never narrows going down a level", all(b >= a for a, b in zip(counts, counts[1:])),
                " → ".join(f"L{n}: {c}" for n, c in enumerate(counts, 1))))

    bad = [f"{u['id']}:{e}" for u in UC for e in u["els"] if e not in EL]
    unreached = [u["id"] for u in UC if not any(EL[e]["level"] == 1 for e in u["els"] if e in EL)]
    res.append(("Every use case names real elements and reaches Level 1", not bad and not unreached,
                "; ".join(bad + unreached) or f"{len(UC)} use cases, {sum(len(u['els']) for u in UC)} references"))

    bad = []
    for d in D:
        rs = _rects(d)
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                (ai, ax, ay, aw, ah), (bi, bx, by, bw, bh) = rs[i], rs[j]
                if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                    bad.append(f"{d['id']}: {ai} overlaps {bi}")
    res.append(("No two boxes overlap in any drawing", not bad, "; ".join(bad) or f"{len(D)} drawings measured"))

    bad = []
    for d in D:
        if d.get("seq"):
            continue
        R = {i: (x, y, w, h) for (i, x, y, w, h) in _rects(d)}
        for ed in d.get("edges", []):
            if not ed.get("l"):
                continue
            pts = epts(d, R, ed)
            _l, _x, _y, (lx, ly, lw, lh) = _label_geom(pts, ed)
            for i, (bx, by, bw, bh) in R.items():
                if lx + 1 < bx + bw and bx + 1 < lx + lw and ly + 1 < by + bh and by + 1 < ly + lh:
                    bad.append(f"{d['id']}: '{ed['l'][:22]}' over {i}")
    res.append(("No edge label lands on a box", not bad, "; ".join(bad) or
                f"{sum(len([e for e in d.get('edges', []) if e.get('l')]) for d in D)} labels measured"))

    bad = []
    for d in D:
        if d.get("seq"):
            continue
        R = {i: (x, y, w, h) for (i, x, y, w, h) in _rects(d)}
        L = []
        for ed in d.get("edges", []):
            if ed.get("l"):
                L.append((ed["l"], _label_geom(epts(d, R, ed), ed)[3]))
        for i in range(len(L)):
            for j in range(i + 1, len(L)):
                (n1, (ax, ay, aw, ah)), (n2, (bx_, by, bw, bh)) = L[i], L[j]
                if ax < bx_ + bw and bx_ < ax + aw and ay < by + bh and by < ay + ah:
                    bad.append(f"{d['id']}: '{n1[:16]}' / '{n2[:16]}'")
    res.append(("No two edge labels overlap each other", not bad, "; ".join(bad) or f"{len(D)} drawings measured"))

    bad = []
    for d in D:
        for (i, x, y, w, h) in _rects(d):
            if len(EL[i]["name"]) * 6.9 > w - 24:
                bad.append(f"{d['id']}:{i}")
    res.append(("Every element name fits the box that carries it", not bad, "; ".join(bad) or f"{len(EL)} names measured"))

    over = []
    for d in D:
        if d.get("seq"):
            continue
        _R, _ys, _hs, bot = layout(d)
        for (i, x, y, w, h) in _rects(d):
            if x < 0 or x + w > VW or y + h > bot + 1:
                over.append(f"{d['id']}:{i}")
    res.append(("Every box fits inside its drawing", not over, "; ".join(over) or f"{len(D)} drawings measured"))
    return res


# --------------------------------------------------------------------------- the map of the set
LEVEL_FILL = {1: "#dfe9ef", 2: "#e1efe7", 3: "#ffffff", 4: "#eef1f0"}
MAP_ORDER = {2: ["C2M", "C2", "C2D", "C2P"], 3: ["C3S", "C3B", "C3G", "C3V"], 4: ["C4R", "C4E", "C4W", "C4X"]}


def render_map() -> str:
    """Derived from D and UC: the shape of the set itself."""
    W, rows = 1000, {1: 150, 2: 288, 3: 426, 4: 564}
    pos, s = {}, ['<svg viewBox="0 0 1000 700" xmlns="http://www.w3.org/2000/svg" font-family="ui-sans-serif,system-ui,sans-serif">',
                  '<defs><marker id="arw-map" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
                  f'<path d="M0 0L10 5L0 10z" fill="{ARROW}"/></marker></defs>']
    for i, u in enumerate(UC):
        x, w, y, h = 10 + i * 124, 112, 24, 74
        pos[u["id"]] = (x + w / 2, y, h)
        s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#f2ece2" stroke="#9a5b1e" stroke-width="1.3"/>')
        s.append(f'<text x="{x+8}" y="{y+16}" font-size="10" font-weight="700" font-family="ui-monospace,Menlo,monospace" fill="#9a5b1e">{E(u["id"])}</text>')
        yy = y + 30
        for ln in _wrap(u["name"], 17)[:4]:
            s.append(f'<text x="{x+8}" y="{yy}" font-size="9.5" fill="#11212e">{E(ln)}</text>'); yy += 11
    for lvl in (1, 2, 3, 4):
        ids = MAP_ORDER.get(lvl) or [d["id"] for d in D if d["level"] == lvl]
        n = len(ids); w = 220 if n > 1 else 300; gap = (W - 60 - n * w) / max(1, n - 1) if n > 1 else 0
        for i, did in enumerate(ids):
            d = next(x for x in D if x["id"] == did)
            x = 30 + i * (w + gap) if n > 1 else (W - w) / 2
            y, h = rows[lvl], 96
            pos[did] = (x + w / 2, y, h)
            s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{LEVEL_FILL[lvl]}" stroke="#3a4d5c" stroke-width="1.5"/>')
            s.append(f'<text x="{x+10}" y="{y+18}" font-size="11.5" font-weight="700" font-family="ui-monospace,Menlo,monospace" fill="#1d5b73">{E(did)}</text>')
            s.append(f'<text x="{x+w-10}" y="{y+18}" font-size="9.5" text-anchor="end" fill="#5f7a88">L{lvl} · {E(d["kind"])}</text>')
            yy = y + 36
            for ln in _wrap(d["title"].split(" — ")[-1], int((w - 20) / 5.4))[:4]:
                s.append(f'<text x="{x+10}" y="{yy}" font-size="10.5" fill="#11212e">{E(ln)}</text>'); yy += 12.5
        s.append(f'<text x="8" y="{rows[lvl]-8}" font-size="10" letter-spacing=".08em" fill="#5f7a88">LEVEL {lvl}</text>')
    s.append('<text x="8" y="16" font-size="10" letter-spacing=".08em" fill="#9a5b1e">CAPSTONE · USE CASES</text>')
    for u in UC:
        (ux, uy, uh), (cx, cy, _) = pos[u["id"]], pos["C1"]
        s.append(f'<path d="M{ux} {uy+uh}L{cx} {cy}" stroke="#c0aa8c" stroke-width="1.1" fill="none" marker-end="url(#arw-map)"/>')
    for d in D:
        if not d.get("parent"):
            continue
        (px, py, ph), (cx, cy, _) = pos[d["parent"]], pos[d["id"]]
        s.append(f'<path d="M{px} {py+ph}L{cx} {cy}" stroke="{ARROW}" stroke-width="1.4" fill="none" marker-end="url(#arw-map)"/>')
        t = 0.34 if d["level"] == 3 else 0.5
        s.append(f'<text x="{px+(cx-px)*t}" y="{py+ph+(cy-py-ph)*t}" font-size="9.5" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" '
                 f'fill="#5f7a88" stroke="#f6f4ee" stroke-width="3" paint-order="stroke">{E(d["focus"])}</text>')
    s.append("</svg>")
    return "".join(s)


# --------------------------------------------------------------------------- html
def dfig(d, live=None) -> str:
    svg = render_seq(d, live) if d.get("seq") else render(d, live)
    t = []
    if d.get("focus"):
        t.append(f'zooms into <code>{E(d["focus"])}</code> drawn on <a href="#dg-{d["parent"]}">{E(d["parent"])}</a>')
    ch = children_of(d["id"])
    if ch:
        t.append("zoomed by " + ", ".join(f'<a href="#dg-{c}">{c}</a>' for c in ch))
    t.append(f'{len(placements(d))} elements')
    us = sorted({u["id"] for u in UC for b in placements(d) if b["id"] in u["els"]})
    if us:
        t.append("exercised by " + ", ".join(us))
    return (f'<a id="dg-{d["id"]}"></a><figure><div class="cap"><span class="fno">{E(d["id"])}</span>'
            f'<span class="ft">{E(d["title"])}</span></div><div class="svgbox">{svg}</div></figure>'
            f'<p class="small">{E(d["shows"])}</p><p class="small"><b>Traces:</b> ' + " · ".join(t) + "</p>")


def _el_rows():
    r = []
    for e in sorted(EL.values(), key=lambda x: (x["level"], x["id"])):
        z = zoomed_by(e["id"])
        r.append(f'<tr><td><code>{E(e["id"])}</code></td><td>L{e["level"]}</td><td>{E(KIND[e["kind"]]["tag"])}</td>'
                 f'<td>{E(e["name"])}</td><td>{("<code>" + E(e["parent"]) + "</code>") if e["parent"] else "—"}</td>'
                 f'<td>{" ".join(f2(i) for i in drawn_in(e["id"]))}</td>'
                 f'<td>{" ".join(f2(i) for i in z) or "—"}</td>'
                 f'<td>{" ".join(ucs_of(e["id"])) or "—"}</td></tr>')
    return "".join(r)


def f2(did):
    return f'<a href="#dg-{did}"><code>{E(did)}</code></a>'


def sections(live=None) -> list[tuple[str, str, str, str]]:
    """(anchor, number, title, html) — generate.py wraps these with roomlib.sec."""
    by = {d["id"]: d for d in D}
    chk = check()
    chk_rows = "".join(f'<tr><td class="{"ok" if ok else "fail"}">{"PASS" if ok else "FAIL"}</td><td>{E(n)}</td><td>{E(det)}</td></tr>'
                       for n, ok, det in chk)
    lv = "".join(f"<tr><td>L{n}</td><td>{E(t)}</td><td>{E(f)}</td><td>{sum(1 for d in D if d['level']==n)}</td></tr>"
                 for n, t, f in [(1, "Context", "the system, its people, and what it must live with"),
                                 (2, "Container", "the separately running things inside it, and where they sit"),
                                 (3, "Component", "the parts of one container"),
                                 (4, "Code", "one decision inside one component, drawn because getting it wrong was expensive")])
    fig_map = ('<figure><div class="cap"><span class="fno">MAP</span><span class="ft">The set itself: every drawing, '
               'its level, and the element it zooms into. Derived from the same registries as the drawings.</span></div>'
               f'<div class="svgbox">{render_map()}</div></figure>')
    uc_rows = "".join(f'<tr><td><code>{E(u["id"])}</code></td><td>{E(u["name"])}</td><td>{E(u["actor"])}</td>'
                      f'<td>{len(u["els"])}</td><td>{" ".join(f2(i) for i in uc_diagrams(u))}</td></tr>' for u in UC)

    s1 = f"""
<p>The room so far argues from the top (§1–4) and inventories from the bottom (§5–9). These six sections are the
middle: one drawing per question, arranged so that each one zooms into a box on the drawing above it, and nothing
is drawn that the model does not also name.</p>
<p><b>How the set is built.</b> There is one registry of elements, one registry of drawings that place them, and one
registry of use cases that name the elements they exercise. Every label, every identifier in the corner of a box,
every "traces" line under a figure, this map, and the tables in §D6 are computed from those three — so a drawing
cannot quietly stop matching the model it claims to zoom into. The eight properties below are checked when this page
is generated; the page is generated on every commit to the kit.</p>
{fig_map}
<table><thead><tr><th>level</th><th>C4 name</th><th>what it answers here</th><th>drawings</th></tr></thead><tbody>{lv}</tbody></table>
<h3>Checks, run at build time</h3>
<table><thead><tr><th></th><th>property</th><th>detail</th></tr></thead><tbody>{chk_rows}</tbody></table>
<p class="small">The last two are not C4 rules; they are the reason the drawings can be authored as coordinates and
still be trusted — a box that grew past its neighbour, or past the edge, fails the build rather than the reader.</p>"""

    s2 = ("<p>One box for the system. The two people either side of it want different things from it: the owner wants "
          "to see and stop it, the plugin author wants to ship it to machines they will never log into. Everything "
          "below this drawing exists to serve both without asking either to configure anything.</p>"
          + dfig(by["C1"], live))

    s3 = ("<p>Four views of the same containers: the path a tool call takes, the plane the owner manages, the order "
          "events happen in on a cold machine, and where the processes actually sit.</p>"
          + dfig(by["C2"], live) + dfig(by["C2M"], live) + dfig(by["C2D"], live) + dfig(by["C2P"], live))

    s4 = ("<p>Two of these are the kit's own halves; one is the console that makes them supportable; one is the "
          "bespoke daemon that came first and still runs, drawn here so the family resemblance is on the record.</p>"
          + dfig(by["C3B"], live) + dfig(by["C3G"], live) + dfig(by["C3S"], live) + dfig(by["C3V"], live))

    s5 = ("<p>Level 4 is normally not worth drawing. These four are, because each one is a decision where the obvious "
          "implementation is wrong in a way that only shows up under real load: replaying a call that already ran, "
          "downgrading a gateway that was newer than yours, killing a child that was merely busy, and asking a "
          "finalizing interpreter to join a thread that will never return.</p>"
          + dfig(by["C4R"], live) + dfig(by["C4E"], live) + dfig(by["C4W"], live) + dfig(by["C4X"], live))

    s6 = f"""
<p>Three tables, all derived. The first reads downward: pick a use case, see every drawing it passes through. The
second reads upward: pick any element on any drawing, see its parent, the drawings that show it, and the drawing that
zooms into it. Together they are the property the request asked for — a set in which you can start anywhere and get
anywhere else without guessing.</p>
<h3>Use cases → drawings <span class="small">(the "+1" of 4+1)</span></h3>
<table><thead><tr><th>id</th><th>use case</th><th>actor</th><th>elements</th><th>drawings it passes through</th></tr></thead><tbody>{uc_rows}</tbody></table>
<h3>Element index</h3>
<p class="small">{len(EL)} elements, {sum(len(placements(d)) for d in D)} placements across {len(D)} drawings. The identifier in the
corner of every box on every figure above is the first column here.</p>
<table><thead><tr><th>id</th><th>level</th><th>kind</th><th>name</th><th>parent</th><th>drawn on</th><th>zoomed by</th><th>use cases</th></tr></thead>
<tbody>{_el_rows()}</tbody></table>"""

    return [("d1", "D1", "The diagram set, and how to read it", "C4 plus a use-case capstone — one registry, thirteen drawings", s1),
            ("d2", "D2", "Level 1 — Context", "What the system is, and what it must live with", s2),
            ("d3", "D3", "Level 2 — Containers", "The request path, the management plane, the order of events, and the machine", s3),
            ("d4", "D4", "Level 3 — Components", "Inside the bridge, the gateway, the console, and the bespoke daemon", s4),
            ("d5", "D5", "Level 4 — Code", "Four decisions that were worth drawing", s5),
            ("d6", "D6", "Traceability", "Every element, every drawing, every use case — one table each", s6)]


NAV = ('<div class="grp">The diagrams</div><ol>'
       + "".join(f'<li><a href="#{a}">{n} · {t}</a></li>' for a, n, t, _r, _b in
                 [(a, n, t.replace("Level 1 — ", "").replace("Level 2 — ", "").replace("Level 3 — ", "").replace("Level 4 — ", ""), r, b)
                  for a, n, t, r, b in sections()])
       + "</ol>")
