"""
ÉTAPE 4 — Lance l'évaluation complète sur le dataset Calendar.

Prérequis :
  1. Agent Calendar démarré : python -m agents.calendar.server
  2. MCP Google Calendar     : http://127.0.0.1:3000/mcp accessible
  3. Token OAuth Eya ouni    : C:/Users/eyaou/.config/google-calendar-mcp/tokens.json
  4. Dataset créé            : python -m tests.evaluation.calendar_create_dataset

Lancer :
    python -m tests.evaluation.calendar_run_evaluation
"""
from dotenv import load_dotenv

load_dotenv()

from langsmith.evaluation import evaluate

from tests.evaluation.calendar_target import run_calendar_agent
from tests.evaluation.calendar_evaluators import (
    evaluate_tool_calls,
    evaluate_no_error,
    evaluate_confirmation_workflow,
)

DATASET_NAME = "agent-calendar-evaluation-v1"
EXPERIMENT_PREFIX = "calendar-agent"


def main():
    results = evaluate(
        run_calendar_agent,
        data=DATASET_NAME,
        evaluators=[
            evaluate_tool_calls,
            evaluate_no_error,
            evaluate_confirmation_workflow,
        ],
        experiment_prefix=EXPERIMENT_PREFIX,
        num_repetitions=1,
        max_concurrency=1,  # OBLIGATOIRE : _current_role / _current_user_id sont globaux
                            # dans calendar/agent.py → race condition si parallèle
        metadata={
            "agent_version": "1.0",
            "model": "openai/gpt-oss-120b",
            "consultant": "Eya ouni",
            "rh": "Ons RH",
        },
    )

    # Résumé console
    print("\n" + "═" * 60)
    print("RÉSULTATS ÉVALUATION AGENT CALENDAR")
    print("═" * 60)

    scores: dict[str, list[float]] = {}
    for r in results:
        eval_results = r.get("evaluation_results", {}).get("results", [])
        for er in eval_results:
            scores.setdefault(er.key, []).append(er.score or 0.0)

    for key, values in scores.items():
        avg = sum(values) / len(values) if values else 0.0
        print(f"  {key:30s} : {avg:.2%}  ({len(values)} tests)")

    print("\n→ Voir les détails sur https://smith.langchain.com")


if __name__ == "__main__":
    main()
