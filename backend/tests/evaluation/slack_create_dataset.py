"""
ÉTAPE 1 — Crée le dataset LangSmith pour l'évaluation de l'agent Slack.

Lancer depuis backend/ :
    python -m tests.evaluation.slack_create_dataset
"""
import os
from dotenv import load_dotenv

load_dotenv()

from langsmith import Client

DATASET_NAME = "agent-slack-evaluation-v1"

EXAMPLES = [
    # ═══════════════════════════════════════════════════════
    # LECTURE / CONSULTATION (sans risque — pas d'envoi)
    # ═══════════════════════════════════════════════════════

    # ── 1. Lister les channels disponibles ─────────────────
    {
        "inputs": {
            "message": "Quels sont les channels Slack disponibles ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["list_slack_channels"],
            "category": "list_channels",
            "reference": (
                "L'agent doit appeler list_slack_channels et afficher la liste des "
                "channels (par leur nom, pas leur ID). RÉPONSE VALIDE : une liste "
                "lisible des channels (#general, #dev-team, etc.)."
            ),
        },
    },
    # ── 2. Lire les derniers messages d'un channel ─────────
    {
        "inputs": {
            "message": "Lis les 5 derniers messages du channel #general",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["read_slack_channel"],
            "category": "read_channel",
            "reference": (
                "L'agent doit appeler read_slack_channel(channel='#general', limit=5) "
                "et afficher les messages sous forme numérotée avec l'auteur "
                "(👤 user / 🤖 bot), le texte et l'heure HH:MM. RÉPONSE VALIDE : "
                "liste lisible OU 'Channel vide' si aucun message."
            ),
        },
    },
    # ── 3. Rechercher des messages ─────────────────────────
    {
        "inputs": {
            "message": "Cherche les messages qui parlent de sprint planning sur Slack",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["search_slack_messages"],
            "category": "search_messages",
            "reference": (
                "L'agent doit appeler search_slack_messages(query='sprint planning'). "
                "RÉPONSES VALIDES : (a) afficher les résultats trouvés avec channel + "
                "auteur + extrait, OU (b) 'Aucun message trouvé' si vide."
            ),
        },
    },
    # ── 4. Trouver un utilisateur Slack par son nom ────────
    {
        "inputs": {
            "message": "Trouve l'utilisateur Slack Chaima Hermi",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["find_slack_user"],
            "category": "find_user",
            "reference": (
                "L'agent doit appeler find_slack_user(name='Chaima Hermi'). "
                "RÉPONSES VALIDES : (a) afficher le nom et l'ID retournés, OU "
                "(b) 'Utilisateur introuvable' si non trouvé. NE DOIT PAS retenter "
                "find_slack_user avec une variante du nom."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # ENVOI DE MESSAGE (écriture — vrais messages Slack !)
    # ═══════════════════════════════════════════════════════

    # ── 5. Envoyer un message dans un channel ──────────────
    {
        "inputs": {
            "message": "Envoie un message dans #test-bot-talan-assistant-pfe disant 'Test eval Slack 1'",
            "role": "consultant",
        },
        "outputs": {
            # Workflow : list_channels (résout ID) → send_message
            "expected_tools": ["list_slack_channels", "send_slack_message"],
            "category": "send_message_channel",
            "reference": (
                "L'agent doit : (1) appeler list_slack_channels pour résoudre l'ID, "
                "(2) appeler send_slack_message(channel=..., text='*Eya Ouni vous "
                "informe :*\\nTest eval Slack 1'). Le message DOIT contenir la "
                "signature '*Eya Ouni vous informe :*' en première ligne. "
                "Confirmation finale : '✅ Message envoyé dans #...'."
            ),
        },
    },
    # ── 6. Envoyer un DM à une personne ────────────────────
    {
        "inputs": {
            "message": "Envoie un message privé à Chaima Hermi : 'Test eval DM Slack'",
            "role": "consultant",
        },
        "outputs": {
            # Workflow : find_user → send_message (DM = channel = user_id)
            "expected_tools": ["find_slack_user", "send_slack_message"],
            "category": "send_message_dm",
            "reference": (
                "L'agent doit : (1) appeler find_slack_user(name='Chaima Hermi') "
                "pour récupérer son ID Slack (format U...), (2) appeler "
                "send_slack_message(channel=<user_id>, text='*Eya Ouni vous "
                "informe :*\\nTest eval DM Slack'). Le DM utilise le user_id "
                "comme champ channel. Signature obligatoire."
            ),
        },
    },
    # ── 7. Envoyer un message à soi-même ───────────────────
    {
        "inputs": {
            "message": "Envoie-moi un rappel : 'Démo prévue demain à 14h'",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["find_slack_user", "send_slack_message"],
            "category": "send_message_self",
            "reference": (
                "L'agent doit : (1) appeler find_slack_user(name='Eya Ouni') car "
                "'envoie-moi' = utilisateur connecté, (2) envoyer le DM avec "
                "signature '*Eya Ouni vous informe :*\\nDémo prévue demain à 14h'."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # RÉACTIONS EMOJI (écriture — modifie de vrais messages)
    # ═══════════════════════════════════════════════════════

    # ── 8. Ajouter une réaction sur le dernier message ─────
    {
        "inputs": {
            "message": "Ajoute un 👍 sur le dernier message de #test-bot-talan-assistant-pfe",
            "role": "consultant",
        },
        "outputs": {
            # Workflow : read_channel (récupère ts) → add_reaction
            "expected_tools": ["read_slack_channel", "add_slack_reaction"],
            "category": "add_reaction",
            "reference": (
                "L'agent doit : (1) appeler read_slack_channel(limit=5) pour "
                "récupérer le ts du dernier message, (2) appeler "
                "add_slack_reaction(channel=..., timestamp=<ts>, reaction='thumbsup'). "
                "Confirmation : '✅ Réaction :thumbsup: ajoutée'."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # HORS PÉRIMÈTRE (l'agent doit refuser proprement)
    # ═══════════════════════════════════════════════════════

    # ── 9. Demande hors périmètre Slack ────────────────────
    {
        "inputs": {
            "message": "Combien me reste-t-il de jours de congé ?",
            "role": "consultant",
        },
        "outputs": {
            # Aucun tool Slack ne doit être appelé pour une demande RH
            "expected_tools": [],
            "category": "out_of_scope",
            "reference": (
                "La demande concerne les congés (agent RH), pas Slack. "
                "L'agent Slack doit répondre poliment qu'il est spécialisé "
                "uniquement dans Slack et rediriger vers l'agent approprié. "
                "AUCUN tool Slack ne doit être appelé."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # MULTI-ÉTAPES (combinaison de tools)
    # ═══════════════════════════════════════════════════════

    # ── 10. Notifier une équipe avec un message composé ────
    {
        "inputs": {
            "message": "Notifie #test-bot-talan-assistant-pfe que la réunion est reportée à demain 10h",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["list_slack_channels", "send_slack_message"],
            "category": "notify_team",
            "reference": (
                "L'agent doit composer un message professionnel (ex: 'La réunion "
                "est reportée à demain 10h.'), avec signature obligatoire "
                "'*Eya Ouni vous informe :*', puis : (1) list_slack_channels "
                "pour résoudre l'ID, (2) send_slack_message dans le channel."
            ),
        },
    },
]


def create_dataset():
    client = Client()

    # Supprime si déjà existant
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"⚠️  Dataset '{DATASET_NAME}' existe déjà — suppression et recréation...")
        client.delete_dataset(dataset_id=existing[0].id)

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "Évaluation agent Slack : lecture, recherche, envoi de messages, "
            "DMs, réactions emoji — 10 cas de test."
        ),
    )
    print(f"✓ Dataset créé : id={dataset.id}")

    for ex in EXAMPLES:
        client.create_example(
            inputs=ex["inputs"],
            outputs=ex["outputs"],
            dataset_id=dataset.id,
            metadata={
                "category": ex["outputs"]["category"],
                "role": ex["inputs"]["role"],
            },
        )

    print(f"✓ {len(EXAMPLES)} exemples ajoutés au dataset '{DATASET_NAME}'")
    print(f"\n→ Voir sur LangSmith : https://smith.langchain.com")


if __name__ == "__main__":
    create_dataset()
