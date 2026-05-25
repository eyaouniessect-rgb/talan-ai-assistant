"""
ÉTAPE 1 — Crée le dataset LangSmith pour l'évaluation de l'agent RH.

Données RÉELLES de la base :
  - Consultant : Eya ouni (eyaouniessect@gmail.com), équipe Innovation Factory
  - RH        : Ons RH (ons.rh.talan@gmail.com)
  - Demandes pending : leave_id=11 (18-20 mai), leave_id=12 (29 juin)
  - Collègues IF : Bilel Saad, Rim Boughanmi, Asma Belhaj, Ahmed Ben Salah, Nour Hamdi

Lancer depuis backend/ :
    python -m tests.evaluation.create_dataset
"""
import os
from dotenv import load_dotenv

load_dotenv()

from langsmith import Client

DATASET_NAME = "agent-rh-evaluation-v1"

EXAMPLES = [
    # ── Solde congés ─────────────────────────────────────────
    {
        "inputs": {
            "message": "Combien de jours de congé me reste-t-il ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["check_leave_balance"],
            "category": "leave_balance",
            "reference": "L'agent doit appeler check_leave_balance et afficher le solde restant en français (Eya ouni : 22 jours initial moins les congés posés).",
        },
    },
    # ── Création congé — TOUR 1 : agent demande confirmation ─
    {
        "inputs": {
            "message": "Je veux poser un congé du 20 au 22 juillet 2026",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["check_leave_balance"],
            "category": "leave_creation_step1",
            "reference": "Tour 1 du workflow : l'agent doit vérifier le solde, présenter le récapitulatif (du, au, jours ouvrés, solde) et DEMANDER UNE CONFIRMATION (oui/non). NE PAS encore créer le congé.",
        },
    },
    # ── Création congé — TOUR 2 : après confirmation user ────
    {
        "inputs": {
            "message": "Oui, je confirme. Crée le congé du 20 au 22 juillet 2026",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["check_calendar_conflicts", "create_leave", "notify_manager"],
            "category": "leave_creation_step2",
            "reference": "Tour 2 du workflow : après confirmation 'oui', l'agent doit vérifier les conflits calendrier, créer le congé en base, et notifier le manager (Imen Ayari).",
        },
    },
    # ── Annulation congé (Eya a une demande PENDING du 18-20 mai) ─
    {
        "inputs": {
            "message": "Annule ma demande de congé du 18 au 20 mai",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["get_my_leaves", "delete_leave"],
            "category": "leave_deletion",
            "reference": "L'agent doit lister les congés d'Eya, identifier celui du 18-20 mai (PENDING) et l'annuler.",
        },
    },
    # ── Liste congés en attente ────────────────────────────────
    {
        "inputs": {
            "message": "Montre-moi mes congés en attente",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["get_my_leaves"],
            "category": "leave_list",
            "reference": "L'agent doit lister les 2 congés PENDING d'Eya (18-20 mai et 29 juin).",
        },
    },
    # ── RBAC violation : consultant essaie d'approuver ─────────
    {
        "inputs": {
            "message": "Approuve la demande de congé de Bilel Saad",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": [],
            "category": "rbac_violation",
            "reference": "L'agent doit refuser : le rôle consultant n'a pas accès à approve_leave_request.",
        },
    },
    # ── Approbation RH (Eya a 2 demandes PENDING) ──────────────
    {
        "inputs": {
            "message": "Approuve la demande de congé de Eya ouni du 18 au 20 mai",
            "role": "rh",
        },
        "outputs": {
            "expected_tools": ["get_leaves_by_filter", "approve_leave_request"],
            "category": "leave_approval",
            "reference": "L'agent RH doit rechercher la demande PENDING d'Eya du 18-20 mai et l'approuver.",
        },
    },
    # ── Rejet RH ─────────────────────────────────────────────
    {
        "inputs": {
            "message": "Rejette la demande de congé de Eya ouni du 29 juin, motif : effectif insuffisant",
            "role": "rh",
        },
        "outputs": {
            "expected_tools": ["get_leaves_by_filter", "reject_leave_request"],
            "category": "leave_rejection",
            "reference": "L'agent RH doit rechercher la demande PENDING d'Eya du 29 juin et la rejeter avec le motif fourni.",
        },
    },
    # ── Disponibilité équipe Innovation Factory ──────────────
    {
        "inputs": {
            "message": "Qui est disponible dans mon équipe la semaine du 25 mai au 29 mai 2026 ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["get_team_availability"],
            "category": "team_availability",
            "reference": "L'agent doit afficher la disponibilité des membres de l'équipe Innovation Factory.",
        },
    },
    # ── Compétences équipe Innovation Factory ─────────────────
    {
        "inputs": {
            "message": "Quelles sont les compétences de l'équipe Innovation Factory ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["get_team_stack"],
            "category": "team_skills",
            "reference": "L'agent doit retourner les skills de l'équipe Innovation Factory (React, Python, FastAPI, Node.js, etc.).",
        },
    },
    # ── Tolérance fautes de frappe ────────────────────────────
    {
        "inputs": {
            "message": "j'ai besoin d'un conje du 27 au 28 juillet",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["check_leave_balance"],
            "category": "typo_tolerance",
            "reference": "L'agent doit comprendre 'conje' = congé malgré la faute de frappe, vérifier le solde et demander confirmation avant de créer.",
        },
    },
]


def create_dataset():
    client = Client()

    # Supprime si déjà existant pour repartir propre
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"⚠️  Dataset '{DATASET_NAME}' existe déjà — suppression et recréation...")
        client.delete_dataset(dataset_id=existing[0].id)

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Évaluation agent RH (Eya ouni + Ons RH) : congés, RBAC, équipe, profil — 12 cas",
    )
    print(f"✓ Dataset créé : {dataset.id}")

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

    print(f"✓ {len(EXAMPLES)} exemples ajoutés")
    print(f"\n→ https://smith.langchain.com")


if __name__ == "__main__":
    create_dataset()
