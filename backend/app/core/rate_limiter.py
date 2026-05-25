import time
import asyncio
from collections import defaultdict, deque
from fastapi import Depends, HTTPException

from app.core.security import get_current_user

RATE_LIMIT = 30       # requêtes max par fenêtre
WINDOW_SEC = 60       # taille de la fenêtre en secondes

_lock = asyncio.Lock()
_windows: dict[str, deque] = defaultdict(deque)  # user_id → timestamps


async def chat_rate_limit(current_user: dict = Depends(get_current_user)) -> None:
    user_id = str(current_user["user_id"])
    now = time.monotonic()
    cutoff = now - WINDOW_SEC

    async with _lock:
        window = _windows[user_id]
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= RATE_LIMIT:
            retry_after = int(WINDOW_SEC - (now - window[0])) + 1
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Limite de {RATE_LIMIT} requêtes/min atteinte. Réessayez dans {retry_after}s.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
