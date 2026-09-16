#!/usr/bin/env python3
"""Generate the shared-MCP reading room. Facts in §5 are read live from svc and the kit's
state so the room cannot drift from the machine; prose is authored here."""
import json, os, re, subprocess, time, html
from pathlib import Path
H = Path.home(); OUT = Path(__file__).with_name("index.html")
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True).stdout
svc = json.loads(sh("svc list --json") or "[]")
gw = [s for s in svc if s["name"].startswith("mcp-") or s["name"] == "spec-vault-graph"]
sessions = int(sh("pgrep -x claude | wc -l").strip() or 0)
bridges = {}
for l in sh("ps -axo command | grep '[s]hared_mcp.py connect'").splitlines():
    m = re.search(r"--name (\S+)", l); bridges[m.group(1)] = bridges.get(m.group(1), 0) + 1 if m else None
bridges["spec-vault"] = int(sh("pgrep -f graph-server/proxy.py | wc -l").strip() or 0)
mem = sh("ps -axo rss,command | grep -E 'shared_mcp|proxy.py|prompting_engine|graphology|prompt-library|ado-backlog|Efforts/mcp|projam/mcp|server.py --transport' | grep -v grep | awk '{s+=$1; n++} END {printf \"%d %d\", s/1024, n}'").split()
mem_mb, mem_n = (int(mem[0]), int(mem[1])) if len(mem) == 2 else (0, 0)
commits = {r: sh(f"git -C {p} log --oneline -8 -- {f} 2>/dev/null").strip() for r, p, f in [
    ("shared-mcp", H/"Developer/shared-mcp", "."), ("svc", H/".local/share/svc", "."),
    ("spec-vault (marketplace)", H/"Developer/AspenESS/ClaudeCodeMarketplace", "plugins/spec-vault plugins/ado-backlog-sync")]}
stamp = time.strftime("%Y-%m-%d %H:%M %Z")
E = html.escape

def gw_rows():
    r = []
    for s in sorted(gw, key=lambda x: x["name"]):
        h = s.get("health", {}); port = ",".join(map(str, s.get("ports", []))) or "—"
        n = s["name"].removeprefix("mcp-"); b = bridges.get(n if n != "spec-vault-graph" else "spec-vault", 0)
        r.append(f"<tr><td><code>{E(s['name'])}</code></td><td>{E(s.get('state') or '')}</td><td>{port}</td><td class='{h.get('verdict','')}'>{E(h.get('verdict',''))}</td><td>{b}</td><td>{E((s.get('purpose') or '')[:110])}</td></tr>")
    return "\n".join(r)

