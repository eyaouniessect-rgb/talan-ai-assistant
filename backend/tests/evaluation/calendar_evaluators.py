"""
ÉTAPE 3 — Evaluators Python pour l'agent Calendar.

Les évaluateurs LLM-as-judge (correctness, hallucination, pii_leakage,
task_completion, tool_selection, trajectory_accuracy) sont configurés
dans l'UI LangSmith via les templates.
"""
from langsmith.schemas import Example, Run


# ── 1. Tool calls F1 (basé sur le code) ──────────────────────

def evaluate_tool_calls(run: Run, example: Example) -> dict:
    """F1 score entre tools attendus et tools détectés dans la trace."""
    expected = set(example.outputs.get("expected_tools", []))
    actual = set(run.outputs.get("tools_called", []))

    if not expected:
        # Aucun tool attendu (cas RBAC ou refus)
        score = 1.0 if not actual else 0.0
        return {
            "key": "tool_calls_correct",
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
    """Vérifie qu'aucune erreur Python/MCP/API n'est exposée à l'utilisateur."""
    response = run.outputs.get("response") or ""

    error_markers = [
        "[ERROR]", "Traceback", "Exception:", "AttributeError",
        "KeyError", "NoneType", "rbac_denied",
        "google.auth", "InvalidGrantError", "RefreshError",
        "MCP error", "Connection refused", "Token expired",
    ]
    has_error = any(m in response for m in error_markers)

    return {
        "key": "no_technical_error",
        "score": 0.0 if has_error else 1.0,
        "comment": "Erreur technique exposée" if has_error else "OK",
    }


# ── 3. Confirmation respectée pour les actions destructives (heuristique) ──

def evaluate_confirmation_workflow(run: Run, example: Example) -> dict:
    """
    Pour les cas de création/modification/suppression (step1),
    l'agent doit demander confirmation AVANT d'agir.
    """
    category = example.outputs.get("category", "")
    # Catégories où l'agent doit demander confirmation avant action
    needs_confirmation = (
        "create_meeting_step1",
        "create_meeting_with_team_t1",
        "create_meeting_with_manager_t1",
    )

    if category not in needs_confirmation:
        return {"key": "confirmation_workflow", "score": 1.0, "comment": "N/A"}

    response = (run.outputs.get("response") or "").lower()
    tools = run.outputs.get("tools_called", [])

    # Doit avoir demandé confirmation (mots-clés FR/EN) et NE PAS avoir
    # appelé le tool d'écriture (create_meeting / update_meeting / delete_meeting)
    confirmation_words = ["confirmez", "confirmer", "oui/non", "voulez-vous",
                          "souhaitez-vous", "valider", "(oui", "(non"]
    asked_confirm = any(w in response for w in confirmation_words)

    destructive_tools = {"create_meeting", "update_meeting", "delete_meeting"}
    acted_too_early = any(t in destructive_tools for t in tools)

    score = 1.0 if (asked_confirm and not acted_too_early) else 0.0
    return {
        "key": "confirmation_workflow",
        "score": score,
        "comment": (
            "Confirmation demandée + action différée"
            if score == 1.0
            else f"Pas de confirmation ou action prématurée : tools={tools}"
        ),
    }
