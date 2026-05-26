"""
ÉTAPE 4 — Lance l'évaluation complète sur le dataset.

Prérequis :
  1. Agent RH démarré : python -m agents.rh.server
  2. Dataset créé    : python -m tests.evaluation.create_dataset

Lancer :
    python -m tests.evaluation.run_evaluation
"""
from dotenv import load_dotenv

load_dotenv()

from langsmith.evaluation import evaluate

from tests.evaluation.rh_target import run_rh_agent
from tests.evaluation.rh_evaluators import (
    evaluate_tool_calls,
    evaluate_rbac,
    evaluate_no_error,
)

DATASET_NAME = "agent-rh-evaluation-v1"
EXPERIMENT_PREFIX = "rh-agent"


def main():
    results = evaluate(
        run_rh_agent,
        data=DATASET_NAME,
        evaluators=[
            evaluate_tool_calls,
            evaluate_rbac,
            evaluate_no_error,
        ],
        experiment_prefix=EXPERIMENT_PREFIX,
        num_repetitions=1,
        max_concurrency=1,  # OBLIGATOIRE : _current_role est une variable globale dans agent.py
                            # tourner en parallèle écrase le rôle entre requêtes → RBAC faussé
        metadata={
            "agent_version": "1.0",
            "model": "openai/gpt-oss-120b",
            "consultant": "Eya ouni",
            "rh": "Ons RH",
        },
    )

    # Résumé console
    print("\n" + "═" * 60)
    print("RÉSULTATS ÉVALUATION AGENT RH")
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