FIG_BEFORE_AFTER = """
<svg viewBox="0 0 980 330" xmlns="http://www.w3.org/2000/svg" font-family="ui-sans-serif,system-ui" font-size="13">
<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#3a4d5c"/></marker></defs>
<text x="20" y="28" font-weight="700" fill="#11212e">Before — one server per session</text>
<g fill="#fff" stroke="#3a4d5c">
 <rect x="20" y="50" width="150" height="40" rx="8"/><rect x="20" y="110" width="150" height="40" rx="8"/><rect x="20" y="170" width="150" height="40" rx="8"/>
 <rect x="260" y="50" width="170" height="40" rx="8" fill="#fbe9e7" stroke="#9a5b1e"/><rect x="260" y="110" width="170" height="40" rx="8" fill="#fbe9e7" stroke="#9a5b1e"/><rect x="260" y="170" width="170" height="40" rx="8" fill="#fbe9e7" stroke="#9a5b1e"/>
 <rect x="300" y="250" width="110" height="40" rx="8" fill="#eef1f0"/>
</g>
<g fill="#11212e"><text x="95" y="75" text-anchor="middle">session 1</text><text x="95" y="135" text-anchor="middle">session 2</text><text x="95" y="195" text-anchor="middle">session N</text>
<text x="345" y="75" text-anchor="middle">server copy 1</text><text x="345" y="135" text-anchor="middle">server copy 2</text><text x="345" y="195" text-anchor="middle">server copy N</text><text x="355" y="275" text-anchor="middle">database</text></g>
<g stroke="#3a4d5c" stroke-width="1.5" fill="none" marker-end="url(#a)"><path d="M170 70H258"/><path d="M170 130H258"/><path d="M170 190H258"/>
<path d="M345 90V250" stroke="#9a5b1e" stroke-dasharray="4 3"/><path d="M355 150V250" stroke="#9a5b1e" stroke-dasharray="4 3"/><path d="M365 210V250" stroke="#9a5b1e" stroke-dasharray="4 3"/></g>
<text x="440" y="275" fill="#9a5b1e" font-style="italic">N writers, one lock: takeover via SIGTERM</text>
<line x1="500" y1="20" x2="500" y2="310" stroke="#d9d2c4"/>
<text x="520" y="28" font-weight="700" fill="#11212e">After — one server per machine</text>
<g fill="#fff" stroke="#3a4d5c">
 <rect x="520" y="50" width="120" height="40" rx="8"/><rect x="520" y="110" width="120" height="40" rx="8"/><rect x="520" y="170" width="120" height="40" rx="8"/>
 <rect x="660" y="50" width="80" height="40" rx="8" fill="#eef4f6"/><rect x="660" y="110" width="80" height="40" rx="8" fill="#eef4f6"/><rect x="660" y="170" width="80" height="40" rx="8" fill="#eef4f6"/>
 <rect x="790" y="95" width="170" height="70" rx="10" fill="#e7f3ec" stroke="#0f5132"/><rect x="820" y="250" width="110" height="40" rx="8" fill="#eef1f0"/>
</g>
<g fill="#11212e"><text x="580" y="75" text-anchor="middle">session 1</text><text x="580" y="135" text-anchor="middle">session 2</text><text x="580" y="195" text-anchor="middle">session N</text>
<text x="700" y="75" text-anchor="middle" font-size="12">bridge</text><text x="700" y="135" text-anchor="middle" font-size="12">bridge</text><text x="700" y="195" text-anchor="middle" font-size="12">bridge</text>
<text x="875" y="122" text-anchor="middle" font-weight="600">gateway</text><text x="875" y="142" text-anchor="middle" font-size="12">original server ×1</text><text x="875" y="275" text-anchor="middle">database</text></g>
<g stroke="#3a4d5c" stroke-width="1.5" fill="none" marker-end="url(#a)"><path d="M640 70H658"/><path d="M640 130H658"/><path d="M640 190H658"/>
<path d="M740 70L788 110"/><path d="M740 130H788"/><path d="M740 190L788 150"/><path d="M875 165V248" stroke="#0f5132"/></g>
<text x="760" y="235" fill="#0f5132" font-size="12" font-style="italic">HTTP on 127.0.0.1 · one writer</text>
<text x="520" y="305" fill="#3a4d5c" font-size="12">launchd keeps the gateway alive; svc shows it</text>
</svg>"""

