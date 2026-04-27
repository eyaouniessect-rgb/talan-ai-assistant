# agents/pm/agents/dependencies/service.py
# Orchestration de la détection de dépendances — 2 passes LLM + post-processing

import asyncio
import json
import re
from collections import defaultdict, deque

from app.core.groq_client import invoke_with_fallback
from agents.pm.agents.dependencies.prompt import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_PASS2,
    build_pass1_prompt,
    build_pass2_prompt,
)

_MODEL = "openai/gpt-oss-120b"
# 1 retry externe à 5s : utile si NVIDIA retourne "" ou "[]" sur 1er essai
_RETRY_DELAYS: list[int] = [5]

# Sémaphore : max 2 appels Pass 1 en parallèle (évite la saturation NVIDIA)
_PASS1_SEM = asyncio.Semaphore(2)

_VALID_DEP_TYPES      = {"functional", "technical"}
_VALID_RELATION_TYPES = {"FS", "SS", "FF", "SF"}


# ──────────────────────────────────────────────────────────────
# Point d'entrée public
# ──────────────────────────────────────────────────────────────

async def run_story_deps(stories: list[dict]) -> list[dict]:
    """
    Détecte les dépendances entre stories en 2 passes :
      Pass 1 — Intra-epic : 1 appel LLM par epic, en parallèle
      Pass 2 — Inter-epic : 1 appel LLM global (titres uniquement)

    Retourne une liste de dépendances normalisées et validées.
    """
    if not stories:
        return []

    valid_ids = {_sid(s) for s in stories}
    stories_by_epic = _group_by_epic(stories)

    # Vraie détection d'orphelins : story dont epic_id est absent ou None.
    # epic_id=0 est l'INDEX du PREMIER epic (valide), pas un signe d'orphelin.
    real_orphans = [s for s in stories if s.get("epic_id") is None]
    if real_orphans:
        orphan_ids = [_sid(s) for s in real_orphans]
        print(f"[deps] ⚠️ {len(real_orphans)} stories sans epic_id (IDs: {orphan_ids}) — analysées dans le groupe par défaut")

    print(f"[deps] {len(stories)} stories | {len(stories_by_epic)} epics")
    for epic_idx, epic_stories in sorted(stories_by_epic.items()):
        print(f"[deps]   epic[{epic_idx}] : {len(epic_stories)} stories")

    # ── Pass 1 : intra-epic en parallèle (max 2 simultanés) ──────
    # Le sémaphore évite que 5+ appels parallèles saturent NVIDIA en même temps
    async def _pass1_semaphored(epic_stories):
        async with _PASS1_SEM:
            return await _run_pass1_intra(epic_stories)

    pass1_results = await asyncio.gather(*[
        _pass1_semaphored(epic_stories)
        for epic_stories in stories_by_epic.values()
    ])
    intra_deps = []
    for deps in pass1_results:
        for d in deps:
            d["level"] = "intra_epic"
        intra_deps.extend(deps)

    print(f"[deps] Pass 1 → {len(intra_deps)} dépendances intra-epic")

    # ── Pass 2 : inter-epic ───────────────────────────────────
    inter_deps = await _run_pass2_inter(stories_by_epic)
    for d in inter_deps:
        d["level"] = "inter_epic"

    print(f"[deps] Pass 2 → {len(inter_deps)} dépendances inter-epic")

    # ── Post-processing ───────────────────────────────────────
    all_deps = intra_deps + inter_deps
    all_deps = _dedup(all_deps)
    all_deps = _validate_ids(all_deps, valid_ids)
    all_deps = _remove_cycles(all_deps)
    # transversal_threshold=8 : only cap sources with >8 inter-epic arcs (very obvious stars)
    # max_per_epic=2 : keep up to 2 arcs per target epic from a transversal source
    all_deps = _cap_fanout_per_epic(all_deps, stories, max_per_epic=2, transversal_threshold=8)
    all_deps = _transitive_reduction(all_deps)

    print(f"[deps] Final → {len(all_deps)} dépendances après post-processing")
    return all_deps


# ──────────────────────────────────────────────────────────────
# Pass 1 — Intra-epic
# ──────────────────────────────────────────────────────────────

