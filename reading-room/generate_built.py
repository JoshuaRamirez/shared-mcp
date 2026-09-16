#!/usr/bin/env python3
"""What was built — an artifact tour. Prose authored; file facts, test output, commit lists and
the live inventory are derived at generation time so the room describes the real artifacts."""
import json, os, re, subprocess, time
from pathlib import Path
from roomlib import E, sec, fig, page
H = Path.home(); OUT = Path(__file__).with_name("what-was-built.html")
def sh(c, cwd=None, t=300):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, cwd=cwd, timeout=t).stdout
    except subprocess.TimeoutExpired: return "(timed out)"
def lines(p): 
    try: return sum(1 for _ in open(p, errors="replace"))
    except OSError: return 0
KIT = H/"Developer/shared-mcp/shared_mcp.py"; SVC = H/".local/share/svc/svc.py"
GS = H/"Developer/AspenESS/ClaudeCodeMarketplace/plugins/spec-vault/graph-server"
stamp = time.strftime("%Y-%m-%d %H:%M %Z")

# ---- live evidence ----
kit_test = sh("python3 tests/test_shared.py 2>&1 | grep -v '^\\[shared-mcp\\] building'", cwd=H/"Developer/shared-mcp")
svc_test = sh("svc selftest 2>&1")
svc_list = sh("svc list 2>&1"); svc_doc = sh("svc doctor 2>&1")
agents = sh("ls ~/Library/LaunchAgents | grep -E 'shared-mcp|spec-vault|svc-prune'")
state = sh("du -sh ~/.local/state/shared-mcp ~/.local/state/spec-vault ~/.local/state/svc 2>/dev/null")
descs = sh("ls ~/.config/svc/services.d/")
commits = {}
for label, path, spec in [("shared-mcp (public)", H/"Developer/shared-mcp", "."), ("svc", H/".local/share/svc", "."),
                          ("ClaudeCodeMarketplace", H/"Developer/AspenESS/ClaudeCodeMarketplace", "plugins/spec-vault plugins/ado-backlog-sync .claude-plugin/marketplace.json"),
                          ("advanced-prompting-engine", H/"Developer/advanced-prompting-engine", "shared_mcp.py .mcp.json README.md"),
                          ("claude-code-profile (prompt-library)", H/".claude/skills/prompt-library", "shared_mcp.py .mcp.json README.md")]:
    commits[label] = sh(f"git log --since=2026-09-13 --format='%h %ad %s' --date=short -- {spec}", cwd=path).strip()
files = [
 ("shared_mcp.py", KIT, "the kit: launcher, bridge, gateway, supervision — one file, stdlib on the per-session path"),
 ("tests/test_shared.py", H/"Developer/shared-mcp/tests/test_shared.py", "end-to-end proof: two bridges share one server, restart survival, stop, fallback"),
 ("tests/fixture_server.py", H/"Developer/shared-mcp/tests/fixture_server.py", "tiny MCP server with a counter — the sharing witness"),
 ("vendor.sh", H/"Developer/shared-mcp/vendor.sh", "copies the kit byte-identically into plugin roots"),
 ("svc.py", SVC, "the console: derived inventory, health, doctor, prune, verified control"),
 ("svc fixtures", H/".local/share/svc/fixtures/expected.json", "pinned plist classifications and launchctl output shapes"),
 ("graph-server/server.py", GS/"server.py", "spec-vault's server: the SIGTERM fix and the --transport http mode"),
 ("graph-server/daemon.sh", GS/"daemon.sh", "spec-vault's own daemon manager (predates the kit; bespoke)"),
 ("graph-server/proxy.py", GS/"proxy.py", "spec-vault's per-session bridge (mcp-library based, heavier than the kit's)"),
 ("reading-room/generate*.py", Path(__file__), "these rooms"),
]
def frow(n, p, d):
    size = p.stat().st_size if p.exists() else 0
    return f"<tr><td><code>{E(n)}</code></td><td>{lines(p) if p.suffix in ('.py','.sh') else '—'}</td><td>{size//1024} KB</td><td>{E(d)}</td><td><code>{E(str(p).replace(str(H),'~'))}</code></td></tr>"