FIG_LADDER = """
<svg viewBox="0 0 980 250" xmlns="http://www.w3.org/2000/svg" font-family="ui-sans-serif,system-ui" font-size="13">
<defs><marker id="b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#3a4d5c"/></marker></defs>
<g fill="#fff" stroke="#3a4d5c">
<rect x="20" y="40" width="200" height="64" rx="10"/><rect x="260" y="40" width="200" height="64" rx="10"/><rect x="500" y="40" width="200" height="64" rx="10"/><rect x="740" y="40" width="220" height="64" rx="10" fill="#fbf3e6" stroke="#9a5b1e"/></g>
<g fill="#11212e" text-anchor="middle"><text x="120" y="64" font-weight="600">child server dies</text><text x="120" y="86" font-size="12">gateway restarts it (ping watchdog)</text>
<text x="360" y="64" font-weight="600">gateway dies / restarts</text><text x="360" y="86" font-size="12">bridge reconnects, replays call</text>
<text x="600" y="64" font-weight="600">gateway stays down</text><text x="600" y="86" font-size="12">bridge runs ensure after 10 s; launchd KeepAlive</text>
<text x="850" y="64" font-weight="600">no daemon possible</text><text x="850" y="86" font-size="12">launcher execs the original server</text></g>
<g stroke="#3a4d5c" stroke-width="1.5" fill="none" marker-end="url(#b)"><path d="M220 72H258"/><path d="M460 72H498"/><path d="M700 72H738"/></g>
<text x="20" y="150" fill="#3a4d5c">Each rung is a defined outcome. The last rung is exactly the pre-existing behaviour, so a plugin can never be worse off on a machine that cannot host a daemon.</text>
<text x="20" y="175" fill="#3a4d5c">Health is never asserted without a probe: gateways answer <tspan font-family="ui-monospace,Menlo">/health</tspan> with their identity; svc treats an unprobed service as unknown, not ok.</text>
<g fill="#fff" stroke="#3a4d5c"><rect x="20" y="195" width="940" height="40" rx="8" fill="#eef1f0"/></g>
<text x="490" y="220" text-anchor="middle" fill="#11212e">Fixed at the source underneath all of this: the graph server's SIGTERM handler aborted at Python 3.13 interpreter shutdown → macOS "Python quit unexpectedly" on every quit.</text>
</svg>"""

def sec(id_, num, title, role, body): return f'<section id="{id_}"><h2><span class="num">{num}</span>{title}</h2><p class="role">{role}</p>{body}</section>'
def fig(n, cap, svg): return f'<figure><div class="cap"><span class="fno">FIG {n}</span><span class="ft">{cap}</span></div><div class="svgbox">{svg}</div></figure>'

