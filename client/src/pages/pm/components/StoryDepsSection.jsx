import { useState, useEffect, useMemo, useCallback } from "react";
import {
  ReactFlow, Background, Controls, MiniMap,
  MarkerType, useNodesState, useEdgesState,
  Handle, Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import {
  List, Network, Lock, ArrowRight, GitBranch,
  Maximize2, X, Star, RotateCcw,
} from "lucide-react";
import clsx from "clsx";
import { getProjectStories, getProjectEpics } from "../../../api/pipeline";

// ── Couleurs par epic (palette fixe cyclique) ─────────────────
const EPIC_COLORS = [
  { bg: "bg-indigo-100",  border: "border-indigo-400",  node: "#e0e7ff", nodeStroke: "#6366f1", text: "text-indigo-700" },
  { bg: "bg-violet-100",  border: "border-violet-400",  node: "#ede9fe", nodeStroke: "#7c3aed", text: "text-violet-700" },
  { bg: "bg-sky-100",     border: "border-sky-400",     node: "#e0f2fe", nodeStroke: "#0284c7", text: "text-sky-700" },
  { bg: "bg-emerald-100", border: "border-emerald-400", node: "#d1fae5", nodeStroke: "#059669", text: "text-emerald-700" },
  { bg: "bg-amber-100",   border: "border-amber-400",   node: "#fef3c7", nodeStroke: "#d97706", text: "text-amber-700" },
  { bg: "bg-rose-100",    border: "border-rose-400",    node: "#ffe4e6", nodeStroke: "#e11d48", text: "text-rose-700" },
  { bg: "bg-cyan-100",    border: "border-cyan-400",    node: "#cffafe", nodeStroke: "#0891b2", text: "text-cyan-700" },
  { bg: "bg-orange-100",  border: "border-orange-400",  node: "#ffedd5", nodeStroke: "#ea580c", text: "text-orange-700" },
];

// ── Styles par type de dépendance ─────────────────────────────
const DEP_TYPE_STYLE = {
  functional: { label: "Fonctionnel", color: "bg-blue-100 text-blue-700",     edge: "#3b82f6" },
  technical:  { label: "Technique",   color: "bg-orange-100 text-orange-700", edge: "#f97316" },
};

const REL_TYPE_LABEL = { FS: "Fin→Début", SS: "Début→Début", FF: "Fin→Fin", SF: "Début→Fin" };

const PIVOT_THRESHOLD = 4; // ≥ 4 liens = story pivot

// ══════════════════════════════════════════════════════════════
// Custom node — design avec bande couleur epic + badge ID + pivot
// ══════════════════════════════════════════════════════════════
function StoryNode({ data }) {
  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />
      <div
        className={clsx(
          "rounded-lg shadow-md transition-all overflow-hidden",
          data.dim ? "opacity-20" : "opacity-100",
          data.isFocus && "ring-4 ring-amber-400 shadow-xl scale-105",
        )}
        style={{
          width: NODE_W,
          background: data.epicBg,
          border: `2px solid ${data.epicColor}`,
        }}
      >
        <div
          className="px-2.5 py-1.5 flex items-center gap-2 border-b"
          style={{ background: data.epicColor, borderColor: data.epicColor }}
        >
          <span className="text-[11px] font-mono font-bold text-white">
            #{data.id}
          </span>
          <span className="text-[10px] font-semibold text-white/90 px-1.5 py-0.5 rounded bg-white/20">
            E{data.epicIdx + 1}
          </span>
          {data.isPivot && (
            <span className="ml-auto" title={`${data.connectivity} liens — story pivot`}>
              <Star size={13} className="text-yellow-200 fill-yellow-300" />
            </span>
          )}
        </div>
        <div className="px-2.5 py-2 text-[12px] leading-snug font-medium text-slate-800">
          {data.title}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />
    </>
  );
}

const nodeTypes = { story: StoryNode };

// ══════════════════════════════════════════════════════════════
// Layout dagre — top→down hiérarchique, évite les croisements
// ══════════════════════════════════════════════════════════════
const NODE_W = 280, NODE_H = 160;

