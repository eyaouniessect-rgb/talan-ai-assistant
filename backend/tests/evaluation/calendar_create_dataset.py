"""
ÉTAPE 1 — Crée le dataset LangSmith pour l'évaluation de l'agent Calendar.

Lancer depuis backend/ :
    python -m tests.evaluation.calendar_create_dataset
"""
import os
from dotenv import load_dotenv

load_dotenv()

from langsmith import Client

DATASET_NAME = "agent-calendar-evaluation-v1"

# Emails utilisés dans les tests (réels)
MY_EMAIL = "eyaouniessect@gmail.com"      # Eya ouni (consultant)
RH_EMAIL = "ons.rh.talan@gmail.com"        # Ons RH

EXAMPLES = [
    # ═══════════════════════════════════════════════════════
    # CONSULTATION (lecture seule — sans risque)
    # ═══════════════════════════════════════════════════════

    # ── 1. Liste des événements ────────────────────────────
    {
        "inputs": {
            "message": "Quelles sont mes réunions de la semaine prochaine ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["get_calendar_events"],
            "category": "list_events",
            "reference": (
                "L'agent doit calculer la semaine prochaine (25-31 mai 2026 si date du "
                "jour = 2026-05-21) et appeler get_calendar_events sur cette période. "
                "RÉPONSES VALIDES (toutes acceptées) : "
                "(a) lister les événements trouvés, OU "
                "(b) répondre 'Aucune réunion prévue' si le calendrier est vide. "
                "Le calendrier de l'utilisateur peut être vide — répondre qu'il n'y a "
                "aucune réunion est une réponse correcte, PAS un échec."
            ),
        },
    },
    # ── 2. Recherche de réunion ────────────────────────────
    {
        "inputs": {
            "message": "Trouve ma réunion sur le sprint planning",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["search_meetings"],
            "category": "search_meeting",
            "reference": (
                "L'agent doit appeler search_meetings('sprint planning'). "
                "RÉPONSES VALIDES : "
                "(a) si la réunion est trouvée → l'afficher avec sa date/heure, "
                "(b) si aucun résultat → répondre 'Aucune réunion trouvée' OU "
                "demander une précision sur la période (ex: 'Pouvez-vous préciser "
                "la date ?'). Les deux comportements sont acceptables."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # DISPONIBILITÉ (lecture seule)
    # ═══════════════════════════════════════════════════════

    # ── 3. Vérifier disponibilité ──────────────────────────
    {
        "inputs": {
            "message": "Suis-je disponible le 28 mai 2026 à 14h pendant 1 heure ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["check_calendar_conflicts"],
            "category": "check_availability",
            "reference": "L'agent doit vérifier la disponibilité sur le créneau 2026-05-28 14:00-15:00 et répondre disponible ou non.",
        },
    },
    # ── 4. Vérifier MA disponibilité pour une réunion future avec un collègue ──
    # NOTE : L'agent Calendar ne peut PAS vérifier le calendrier d'un autre
    # utilisateur (l'outil check_calendar_conflicts utilise uniquement le token
    # OAuth de l'utilisateur connecté). On vérifie donc la disponibilité du
    # consultant connecté pour planifier une future réunion avec Ons RH.
    {
        "inputs": {
            "message": "Suis-je disponible le 30 mai 2026 à 10h pour une réunion avec Ons RH ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["check_calendar_conflicts"],
            "category": "check_availability",
            "reference": (
                "L'agent doit vérifier la disponibilité de l'UTILISATEUR CONNECTÉ "
                "(consultant Eya ouni) sur le créneau 2026-05-30 10:00-11:00 via "
                "check_calendar_conflicts. RÉPONSES VALIDES : "
                "(a) 'Vous êtes disponible' si aucun conflit, "
                "(b) 'Vous avez un conflit avec [titre]' si conflit. "
                "L'agent peut optionnellement appeler lookup_user_by_name pour "
                "récupérer l'email d'Ons RH (utile pour une invitation future), "
                "mais ce n'est PAS obligatoire. Il NE PEUT PAS vérifier le "
                "calendrier d'Ons RH — c'est une limitation technique attendue."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # PROFIL ÉQUIPE
    # ═══════════════════════════════════════════════════════

    # ── 5. Récupérer son manager ───────────────────────────
    {
        "inputs": {
            "message": "Qui est mon manager ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["get_my_manager"],
            "category": "my_manager",
            "reference": "L'agent doit retourner le manager d'Eya ouni : Imen Ayari.",
        },
    },
    # ── 6. Récupérer son équipe ────────────────────────────
    {
        "inputs": {
            "message": "Qui sont les membres de mon équipe ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["get_my_team"],
            "category": "my_team",
            "reference": "L'agent doit lister les membres de l'équipe Innovation Factory avec leurs emails.",
        },
    },
    # ── 7. Lookup email ────────────────────────────────────
    {
        "inputs": {
            "message": "Quel est l'email de Bilel Saad ?",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["lookup_user_by_name"],
            "category": "lookup_email",
            "reference": "L'agent doit retourner l'email professionnel de Bilel Saad.",
        },
    },

    # ═══════════════════════════════════════════════════════
    # CRÉATION (écriture — vrais events créés !)
    # ═══════════════════════════════════════════════════════

    # ── 8. Création — l'agent confirme AVANT de créer ──────
    {
        "inputs": {
            "message": "Crée une réunion 'Test Evaluation 1' le 27 mai 2026 de 9h à 10h",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["check_calendar_conflicts"],
            "category": "create_meeting_step1",
            "reference": "Tour 1 : l'agent doit vérifier la disponibilité, présenter le récap et DEMANDER UNE CONFIRMATION (oui/non) avant de créer.",
        },
    },
    # ── 9. Création avec MON ÉQUIPE — T1 uniquement (résolution + confirmation, PAS de create) ──
    {
        "inputs": {
            # Pas de "oui confirme" → l'agent doit s'arrêter à la demande de confirmation
            "message": "Crée une réunion d'équipe 'Sync IF Test' le 27 mai 2026 de 15h à 16h avec mon équipe",
            "role": "consultant",
        },
        "outputs": {
            # Workflow : conflicts → get_my_team → demande confirmation (STOP, pas de create)
            "expected_tools": ["check_calendar_conflicts", "get_my_team"],
            "category": "create_meeting_with_team_t1",
            "reference": (
                "TEST DE RÉSOLUTION (sans création réelle pour ne pas notifier l'équipe). "
                "L'agent doit : (1) vérifier la disponibilité 27/05 15h-16h, "
                "(2) résoudre les participants via get_my_team() (équipe Innovation Factory) "
                "automatiquement (sans demander), (3) afficher le récapitulatif avec la liste "
                "des membres, (4) DEMANDER UNE CONFIRMATION (oui/non) et S'ARRÊTER. "
                "create_meeting NE DOIT PAS être appelé car l'utilisateur n'a pas confirmé."
            ),
        },
    },
    # ── 10. Création avec MON MANAGER — T1 uniquement ──────
    {
        "inputs": {
            # Pas de "oui confirme" → workflow s'arrête à la confirmation
            "message": "Crée une réunion 'Point hebdo Test' avec mon manager le 28 mai 2026 de 14h à 15h",
            "role": "consultant",
        },
        "outputs": {
            # Workflow : conflicts → get_my_manager → confirmation (STOP)
            "expected_tools": ["check_calendar_conflicts", "get_my_manager"],
            "category": "create_meeting_with_manager_t1",
            "reference": (
                "TEST DE RÉSOLUTION MANAGER (sans création réelle). "
                "L'agent doit : (1) vérifier disponibilité 28/05 14h-15h, "
                "(2) résoudre l'email du manager via get_my_manager() (sans demander à "
                "l'utilisateur), (3) afficher Imen Ayari dans le récap, (4) DEMANDER "
                "UNE CONFIRMATION et S'ARRÊTER. create_meeting NE DOIT PAS être appelé."
            ),
        },
    },
    # ── 11. Création SOLO (réunion sans participants — pas de spam) ──
    {
        "inputs": {
            "message": "Oui, confirme. Crée une réunion solo 'Bloc Focus Eval' le 27 mai 2026 de 10h à 11h, sans participants",
            "role": "consultant",
        },
        "outputs": {
            # Workflow : conflicts (libre) → create_meeting (sans attendees)
            "expected_tools": ["check_calendar_conflicts", "create_meeting"],
            "category": "create_meeting_solo",
            "reference": (
                "Réunion solo créée pour Eya uniquement (aucun participant invité → aucun "
                "email envoyé). Workflow : check_calendar_conflicts → create_meeting avec "
                "attendees=[] ou attendees=null. Cette réunion sert de base pour les tests "
                "de conflit (#12), modification (#13) et suppression (#14)."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # MODIFICATION (écriture — modifie de vrais events)
    # ═══════════════════════════════════════════════════════

    # ── 12. Conflit sur créneau occupé par #11 (refus attendu) ──
    {
        "inputs": {
            "message": "Crée une réunion 'Test Conflit' le 27 mai 2026 de 10h à 11h",
            "role": "consultant",
        },
        "outputs": {
            # Workflow : conflicts détecté → STOP, refuser, PAS de create
            "expected_tools": ["check_calendar_conflicts"],
            "category": "create_meeting_conflict",
            "reference": (
                "Le créneau 27/05 10h-11h est OCCUPÉ par 'Bloc Focus Eval' (créé au cas #11). "
                "L'agent doit : (1) appeler check_calendar_conflicts, (2) DÉTECTER le conflit, "
                "(3) REFUSER de créer la réunion, (4) lister 'Bloc Focus Eval' et demander un "
                "autre créneau. AUCUN appel à create_meeting ne doit avoir lieu."
            ),
        },
    },
    # ── 13. Déplacer la réunion solo (référence au cas #11) ──
    {
        "inputs": {
            "message": "Déplace ma réunion 'Bloc Focus Eval' du 27 mai au 29 mai à la même heure",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["search_meetings", "update_meeting"],
            "category": "update_meeting_reschedule",
            "reference": (
                "L'agent doit : (1) retrouver la réunion 'Bloc Focus Eval' du 27/05 via "
                "search_meetings, (2) la déplacer au 29/05 (même heure 10h-11h) via "
                "update_meeting en conservant le même event_id."
            ),
        },
    },

    # ═══════════════════════════════════════════════════════
    # ANNULATION (écriture — supprime de vrais events)
    # ═══════════════════════════════════════════════════════

    # ── 14. Annuler la réunion solo (référence au cas #11/#13) ──
    {
        "inputs": {
            "message": "Annule ma réunion 'Bloc Focus Eval' du 29 mai 2026",
            "role": "consultant",
        },
        "outputs": {
            "expected_tools": ["search_meetings", "delete_meeting"],
            "category": "delete_meeting",
            "reference": (
                "L'agent doit : (1) retrouver 'Bloc Focus Eval' du 29/05 (après le "
                "déplacement du cas #13), (2) la supprimer via delete_meeting. Aucun "
                "email d'annulation envoyé car la réunion n'avait pas de participants."
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
            "Évaluation agent Calendar : consultation, disponibilité, création, "
            "modification, annulation — 14 cas de test."
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
