# shared-mcp

Run a stdio MCP server **once per machine** and let every Claude Code session share it.
One file, no third-party imports on the per-session path, safe on any machine: if a
background gateway cannot be set up, the original server runs directly (today's behaviour).

```jsonc
// .mcp.json — replace the command with the launcher, keep the original after `--`
{ "mcpServers": { "my-server": {
    "command": "python3",
    "args": ["${CLAUDE_PLUGIN_ROOT}/shared_mcp.py", "connect", "--name", "my-server",
             "--env", "MY_TOKEN",                      // env vars to forward to the shared process
             "--", "python3", "${CLAUDE_PLUGIN_ROOT}/server.py"] } } }
```

- `connect` bridges to the gateway (≈25 MB/session) or creates it: venv with `mcp`, then
  launchd (macOS) / systemd --user (Linux) / detached process (elsewhere), then bridges.
- The gateway runs the original command exactly once, restarts it if it dies, serves it over
  streamable HTTP on 127.0.0.1:<stable port>, and answers `/health` with its identity.
- Bridges reconnect and replay when the gateway restarts (plugin upgrade, crash).
- `shared_mcp.py status|stop|logs|ensure --name X`. State: `~/.local/state/shared-mcp/<name>/`.
- Registers with [`svc`](../../.local/share/svc) when `~/.config/svc/services.d` exists.
- Escape hatch: `SHARED_MCP_DISABLE=1` runs the original server per session.

Caveat: a shared server is machine-scoped. A server whose behaviour depends on the
session's working directory should not be shared (the first session's cwd wins).

Vendor into a plugin: `./vendor.sh <plugin-dir>...` (copies `shared_mcp.py`, stamps version).
Tests: `python3 tests/test_shared.py`.

## What it installs on a user's machine (disclosure)

On first use for a given server, `connect` creates `~/.local/state/shared-mcp/venv` (a Python
environment holding the `mcp` package), `~/.local/state/shared-mcp/<name>/` (spec.json at 0600 with
the server's command and declared env vars, plus gateway.log), and a **login-time background
service** — a launchd agent `com.shared-mcp.<name>` on macOS, a `systemd --user` unit on Linux, a
detached process elsewhere — bound to 127.0.0.1 only. It prints a one-line notice to stderr the first
time. Opt out with `SHARED_MCP_DISABLE=1`; remove with `shared_mcp.py stop --name <name>`.

## Reading rooms

Two long-form, self-contained HTML documents live in `reading-room/` (open them in a browser):
`index.html` is the coherent picture — why one server per machine, seen from every concern;
`what-was-built.html` is the artifact tour — each file, how it works, machine state, undo, day-to-day
operation, with the tests run live at generation. Regenerate with `reading-room/generate.py` and
`reading-room/generate_built.py`.

## Edge cases

Handled: gateway restart (bridge reconnects and replays); child death (gateway restarts it with
backoff up to 60 s, for dependencies that come up late after login); gateway left down (bridge runs
`ensure` after 10 s; the service manager restarts on crash); no daemon possible (original server runs
per session); sessions cold-starting together (mkdir lock); sessions disagreeing about env or command
(flap guard keeps the running definition and says so); in-place code updates (content fingerprint);
hashed port held by a stranger (steps to the next free port); two OS users on one machine (identity
and port include the user); plugin removed while its gateway lives on (`svc doctor` flags it);
single-client servers (`--serialize`); servers that must not be shared (`--per-session`).

Known limits: server-initiated requests (roots, sampling, elicitation) are not forwarded to a specific
session — a server that needs them is per-session by nature, use `--per-session`; server→client
notifications (progress, tools-list-changed) are not relayed, so a session sees tool-list changes on
reconnect; a call longer than 600 s trips the bridge's HTTP timeout (`SPEC_VAULT`-style env override
not yet exposed); when Claude Code moves to the 2026-07-28 protocol the gateway's `mcp` dependency
must be bumped (`MCP_REQUIREMENT`); Windows and Linux paths are implemented but untested here.

## Standards alignment (checked 2026-09-15)

- MCP has no standard for a *shared* local server: stdio is specified as one subprocess per client,
  Streamable HTTP for many clients. This kit converts the former into the latter on loopback — a common
  community pattern (mcp-proxy, supergateway, Docker MCP Gateway), not a specified one.
- Spec 2026-07-28 (SEP-2575/2567) removed the initialize handshake, protocol sessions and `ping`.
  The bridge is correct in both generations: it only waits for / replays an `initialize` if the client
  sent one, tracks a session id only if the server issued one, and forwards JSON-RPC errors carried on
  4xx responses. The gateway's liveness probe is an ordinary RPC (`tools/list`), not `ping`.
- Each gateway serves a Server Card (SEP-2127, in review) at `/.well-known/mcp/server-cards.json`
  (alias `/.well-known/mcp.json`) so it can be discovered without connecting.
- Roadmap item "HTTP over stdio" (Transports WG) would make the bridge a byte relay; the kit's
  public shape (`connect`, `gateway`, state layout) is meant to survive that swap unchanged.