function getLayoutedElements(nodes, edges, direction = "TB") {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 70, ranksep: 130, marginx: 30, marginy: 30 });

  nodes.forEach(n => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach(e => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return {
    nodes: nodes.map(n => {
      const p = g.node(n.id);
      return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
    }),
    edges,
  };
}

// ══════════════════════════════════════════════════════════════
// Focus mode : ensemble visible = root + ancêtres + descendants (à profondeur N)
// ══════════════════════════════════════════════════════════════
function computeVisibleSet(focusedId, deps, depth) {
  const root = Number(focusedId);
  const set = new Set([root]);
  const adj = {}, radj = {};
  for (const d of deps) {
    (adj[d.from_story_id] ??= []).push(d.to_story_id);
    (radj[d.to_story_id] ??= []).push(d.from_story_id);
  }

  const bfs = (start, graph) => {
    let frontier = [start];
    for (let i = 0; i < depth; i++) {
      const next = [];
      for (const n of frontier) {
        for (const m of (graph[n] || [])) {
          if (!set.has(m)) { set.add(m); next.push(m); }
        }
      }
      frontier = next;
      if (!frontier.length) break;
    }
  };
  bfs(root, adj);
  bfs(root, radj);
  return set;
}

// ══════════════════════════════════════════════════════════════
// Build nodes + edges pour ReactFlow
// ══════════════════════════════════════════════════════════════
function buildGraph({ deps, storyMap, epicColorMap, epicIdxMap, focusedId, depth }) {
  // Compteurs in/out par story (pour pivots)
  const inDeg = {}, outDeg = {};
  for (const d of deps) {
    outDeg[d.from_story_id] = (outDeg[d.from_story_id] || 0) + 1;
    inDeg[d.to_story_id]    = (inDeg[d.to_story_id]    || 0) + 1;
  }

  const visible = focusedId ? computeVisibleSet(focusedId, deps, depth) : null;

  // Ne montre que les stories qui ont au moins une dépendance
  const referencedIds = new Set();
  for (const d of deps) {
    referencedIds.add(d.from_story_id);
    referencedIds.add(d.to_story_id);
  }

  const nodes = Object.values(storyMap)
    .filter(s => referencedIds.has(s.db_id))
    .map(s => {
      const epicColor    = epicColorMap[s.epic_id] ?? EPIC_COLORS[0];
      const connectivity = (inDeg[s.db_id] || 0) + (outDeg[s.db_id] || 0);
      const isPivot      = connectivity >= PIVOT_THRESHOLD;
      const dim          = visible ? !visible.has(s.db_id) : false;
      const isFocus      = String(s.db_id) === focusedId;

      return {
        id:       String(s.db_id),
        type:     "story",
        position: { x: 0, y: 0 },
        data: {
          id:           s.db_id,
          title:        s.title,
          epicColor:    epicColor.nodeStroke,
          epicBg:       epicColor.node,
          epicIdx:      epicIdxMap[s.epic_id] ?? 0,
          connectivity,
          isPivot,
          isFocus,
          dim,
        },
      };
    });

  const edges = deps.map((d, i) => {
    const dim       = visible && (!visible.has(d.from_story_id) || !visible.has(d.to_story_id));
    const edgeColor = DEP_TYPE_STYLE[d.dependency_type]?.edge ?? "#94a3b8";
    return {
      id:           `e${i}`,
      source:       String(d.from_story_id),
      target:       String(d.to_story_id),
      type:         "default",
      label:        d.relation_type,
      animated:     !dim,
      style:        { stroke: dim ? "#cbd5e1" : edgeColor, strokeWidth: dim ? 1 : 2, opacity: dim ? 0.3 : 1 },
      labelStyle:   { fontSize: 10, fill: dim ? "#94a3b8" : edgeColor, fontWeight: 600 },
      labelBgStyle: { fill: "#fff", fillOpacity: dim ? 0.4 : 0.85 },
      markerEnd:    { type: MarkerType.ArrowClosed, color: dim ? "#cbd5e1" : edgeColor },
    };
  });

  return getLayoutedElements(nodes, edges);
}

// ══════════════════════════════════════════════════════════════
// Liste view
// ══════════════════════════════════════════════════════════════
function DepCard({ dep, storyMap, epicColorMap }) {
  const fromStory = storyMap[dep.from_story_id];
  const toStory   = storyMap[dep.to_story_id];
  const style     = DEP_TYPE_STYLE[dep.dependency_type] ?? DEP_TYPE_STYLE.functional;
  const epicColor = epicColorMap[fromStory?.epic_id ?? 0] ?? EPIC_COLORS[0];

  return (
    <div className={clsx(
      "rounded-xl border p-3 bg-white space-y-2",
      dep.level === "inter_epic" ? "border-amber-300 bg-amber-50/30" : "border-slate-200"
    )}>
      <div className="flex items-center gap-2">
        <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium shrink-0", style.color)}>
          {style.label}
        </span>
        <span className="text-xs text-slate-500 shrink-0">
          {REL_TYPE_LABEL[dep.relation_type] ?? dep.relation_type}
        </span>
        <span className="ml-auto flex items-center gap-1 text-xs text-red-600 shrink-0">
          <Lock size={10} /> Bloquant
        </span>
        {dep.level === "inter_epic" && (
          <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full shrink-0">
            inter-epic
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 text-sm">
        <div className={clsx("flex-1 rounded-lg border px-2 py-1.5 text-xs", epicColor.bg, epicColor.border)}>
          <span className="text-slate-400 text-[10px] block mb-0.5">#{dep.from_story_id}</span>
          <span className="font-medium text-slate-700 line-clamp-2">
            {fromStory?.title ?? `Story ${dep.from_story_id}`}
          </span>
        </div>
        <ArrowRight size={16} className="text-slate-400 shrink-0" />
        <div className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs">
          <span className="text-slate-400 text-[10px] block mb-0.5">#{dep.to_story_id}</span>
          <span className="font-medium text-slate-700 line-clamp-2">
            {toStory?.title ?? `Story ${dep.to_story_id}`}
          </span>
        </div>
      </div>
      {dep.reason && (
        <p className="text-xs text-slate-500 italic border-t border-slate-100 pt-2">{dep.reason}</p>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Graph view
// ══════════════════════════════════════════════════════════════
function GraphView({
  deps, storyMap, epicColorMap, epicIdxMap,
  fullscreen = false, onToggleFullscreen,
  focusedId, setFocusedId, depth,
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const { nodes: n, edges: e } = buildGraph({
      deps, storyMap, epicColorMap, epicIdxMap, focusedId, depth,
    });
    setNodes(n);
    setEdges(e);
  }, [deps, storyMap, epicColorMap, epicIdxMap, focusedId, depth, setNodes, setEdges]);

  const onNodeClick = useCallback((_evt, node) => {
    setFocusedId(prev => prev === node.id ? null : node.id);
  }, [setFocusedId]);

  const onPaneClick = useCallback(() => {
    setFocusedId(null);
  }, [setFocusedId]);

  return (
    <div className={clsx(
      "relative rounded-xl border border-slate-200 overflow-hidden bg-slate-50",
      fullscreen ? "h-full w-full" : "h-[600px]"
    )}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        fitView
        fitViewOptions={{ padding: 0.2, minZoom: 0.3, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={2}
        defaultEdgeOptions={{ type: "default" }}
      >
        <Background color="#e2e8f0" gap={20} />
        <Controls />
        <MiniMap
          nodeColor={(n) => n.data?.epicColor ?? "#cbd5e1"}
          nodeStrokeWidth={3}
          pannable
          zoomable
        />
      </ReactFlow>

      {focusedId && (
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2 bg-white/95 border border-amber-300 rounded-lg shadow-sm px-2.5 py-1.5">
          <span className="text-xs text-slate-700">
            <strong className="text-amber-700">Focus :</strong> story #{focusedId} · profondeur {depth}
          </span>
          <button
            onClick={() => setFocusedId(null)}
            className="text-slate-400 hover:text-slate-600"
            title="Tout afficher"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      )}

      {onToggleFullscreen && (
        <button
          onClick={onToggleFullscreen}
          className="absolute top-3 right-3 z-10 flex items-center gap-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-sm transition-colors"
          title={fullscreen ? "Quitter le plein écran (Échap)" : "Plein écran"}
        >
          {fullscreen ? <X size={13} /> : <Maximize2 size={13} />}
          {fullscreen ? "Fermer" : "Plein écran"}
        </button>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Composant principal
// ══════════════════════════════════════════════════════════════
export default function StoryDepsSection({ aiOutput, projectId }) {
  const [stories,       setStories]       = useState([]);
  const [epics,         setEpics]         = useState([]);
  const [view,          setView]          = useState("list");
  const [filterType,    setFilterType]    = useState("all");
  const [filterLevel,   setFilterLevel]   = useState("all");
  const [selectedEpics, setSelectedEpics] = useState(new Set());
  const [focusedId,     setFocusedId]     = useState(null);
  const [depth,         setDepth]         = useState(2);
  const [isFullscreen,  setIsFullscreen]  = useState(false);

  const deps = Array.isArray(aiOutput) ? aiOutput : (aiOutput?.story_dependencies ?? []);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProjectStories(projectId), getProjectEpics(projectId)])
      .then(([s, e]) => { setStories(s); setEpics(e); })
      .catch(() => {});
  }, [projectId]);

  // Touche Échap pour fermer le plein écran
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (ev) => { if (ev.key === "Escape") setIsFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isFullscreen]);

  // Maps de lookup
  const storyMap = useMemo(
    () => Object.fromEntries(stories.map(s => [s.db_id, s])),
    [stories]
  );

  // L'API /pipeline/{id}/epics retourne db_id (pas id) ; les stories ont epic_id = FK DB
  const epicList = useMemo(() => {
    if (epics.length) return epics.map(e => ({ ...e, key: e.db_id ?? e.id }));
    return [...new Set(stories.map(s => s.epic_id))].map(id => ({ key: id, db_id: id }));
  }, [epics, stories]);

  const epicColorMap = useMemo(() => Object.fromEntries(
    epicList.map((e, i) => [e.key, EPIC_COLORS[i % EPIC_COLORS.length]])
  ), [epicList]);

  const epicIdxMap = useMemo(() => Object.fromEntries(
    epicList.map((e, i) => [e.key, i])
  ), [epicList]);

  // Filtres combinés
  const filtered = useMemo(() => deps.filter(d => {
    if (filterType  !== "all" && d.dependency_type !== filterType)  return false;
    if (filterLevel !== "all" && d.level           !== filterLevel) return false;
    if (selectedEpics.size > 0) {
      const fromEpic = storyMap[d.from_story_id]?.epic_id;
      const toEpic   = storyMap[d.to_story_id]?.epic_id;
      // Garde l'arc si au moins un des deux endpoints est dans les epics sélectionnés
      if (!selectedEpics.has(fromEpic) && !selectedEpics.has(toEpic)) return false;
    }
    return true;
  }), [deps, filterType, filterLevel, selectedEpics, storyMap]);

  const toggleEpic = (epicId) => {
    setSelectedEpics(prev => {
      const next = new Set(prev);
      if (next.has(epicId)) next.delete(epicId);
      else next.add(epicId);
      return next;
    });
  };

  // Stats
  const totalDeps  = deps.length;
  const intraCount = deps.filter(d => d.level === "intra_epic").length;
  const interCount = deps.filter(d => d.level === "inter_epic").length;

  const pivotCount = useMemo(() => {
    const conn = {};
    for (const d of deps) {
      conn[d.from_story_id] = (conn[d.from_story_id] || 0) + 1;
      conn[d.to_story_id]   = (conn[d.to_story_id]   || 0) + 1;
    }
    return Object.values(conn).filter(c => c >= PIVOT_THRESHOLD).length;
  }, [deps]);

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        {[
          ["Dépendances",     totalDeps,  "text-navy"],
          ["Stories pivots",  pivotCount, "text-amber-600"],
          ["Intra-epic",      intraCount, "text-indigo-600"],
          ["Inter-epic",      interCount, "text-rose-600"],
        ].map(([k, v, cls]) => (
          <div key={k} className="bg-slate-50 rounded-xl p-3 text-center">
            <div className={clsx("font-display font-bold text-xl", cls)}>{v}</div>
            <div className="text-xs text-slate-400 mt-0.5">{k}</div>
          </div>
        ))}
      </div>

      {/* Légende epic — cliquable pour filtrer */}
      <div>
        <div className="text-[11px] text-slate-500 mb-1.5">
          Filtrer par epic ({selectedEpics.size === 0 ? "tous affichés" : `${selectedEpics.size} sélectionné(s)`})
          {selectedEpics.size > 0 && (
            <button
              onClick={() => setSelectedEpics(new Set())}
              className="ml-2 text-navy underline hover:text-navy/70"
            >
              réinitialiser
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {epicList.map((epic, i) => {
            const color  = EPIC_COLORS[i % EPIC_COLORS.length];
            const active = selectedEpics.size === 0 || selectedEpics.has(epic.key);
            const label  = epic.title ? epic.title.slice(0, 28) + (epic.title.length > 28 ? "…" : "") : "";
            return (
              <button
                key={epic.key}
                onClick={() => toggleEpic(epic.key)}
                title={epic.title}
                className={clsx(
                  "text-[11px] px-2 py-0.5 rounded-full border transition-all",
                  active
                    ? `${color.bg} ${color.border} ${color.text}`
                    : "bg-white border-slate-200 text-slate-400 opacity-50"
                )}
              >
                E{i + 1}{label && ` · ${label}`}
              </button>
            );
          })}
        </div>
      </div>

      {/* Légende types */}
      <div className="flex flex-wrap items-center gap-2">
        {Object.entries(DEP_TYPE_STYLE).map(([k, v]) => (
          <span key={k} className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", v.color)}>
            {v.label}
          </span>
        ))}
        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
          inter-epic
        </span>
        <span className="ml-auto flex items-center gap-1 text-xs text-slate-500">
          <Star size={10} className="text-amber-500 fill-amber-400" />
          Story pivot (≥{PIVOT_THRESHOLD} liens)
        </span>
      </div>

      {/* Contrôles */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex rounded-lg border border-slate-200 overflow-hidden">
          <button
            onClick={() => setView("list")}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
              view === "list" ? "bg-navy text-white" : "bg-white text-slate-600 hover:bg-slate-50"
            )}
          >
            <List size={13} /> Liste
          </button>
          <button
            onClick={() => setView("graph")}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
              view === "graph" ? "bg-navy text-white" : "bg-white text-slate-600 hover:bg-slate-50"
            )}
          >
            <Network size={13} /> Graphe
          </button>
        </div>

        <select
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white text-slate-600"
        >
          <option value="all">Tous les types</option>
          <option value="functional">Fonctionnel</option>
          <option value="technical">Technique</option>
        </select>

        <select
          value={filterLevel}
          onChange={e => setFilterLevel(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white text-slate-600"
        >
          <option value="all">Intra + Inter</option>
          <option value="intra_epic">Intra-epic seulement</option>
          <option value="inter_epic">Inter-epic seulement</option>
        </select>

        {/* Slider profondeur — visible uniquement en mode graphe avec focus actif */}
        {view === "graph" && focusedId && (
          <label className="flex items-center gap-1.5 text-xs text-slate-600 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1">
            Profondeur :
            <input
              type="range"
              min={1}
              max={4}
              value={depth}
              onChange={e => setDepth(Number(e.target.value))}
              className="w-20 accent-amber-500"
            />
            <span className="font-mono text-amber-700 w-3">{depth}</span>
          </label>
        )}

        <span className="text-xs text-slate-400 ml-auto">
          {filtered.length} / {totalDeps} affiché(s)
        </span>
      </div>

      {/* Contenu */}
      {deps.length === 0 ? (
        <div className="text-center py-10 text-slate-400 text-sm">
          <GitBranch size={32} className="mx-auto mb-2 opacity-30" />
          Aucune dépendance détectée entre les stories.
        </div>
      ) : view === "graph" ? (
        <>
          {!focusedId && (
            <div className="text-[11px] text-slate-500 px-1">
              💡 Cliquez sur une story pour voir uniquement ses prédécesseurs et successeurs.
              Cliquez sur le fond pour réinitialiser.
            </div>
          )}
          <GraphView
            deps={filtered}
            storyMap={storyMap}
            epicColorMap={epicColorMap}
            epicIdxMap={epicIdxMap}
            focusedId={focusedId}
            setFocusedId={setFocusedId}
            depth={depth}
            onToggleFullscreen={() => setIsFullscreen(true)}
          />
        </>
      ) : (
        <div className="space-y-2">
          {filtered.map((dep, i) => (
            <DepCard
              key={i}
              dep={dep}
              storyMap={storyMap}
              epicColorMap={epicColorMap}
            />
          ))}
        </div>
      )}

      {/* Modal plein écran */}
      {isFullscreen && (
        <div className="fixed inset-0 z-50 bg-slate-900/80 backdrop-blur-sm p-4 sm:p-6 flex flex-col">
          <div className="flex items-center justify-between mb-3 text-white">
            <div className="flex items-center gap-2">
              <Network size={18} />
              <span className="font-display font-semibold">Dépendances Stories — Vue plein écran</span>
              <span className="text-xs text-slate-300 ml-2">{filtered.length} dépendance(s)</span>
            </div>
            <button
              onClick={() => setIsFullscreen(false)}
              className="flex items-center gap-1.5 bg-white/10 hover:bg-white/20 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <X size={13} /> Fermer (Échap)
            </button>
          </div>
          <div className="flex-1 min-h-0">
            <GraphView
              deps={filtered}
              storyMap={storyMap}
              epicColorMap={epicColorMap}
              epicIdxMap={epicIdxMap}
              focusedId={focusedId}
              setFocusedId={setFocusedId}
              depth={depth}
              fullscreen
            />
          </div>
        </div>
      )}
    </div>
  );
}