async def _run_pass1_intra(stories: list[dict]) -> list[dict]:
    """1 appel LLM pour les stories d'un seul epic, avec retries NVIDIA."""
    if len(stories) < 2:
        return []

    prompt = build_pass1_prompt(stories)
    # nvidia_retries=2 par clé + les 2 clés disponibles + 1 retry externe à 5s
    # Timeout 60s pour le parallélisme limité à 2 epics simultanés
    raw = await _call_llm(
        prompt,
        nvidia_retries   = 2,
        nvidia_key_index = 0,
        nvidia_max_keys  = 2,   # essaie les 2 clés si la #1 retourne vide
        nvidia_timeout   = 60,
    )
    deps = _parse_deps(raw)

    # Filtrer les paires inter-epic qui se seraient glissées
    epic_id   = stories[0].get("epic_id")
    story_ids = {_sid(s) for s in stories}
    deps = [d for d in deps
            if d["from_story_id"] in story_ids and d["to_story_id"] in story_ids]

    print(f"[deps/pass1] epic={epic_id} → {len(deps)} dépendances")
    return deps


# ──────────────────────────────────────────────────────────────
# Pass 2 — Inter-epic
# ──────────────────────────────────────────────────────────────

async def _run_pass2_inter(stories_by_epic: dict) -> list[dict]:
    """1 appel LLM global avec titres uniquement groupés par epic."""
    # Besoin d'au moins 2 epics pour avoir des dépendances inter-epic
    if len(stories_by_epic) < 2:
        print(f"[deps/pass2] SKIP — seulement {len(stories_by_epic)} epic(s), inter-epic impossible")
        return []

    prompt = build_pass2_prompt(stories_by_epic)
    prompt_size = len(prompt) + len(SYSTEM_PROMPT_PASS2)
    print(f"[deps/pass2] prompt inter-epic : user={len(prompt)} chars | system={len(SYSTEM_PROMPT_PASS2)} chars | total≈{prompt_size} chars | {len(stories_by_epic)} epics")
    # Stratégie Pass 2 : FORCER NVIDIA (128k context) car Groq fail toujours avec 413.
    # nvidia_key_index=1 : démarre sur NVIDIA_API_KEY2 (clé dédiée Pass 2).
    # nvidia_max_keys=2  : si NVIDIA_API_KEY2 échoue, rotation vers NVIDIA_API_KEY.
    # nvidia_retries=3   : tentatives par clé avec température variée (0, 0.05, 0.10).
    # nvidia_timeout=90  : Pass 2 a un gros prompt → garder 90s de marge.
    raw = await _call_llm(
        prompt,
        system_prompt    = SYSTEM_PROMPT_PASS2,
        max_tokens       = 4096,
        skip_nvidia      = False,
        skip_groq        = True,
        nvidia_retries   = 3,
        nvidia_key_index = 1,
        nvidia_max_keys  = 2,
        nvidia_timeout   = 90,
    )
    print(f"[deps/pass2] réponse brute ({len(raw)} chars) : {raw[:120]!r}")
    deps = _parse_deps(raw)

    # Si le LLM a répondu [] (pas d'erreur, mais résultat vide), retenter avec
    # une température plus élevée pour obtenir une perspective différente.
    if not deps:
        for t_idx in range(2):
            temp = 0.1 + 0.1 * t_idx
            print(f"[deps/pass2] Résultat vide → retry {t_idx + 1}/2 (température={temp:.1f})")
            raw2 = await _call_llm(
                prompt,
                system_prompt    = SYSTEM_PROMPT_PASS2,
                max_tokens       = 4096,
                skip_groq        = True,
                nvidia_retries   = 2,
                nvidia_key_index = 1,
                nvidia_max_keys  = 2,
                nvidia_timeout   = 90,
                temperature      = temp,
            )
            deps2 = _parse_deps(raw2)
            if deps2:
                deps = deps2
                print(f"[deps/pass2] Retry {t_idx + 1} → {len(deps)} dépendances trouvées")
                break
            print(f"[deps/pass2] Retry {t_idx + 1} → encore vide")

    # Filtrer les paires intra-epic qui se seraient glissées
    epic_by_story: dict[int, int] = {}
    for epic_id, stories in stories_by_epic.items():
        for s in stories:
            epic_by_story[_sid(s)] = epic_id

    deps = [
        d for d in deps
        if epic_by_story.get(d["from_story_id"]) != epic_by_story.get(d["to_story_id"])
    ]

    print(f"[deps/pass2] inter-epic → {len(deps)} dépendances")
    return deps


