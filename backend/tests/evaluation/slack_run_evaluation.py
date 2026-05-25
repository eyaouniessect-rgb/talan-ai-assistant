"""
ÉTAPE 4 — Lance l'évaluation complète sur le dataset Slack.

Prérequis :
  1. Agent Slack démarré : python -m agents.slack.server
  2. SLACK_BOT_TOKEN ou SLACK_USER_TOKEN configuré dans .env
  3. Dataset créé             : python -m tests.evaluation.slack_create_dataset

Lancer :
    python -m tests.evaluation.slack_run_evaluation
"""
from dotenv import load_dotenv

load_dotenv()

from langsmith.evaluation import evaluate

from tests.evaluation.slack_target import run_slack_agent
from tests.evaluation.slack_evaluators import (
    evaluate_tool_calls,
    evaluate_no_error,
)

DATASET_NAME = "agent-slack-evaluation-v1"
EXPERIMENT_PREFIX = "slack-agent"


def main():
    results = evaluate(
        run_slack_agent,
        data=DATASET_NAME,
        evaluators=[
            evaluate_tool_calls,
            evaluate_no_error,
        ],
        experiment_prefix=EXPERIMENT_PREFIX,
        num_repetitions=1,
        max_concurrency=1,  # Sécurité : éviter les rate-limits Slack API
        metadata={
            "agent_version": "1.0",
            "model": "openai/gpt-oss-120b",
            "consultant": "Eya Ouni",
        },
    )

    # Résumé console
    print("\n" + "═" * 60)
    print("RÉSULTATS ÉVALUATION AGENT SLACK")
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
