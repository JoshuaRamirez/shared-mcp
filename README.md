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