FIG_MAP = """<svg viewBox="0 0 980 420" xmlns="http://www.w3.org/2000/svg" font-family="ui-sans-serif,system-ui" font-size="12.5">
<defs><marker id="m" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#3a4d5c"/></marker></defs>
<text x="20" y="26" font-weight="700" font-size="14" fill="#11212e">Where each artifact lives, and what talks to what</text>
<g stroke="#3a4d5c" fill="#fff">
<rect x="20" y="50" width="290" height="150" rx="10" fill="#f3f6f8"/><rect x="340" y="50" width="300" height="150" rx="10" fill="#f3f6f8"/><rect x="670" y="50" width="290" height="150" rx="10" fill="#f3f6f8"/>
<rect x="20" y="240" width="940" height="150" rx="10" fill="#fbfaf6"/></g>
<g fill="#1d5b73" font-weight="700"><text x="34" y="72">~/Developer/shared-mcp  (public repo)</text><text x="354" y="72">~/.local/share/svc  (repo)</text><text x="684" y="72">plugin repos (published)</text><text x="34" y="262">machine state this created</text></g>
<g fill="#11212e"><text x="34" y="96">shared_mcp.py — kit</text><text x="34" y="116">tests/ · vendor.sh · README</text><text x="34" y="136">reading-room/ (these pages)</text>
<text x="354" y="96">svc.py + libexec/ seam</text><text x="354" y="116">fixtures/ + selftest</text><text x="354" y="136">MANIFESTO.md (ledger)</text>
<text x="684" y="96">ClaudeCodeMarketplace: spec-vault, ado-backlog-sync</text><text x="684" y="116">advanced-prompting-engine: vendored kit</text><text x="684" y="136">claude-code-profile: prompt-library</text><text x="684" y="156">~/.claude.json: projam · graphology · efforts</text>
<text x="34" y="286">~/Library/LaunchAgents/com.shared-mcp.&lt;name&gt;.plist ×6 · com.spec-vault.graph-server.plist · com.joshua.svc-prune.plist</text>
<text x="34" y="308">~/.local/state/shared-mcp/{venv, &lt;name&gt;/spec.json (0600), gateway.log} · ~/.local/state/spec-vault/ · ~/.local/state/svc/prune.log</text>
<text x="34" y="330">~/.config/svc/services.d/&lt;label&gt;.json — one descriptor per service (purpose, source, health, manage)</text>
<text x="34" y="352" fill="#3a4d5c" font-style="italic">Undo everything: `svc list` to see it, `shared_mcp.py stop --name X` per gateway, `daemon.sh stop`, `launchctl bootout` + rm for svc-prune, then rm -rf the three state dirs.</text></g>
<g stroke="#3a4d5c" stroke-width="1.5" fill="none" marker-end="url(#m)"><path d="M165 200V238"/><path d="M490 200V238"/><path d="M815 200V238"/><path d="M310 100H338" stroke-dasharray="3 3"/><path d="M640 100H668" stroke-dasharray="3 3"/></g>
<text x="318" y="92" fill="#3a4d5c" font-size="11">writes descriptors</text><text x="620" y="92" fill="#3a4d5c" font-size="11">vendored into</text>
</svg>"""

