"""
ÉTAPE 3 — Evaluators Python pour l'agent Slack.

Les évaluateurs LLM-as-judge (correctness, hallucination, pii_leakage,
task_completion, tool_selection) sont configurés dans l'UI LangSmith.
"""
from langsmith.schemas import Example, Run


# ── 1. Tool calls F1 (basé sur le code) ──────────────────────

def evaluate_tool_calls(run: Run, example: Example) -> dict:
    """F1 score entre tools attendus et tools détectés dans la trace."""
    expected = set(example.outputs.get("expected_tools", []))
    actual = set(run.outputs.get("tools_called", []))

    if not expected:
        # Aucun tool attendu (cas hors périmètre ou refus)
        score = 1.0 if not actual else 0.0
        return {
            "key": "tool_calls_f1",
            "score": score,
            "comment": "OK" if score == 1.0 else f"Tools appelés malgré refus attendu : {actual}",
        }

    correct = expected & actual
    precision = len(correct) / len(actual) if actual else 0.0
    recall = len(correct) / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "key": "tool_calls_f1",
        "score": round(f1, 2),
        "comment": f"Manquants: {expected - actual} | Extra: {actual - expected}",
    }


# ── 2. Réponse sans erreur technique (heuristique) ──────────

def evaluate_no_error(run: Run, example: Example) -> dict:
    """Vérifie qu'aucune erreur Python/Slack API n'est exposée à l'utilisateur."""
    response = run.outputs.get("response") or ""

    error_markers = [
        "[ERROR]", "Traceback", "Exception:", "AttributeError",
        "KeyError", "NoneType", "rbac_denied",
        "slack_sdk", "SlackApiError", "invalid_auth",
        "channel_not_found", "user_not_found",
        "MCP error", "Connection refused", "Token expired",
    ]
    has_error = any(m in response for m in error_markers)

    return {
        "key": "no_technical_error",
        "score": 0.0 if has_error else 1.0,
        "comment": "Erreur technique exposée" if has_error else "OK",
    }
