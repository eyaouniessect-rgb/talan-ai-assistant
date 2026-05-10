# agents/pm/agents/staffing/steps/story_distribution/service.py
# Step 3 — Répartition initiale des stories par sprint
#
# Logique déterministe (pas de LLM) :
#   1. Récupère les dates du projet en DB (crm.projects)
#   2. Calcule les jours ouvrables (lundi-vendredi) entre start et end
#   3. Nombre de sprints = ceil(jours_ouvrables / 10)
#      → le dernier sprint peut être plus court mais doit exister
#   4. Calcule les dates exactes de chaque sprint
#   5. Répartition adaptative avec recalcul glissant (_adaptive_distribute) :
#        Pour chaque sprint i :
#          a. cible_i = ceil(SP_restant / sprints_restants)
#          b. Greedy fill du sprint i jusqu'à atteindre (sans dépasser) la cible
#          c. target_capacity_sp = actual_sp → delta = 0 → résultat auto-équilibré
#          d. Recalcul pour i+1 avec le SP restant mis à jour
#   6. Le PM peut ensuite ajuster manuellement les capacités via l'UI
#      → redistribute_with_capacities() reprend avec _greedy_distribute()

from __future__ import annotations

import math
from datetime import date, timedelta

from agents.pm.agents.staffing.schemas import (
    SprintStory,
    SprintWindow,
    StoryDistributionResult,
)

SPRINT_DURATION_WORKING_DAYS = 10   # 2 semaines ouvrables — fixe pour l'instant


# ── Helpers calendrier ─────────────────────────────────────────

def _is_working_day(d: date) -> bool:
    return d.weekday() < 5  # 0=lundi … 4=vendredi


