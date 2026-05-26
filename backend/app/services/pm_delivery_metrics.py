# app/services/pm_delivery_metrics.py
# ═══════════════════════════════════════════════════════════════════════════════
# Indicateurs de livraison PM — fonctions pures (sans accès DB).
#
# Deux contextes d'utilisation :
#
#   1) Dashboard PM (/dashboard) — vue d'ensemble du portefeuille
#      ───────────────────────────────────────────────────────────
#      Utilise : status_distribution(), sprint_delay_distribution(),
#                velocity_weekly(), count_velocity_30d(),
#                avg_sprint_delay_days(), build_project_summary().
#      Objectif : KPIs portefeuille + cartes "Projets actifs" (chacune avec
#                 son insight texte) + ranking "Projets à risque" + petits
#                 graphes (distribution retards sprints / statuts / vélocité).
#      => Le détail sprint par sprint N'EST PAS exposé ici (volontaire).
#
#   2) Onglet Monitoring d'un projet (/projet/:id, phase 8 "monitoring")
#      ───────────────────────────────────────────────────────────
#      Utilise : build_project_summary() pour l'insight projet,
#                serialize_sprint_for_monitoring() pour chaque sprint.
#      Objectif : afficher pour CE projet uniquement la liste détaillée
#                 des sprints (planifié vs réel, jours en avance/retard,
#                 charge en story points, jours restants/débordement).
#
# Sémantique du retard (validée avec le PM) :
#   - sprint clos       : delta = actual_end_date - end_date  (jours)
#                         +N = clos en retard de N jours
#                         -N = clos en avance de N jours
#   - sprint actif      : si today > end_date → débordement = today - end_date
#                         (sinon 0 — pas de pénalisation tant que la date
#                         planifiée n'est pas atteinte)
#   - retard cumulé     : somme algébrique sur tous les sprints du projet
#                         => une avance compense un retard ultérieur, et
#                            inversement (souhait explicite du PM).
#
# Pas de niveau de risque catégoriel : on expose seulement le nombre de
# jours et un insight texte généré (voir build_project_insight).
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Iterable


# ──────────────────────────────────────────────────────────────────────────────
# Helpers atomiques sur un Sprint
#   Consommés par les deux contextes (dashboard ET monitoring projet).
# ──────────────────────────────────────────────────────────────────────────────

def sprint_end_offset_days(sprint) -> int | None:
    """+N = clos en retard de N jours ; -N = clos en avance ; None si pas clos."""
    if not sprint.actual_end_date:
        return None
    return (sprint.actual_end_date - sprint.end_date).days


def sprint_start_offset_days(sprint) -> int | None:
    """Idem pour la date de démarrage (utile dans l'onglet Monitoring projet
    pour afficher 'démarré 2 jours en avance')."""
    if not sprint.actual_start_date:
        return None
    return (sprint.actual_start_date - sprint.start_date).days


def capacity_load_pct(sprint) -> int:
    """Charge en story points : actual_sp / target_capacity_sp * 100.
    Affiché dans la barre de charge du sprint (onglet Monitoring projet)."""
    if not sprint or not sprint.target_capacity_sp:
        return 0
    return round((sprint.actual_sp or 0) / sprint.target_capacity_sp * 100)


# ──────────────────────────────────────────────────────────────────────────────
# Calcul du retard cumulé d'un projet
#   Consommé par les deux contextes :
#     - dashboard PM : pour le KPI "à risque" et le ranking des projets en retard
#     - onglet Monitoring projet : pour le grand chiffre "Retard cumulé : +Xj"
# ──────────────────────────────────────────────────────────────────────────────

def cumulative_delay_days(sprints: Iterable, today: date) -> int:
    total = 0
    for s in sprints:
        if s.status == "completed":
            total += sprint_end_offset_days(s) or 0
        elif s.status == "active" and today > s.end_date:
            total += (today - s.end_date).days
    return total


# ──────────────────────────────────────────────────────────────────────────────
# Sprint "courant" et son enrichissement pour l'onglet Monitoring projet.
# ──────────────────────────────────────────────────────────────────────────────

def current_sprint(sprints: list):
    """Sprint pertinent à mettre en avant :
       actif > 1er planifié restant > dernier clos. None si pas de sprints."""
    if not sprints:
        return None
    for s in sprints:
        if s.status == "active":
            return s
    planned = [s for s in sprints if s.status == "planned"]
    if planned:
        return planned[0]
    completed = [s for s in sprints if s.status == "completed"]
    if completed:
        return completed[-1]
    return sprints[0]


