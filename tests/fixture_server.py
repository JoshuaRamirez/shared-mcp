"""Tiny stdio MCP server for tests: a counter proves that clients share ONE process."""
import os
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("fixture")
_n = {"v": 0}
@mcp.tool()
def counter() -> str:
    """Increment and return a process-local counter."""
    _n["v"] += 1
    return f"{_n['v']} pid={os.getpid()} token={os.environ.get('SM_TEST_TOKEN', '')}"
@mcp.resource("fixture://hello")
def hello() -> str:
    """A text resource, to prove resources/read forwards through the gateway."""
    return "hello from the shared fixture"
if __name__ == "__main__":
    mcp.run(transport="stdio")