def _all_working_days(start: date, end: date) -> list[date]:
    """Retourne tous les jours ouvrables entre start et end (inclusif)."""
    days: list[date] = []
    current = start
    while current <= end:
        if _is_working_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _build_sprint_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Découpe [start..end] en sprints de SPRINT_DURATION_WORKING_DAYS jours
    ouvrables. Le dernier sprint peut être plus court (1 à 9 jours ouvrables)
    mais doit exister tant qu'il reste au moins un jour ouvrable.
    """
    working_days = _all_working_days(start, end)
    if not working_days:
        return []

    windows: list[tuple[date, date]] = []
    for i in range(0, len(working_days), SPRINT_DURATION_WORKING_DAYS):
        chunk = working_days[i: i + SPRINT_DURATION_WORKING_DAYS]
        windows.append((chunk[0], chunk[-1]))
    return windows


# ── Algorithme de répartition ──────────────────────────────────

def _greedy_distribute(
    stories: list[dict],
    target_capacities: list[int],
) -> tuple[list[list[dict]], list[int]]:
    """
    Répartit les stories (triées par rang) dans len(target_capacities) sprints.

    target_capacities : capacité cible (en story points) propre à chaque sprint.
                        Ex : [25, 20, 22, 21, 21, 21, 19] pour 7 sprints.

    Stratégie : favoriser la sous-estimation plutôt que le dépassement.
      - Avant d'ajouter une story, vérifier si ça ferait dépasser la cible
        DU SPRINT COURANT (chaque sprint a sa propre cible).
      - Si oui ET le sprint courant n'est pas vide → passer au sprint suivant.
      - Sauvegarde anti-stranding : un sprint vide accepte toujours au moins
        une story (cas où une story seule a déjà plus de SP que sa cible).
      - Le dernier sprint absorbe tout ce qui reste (pas de saut possible).
      - Une story n'est jamais découpée.
    """
    num_sprints = len(target_capacities)
    buckets   = [[] for _ in range(num_sprints)]
    bucket_sp = [0]  * num_sprints
    current   = 0

    for story in stories:
        sp = story.get("story_points", 0)
        # Avancer si l'ajout dépasserait la cible du sprint courant
        # (sauf sprint vide ou dernier sprint)
        while (
            current < num_sprints - 1
            and bucket_sp[current] > 0
            and bucket_sp[current] + sp > target_capacities[current]
        ):
            current += 1
        buckets[current].append(story)
        bucket_sp[current] += sp

    return buckets, bucket_sp


def _adaptive_distribute(
    stories: list[dict],
    num_sprints: int,
) -> tuple[list[list[dict]], list[int]]:
    """
    Répartition adaptative avec recalcul glissant de la cible.

    Pour chaque sprint i (dans l'ordre) :
      1. remaining_sp   = somme des SP des stories non encore affectées
         remaining_sprints = num_sprints - i
      2. cible_i = ceil(remaining_sp / remaining_sprints)
      3. Greedy fill : prendre les stories en ordre de priorité tant que
           a. Le sprint est vide (anti-stranding)
           OU b. L'ajout ne dépasse pas cible_i
         → arrêter dès qu'une story dépasserait ET que le sprint n'est pas vide.
      4. target_capacity_sp = actual_sp   (delta = 0 : résultat auto-équilibré)
         Le PM part d'une vue propre et peut augmenter certains sprints via l'UI.
      5. Recalcul : remaining_sp -= actual_sp, remaining_sprints -= 1

    Le dernier sprint absorbe tout ce qui reste (par construction, remaining_sprints = 1
    → cible = remaining_sp = toutes les stories non affectées).

    Retourne :
      buckets   : list[list[dict]]  — stories assignées par sprint
      bucket_sp : list[int]         — SP réels par sprint (= target affiché)
    """
    buckets:   list[list[dict]] = [[] for _ in range(num_sprints)]
    bucket_sp: list[int]        = [0]  * num_sprints

    remaining_stories: list[dict] = list(stories)  # copy — on consomme au fur et à mesure

    for sprint_idx in range(num_sprints):
        is_last           = (sprint_idx == num_sprints - 1)
        remaining_sp      = sum(s.get("story_points", 0) for s in remaining_stories)
        remaining_sprints = num_sprints - sprint_idx

        if is_last:
            # Dernier sprint : absorbe tout le reste
            buckets[sprint_idx]   = remaining_stories
            bucket_sp[sprint_idx] = remaining_sp
            remaining_stories     = []
        else:
            target = max(1, math.ceil(remaining_sp / remaining_sprints))

            sprint_bucket: list[dict] = []
            sprint_sp     = 0
            leftover:     list[dict] = []

            for story in remaining_stories:
                sp = story.get("story_points", 0)
                if sprint_sp == 0 or sprint_sp + sp <= target:
                    # Sprint vide (anti-stranding) OU ajout dans la limite
                    sprint_bucket.append(story)
                    sprint_sp += sp
                else:
                    leftover.append(story)

            buckets[sprint_idx]   = sprint_bucket
            bucket_sp[sprint_idx] = sprint_sp
            remaining_stories     = leftover

    return buckets, bucket_sp


# ── Point d'entrée public ──────────────────────────────────────

async def distribute_stories(
    project_id: int,
    stories_input: list[dict],
    priorities: list[dict],
) -> StoryDistributionResult:
    """
    stories_input : liste de dicts {story_id, title, story_points, …}
    priorities    : liste de dicts {story_id, final_rank}
    """
    print(f"[story_distribution] ▶ Step 3 — Répartition initiale | projet={project_id}")

    # 1. Dates du projet depuis la DB
    from sqlalchemy import select
    from app.database.connection import AsyncSessionLocal
    from app.database.models.crm.project import Project

    async with AsyncSessionLocal() as db:
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        start_date: date = project.start_date
        end_date:   date = project.end_date

    if not start_date or not end_date or end_date <= start_date:
        raise ValueError(
            f"Dates de projet invalides : start={start_date}, end={end_date}"
        )

    # 2. Fenêtres de sprint (ceil — dernier sprint peut être plus court)
    windows = _build_sprint_windows(start_date, end_date)
    if not windows:
        raise ValueError(
            f"Aucun jour ouvrable entre {start_date} et {end_date}"
        )
    number_of_sprints  = len(windows)
    total_working_days = sum(
        len(_all_working_days(s_start, s_end))
        for s_start, s_end in windows
    )
    print(
        f"[story_distribution]   jours ouvrables={total_working_days} "
        f"→ {number_of_sprints} sprint(s) "
        f"(dernier sprint = {len(_all_working_days(*windows[-1]))} j.o.)"
    )

    # 3. Construire la map rang et trier les stories
    rank_map = {
        p["story_id"]: p.get("final_rank", 999)
        for p in priorities
        if isinstance(p, dict) and "story_id" in p
    }

    sorted_stories = sorted(
        [
            {
                "story_id":     s.get("story_id") or s.get("db_id"),
                "title":        s.get("title", ""),
                "story_points": s.get("story_points", 3),
                "rank":         rank_map.get(s.get("story_id") or s.get("db_id"), 999),
            }
            for s in stories_input
            if (s.get("story_id") or s.get("db_id")) is not None
        ],
        key=lambda x: x["rank"],
    )

    total_sp     = sum(s["story_points"] for s in sorted_stories)
    avg_capacity = max(1, round(total_sp / number_of_sprints))
    print(
        f"[story_distribution]   total_SP={total_sp} | "
        f"cible moyenne initiale={avg_capacity}"
    )

    # 4. Répartition adaptative avec recalcul glissant sprint par sprint
    buckets, bucket_sp = _adaptive_distribute(sorted_stories, number_of_sprints)

    # 5. Construire le résultat
    # target_capacity_sp = actual_sp → delta = 0 pour tous les sprints.
    # Le PM part d'une répartition auto-équilibrée et ajuste depuis l'UI si besoin.
    sprints = []
    for i, (s_start, s_end) in enumerate(windows):
        actual_sp = bucket_sp[i]
        sprints.append(SprintWindow(
            sprint_number       = i + 1,
            start_date          = s_start.isoformat(),
            end_date            = s_end.isoformat(),
            target_capacity_sp  = actual_sp,     # cible = réalisé (delta = 0)
            assigned_stories    = [
                SprintStory(
                    story_id     = st["story_id"],
                    title        = st["title"],
                    story_points = st["story_points"],
                    rank         = st["rank"],
                )
                for st in buckets[i]
            ],
            actual_sp = actual_sp,
            delta_sp  = 0,
        ))
        print(
            f"[story_distribution]   Sprint {i+1} "
            f"({s_start} → {s_end}) : "
            f"{len(buckets[i])} stories | {actual_sp} SP"
        )

    print(f"[story_distribution] ✅ terminé — {number_of_sprints} sprints répartis")

    return StoryDistributionResult(
        number_of_sprints          = number_of_sprints,
        sprint_duration_days       = SPRINT_DURATION_WORKING_DAYS,
        total_story_points         = total_sp,
        target_capacity_per_sprint = avg_capacity,
        sprints                    = sprints,
    )


# ── Redistribution avec capacités personnalisées par le PM ─────

def redistribute_with_capacities(
    distrib_result:    dict,
    stories_input:     list[dict],
    priorities:        list[dict],
    target_capacities: list[int],
) -> StoryDistributionResult:
    """
    Re-répartit les stories selon des capacités cible personnalisées par sprint.

    Les fenêtres de sprint (dates) sont conservées telles quelles depuis
    distrib_result — seule la composition story-par-sprint change.

    distrib_result    : ancien résultat (StoryDistributionResult.model_dump())
    stories_input     : liste de stories du backlog (story_id, title, story_points, …)
    priorities        : liste des priorités (story_id, final_rank)
    target_capacities : nouvelle capacité cible par sprint (longueur = nb sprints)

    ValueError si len(target_capacities) ≠ nombre de sprints existant.
    """
    existing_sprints = distrib_result.get("sprints", []) or []
    num_sprints      = len(existing_sprints)

    if len(target_capacities) != num_sprints:
        raise ValueError(
            f"Nombre de capacités fournies ({len(target_capacities)}) "
            f"≠ nombre de sprints existants ({num_sprints})"
        )
    if any(c < 1 for c in target_capacities):
        raise ValueError("Toutes les capacités doivent être ≥ 1 SP.")

    # Map rang
    rank_map = {
        p["story_id"]: p.get("final_rank", 999)
        for p in priorities
        if isinstance(p, dict) and "story_id" in p
    }

    sorted_stories = sorted(
        [
            {
                "story_id":     s.get("story_id") or s.get("db_id"),
                "title":        s.get("title", ""),
                "story_points": s.get("story_points", 3),
                "rank":         rank_map.get(s.get("story_id") or s.get("db_id"), 999),
            }
            for s in stories_input
            if (s.get("story_id") or s.get("db_id")) is not None
        ],
        key=lambda x: x["rank"],
    )

    total_sp = sum(s["story_points"] for s in sorted_stories)

    print(
        f"[story_distribution] ♻️  redistribution avec capacités custom : {target_capacities} "
        f"(total_SP={total_sp}, total_capacité={sum(target_capacities)})"
    )

    buckets, bucket_sp = _greedy_distribute(sorted_stories, target_capacities)

    # Reprendre les fenêtres de sprint existantes
    sprints = []
    for i, existing in enumerate(existing_sprints):
        actual_sp = bucket_sp[i]
        sprints.append(SprintWindow(
            sprint_number       = i + 1,
            start_date          = existing.get("start_date", ""),
            end_date            = existing.get("end_date",   ""),
            target_capacity_sp  = target_capacities[i],
            assigned_stories    = [
                SprintStory(
                    story_id     = st["story_id"],
                    title        = st["title"],
                    story_points = st["story_points"],
                    rank         = st["rank"],
                )
                for st in buckets[i]
            ],
            actual_sp           = actual_sp,
            delta_sp            = actual_sp - target_capacities[i],
        ))

    avg_target = max(1, round(sum(target_capacities) / num_sprints))

    return StoryDistributionResult(
        number_of_sprints          = num_sprints,
        sprint_duration_days       = SPRINT_DURATION_WORKING_DAYS,
        total_story_points         = total_sp,
        target_capacity_per_sprint = avg_target,
        sprints                    = sprints,
    )
