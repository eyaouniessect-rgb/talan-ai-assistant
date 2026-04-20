# agents/slack/mcp_client.py
# ═══════════════════════════════════════════════════════════
# Client MCP Slack — JSON-RPC 2.0 over Streamable HTTP
# Connexion au MCP Server local : http://127.0.0.1:3001
# (même pattern que Calendar MCP sur port 3000)
# ═══════════════════════════════════════════════════════════

import json
import httpx

MCP_URL = "http://127.0.0.1:3001/mcp"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

_session_id: "str | None" = None
_request_counter = 0


def _next_id() -> int:
    global _request_counter
    _request_counter += 1
    return _request_counter


def _parse_response(response: httpx.Response) -> dict:
    """Parse JSON ou SSE (text/event-stream) depuis le MCP Server."""
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
    """Envoie MCP initialize et retourne le session ID."""
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
                    "clientInfo": {"name": "slack-agent", "version": "1.0.0"},
                },
            },
            headers=_HEADERS,
        )
        r.raise_for_status()
        data = _parse_response(r)
        if "error" in data:
            raise Exception(f"MCP init error: {data['error']}")
        sid = r.headers.get("mcp-session-id")
        print(f"  [Slack MCP] Session initialisée : {sid}")
        return sid


async def list_tools() -> list[dict]:
    """Liste les outils disponibles sur le Slack MCP Server local."""
    global _session_id
    if _session_id is None:
        _session_id = await _initialize()

    headers = dict(_HEADERS)
    if _session_id:
        headers["mcp-session-id"] = _session_id

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            MCP_URL,
            json={"jsonrpc": "2.0", "id": _next_id(), "method": "tools/list", "params": {}},
            headers=headers,
        )
        r.raise_for_status()
        data = _parse_response(r)
        tools = data.get("result", {}).get("tools", [])
        print(f"  [Slack MCP] tools/list -> {tools}")
        return tools


async def call_mcp(tool: str, arguments: dict, _retry: bool = True) -> dict:
    """
    Appelle un outil du Slack MCP Server local.
    Session initialisée une fois et mise en cache.
    Réinitialise automatiquement en cas d'expiration (400/404).
    """
    global _session_id

    if _session_id is None:
        _session_id = await _initialize()

    headers = dict(_HEADERS)
    if _session_id:
        headers["mcp-session-id"] = _session_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": _next_id(),
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            },
            headers=headers,
        )

        if r.status_code in (400, 404) and _retry:
            _session_id = None
            return await call_mcp(tool, arguments, _retry=False)

        r.raise_for_status()
        data = _parse_response(r)

    if "error" in data:
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise Exception(f"Slack MCP error [{tool}]: {msg}")

    result = data.get("result", {})
    content = result.get("content", [])
    if content and content[0].get("type") == "text":
        try:
            return json.loads(content[0]["text"])
        except json.JSONDecodeError:
            return {"text": content[0]["text"]}
    return result