def serialize_sprint_for_monitoring(sprint, today: date) -> dict:
    """Sérialisation détaillée d'un sprint.

    >>> Utilisé UNIQUEMENT par l'endpoint /pipeline/{id}/monitoring/delivery,
        rendu dans l'onglet Monitoring du projet (PhaseResult → MonitoringSection).
        Pas envoyé au dashboard PM (qui n'affiche pas le détail sprint).
    """
    days_remaining = None
    days_overdue = None
    if sprint.status == "active":
        delta = (sprint.end_date - today).days
        if delta >= 0:
            days_remaining = delta
        else:
            days_overdue = -delta

    return {
        "sprint_number":      sprint.sprint_number,
        "name":               sprint.name,
        "status":             sprint.status,
        "planned_start":      sprint.start_date.isoformat(),
        "planned_end":        sprint.end_date.isoformat(),
        "actual_start":       sprint.actual_start_date.isoformat() if sprint.actual_start_date else None,
        "actual_end":         sprint.actual_end_date.isoformat()   if sprint.actual_end_date   else None,
        "start_offset_days":  sprint_start_offset_days(sprint),
        "end_offset_days":    sprint_end_offset_days(sprint),
        "days_remaining":     days_remaining,
        "days_overdue":       days_overdue,
        "target_capacity_sp": sprint.target_capacity_sp,
        "actual_sp":          sprint.actual_sp or 0,
        "capacity_load_pct":  capacity_load_pct(sprint),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Insight textuel par projet
#   Consommé par les deux contextes :
#     - dashboard PM : phrase courte sous chaque carte "Projet actif"
#     - onglet Monitoring projet : phrase en tête de l'onglet
# ──────────────────────────────────────────────────────────────────────────────

def build_project_insight(project, sprints: list, cum_delay: int) -> str:
    """Génère une phrase orientée prise de décision.

    Règles :
      - projet DELIVERED      → "Projet livré."
      - aucun sprint démarré  → "En attente du démarrage du 1er sprint."
      - cum_delay <= 0        → si avance → "Projet en avance de Nj sur le planning."
                                sinon     → "Projet à l'heure sur le planning."
      - cum_delay > 0         → "Projet risque d'avoir un retard de Nj — pensez
                                à compenser sur le prochain sprint."
                                (mention "sur le sprint en cours" si actif)
    """
    if project.status == "delivered":
        return "Projet livré."

    if not any(s.status in ("active", "completed") for s in sprints):
        return "En attente du démarrage du 1er sprint."

    if cum_delay <= 0:
        if cum_delay < 0:
            return f"Projet en avance de {-cum_delay} jour{'s' if -cum_delay > 1 else ''} sur le planning."
        return "Projet à l'heure sur le planning."

    from datetime import date as _date
    today = _date.today()
    active = next((s for s in sprints if s.status == "active"), None)
    # Si le sprint actif est déjà en débordement (today > end_date planifiée),
    # compenser sur "ce" sprint est impossible → on renvoie vers le sprint suivant.
    if active and today > active.end_date:
        suffix = "le sprint suivant"
    elif active:
        suffix = "le sprint en cours"
    else:
        suffix = "le prochain sprint"
    return (
        f"Projet risque d'avoir un retard de {cum_delay} jour"
        f"{'s' if cum_delay > 1 else ''} — pensez à compenser sur {suffix}."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Résumé projet pour la liste "Projets actifs" du dashboard
#   et la carte d'entête de l'onglet Monitoring projet.
# ──────────────────────────────────────────────────────────────────────────────

def _delay_source(sprints: list, today: date) -> dict | None:
    """Identifie le sprint principal à l'origine du retard cumulé.

    Priorité :
      1. Sprint actif en débordement (today > end_date) — impact immédiat visible.
      2. Dernier sprint clos avec end_offset > 0 — retard historique.
    Retourne None si aucun sprint ne contribue au retard.
    """
    # 1. Sprint actif en débordement
    for s in sprints:
        if s.status == "active" and today > s.end_date:
            return {
                "sprint_number":  s.sprint_number,
                "type":           "overdue",           # actif et dépassé
                "planned_end":    s.end_date.isoformat(),
                "days":           (today - s.end_date).days,
            }
    # 2. Dernier sprint clos en retard
    delayed_closed = [
        s for s in sprints
        if s.status == "completed" and sprint_end_offset_days(s) and sprint_end_offset_days(s) > 0
    ]
    if delayed_closed:
        worst = max(delayed_closed, key=lambda s: sprint_end_offset_days(s))
        return {
            "sprint_number": worst.sprint_number,
            "type":          "closed_late",            # clos en retard
            "planned_end":   worst.end_date.isoformat(),
            "days":          sprint_end_offset_days(worst),
        }
    return None


def build_project_summary(project, sprints: list, today: date) -> dict:
    total = len(sprints)
    completed = sum(1 for s in sprints if s.status == "completed")
    # Préfère le ratio sprints clos / total ; fallback sur project.progress
    progress_pct = round(completed / total * 100) if total else round(project.progress or 0)
    cum_delay = cumulative_delay_days(sprints, today)
    cur = current_sprint(sprints)
    return {
        "id":                    project.id,
        "name":                  project.name,
        "client_name":           project.client.name if project.client else "—",
        "status":                project.status,
        "deadline":              project.end_date.isoformat() if project.end_date else None,
        "progress_pct":          progress_pct,
        "completed_sprints":     completed,
        "total_sprints":         total,
        "current_sprint_number": cur.sprint_number if cur else None,
        # Dates du sprint courant (pour la carte "En développement" du dashboard)
        "current_sprint_actual_start": (
            cur.actual_start_date.isoformat() if cur and cur.actual_start_date else None
        ),
        "current_sprint_planned_end": (
            cur.end_date.isoformat() if cur else None
        ),
        "current_sprint_start_offset": (
            sprint_start_offset_days(cur) if cur else None
        ),
        "cumulative_delay_days": cum_delay,
        # Source principale du retard cumulé (pour la section "Projets à risque")
        # → le sprint actif en débordement prime ; sinon le dernier sprint clos en retard.
        "delay_source":          _delay_source(sprints, today),
        "insight":               build_project_insight(project, sprints, cum_delay),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Agrégats portefeuille — exclusivement consommés par le dashboard PM.
# ──────────────────────────────────────────────────────────────────────────────

def status_distribution(projects: list) -> list[dict]:
    """Donut "Répartition des statuts" du dashboard PM."""
    counter = Counter(p.status for p in projects)
    return [{"status": s, "count": c} for s, c in counter.most_common()]


def sprint_delay_distribution(all_sprints: list) -> list[dict]:
    """Histogramme "Retards des sprints clos" du dashboard PM.

    Trois buckets seulement (sans 'léger', sur demande PM) :
      - early   : clos avec ≥ 1 jour d'avance     (end_offset ≤ -1)
      - on_time : clos pile à la date planifiée   (end_offset == 0)
      - late    : clos avec ≥ 1 jour de retard    (end_offset ≥ 1)
    """
    buckets = {"early": 0, "on_time": 0, "late": 0}
    for s in all_sprints:
        if s.status != "completed":
            continue
        off = sprint_end_offset_days(s)
        if off is None:
            continue
        if off <= -1:
            buckets["early"] += 1
        elif off == 0:
            buckets["on_time"] += 1
        else:  # off >= 1
            buckets["late"] += 1
    labels = {"early": "En avance", "on_time": "À l'heure", "late": "En retard"}
    return [
        {"bucket": k, "label": labels[k], "count": v}
        for k, v in buckets.items()
    ]


_MONTHS_FR = {
    1: "jan", 2: "fév", 3: "mar", 4: "avr", 5: "mai", 6: "juin",
    7: "juil", 8: "aoû", 9: "sep", 10: "oct", 11: "nov", 12: "déc",
}


def _week_label(monday: date) -> str:
    """Plage lisible : '28 avr – 3 mai' ou '19–25 mai'."""
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday.day} {_MONTHS_FR[sunday.month]}"
    return f"{monday.day} {_MONTHS_FR[monday.month]} – {sunday.day} {_MONTHS_FR[sunday.month]}"


def velocity_weekly(
    all_sprints: list,
    weeks: int,
    today: date,
    project_names: dict | None = None,
) -> list[dict]:
    """Courbe 'Sprints clos par semaine' sur `weeks` semaines glissantes.

    Chaque entrée contient :
      - week      : identifiant ISO (2026-W18)
      - label     : plage lisible  ('28 avr – 3 mai')
      - completed : nombre de sprints clos cette semaine
      - sprints   : liste des sprints clos (project_name, sprint_number,
                    actual_end_date) — affiché dans le tooltip du graphe.

    `project_names` : dict {project_id: project_name} pour humaniser les noms.
    """
    pnames = project_names or {}
    today_monday = today - timedelta(days=today.weekday())
    start_window = today_monday - timedelta(weeks=weeks - 1)

    counts: Counter = Counter()
    sprints_per_week: dict[tuple, list] = {}

    for s in all_sprints:
        if s.status != "completed" or not s.actual_end_date:
            continue
        if s.actual_end_date < start_window:
            continue
        iso_year, iso_week, _ = s.actual_end_date.isocalendar()
        key = (iso_year, iso_week)
        counts[key] += 1
        sprints_per_week.setdefault(key, []).append({
            "project_name":      pnames.get(s.project_id, f"Projet {s.project_id}"),
            "sprint_number":     s.sprint_number,
            "actual_end_date":   s.actual_end_date.isoformat(),
            "actual_sp":         s.actual_sp or 0,
            "target_capacity_sp": s.target_capacity_sp or 0,
        })

    out = []
    for i in range(weeks):
        monday = start_window + timedelta(weeks=i)
        iso_year, iso_week, _ = monday.isocalendar()
        key = (iso_year, iso_week)
        out.append({
            "week":      f"{iso_year}-W{iso_week:02d}",
            "label":     _week_label(monday),
            "completed": counts.get(key, 0),
            "sprints":   sprints_per_week.get(key, []),
        })
    return out


def avg_sprint_delay_days(all_sprints: list) -> float:
    """KPI dashboard : moyenne signée des retards de sprints clos."""
    deltas = [sprint_end_offset_days(s) for s in all_sprints if s.status == "completed"]
    deltas = [d for d in deltas if d is not None]
    if not deltas:
        return 0.0
    return round(sum(deltas) / len(deltas), 1)


def count_velocity_30d(all_sprints: list, today: date) -> int:
    """KPI dashboard : nombre de sprints clos sur les 30 derniers jours."""
    cutoff = today - timedelta(days=30)
    return sum(
        1 for s in all_sprints
        if s.status == "completed" and s.actual_end_date and s.actual_end_date >= cutoff
    )