# ──────────────────────────────────────────────────────────────
# LLM call
# ──────────────────────────────────────────────────────────────

async def _call_llm(
    prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    max_tokens: int = 4096,
    skip_nvidia: bool = False,
    skip_groq: bool = False,
    nvidia_retries: int = 1,
    nvidia_key_index: int = 0,
    nvidia_max_keys: int | None = None,
    nvidia_timeout: int = 90,
    temperature: float = 0,
) -> str:
    """
    Appelle le LLM avec retries internes + retries externes du wrapper invoke_with_fallback.

    Pour Pass 2 (gros prompt) : skip_groq=True, nvidia_retries=4 → force NVIDIA avec retries
                                agressifs car Groq fail systématiquement (413).
    Pour Pass 1 (petit prompt) : params par défaut → NVIDIA puis Groq fallback.
    """
    last_error = None
    for attempt in range(1 + len(_RETRY_DELAYS)):
        try:
            raw = await invoke_with_fallback(
                model             = _MODEL,
                messages          = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens        = max_tokens,
                temperature       = temperature,
                skip_nvidia       = skip_nvidia,
                skip_groq         = skip_groq,
                nvidia_retries    = nvidia_retries,
                nvidia_key_index  = nvidia_key_index,
                nvidia_max_keys   = nvidia_max_keys,
                nvidia_timeout    = nvidia_timeout,
            )
            if not raw or not raw.strip():
                raise ValueError("Réponse vide du LLM")
            return raw
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # 413 / contexte trop long → inutile de retenter, le prompt est identique
            if "413" in error_str or "request too large" in error_str or "trop longue" in error_str:
                print(f"[deps/llm] contexte trop long (413) → abandon immédiat, retour []")
                return "[]"
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                print(f"[deps/llm] tentative {attempt+1} échouée ({type(e).__name__}: {str(e)[:80]}) → retry dans {delay}s")
                await asyncio.sleep(delay)

    print(f"[deps/llm] {1+len(_RETRY_DELAYS)} tentatives échouées → retour []")
    return "[]"


# ──────────────────────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────────────────────

def _extract_partial_objects(text: str) -> list[dict]:
    """
    Extrait les objets JSON {...} complets et bien formés depuis un texte,
    même si l'ensemble n'est pas un JSON valide (tronqué, texte parasite).
    Compte les accolades en respectant les chaînes pour ne pas couper au mauvais endroit.
    """
    objects: list[dict] = []
    depth      = 0
    start      = -1
    in_string  = False
    escape     = False

    for i, c in enumerate(text):
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                snippet = text[start:i+1]
                try:
                    obj = json.loads(snippet)
                    if isinstance(obj, dict):
                        objects.append(obj)
                except (json.JSONDecodeError, ValueError):
                    pass
                start = -1
    return objects