body = "".join([
sec("s0","0","Front matter","What this room is",f"""
<p>This is the coherent picture of how Claude Code's MCP servers now run on this machine and inside the plugins you publish: one process per server per machine, shared by every session, guaranteed by the plugin itself, visible from one console. It combines the concerns raised while building it — distributed, user, experience, technical, infrastructural, functional, feature, exceptional, ecosystem, development, networking — into one account rather than eleven.</p>
<p><b>Nouns used throughout.</b> An <b>MCP server</b> is a program that exposes tools to Claude over the Model Context Protocol. <b>stdio</b> means Claude talks to it through the process's own input and output pipes, which is one-to-one. A <b>gateway</b> is the process that runs one original server and serves it to many clients over HTTP on the loopback interface. A <b>bridge</b> is the small per-session program that speaks stdio to Claude and HTTP to a gateway. <b>launchd</b> is macOS's service manager. <b>svc</b> is the console built for this that lists and manages everything launchd runs for you.</p>
<p>§5 is generated from live state at {E(stamp)}; the rest is authored. Regenerate with <code>python3 reading-room/generate.py</code>.</p>"""),
sec("s1","1","The one sentence","The invariant everything else is a view of","""
<p class="big">An MCP server is a service that should exist once per machine; a Claude session is a client of it; the plugin that ships the server guarantees that arrangement on any machine, degrading to today's behaviour when it cannot; and the machine's owner sees and manages every such service from one console.</p>"""
 + fig(1,"Topology before and after. Left: Claude Code's default, a private server per session, N writers contending for one database through pid-file takeover. Right: bridges to one gateway per server; one writer; supervised by launchd; listed by svc.",FIG_BEFORE_AFTER)),
sec("s2","2","What a session sees","User · experience · functional · feature · exceptional","""
<h3>User and experience</h3><p>Nothing changes inside a conversation. Tool names are identical because server names are identical; <code>/mcp</code> lists the same servers; a fresh install's first session works with no setup. The visible differences are negative space: no crash dialog on quit, and gigabytes of memory returned to the machine.</p>
<h3>Functional</h3><p>Every tool, prompt and resource request is forwarded verbatim through the gateway to the single original process. A server that owns state — a database file, a lock — now has exactly one owner, so two sessions writing at once no longer fight.</p>
<h3>Feature</h3><p>Sharing is the plugin's default, not a per-machine override. The entire feature surface a plugin author touches is one line in <code>.mcp.json</code> pointing at the vendored launcher, with the original command after a <code>--</code> and the environment variables to forward declared with <code>--env</code>.</p>
<h3>Exceptional</h3><p>Failure has a defined shape at every layer, and the ladder ends on the old behaviour, never on a broken server.</p>"""
 + fig(2,"The failure ladder. Each rung is handled by a different component; the bottom rung is the plain per-session server, which is what existed before any of this.",FIG_LADDER)),
sec("s3","3","What the machine runs","Infrastructural · technical · networking · distributed","""
<h3>Infrastructural</h3><p>Each shared server is a launchd agent with a stable label, a state directory under <code>~/.local/state/shared-mcp/&lt;name&gt;/</code>, a log truncated at 5 MB, and a health endpoint that returns its identity. <code>svc</code> derives its inventory from launchd, the process table and the filesystem on every run, so the list cannot rot; the only authored facts are the ones launchd cannot know — purpose, source, health probe — kept as one small descriptor per service, written by the daemon itself when it starts.</p>
<h3>Technical</h3><p>Three moving parts. The <b>bridge</b>: standard-library Python, about 25 MB, one thread per client message, reconnects and replays when the gateway's session disappears, waits for the initialize handshake before forwarding pipelined messages. The <b>gateway</b>: the <code>mcp</code> library in a private virtualenv, runs the original command once, serves streamable HTTP, pings the child every 15 s and treats an error <em>reply</em> as alive (some servers reject ping) and only silence as dead. The <b>supervisor</b>: launchd here with <code>ProcessType Interactive</code> — without it the agent runs on efficiency cores and a 9 s cold start becomes 50 s, past Claude's 30 s connect timeout — systemd on Linux, a detached process elsewhere.</p>
<h3>Networking</h3><p>Loopback only, never bound off the machine. One port per server, hashed from the server name, so it is stable across restarts and machines and cannot collide between plugins from different authors. That is also why the numbers look arbitrary; legibility is the open question in §6. The spec-vault daemon moved off 8765 because an unidentified local client hammers that port with WebSocket upgrades.</p>
<h3>Distributed</h3><p>Many sessions, one process, per machine; nothing crosses machines. Secrets a server needs are captured once, from the declaring session, into a private <code>spec.json</code> rather than into launchd's plist. A session that cannot even resolve the server's executable keeps a healthy gateway started by a better-equipped session instead of replacing it with a definition that cannot run.</p>"""),
sec("s4","4","How it spreads and evolves","Ecosystem · development","""
<h3>Ecosystem</h3><p>The plugins stay publishable. Anyone installing them from your marketplaces gets the shared behaviour where their machine allows it and the old behaviour where it does not, with no dependency on anything that exists only on this Mac. Claude Code offers no per-user override of a plugin's server definition and no way to disable one plugin server while keeping its skills; redefining a server under your own name changes every tool name and breaks the plugin's skills and agents. The bridge is therefore the only shape that keeps tool names intact for everyone, and the four plugin servers keep bridges by necessity.</p>
<h3>Standards (checked 2026-09-15)</h3><p>MCP specifies stdio as one subprocess per client and Streamable HTTP for many clients; a <em>shared local</em> server is not specified. Converting the former into the latter on loopback is common community practice (mcp-proxy, supergateway, Docker's MCP Gateway) but a plugin installing a login-time service to get there is unusual, so every plugin now discloses it in its README and the launcher prints a first-run notice with the opt-out. Spec release 2026-07-28 (SEP-2575, SEP-2567) removed the initialize handshake, protocol sessions and <code>ping</code>; the bridge is correct in both generations (it waits for or replays <code>initialize</code> only if the client sent one, tracks a session id only if the server issued one, forwards JSON-RPC errors carried on 4xx) and the gateway's liveness probe is an ordinary RPC. Each gateway serves a Server Card (SEP-2127, in review) at <code>/.well-known/mcp/server-cards.json</code>. The roadmap's Transports WG item "HTTP over stdio" would reduce the bridge to a byte relay; the kit's public shape is meant to survive that unchanged, and this machine's case — a dozen clients, single-writer state — is a use case worth bringing to that working group.</p>
<h3>Development</h3><p>One canonical kit, <code>~/Developer/shared-mcp/shared_mcp.py</code>, with an end-to-end test whose fixture server carries a counter — two sessions seeing 1, 2, 3 is the proof of sharing — and a vendor script that stamps byte-identical copies into plugin roots. Fixes flow outward by re-vendoring and bumping. Three real bugs were found only by running it under your actual load and are now pinned: a restart loop from a rejected health ping, a PATH race between sessions with different environments, and an HTTP redirect on a mounted path. The graph server's own crash was fixed at its source first.</p>"""),
sec("s5","5","Current inventory","Derived live from svc and the process table",f"""
<p><b>{sessions}</b> Claude processes are running. MCP-related processes: <b>{mem_n}</b>, holding <b>{mem_mb} MB</b> (was 130 processes / 5.8 GB before the conversion; the remaining bulk is bridges at ≈25 MB each).</p>
<table><thead><tr><th>gateway</th><th>state</th><th>port</th><th>health</th><th>bridges</th><th>purpose</th></tr></thead><tbody>{gw_rows()}</tbody></table>
<p class="small">Health verdicts come from a live probe of each gateway's <code>/health</code> (or <code>/mcp</code> for spec-vault). "bridges" counts per-session bridge processes currently attached.</p>"""),
sec("s6","6","Open questions and the next step","What is not settled","""
<p><b>Legibility of addresses.</b> Hashed ports are correct for plugins shipped to strangers and unmemorable for the owner. For your three personal servers — projam, graphology, efforts — the right answer is one front door: a single process on one readable port with a path per server, e.g. <code>http://127.0.0.1:47800/servers/projam/mcp</code>. The open-source <a href="https://github.com/sparfenyuk/mcp-proxy">mcp-proxy</a> does exactly this in its server mode, one child per named server shared by every client. It cannot replace the kit inside plugins (it is a package with dependencies, not a single vendorable file, and it has no fallback), but for the personal three it removes 36 bridges and three launchd agents in exchange for one.</p>
<p><b>Unpushed.</b> The claude-code-profile repo (prompt-library lives inside it) has 16 unpushed commits including meeting-corpus content; its remote is GitHub, so pushing it is the owner's call. The marketplace (Azure DevOps) and advanced-prompting-engine (feature branch) are pushed.</p>
<p><b>What direct HTTP gives up.</b> Claude Code reconnects to HTTP servers with backoff, but the documentation does not say whether a terminated session after a gateway restart is retried; a <code>/mcp</code> reconnect may be needed in open sessions after the rare gateway restart. The bridge hides this today.</p>
<p><b>Unrelated but surfaced.</b> Graphology's tools fail because its Neo4j database is stopped (<code>brew services start neo4j</code>). The AutoBets jobs have 681 log files and 217 MB with no retention. Both iCloud agents log to /dev/null. One agent, <code>ai.openclaw.gateway</code> on port 18789, is unattributed.</p>"""),
sec("sref","R","Reference","Commands, paths, commits","""
<h3>Daily commands</h3>
<table><tbody>
<tr><td><code>svc list</code> / <code>svc doctor</code> / <code>svc health</code></td><td>everything launchd runs for you; findings; probes</td></tr>
<tr><td><code>svc show mcp-projam</code> · <code>svc logs mcp-projam</code></td><td>one service in full; its log</td></tr>
<tr><td><code>svc restart mcp-projam --go</code></td><td>dry-run without <code>--go</code>; verifies the effect before claiming success</td></tr>
<tr><td><code>python3 ~/Developer/shared-mcp/shared_mcp.py status|stop|ensure|logs --name X</code></td><td>the kit's own verbs</td></tr>
<tr><td><code>SHARED_MCP_DISABLE=1</code></td><td>escape hatch: run a plugin's server per session again</td></tr>
<tr><td><code>herdr server stop && herdr</code></td><td>restart every session so it picks up config changes</td></tr>
</tbody></table>
<h3>Paths</h3>
<table><tbody>
<tr><td><code>~/Developer/shared-mcp/</code></td><td>the kit, its test, vendor script, this room</td></tr>
<tr><td><code>~/.local/share/svc/</code></td><td>svc source, fixtures, MANIFESTO</td></tr>
<tr><td><code>~/.config/svc/services.d/</code></td><td>one descriptor per service (purpose, source, health, manage)</td></tr>
<tr><td><code>~/.local/state/shared-mcp/&lt;name&gt;/</code></td><td>spec.json (0600), gateway.log</td></tr>
<tr><td><code>~/Library/LaunchAgents/com.shared-mcp.*.plist</code>, <code>com.spec-vault.graph-server.plist</code></td><td>the agents</td></tr>
</tbody></table>
<h3>Recent commits</h3>""" + "".join(f"<h4>{E(r)}</h4><pre>{E(c) or '(none)'}</pre>" for r, c in commits.items())),
])

