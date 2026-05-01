# agents/pm/agents/cpm/agent.py
# Phase 6 — Critical Path Method (CPM) sur les user stories.
# Algorithme déterministe (pas de LLM).
#
# Entrées :
#   state["stories"]            — liste de stories avec db_id + story_points
#   state["story_dependencies"] — liste {from_story_id, to_story_id, relation_type}
#
# Sorties :
#   cpm_result    : { story_id → { earliest_start, latest_start, slack, is_critical } }
#   critical_path : [story_id, ...] avec slack == 0 (durée totale du projet = max ES + duration)
#
# Notes :
#   - duration de chaque story = story_points (1 SP = 1 unité). Défaut = 1 si manquant.
#   - on traite uniquement les arcs FS (les SS/FF sont ignorés pour le CPM classique).

from agents.pm.state import PMPipelineState


async def node_cpm(state: PMPipelineState) -> dict:
    project_id = state.get("project_id")
    stories    = state.get("stories", []) or []
    deps       = state.get("story_dependencies", []) or []

    print(f"[cpm] Phase 6 | projet={project_id} | {len(stories)} stories | {len(deps)} déps")

    # Map id → story, durée
    story_by_id = {}
    duration    = {}
    for s in stories:
        sid = s.get("db_id") or s.get("id")
        if sid is None:
            continue
        story_by_id[sid] = s
        duration[sid] = max(1, int(s.get("story_points") or 1))

    # Adjacence (uniquement FS — sinon le CPM classique n'est pas défini)
    successors   = {sid: [] for sid in story_by_id}
    predecessors = {sid: [] for sid in story_by_id}
    for d in deps:
        if d.get("relation_type", "FS") != "FS":
            continue
        u, v = d.get("from_story_id"), d.get("to_story_id")
        if u in story_by_id and v in story_by_id:
            successors[u].append(v)
            predecessors[v].append(u)

    # Tri topologique (Kahn)
    in_deg = {sid: len(predecessors[sid]) for sid in story_by_id}
    queue  = [sid for sid, d in in_deg.items() if d == 0]
    order  = []
    head   = 0
    in_deg_copy = dict(in_deg)
    while head < len(queue):
        u = queue[head]; head += 1
        order.append(u)
        for v in successors[u]:
            in_deg_copy[v] -= 1
            if in_deg_copy[v] == 0:
                queue.append(v)

    # Forward pass : Earliest Start / Earliest Finish
    es = {sid: 0.0 for sid in story_by_id}
    ef = {sid: 0.0 for sid in story_by_id}
    for u in order:
        es[u] = max((ef[p] for p in predecessors[u]), default=0.0)
        ef[u] = es[u] + duration[u]

    project_duration = max(ef.values(), default=0.0)

    # Backward pass : Latest Finish / Latest Start
    lf = {sid: project_duration for sid in story_by_id}
    ls = {sid: project_duration for sid in story_by_id}
    for u in reversed(order):
        lf[u] = min((ls[s] for s in successors[u]), default=project_duration)
        ls[u] = lf[u] - duration[u]

    cpm_result    = {}
    critical_path = []
    for sid in story_by_id:
        slack       = ls[sid] - es[sid]
        is_critical = abs(slack) < 1e-9
        cpm_result[sid] = {
            "earliest_start": es[sid],
            "earliest_finish": ef[sid],
            "latest_start":   ls[sid],
            "latest_finish":  lf[sid],
            "duration":       duration[sid],
            "slack":          slack,
            "is_critical":    is_critical,
        }
        if is_critical:
            critical_path.append(sid)

    # Tri du chemin critique par ES pour un affichage chronologique
    critical_path.sort(key=lambda sid: es[sid])

    print(f"[cpm] durée projet={project_duration} | chemin critique={len(critical_path)} stories")

    return {
        "cpm_result":        cpm_result,
        "critical_path":     critical_path,
        "current_phase":     "cpm",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
