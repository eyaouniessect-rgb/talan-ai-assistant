"""
Tests du rate limiter sur /chat.
Lance : pytest tests/test_rate_limit.py -v
"""
import pytest
import asyncio
from fastapi import HTTPException

import app.core.rate_limiter as rl


def _reset_state():
    """Vide le compteur entre les tests."""
    rl._windows.clear()


async def _call(user_id: str = "42") -> None:
    """Simule un appel au rate limiter pour un user donné."""
    fake_user = {"user_id": int(user_id)}
    await rl.chat_rate_limit(current_user=fake_user)


# ── Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_under_limit_passes():
    """29 requêtes doivent toutes passer."""
    _reset_state()
    for _ in range(29):
        await _call()  # aucune exception attendue


@pytest.mark.asyncio
async def test_exactly_at_limit_passes():
    """La 30ème requête (= RATE_LIMIT) doit passer."""
    _reset_state()
    for _ in range(rl.RATE_LIMIT):
        await _call()


@pytest.mark.asyncio
async def test_over_limit_raises_429():
    """La 31ème requête doit lever HTTP 429."""
    _reset_state()
    for _ in range(rl.RATE_LIMIT):
        await _call()

    with pytest.raises(HTTPException) as exc_info:
        await _call()

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"] == "rate_limit_exceeded"
    assert "retry_after" in exc_info.value.detail


@pytest.mark.asyncio
async def test_different_users_independent():
    """Deux utilisateurs ont des compteurs séparés — user B ne doit pas être limité par user A."""
    _reset_state()

    # user A épuise son quota
    for _ in range(rl.RATE_LIMIT):
        await _call("1")

    # user B doit encore passer sans problème
    await _call("2")


@pytest.mark.asyncio
async def test_window_expires():
    """Après expiration de la fenêtre, les requêtes repassent."""
    _reset_state()

    # Remplir le quota avec des timestamps volontairement vieux
    import time
    user_id = "99"
    old_time = time.monotonic() - rl.WINDOW_SEC - 5  # 5s avant la fenêtre
    for _ in range(rl.RATE_LIMIT):
        rl._windows[user_id].append(old_time)

    # La fenêtre est expirée → doit passer
    await _call(user_id)
