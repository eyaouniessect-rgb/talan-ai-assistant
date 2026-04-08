# Client MCP Google Calendar — JSON-RPC 2.0 over Streamable HTTP.
# Session is initialized once and reused (SDK v1.27+ stateful mode).
import json
import httpx

MCP_URL = "http://127.0.0.1:3000/mcp"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# Module-level session cache — initialize once per server lifecycle
_session_id: "str | None" = None
_request_counter = 0


def _next_id() -> int:
    global _request_counter
    _request_counter += 1
    return _request_counter


def _parse_response(response: httpx.Response) -> dict:
    """Parse JSON or SSE (text/event-stream) MCP response."""
    ct = response.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in response.text.splitlines():
            if line.startswith("data: "):
                data = line[6:].strip()
                if data and data != "[DONE]":
                    return json.loads(data)
        return {}
    return response.json()


async def _initialize() -> "str | None":
    """Send MCP initialize and return the session ID."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": _next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "calendar-agent", "version": "1.0.0"},
                },
            },
            headers=_HEADERS,
        )
        r.raise_for_status()
        data = _parse_response(r)
        if "error" in data:
            raise Exception(f"MCP init error: {data['error']}")
        return r.headers.get("mcp-session-id")


async def call_mcp(tool: str, arguments: dict, account_id: "str | None" = None, _retry: bool = True):
    """
    Call a Google Calendar MCP tool.
    - Session is initialized once and cached at module level.
    - On session expiry (400/404), re-initializes automatically.
    """
    global _session_id

    # Initialize session on first call
    if _session_id is None:
        _session_id = await _initialize()

    tool_headers = dict(_HEADERS)
    if _session_id:
        tool_headers["mcp-session-id"] = _session_id

    # Inject account selection for multi-user MCP support
    call_arguments = dict(arguments)
    if account_id is not None:
        call_arguments["account"] = account_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": _next_id(),
                "method": "tools/call",
                "params": {
                    "name": tool,
                    "arguments": call_arguments,
                },
            },
            headers=tool_headers,
        )

        # Session expired or invalid — reinitialize once
        if r.status_code in (400, 404) and _retry:
            _session_id = None
            return await call_mcp(tool, arguments, account_id=account_id, _retry=False)

        r.raise_for_status()
        data = _parse_response(r)

    if "error" in data:
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise Exception(f"MCP error: {msg}")

    result = data.get("result", {})
    content = result.get("content", [])
    if content and content[0].get("type") == "text":
        try:
            return json.loads(content[0]["text"])
        except json.JSONDecodeError:
            return {"text": content[0]["text"]}
    return result