FIG_CONNECT = """<svg viewBox="0 0 980 400" xmlns="http://www.w3.org/2000/svg" font-family="ui-sans-serif,system-ui" font-size="12.5">
<defs><marker id="c" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#3a4d5c"/></marker></defs>
<text x="20" y="26" font-weight="700" font-size="14" fill="#11212e">One session start: what `shared_mcp.py connect` does, top to bottom</text>
<g fill="#fff" stroke="#3a4d5c">
<rect x="20" y="50" width="220" height="46" rx="8"/><rect x="20" y="116" width="220" height="46" rx="8"/><rect x="20" y="182" width="220" height="46" rx="8" fill="#e7f3ec" stroke="#0f5132"/><rect x="20" y="248" width="220" height="46" rx="8"/><rect x="20" y="314" width="220" height="46" rx="8" fill="#eef4f6"/>
<rect x="300" y="116" width="300" height="46" rx="8"/><rect x="300" y="182" width="300" height="46" rx="8"/><rect x="300" y="248" width="300" height="46" rx="8" fill="#fbf3e6" stroke="#9a5b1e"/>
<rect x="660" y="116" width="300" height="46" rx="8" fill="#fbfaf6"/><rect x="660" y="182" width="300" height="46" rx="8" fill="#fbfaf6"/><rect x="660" y="248" width="300" height="46" rx="8" fill="#fbfaf6"/><rect x="660" y="314" width="300" height="46" rx="8" fill="#fbfaf6"/></g>
<g fill="#11212e"><text x="130" y="70" text-anchor="middle" font-weight="600">Claude runs .mcp.json command</text><text x="130" y="88" text-anchor="middle" font-size="11">python3 shared_mcp.py connect --name X -- ...</text>
<text x="130" y="136" text-anchor="middle" font-weight="600">build_spec()</text><text x="130" y="154" text-anchor="middle" font-size="11">resolve exe · hash port · capture declared env</text>
<text x="130" y="202" text-anchor="middle" font-weight="600">ensure(spec)</text><text x="130" y="220" text-anchor="middle" font-size="11">gateway healthy &amp; same? → done</text>
<text x="130" y="268" text-anchor="middle" font-weight="600">Bridge(spec).run()</text><text x="130" y="286" text-anchor="middle" font-size="11">stdin lines → POST /mcp → stdout</text>
<text x="130" y="334" text-anchor="middle" font-weight="600">on failure: exec original</text><text x="130" y="352" text-anchor="middle" font-size="11">plain per-session server (old behaviour)</text>
<text x="450" y="136" text-anchor="middle" font-weight="600">not running → ensure_venv()</text><text x="450" y="154" text-anchor="middle" font-size="11">uv venv or python -m venv; pip install mcp</text>
<text x="450" y="202" text-anchor="middle" font-weight="600">start_gateway(spec)</text><text x="450" y="220" text-anchor="middle" font-size="11">launchd plist · systemd unit · detached</text>
<text x="450" y="268" text-anchor="middle" font-weight="600">running but stale def → restart</text><text x="450" y="286" text-anchor="middle" font-size="11">plugin upgraded; unresolvable exe → keep</text>
<text x="810" y="136" text-anchor="middle" font-weight="600">gateway (in venv)</text><text x="810" y="154" text-anchor="middle" font-size="11">stdio_client(original cmd) once</text>
<text x="810" y="202" text-anchor="middle" font-weight="600">uvicorn on 127.0.0.1:port</text><text x="810" y="220" text-anchor="middle" font-size="11">/mcp · /health · /.well-known/mcp/server-cards.json</text>
<text x="810" y="268" text-anchor="middle" font-weight="600">watchdog: tools/list every 30s</text><text x="810" y="286" text-anchor="middle" font-size="11">any reply = alive; silence → restart child</text>
<text x="810" y="334" text-anchor="middle" font-weight="600">write_svc_descriptor()</text><text x="810" y="352" text-anchor="middle" font-size="11">only if ~/.config/svc/services.d exists</text></g>
<g stroke="#3a4d5c" stroke-width="1.5" fill="none" marker-end="url(#c)"><path d="M130 96V114"/><path d="M130 162V180"/><path d="M130 228V246"/><path d="M240 205H298"/><path d="M450 162V180"/><path d="M600 205H658"/><path d="M810 162V180"/><path d="M810 228V246"/><path d="M810 294V312"/><path d="M240 271H298" stroke-dasharray="3 3"/><path d="M130 294V312" stroke-dasharray="3 3" stroke="#9a5b1e"/></g>
</svg>"""

def pre(t): return f"<pre>{E(t.strip() or '(empty)')}</pre>"