def _parse_deps(raw: str) -> list[dict]:
    """Parse la réponse LLM avec 3 stratégies de récupération en cascade :
      1. json.loads direct sur le texte nettoyé (markdown retiré)
      2. Extraction du premier tableau JSON [...] via regex (texte parasite avant/après)
      3. Extraction objet par objet via comptage d'accolades (JSON tronqué)
    """
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    data = None

    # Stratégie 1 : parsing direct
    try:
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        pass

    # Stratégie 2 : extraire le premier tableau JSON [...] via regex
    # Utile quand le LLM préfixe ("Voici les dépendances :") ou suffixe ("Voilà !")
    if data is None:
        match = re.search(r"\[\s*(?:\{.*?\}\s*,?\s*)*\]", clean, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                print(f"[deps/parse] Tableau JSON extrait via regex (texte parasite ignoré)")
            except (json.JSONDecodeError, ValueError):
                pass

    # Stratégie 3 : récupération objet par objet (JSON tronqué/incomplet)
    if data is None:
        recovered = _extract_partial_objects(clean)
        if recovered:
            print(f"[deps/parse] JSON tronqué récupéré : {len(recovered)} objet(s) extrait(s) sur {len(raw)} chars")
            data = recovered
        else:
            print(f"[deps/parse] JSON invalide ({len(raw)} chars). Début: {raw[:200]!r} | Fin: {raw[-200:]!r}")
            return []

    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        from_id = item.get("from_story_id")
        to_id   = item.get("to_story_id")
        if not isinstance(from_id, int) or not isinstance(to_id, int):
            continue
        if from_id == to_id:
            continue

        dep_type = item.get("dependency_type", "functional")
        if dep_type not in _VALID_DEP_TYPES:
            dep_type = "functional"

        rel_type = item.get("relation_type", "FS")
        if rel_type not in _VALID_RELATION_TYPES:
            rel_type = "FS"

        # is_blocking forcé à True : on ne détecte plus les dépendances optionnelles
        # (filet de sécurité au cas où le LLM en retourne quand même)
        if item.get("is_blocking") is False:
            continue

        result.append({
            "from_story_id":   from_id,
            "to_story_id":     to_id,
            "dependency_type": dep_type,
            "relation_type":   rel_type,
            "is_blocking":     True,
            "reason":          str(item.get("reason", ""))[:500],
        })

    return result


# ──────────────────────────────────────────────────────────────
# Post-processing
# ──────────────────────────────────────────────────────────────

def _sid(s: dict) -> int:
    """Retourne l'ID DB d'une story (db_id ou id)."""
    return s.get("db_id") or s.get("id")


def _group_by_epic(stories: list[dict]) -> dict:
    groups: dict = defaultdict(list)
    for s in stories:
        groups[s.get("epic_id", 0)].append(s)
    return dict(groups)


def _dedup(deps: list[dict]) -> list[dict]:
    """Supprime les paires (from, to) dupliquées — garde la première occurrence."""
    seen: set = set()
    result = []
    for d in deps:
        key = (d["from_story_id"], d["to_story_id"])
        if key not in seen:
            seen.add(key)
            result.append(d)
    return result


def _validate_ids(deps: list[dict], valid_ids: set) -> list[dict]:
    """Supprime les dépendances dont les IDs n'existent pas dans la liste de stories."""
    filtered = [
        d for d in deps
        if d["from_story_id"] in valid_ids and d["to_story_id"] in valid_ids
    ]
    removed = len(deps) - len(filtered)
    if removed:
        print(f"[deps/validate] {removed} dépendance(s) avec IDs invalides supprimée(s)")
    return filtered


def _remove_cycles(deps: list[dict]) -> list[dict]:
    """
    Détecte et supprime les arcs qui créent des cycles via l'algorithme de Kahn.
    Stratégie : tenter d'ajouter chaque arc dans l'ordre — ignorer l'arc si
    il crée un cycle avec les arcs déjà acceptés.
    """
    accepted: list[dict] = []

    for dep in deps:
        # Tester si l'ajout de cet arc crée un cycle dans accepted + [dep]
        if not _creates_cycle(accepted, dep["from_story_id"], dep["to_story_id"]):
            accepted.append(dep)
        else:
            print(f"[deps/cycle] Arc {dep['from_story_id']}→{dep['to_story_id']} ignoré (cycle)")

    return accepted


def _cap_fanout_per_epic(
    deps: list[dict],
    stories: list[dict],
    max_per_epic: int = 1,
    transversal_threshold: int = 5,
) -> list[dict]:
    """
    Anti-étoile CIBLÉ : limite uniquement les dépendances INTER-EPIC d'une story
    qui se comporte comme un composant transversal (fan-out total > threshold).

    Règles strictes :
      1. Les dépendances INTRA-EPIC ne sont JAMAIS limitées
         (workflow CRUD, chaînes Create→Modify→Delete sont légitimes)
      2. Une story est considérée transversale si elle a > N dépendances
         inter-epic sortantes (signe : auth, configuration globale, etc.)
      3. Pour les sources transversales, on garde max_per_epic arc par
         epic destination (cible de plus petit ID = racine de l'epic)

    Cas typiques traités :
      ✅ Conservé : "Créer projet"→{Modifier, Supprimer, Lister} (intra-epic CRUD)
      ❌ Retiré   : "Auth JWT"→{19 stories d'action dans 6 epics différents}
    """
    epic_by_story = {(s.get("db_id") or s.get("id")): s.get("epic_id", 0) for s in stories}

    # Étape 1 : compter le fan-out INTER-EPIC par source
    inter_epic_count: dict = defaultdict(int)
    for d in deps:
        src_epic = epic_by_story.get(d["from_story_id"], 0)
        tgt_epic = epic_by_story.get(d["to_story_id"], 0)
        if src_epic != tgt_epic:
            inter_epic_count[d["from_story_id"]] += 1

    # Identifier les sources transversales (fan-out inter-epic > threshold)
    transversal_sources = {
        src for src, n in inter_epic_count.items() if n > transversal_threshold
    }
    if transversal_sources:
        print(f"[deps/fanout] Sources transversales détectées (>{transversal_threshold} arcs inter-epic) : {sorted(transversal_sources)}")

    # Étape 2 : grouper par (source transversale, epic destination)
    groups: dict = defaultdict(list)
    untouched = []
    for d in deps:
        src_epic = epic_by_story.get(d["from_story_id"], 0)
        tgt_epic = epic_by_story.get(d["to_story_id"], 0)
        # Intra-epic ou source non-transversale → ne pas toucher
        if src_epic == tgt_epic or d["from_story_id"] not in transversal_sources:
            untouched.append(d)
            continue
        # Inter-epic depuis source transversale → groupe à plafonner
        groups[(d["from_story_id"], tgt_epic)].append(d)

    # Étape 3 : appliquer le cap sur les groupes concernés
    capped = []
    removed = 0
    for (source, target_epic), group_deps in groups.items():
        if len(group_deps) <= max_per_epic:
            capped.extend(group_deps)
            continue
        # Garder l'arc vers la cible de plus petit ID (racine de l'epic)
        sorted_deps = sorted(group_deps, key=lambda d: d["to_story_id"])
        capped.extend(sorted_deps[:max_per_epic])
        for d in sorted_deps[max_per_epic:]:
            removed += 1
            print(f"[deps/fanout] Arc {d['from_story_id']}→{d['to_story_id']} retiré (étoile inter-epic vers epic {target_epic})")

    if removed:
        print(f"[deps/fanout] {removed} arc(s) en étoile retirés (intra-epic préservées)")
    else:
        print(f"[deps/fanout] aucun cap appliqué (pas d'étoile inter-epic détectée)")

    return untouched + capped


def _transitive_reduction(deps: list[dict]) -> list[dict]:
    """
    Supprime les arcs A→X qui sont déjà impliqués par une chaîne A→Y→...→X.
    Garantit un graphe minimal sans dépendance redondante.

    Algorithme : pour chaque arc A→X, vérifier s'il existe un chemin alternatif
    A→...→X de longueur ≥ 2 dans le graphe SANS cet arc. Si oui, l'arc A→X
    est redondant et peut être supprimé.
    """
    if len(deps) < 3:
        return deps

    # Liste d'adjacence
    graph: dict[int, set] = defaultdict(set)
    for d in deps:
        graph[d["from_story_id"]].add(d["to_story_id"])

    def has_path(src: int, dst: int, exclude: tuple[int, int]) -> bool:
        """BFS depuis src vers dst en ignorant l'arc 'exclude'."""
        visited = {src}
        queue = deque([src])
        while queue:
            node = queue.popleft()
            for nxt in graph[node]:
                if (node, nxt) == exclude:
                    continue
                if nxt == dst:
                    return True
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        return False

    kept = []
    removed = 0
    for d in deps:
        src, dst = d["from_story_id"], d["to_story_id"]
        # Si un autre chemin src→...→dst existe (sans cet arc direct), l'arc est redondant
        if has_path(src, dst, exclude=(src, dst)):
            removed += 1
            print(f"[deps/transitive] Arc {src}→{dst} retiré (redondant via chemin transitif)")
        else:
            kept.append(d)

    if removed:
        print(f"[deps/transitive] {removed} arc(s) redondant(s) supprimé(s) sur {len(deps)}")
    return kept


def _creates_cycle(existing: list[dict], src: int, dst: int) -> bool:
    """
    Retourne True si ajouter src→dst crée un cycle dans le graphe existant.
    Utilise un BFS depuis dst pour voir si src est atteignable.
    """
    # Construire la liste d'adjacence
    graph: dict[int, list[int]] = defaultdict(list)
    for d in existing:
        graph[d["from_story_id"]].append(d["to_story_id"])

    # BFS depuis dst : si on atteint src, il y a un cycle
    visited = set()
    queue = deque([dst])
    while queue:
        node = queue.popleft()
        if node == src:
            return True
        if node in visited:
            continue
        visited.add(node)
        queue.extend(graph[node])

    return False