nav = """<nav class="toc"><h1>Shared MCP</h1><p class="sub">One server per machine — Reading Room</p>
<div class="grp">Primary</div><ol><li><a href="#s0">0 · Front matter</a></li><li><a href="#s1">1 · The one sentence</a></li></ol>
<div class="grp">Views</div><ol><li><a href="#s2">2 · What a session sees</a></li><li><a href="#s3">3 · What the machine runs</a></li><li><a href="#s4">4 · How it spreads and evolves</a></li><li><a href="#s5">5 · Current inventory (live)</a></li><li><a href="#s6">6 · Open questions</a></li></ol>
<div class="grp">Reference</div><ol><li><a href="#sref">R · Commands, paths, commits</a></li></ol></nav>"""

CSS = """
:root{--ink:#11212e;--ink-soft:#3a4d5c;--paper:#f6f4ee;--card:#fff;--rule:#d9d2c4;--accent:#1d5b73;--accent-2:#7a5ca6;--warn:#9a5b1e;--ok:#0f5132;--code:#eef1f0;--shadow:0 1px 3px rgba(0,0,0,.08),0 8px 28px rgba(0,0,0,.06)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.62 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.shell{display:grid;grid-template-columns:288px minmax(0,1fr);min-height:100vh}
nav.toc{position:sticky;top:0;align-self:start;height:100vh;overflow-y:auto;background:#10242f;color:#cfe0e6;padding:28px 22px;border-right:1px solid #0a1922}
nav.toc h1{font-size:15px;letter-spacing:.04em;text-transform:uppercase;color:#f6f4ee;margin:0 0 4px}
nav.toc .sub{font-size:12.5px;color:#8fb0bb;margin:0 0 22px;font-style:italic}
nav.toc ol{list-style:none;margin:0;padding:0}nav.toc li{margin:2px 0}
nav.toc a{display:block;color:#bcd2da;padding:5px 8px;border-radius:6px;font-size:13.5px;font-family:ui-sans-serif,system-ui,sans-serif}
nav.toc a:hover{background:#16323f;text-decoration:none;color:#fff}
nav.toc .grp{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#5f8694;margin:18px 0 4px;font-family:ui-sans-serif,system-ui,sans-serif}
.wrap{max-width:1100px;padding:56px 64px 120px}
header.doc{border-bottom:2px solid var(--ink);padding-bottom:26px;margin-bottom:8px}
header.doc .kicker{font:600 12px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:var(--accent)}
header.doc h1{font-size:33px;line-height:1.18;margin:14px 0 10px;letter-spacing:-.01em}
header.doc .lede{font-size:17px;color:var(--ink-soft);margin:0}
.meta{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:18px;font:13px/1.4 ui-sans-serif,system-ui,sans-serif;color:var(--ink-soft)}.meta b{color:var(--ink);font-weight:600}
section{padding:38px 0 8px;border-top:1px solid var(--rule);margin-top:30px}section:first-of-type{border-top:none}
h2{font-size:24px;margin:0 0 4px;letter-spacing:-.01em}h2 .num{color:var(--accent);font-variant-numeric:tabular-nums;margin-right:10px}
h3{font-size:16.5px;margin:26px 0 6px}h4{font:600 13px/1 ui-sans-serif,system-ui,sans-serif;margin:18px 0 6px;color:var(--ink-soft)}
.role{font:600 11.5px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--accent-2);margin:0 0 14px}
p{margin:12px 0}p.big{font-size:20px;line-height:1.5;border-left:4px solid var(--accent);padding:6px 0 6px 18px;margin:18px 0}p.small{font-size:13.5px;color:var(--ink-soft)}
code{background:var(--code);padding:.1em .42em;border-radius:4px;font:13.5px/1.5 ui-monospace,"SF Mono",Menlo,monospace}
pre{background:var(--code);padding:12px 14px;border-radius:8px;font:12.5px/1.5 ui-monospace,Menlo,monospace;overflow:auto}
figure{margin:26px 0;background:var(--card);border:1px solid var(--rule);border-radius:12px;box-shadow:var(--shadow);overflow:hidden}
figure .cap{display:flex;gap:10px;align-items:center;padding:13px 18px;border-bottom:1px solid var(--rule);background:#fbfaf6}
figure .cap .fno{font:700 12px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent);white-space:nowrap}
figure .cap .ft{font:13.5px/1.4 ui-sans-serif,system-ui,sans-serif;color:var(--ink-soft)}
figure .svgbox{padding:18px}.svgbox svg{width:100%;height:auto;display:block}
table{width:100%;border-collapse:collapse;margin:14px 0;font:14px/1.45 ui-sans-serif,system-ui,sans-serif;background:var(--card);border:1px solid var(--rule);border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}th{background:#fbfaf6;font-weight:600}
td.ok{color:var(--ok);font-weight:600}td.fail{color:var(--warn);font-weight:600}
footer{margin-top:60px;padding-top:18px;border-top:1px solid var(--rule);font:13px/1.5 ui-sans-serif,system-ui,sans-serif;color:var(--ink-soft)}
@media (max-width:900px){.shell{grid-template-columns:1fr}nav.toc{position:static;height:auto}.wrap{padding:28px 20px 80px}}
"""
OUT.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shared MCP — One Server per Machine · Reading Room</title><style>{CSS}</style></head><body><div class="shell">{nav}
<main><div class="wrap"><header class="doc"><div class="kicker">Personal infrastructure · reading room</div>
<h1>Shared MCP: one server per machine, shared by every Claude session</h1>
<p class="lede">How Claude Code's per-session MCP servers became shared, supervised, self-registering services — the crash that started it, the kit that makes sharing a plugin's default while staying safe on any machine, the console that keeps the daemons visible, and what remains open.</p>
<div class="meta"><span><b>Subject:</b> <code>~/Developer/shared-mcp</code> · <code>~/.local/share/svc</code> · spec-vault graph server</span><span><b>Generated:</b> {E(stamp)}</span><span><b>Machine:</b> this Mac; plugins publishable</span></div></header>
{body}
<footer>Generated by <code>reading-room/generate.py</code>. Prose authored; §5 and the commit lists derived at generation time. Regenerate after changes so the room never lies about the machine.</footer>
</div></main></div></body></html>""")
print(f"wrote {OUT} ({OUT.stat().st_size//1024} KB)")