body = "".join([
sec("s0","0","How to read this","Front matter", f"""
<p>This room is a tour of the <em>things</em>: every file, service and configuration change made between 2026-09-13 and today to fix the quit-time crash and share MCP servers across sessions. Its companion, <a href="index.html">the coherent picture</a>, is the argument; this is the inventory. Read §1 for the map, then whichever component you want to understand. §8 is live evidence produced when this page was generated ({E(stamp)}); rerun <code>reading-room/generate_built.py</code> to refresh it.</p>
<p>Nouns: an <b>MCP server</b> exposes tools to Claude over the Model Context Protocol; <b>stdio</b> is the one-to-one pipe transport; a <b>gateway</b> runs one server and serves many clients over HTTP on loopback; a <b>bridge</b> is the per-session stdio-to-HTTP adapter; <b>launchd</b> is macOS's service manager; a <b>descriptor</b> is the small JSON file that tells <b>svc</b> what launchd cannot know about a service.</p>""")
+ fig(1,"Repositories, machine state, and the arrows between them. Everything under the bottom band was created by the artifacts above it and can be removed with the commands in §6.",FIG_MAP),
sec("s1","1","The files","What exists, with size and line counts read from disk", f"""
<table><thead><tr><th>artifact</th><th>lines</th><th>size</th><th>what it is</th><th>path</th></tr></thead><tbody>{''.join(frow(*f) for f in files)}</tbody></table>"""),
sec("s2","2","The crash fix","spec-vault graph-server/server.py — the root cause everything else grew from", """
<p><b>Symptom.</b> macOS "Python quit unexpectedly" on every Claude quit. <b>Cause.</b> The graph server's SIGTERM handler called <code>sys.exit(0)</code>. That starts Python's interpreter finalization while the MCP library's stdin reader is blocked in a read on a non-daemon worker thread that holds the stdin buffer lock. Finalization waited on that thread forever (servers lingered for days after pid-file takeover), and when Claude closed the pipe the thread woke into a finalizing Python 3.13 interpreter, was parked, and the main thread aborted with "could not acquire lock for &lt;_io.BufferedReader name='&lt;stdin&gt;'&gt; at interpreter shutdown".</p>
<p><b>Fix</b> (commit f4ee628). The handler now runs the two cleanups itself, guarded against re-entry, and leaves via <code>os._exit(0)</code>, skipping finalization and the join. Signal registration moved below the pid-file helpers so the handler can never reference an undefined name. Verified with SIGTERM while stdin open (previously hung forever), stdin EOF then SIGTERM, and double SIGTERM: all exit 0 in under a second.</p>
<p><b>Then</b> the same file gained <code>--transport http</code> (streamable HTTP via FastMCP, host/port flags or env) so one instance can serve every session — the first shared daemon, before the generic kit existed.</p>"""),
sec("s3","3","spec-vault's own daemon","graph-server/daemon.sh + proxy.py — bespoke, predates the kit", """
<p><code>daemon.sh</code> is a bash manager the plugin ships. <code>connect</code> (what <code>.mcp.json</code> runs) builds a persistent venv at <code>~/.local/state/spec-vault/venv</code> when <code>requirements.txt</code> changes, starts the daemon via a generated launchd agent <code>com.spec-vault.graph-server</code> (ProcessType Interactive — without it launchd puts the process on efficiency cores and cold start goes from 9 s to 50 s, past Claude's 30 s connect timeout), restarts it when the plugin path changed after an upgrade, rotates its log at 5 MB, writes an svc descriptor, waits for the port, then execs <code>proxy.py</code>. Other verbs: <code>status</code>, <code>logs</code>, <code>stop</code> (waits for the port to go quiet; removes the descriptor), <code>ensure</code>. It survives two launchd races: bootstrap right after bootout (EIO; retried) and a dying process mistaken for a foreign one.</p>
<p><code>proxy.py</code> is the per-session bridge, built on the <code>mcp</code> library (~38 MB per session). Its upstream connection lives in one supervising task that reconnects and replays the in-flight call when the daemon restarts; a watchdog polls the daemon's health while a request waits so a call in flight during a restart cannot hang. Port 47765 (moved off 8765, which an unidentified local client hammers with WebSocket upgrades).</p>
<p><b>Why it still exists alongside the kit.</b> It works, it is the plugin's own code, and the graph server has native HTTP so it needs no gateway wrapper. Migrating it to the kit would trade a heavier bridge for uniformity; recorded as optional.</p>"""),
sec("s4","4","The shared-mcp kit","shared_mcp.py — one file that makes sharing a plugin's default while staying safe anywhere", """
<p>A plugin points its MCP entry at <code>python3 shared_mcp.py connect --name X [--env KEY]... -- &lt;original command&gt;</code>. The file is ~700 lines in six parts, in file order:</p>
<table><tbody>
<tr><td><b>spec / paths</b></td><td><code>build_spec</code> resolves the executable with the session's PATH (a venv once shadowed <code>python3</code>), hashes a stable port from the name (47800–48799), captures only the declared env vars, records cwd and the launcher path. <code>~/.local/state/shared-mcp/&lt;name&gt;/spec.json</code>, mode 0600.</td></tr>
<tr><td><b>health</b></td><td><code>/health</code> returns an identity card; <code>gateway_ok</code> checks the <em>name</em> so a foreign process on the port is never mistaken for ours.</td></tr>
<tr><td><b>venv</b></td><td>One shared environment with the <code>mcp</code> package, built by uv if present else <code>python -m venv</code>, rebuilt only when the requirement string changes.</td></tr>
<tr><td><b>supervision</b></td><td>launchd plist (Interactive, KeepAlive, session PATH, venv <em>not</em> prepended) on macOS; <code>systemd --user</code> unit on Linux; detached process + pid file elsewhere. <code>stop_gateway</code> waits for the port to go quiet and removes the descriptor.</td></tr>
<tr><td><b>ensure</b></td><td>Healthy and same definition <em>and same content fingerprint</em> (plugin version + entry-script hash + launcher hash — so an in-place update restarts the gateway even when the path is unchanged) → return. Healthy but this session cannot resolve the executable → keep it. Stale definition → restart. Otherwise build, start, write descriptor, wait up to 60 s, and on the very first run print a disclosure of what is being installed and how to opt out.</td></tr>
<tr><td><b>Bridge</b></td><td>Standard library only (~25 MB). One thread per client message; POSTs to <code>/mcp</code>; parses JSON or SSE replies; forwards JSON-RPC errors carried on 4xx. Waits for the initialize round-trip only if the client sent one; tracks a session id only if the server issued one — correct under both the 2025 protocol and the 2026-07-28 release. On connection loss: wait for the gateway, run <code>ensure</code> after 10 s of silence, re-initialize with the client's own parameters, replay.</td></tr>
<tr><td><b>gateway</b></td><td>Runs in the venv. <code>stdio_client</code> starts the original command once; a low-level <code>Server</code> forwards tools, prompts and resources; a <code>StreamableHTTPSessionManager</code> behind uvicorn on loopback serves <code>/mcp</code>, <code>/health</code> and a Server Card at <code>/.well-known/mcp/server-cards.json</code>. A watchdog calls <code>tools/list</code> every 30 s; any reply means alive; silence restarts the child. The outer loop restarts the child on any failure.</td></tr>
<tr><td><b>CLI</b></td><td><code>connect</code>, <code>ensure|status|stop|logs --name X</code>, <code>gateway --spec</code> (internal). <code>SHARED_MCP_DISABLE=1</code> runs the original per session.</td></tr>
</tbody></table>"""
+ fig(2,"The connect path. Left column is what every session does; middle is the cold-start branch; right is what the gateway process does once it exists. The dashed bottom arrow is the fallback that keeps a plugin working on a machine where none of this is possible.",FIG_CONNECT) + """
<p><b>The test</b> (<code>tests/test_shared.py</code>) is the proof, not the description: two bridges call a fixture server's <code>counter</code> tool and see 1, 2, 3 from one process id with a declared secret forwarded; the gateway is killed and both bridges recover; stdin EOF exits 0; the descriptor is written and removed; and with the state directory made unwritable the original server runs directly. §8 has today's run.</p>
<p><b>Distribution.</b> <code>vendor.sh</code> copies the file byte-identically into plugin roots. Vendored today into ado-backlog-sync, prompt-library and advanced-prompting-engine; your three personal servers (projam, graphology, efforts) use the canonical copy via <code>~/.claude.json</code>. Public at <a href="https://github.com/JoshuaRamirez/shared-mcp">github.com/JoshuaRamirez/shared-mcp</a>.</p>"""),
sec("s5","5","The svc console","svc.py — one place for everything launchd runs for you", """
<p><code>svc</code> is on your PATH (symlink from <code>~/.local/bin/svc</code> to <code>~/.local/share/svc/svc.py</code>). Its substrate is <em>derived</em> on every run: it reads the plists in <code>~/Library/LaunchAgents</code>, asks <code>launchctl print</code> for state, pid and last exit, asks lsof for listening ports, stats the log files, and joins the descriptors in <code>~/.config/svc/services.d/</code>. Nothing that can be computed is ever written down, so it cannot go stale; a descriptor holds only purpose, source, health probe, friendly name and manage overrides.</p>
<table><tbody>
<tr><td><code>svc list [--all]</code></td><td>owned services and jobs (vendor and brew agents hidden unless --all)</td></tr>
<tr><td><code>svc show &lt;name&gt;</code></td><td>everything known, including the exact restart/stop/start/logs commands</td></tr>
<tr><td><code>svc logs &lt;name&gt; [-n N] [-f]</code></td><td>tail the real log files</td></tr>
<tr><td><code>svc health</code></td><td>probe every owned service; never says ok without evidence</td></tr>
<tr><td><code>svc doctor</code></td><td>dormant plists, failing runs, missing programs, both streams discarded, runaway logs, piles of per-run logs, unregistered agents, orphaned descriptors, port clashes</td></tr>
<tr><td><code>svc start|stop|restart &lt;name&gt; [--go]</code></td><td>dry-run without --go; after --go it re-reads reality and refuses to claim success it cannot see</td></tr>
<tr><td><code>svc prune [--go] [--days N] [--install]</code></td><td>truncate live logs over 20 MB to their last 2000 lines; delete rotated/per-run logs older than 14 days; --install registers the daily 03:30 agent <code>com.joshua.svc-prune</code></td></tr>
<tr><td><code>svc register &lt;label&gt; [--go]</code></td><td>write a descriptor prefilled from derived facts; you fill in purpose</td></tr>
<tr><td><code>svc selftest</code></td><td>fixture tests for plist classification and the launchctl output parser (the one place launchctl's text is read)</td></tr>
<tr><td><code>svc &lt;anything&gt;</code></td><td>dispatches to <code>libexec/svc-&lt;anything&gt;</code> or <code>svc-&lt;anything&gt;</code> on PATH — the extension seam</td></tr>
</tbody></table>
<p>Health rules worth knowing: a service with <code>KeepAlive</code> only-on-failure that exited 0 is <em>ok, stopped by design</em>; a probe URL's expected status codes are declared in the descriptor; periodic jobs are judged by last exit code. <code>MANIFESTO.md</code> in the repo keeps the honest ledger of what the tool does and does not model.</p>"""),
sec("s6","6","Machine state this created, and how to undo it","Everything that exists on this Mac because of the work", f"""
<h3>launchd agents</h3>{pre(agents)}
<h3>state directories</h3>{pre(state)}
<h3>descriptors</h3>{pre(descs)}
<h3>Undo, in order</h3>
<table><tbody>
<tr><td>one shared server</td><td><code>python3 ~/Developer/shared-mcp/shared_mcp.py stop --name &lt;X&gt;</code> — removes agent + descriptor; next session start would recreate it unless the plugin config is reverted</td></tr>
<tr><td>spec-vault daemon</td><td><code>~/Developer/AspenESS/ClaudeCodeMarketplace/plugins/spec-vault/graph-server/daemon.sh stop</code></td></tr>
<tr><td>daily prune</td><td><code>launchctl bootout gui/$(id -u)/com.joshua.svc-prune && rm ~/Library/LaunchAgents/com.joshua.svc-prune.plist ~/.config/svc/services.d/com.joshua.svc-prune.json</code></td></tr>
<tr><td>revert a plugin</td><td>put the original <code>command</code>/<code>args</code> back in its <code>.mcp.json</code>, or set <code>SHARED_MCP_DISABLE=1</code> to keep the launcher but run per session</td></tr>
<tr><td>state</td><td><code>rm -rf ~/.local/state/shared-mcp ~/.local/state/spec-vault ~/.local/state/svc</code></td></tr>
<tr><td>svc itself</td><td><code>rm ~/.local/bin/svc; rm -rf ~/.local/share/svc ~/.config/svc</code></td></tr>
</tbody></table>"""),
sec("s6b","6b","Edge cases","What is handled, and what is a known limit", """
<h3>Handled</h3><table><tbody>
<tr><td>gateway restarts (upgrade, crash)</td><td>bridge reconnects and replays the in-flight call</td></tr>
<tr><td>child server dies</td><td>gateway restarts it; backoff to 60 s for dependencies that come up late after login</td></tr>
<tr><td>gateway left down</td><td>bridge runs <code>ensure</code> after 10 s of silence; launchd restarts on crash</td></tr>
<tr><td>no daemon possible</td><td>launcher execs the original server — the old per-session behaviour</td></tr>
<tr><td>sessions cold-start together (herdr restore)</td><td>mkdir lock serialises the bootstrap</td></tr>
<tr><td>sessions disagree about env or command</td><td>flap guard keeps the running definition and logs why</td></tr>
<tr><td>server code updated in place</td><td>content fingerprint (plugin version + entry script + launcher) restarts the gateway</td></tr>
<tr><td>hashed port held by a stranger</td><td>steps forward to the next free port; a running gateway keeps its port</td></tr>
<tr><td>two OS users on one Mac</td><td>identity and port include the user; user B never adopts user A's gateway</td></tr>
<tr><td>plugin removed, gateway lives on</td><td><code>svc doctor</code> flags a service whose argument paths vanished</td></tr>
<tr><td>server written for one client</td><td><code>--serialize</code>: one tool call at a time</td></tr>
<tr><td>server that must not be shared</td><td><code>--per-session</code>: uniform launcher, original behaviour (Roslyn, browser-attached)</td></tr>
</tbody></table>
<h3>Fixed after an independent code review (0.3.0)</h3><p>A high-effort review of the kit returned 23 confirmed findings; all were fixed in 0.3.0 and the two worst are worth knowing: a bridge cached its gateway's port at start, so after a port move it would have posted to a dead port for the rest of the session (now read live); and a reconnect could raise out of the request thread, hanging Claude's tool call instead of returning an error (now never raises, and a failed handshake releases any pipelined messages). Also: the cold-start lock now heartbeats, claims stale locks atomically and never removes another holder's lock; the venv build takes a machine-wide lock; a reconnecting bridge can revive or adopt a gateway but never replace a live one, so an old session cannot downgrade an upgrade; a registered-but-not-yet-answering gateway is waited for instead of torn down; identity is the declared command, not one session's PATH resolution; the watchdog stays quiet while the child is busy and needs two consecutive silences; binary resources are forwarded as bytes; plist and unit strings are escaped. Unit tests in <code>tests/test_unit.py</code> pin the failure paths.</p>
<h3>Known limits</h3><ul>
<li>Server-initiated requests — roots, sampling, elicitation — are not forwarded to a particular session. A server that needs them is per-session by nature; use <code>--per-session</code>. (All three are deprecated in the 2026-07-28 spec.)</li>
<li>Server→client notifications (progress, tools-list-changed) are not relayed; a session sees a changed tool list on reconnect.</li>
<li>A single tool call longer than 600 s trips the bridge's HTTP timeout.</li>
<li>When Claude Code moves to the 2026-07-28 protocol, the gateway's <code>mcp</code> dependency must be bumped; the bridge already tolerates both generations.</li>
<li>Linux (systemd --user) and Windows (detached process, no auto-restart) paths are implemented but have not been exercised on this machine.</li>
</ul>"""),
sec("s7","7","Operating it day to day","The five gestures", """
<ol>
<li><b>Something MCP-ish feels off:</b> <code>svc doctor</code>, then <code>svc show mcp-&lt;name&gt;</code>, then <code>svc logs mcp-&lt;name&gt;</code>.</li>
<li><b>A tool says the server failed to connect:</b> <code>svc health</code>. If the gateway is up, <code>/mcp</code> reconnect in that session; if not, <code>svc restart mcp-&lt;name&gt; --go</code> (or wait — a bridge revives its gateway after 10 s).</li>
<li><b>You changed a server's env or command:</b> the next session's connect detects the new definition and restarts the gateway. To force it now: <code>shared_mcp.py stop --name X</code> then start a session.</li>
<li><b>New plugin with an MCP server:</b> <code>vendor.sh &lt;plugin-dir&gt;</code>, point its <code>.mcp.json</code> at <code>connect</code>, declare forwarded env with <code>--env</code>, add the README disclosure paragraph. Do not share a server that depends on the session's working directory or attaches to a per-session resource.</li>
<li><b>New background job of any kind:</b> <code>svc register &lt;label&gt; --go</code> and fill in purpose; give it a health probe.</li>
</ol>"""),
sec("s8","8","Live evidence","Produced when this page was generated", f"""
<h3>shared-mcp end-to-end test</h3>{pre(kit_test)}
<h3>svc selftest</h3>{pre(svc_test)}
<h3>svc list</h3>{pre(svc_list)}
<h3>svc doctor</h3>{pre(svc_doc)}"""),
sec("sref","R","Commits since 2026-09-13, per repository","Derived from git", "".join(f"<h4>{E(k)}</h4>{pre(v or '(none in range)')}" for k, v in commits.items())),
])
nav = """<nav class="toc"><h1>Shared MCP</h1><p class="sub">What was built — artifact tour</p>
<div class="grp">Primary</div><ol><li><a href="#s0">0 · How to read this</a></li><li><a href="#s1">1 · The files</a></li></ol>
<div class="grp">Components</div><ol><li><a href="#s2">2 · The crash fix</a></li><li><a href="#s3">3 · spec-vault's own daemon</a></li><li><a href="#s4">4 · The shared-mcp kit</a></li><li><a href="#s5">5 · The svc console</a></li></ol>
<div class="grp">Operating</div><ol><li><a href="#s6">6 · Machine state &amp; undo</a></li><li><a href="#s6b">6b · Edge cases</a></li><li><a href="#s7">7 · Day to day</a></li><li><a href="#s8">8 · Live evidence</a></li></ol>
<div class="grp">Reference</div><ol><li><a href="#sref">R · Commits per repo</a></li></ol>
<div class="grp">Companion</div><ol><li><a href="index.html">→ The coherent picture</a></li></ol></nav>"""
OUT.write_text(page("Shared MCP — What Was Built · Reading Room", "Personal infrastructure · artifact tour",
    "What was built: the crash fix, the shared-mcp kit, and the svc console",
    "A component-by-component tour of the artifacts created to stop the quit-time crash and to run each MCP server once per machine — what each file is, how it works inside, what it leaves on the machine, how to operate it, and how to remove it. Tests and inventory are run live at generation.",
    f"<span><b>Generated:</b> {E(stamp)}</span><span><b>Kit:</b> <a href='https://github.com/JoshuaRamirez/shared-mcp'>github.com/JoshuaRamirez/shared-mcp</a></span><span><b>Console:</b> <code>~/.local/share/svc</code></span>",
    nav, body, "Generated by <code>reading-room/generate_built.py</code>. Prose authored; §1, §6, §8 and R derived at generation time."))
print(f"wrote {OUT} ({OUT.stat().st_size//1024} KB)")
