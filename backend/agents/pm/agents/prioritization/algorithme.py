# agents/pm/agents/prioritization/algorithme.py
# Phase Priorisation — backpropagation sur le DAG en utilisant la marge CPM.
#
# Entrées :
#   state["stories"]            — liste de stories avec db_id + story_points
#   state["story_dependencies"] — liste {from_story_id, to_story_id, relation_type}
#   state["cpm_result"]         — { story_id → { slack, ... } }  (calculé par node_cpm)
#
# Sortie :
#   priorities : [{ "story_id": int, "priority_score": float, "final_rank": int }]
#
# Algorithme :
#   1. Tri topologique (Kahn) — erreur si cycle détecté.
#   2. marge_max = max(slack) sur toutes les stories.
#   3. Backpropagation (ordre inverse) :
#        sans successeurs → priority = 0
#        avec successeurs → priority = MAX(priority[s] + marge_max - marge[n])
#   4. Tri : priority↓, marge↑, nb_successeurs↓, story_points↑, id↑

from agents.pm.state import PMPipelineState


async def node_prioritization(state: PMPipelineState) -> dict:
    project_id = state.get("project_id")
    stories    = state.get("stories", []) or []
    deps       = state.get("story_dependencies", []) or []
    cpm_result = state.get("cpm_result", {}) or {}

    print(f"[prioritization] projet={project_id} | {len(stories)} stories | {len(deps)} dépendances")

    # ── Index stories ─────────────────────────────────────────────
    story_by_id   = {}
    story_points  = {}
    for s in stories:
        sid = s.get("db_id") or s.get("id")
        if sid is None:
            continue
        story_by_id[sid]  = s
        story_points[sid] = max(1, int(s.get("story_points") or 1))

    # ── Marge (slack CPM) ─────────────────────────────────────────
    marge = {}
    for sid in story_by_id:
        key = str(sid) if str(sid) in cpm_result else sid
        marge[sid] = float(cpm_result[key]["slack"]) if key in cpm_result else 0.0

    # ── Adjacence (uniquement FS) ─────────────────────────────────
    successors   = {sid: [] for sid in story_by_id}
    predecessors = {sid: [] for sid in story_by_id}
    for d in deps:
        if d.get("relation_type", "FS") != "FS":
            continue
        u, v = d.get("from_story_id"), d.get("to_story_id")
        if u in story_by_id and v in story_by_id:
            successors[u].append(v)
            predecessors[v].append(u)

    # ── Tri topologique (Kahn) ────────────────────────────────────
    in_deg      = {sid: len(predecessors[sid]) for sid in story_by_id}
    in_deg_copy = dict(in_deg)
    queue       = [sid for sid, d in in_deg.items() if d == 0]
    order       = []
    head        = 0
    while head < len(queue):
        u = queue[head]; head += 1
        order.append(u)
        for v in successors[u]:
            in_deg_copy[v] -= 1
            if in_deg_copy[v] == 0:
                queue.append(v)

    if len(order) != len(story_by_id):
        raise ValueError("[prioritization] Le graphe contient un cycle — tri topologique impossible.")

    # ── Marge maximale ────────────────────────────────────────────
    marge_max = max(marge.values(), default=0.0)

    # ── Nœud puits fictif : toutes les feuilles y pointent ───────
    # Permet à chaque feuille d'obtenir un score > 0 (marge_max - marge[n])
    # au lieu d'être tous à 0. Le nœud fictif n'est pas inclus dans le résultat.
    SINK = -1
    marge[SINK]     = 0.0
    priority_sink   = 0.0

    leaves = [n for n in story_by_id if not successors[n]]
    for leaf in leaves:
        successors[leaf] = [SINK]

    # ── Backpropagation (ordre topologique inverse) ───────────────
    priority = {sid: 0.0 for sid in story_by_id}
    priority[SINK] = priority_sink

    for n in reversed(order):
        succs = successors[n]
        priority[n] = max(
            priority[s] + 1 + marge_max - marge[n]
            for s in succs
        )

    # ── Tri des stories ───────────────────────────────────────────
    ranked = sorted(
        story_by_id.keys(),
        key=lambda sid: (
            -priority[sid],          # priorité décroissante
            marge[sid],              # marge croissante
            -len(successors[sid]),   # nb successeurs décroissant
            story_points[sid],       # story_points croissant
            sid,                     # id croissant
        ),
    )

    priorities = [
        {
            "story_id":       sid,
            "priority_score": priority[sid],
            "final_rank":     rank,
        }
        for rank, sid in enumerate(ranked, start=1)
    ]

    print(f"[prioritization] scores : {[(p['story_id'], p['priority_score']) for p in priorities]}")

    return {
        "priorities":        priorities,
        "current_phase":     "prioritization",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
