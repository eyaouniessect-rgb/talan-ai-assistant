import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import html2canvas from "html2canvas";
import {
  ReactFlow, Background, Controls, MiniMap,
  MarkerType, useNodesState, useEdgesState,
  Handle, Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import {
  List, Network, Lock, ArrowRight, GitBranch,
  Maximize2, X, Star, RotateCcw, Download, Image,
  Pencil, Check, Plus, AlertTriangle,
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
      <Handle type="target" position={Position.Left} className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />
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
      <Handle type="source" position={Position.Right} className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />
    </>
  );
}

// ── Nœuds virtuels Début / Fin ─────────────────────────────
function MarkerNode({ data }) {
  const isStart = data.role === "start";
  return (
    <>
      {!isStart && <Handle type="target" position={Position.Left} className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />}
      <div
        className={clsx(
          "rounded-full shadow-md flex items-center justify-center font-display font-semibold text-white",
          isStart ? "bg-emerald-500" : "bg-rose-500"
        )}
        style={{ width: MARKER_SIZE, height: MARKER_SIZE }}
      >
        <span className="text-sm">{isStart ? "▶ Début" : "■ Fin"}</span>
      </div>
      {isStart && <Handle type="source" position={Position.Right} className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />}
    </>
  );
}

const nodeTypes = { story: StoryNode, marker: MarkerNode, lane: LaneNode };

// ══════════════════════════════════════════════════════════════
// Dimensions & couleurs de couloirs
// ══════════════════════════════════════════════════════════════
const NODE_W = 280, NODE_H = 160;
const MARKER_SIZE = 90;
const COL_W   = NODE_W + 130;   // largeur d'une colonne (story + espacement)
const ROW_H   = NODE_H + 60;    // hauteur d'une ligne (story + espacement)
const LANE_PAD_X = 24;
const LANE_PAD_Y = 44;

const LANE_PALETTE = [
  { bg: "rgba(224,231,255,0.55)", border: "#818cf8", text: "#4338ca" },
  { bg: "rgba(220,252,231,0.55)", border: "#4ade80", text: "#166534" },
  { bg: "rgba(254,243,199,0.55)", border: "#fbbf24", text: "#92400e" },
  { bg: "rgba(224,242,254,0.55)", border: "#38bdf8", text: "#075985" },
  { bg: "rgba(252,231,243,0.55)", border: "#f472b6", text: "#9d174d" },
  { bg: "rgba(237,233,254,0.55)", border: "#a78bfa", text: "#5b21b6" },
  { bg: "rgba(209,250,229,0.55)", border: "#34d399", text: "#065f46" },
  { bg: "rgba(255,237,213,0.55)", border: "#fb923c", text: "#9a3412" },
];

// ══════════════════════════════════════════════════════════════
// Rang topologique — BFS depuis les racines (in-degree 0)
// Rang = longueur du plus long chemin depuis une racine
// IMPORTANT : on ignore les arcs dont les endpoints ne sont pas
// dans storyIds (sinon un filtre par epic peut bloquer la BFS).
// ══════════════════════════════════════════════════════════════
function computeRanks(reducedDeps, storyIds) {
  const idSet = new Set(storyIds);
  const adj = {};
  const inDeg = {};
  for (const id of storyIds) inDeg[id] = 0;
  for (const d of reducedDeps) {
    const u = String(d.from_story_id), v = String(d.to_story_id);
    if (!idSet.has(u) || !idSet.has(v)) continue;  // ignore arcs avec endpoints externes
    (adj[u] ??= []).push(v);
    inDeg[v] = (inDeg[v] || 0) + 1;
  }
  const rank = {};
  const queue = storyIds.filter(id => inDeg[id] === 0);
  for (const id of queue) rank[id] = 0;
  let qi = 0;
  while (qi < queue.length) {
    const u = queue[qi++];
    for (const v of (adj[u] ?? [])) {
      rank[v] = Math.max(rank[v] ?? 0, (rank[u] ?? 0) + 1);
      if (--inDeg[v] === 0) queue.push(v);
    }
  }
  // Fallback : stories non atteintes par la BFS (cycles résiduels)
  // → rang basé sur le max des prédécesseurs déjà rangés + 1
  let progressed = true;
  while (progressed) {
    progressed = false;
    for (const id of storyIds) {
      if (rank[id] != null) continue;
      // chercher des prédécesseurs déjà rangés
      const preds = [];
      for (const d of reducedDeps) {
        const u = String(d.from_story_id), v = String(d.to_story_id);
        if (v === id && idSet.has(u) && rank[u] != null) preds.push(rank[u]);
      }
      if (preds.length) {
        rank[id] = Math.max(...preds) + 1;
        progressed = true;
      }
    }
  }
  // Stories toujours sans rang (cycles complets) → rang 0
  for (const id of storyIds) if (rank[id] == null) rank[id] = 0;
  return rank;
}

// ══════════════════════════════════════════════════════════════
// Nœud de fond couloir (LaneNode) — rendu derrière les stories
// ══════════════════════════════════════════════════════════════
function LaneNode({ data }) {
  const palette = LANE_PALETTE[data.rankIdx % LANE_PALETTE.length];
  return (
    <div
      className="rounded-2xl flex flex-col pointer-events-none select-none"
      style={{
        width:   data.width,
        height:  data.height,
        background: palette.bg,
        border: `2px dashed ${palette.border}`,
      }}
    >
      <span
        className="px-3 pt-2 text-[11px] font-bold uppercase tracking-widest"
        style={{ color: palette.text }}
      >
        Vague {data.rankIdx + 1}
        <span className="ml-2 font-normal normal-case tracking-normal opacity-70">
          · {data.count} tâche{data.count > 1 ? "s" : ""} en parallèle
        </span>
      </span>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Layout par rang — positionne les nœuds colonne par colonne
// ══════════════════════════════════════════════════════════════
function getLayoutedByRank(storyNodes, markerNodes, laneNodes, edges, ranks, maxRank) {
  // Index de colonne : Start=-1(idx=0), rank0(idx=1), …, rankN(idx=N+1), End(idx=N+2)
  const colX = (rankIdx) => (rankIdx + 1) * COL_W;  // +1 pour laisser place au Start

  // Grouper les story nodes par rang
  const byRank = {};
  for (const n of storyNodes) {
    const r = ranks[n.id] ?? 0;
    (byRank[r] ??= []).push(n);
  }

  // Positionner stories
  const posStories = storyNodes.map(n => {
    const r = ranks[n.id] ?? 0;
    const col = byRank[r];
    const idx = col.indexOf(n);
    const colH = col.length * ROW_H;
    return {
      ...n,
      position: {
        x: colX(r),
        y: idx * ROW_H - colH / 2 + ROW_H / 2 - NODE_H / 2,
      },
      zIndex: 10,
    };
  });

  // Positionner Start / End markers
  const maxColH = Math.max(...Object.values(byRank).map(c => c.length)) * ROW_H;
  const posMarkers = markerNodes.map(n => ({
    ...n,
    position: {
      x: n.id === "__start__"
        ? colX(-1) + (COL_W - MARKER_SIZE) / 2
        : colX(maxRank + 1) + (COL_W - MARKER_SIZE) / 2,
      y: -MARKER_SIZE / 2,
    },
    zIndex: 10,
  }));

  // Positionner les lanes (fond)
  const posLanes = laneNodes.map(n => {
    const r    = n.data.rank;
    const col  = byRank[r] ?? [];
    const colH = col.length * ROW_H;
    return {
      ...n,
      position: {
        x: colX(r) - LANE_PAD_X,
        y: -(colH / 2) - LANE_PAD_Y + ROW_H / 2 - NODE_H / 2,
      },
      zIndex: 0,
      selectable: false,
      draggable:  false,
    };
  });

  return { nodes: [...posLanes, ...posStories, ...posMarkers], edges };
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
// Réduction transitive — supprime les arcs redondants A→C
// quand un chemin A→...→C existe déjà via d'autres arcs.
// ══════════════════════════════════════════════════════════════
function transitiveReduction(deps) {
  // Graphe d'adjacence : id → Set d'ids successeurs
  const adj = {};
  for (const d of deps) (adj[d.from_story_id] ??= new Set()).add(d.to_story_id);

  // DFS : v est-il atteignable depuis start ?  (visited évite les cycles)
  function canReach(start, target, visited = new Set()) {
    if (visited.has(start)) return false;
    visited.add(start);
    for (const next of (adj[start] ?? [])) {
      if (next === target || canReach(next, target, visited)) return true;
    }
    return false;
  }

  return deps.filter(d => {
    const { from_story_id: u, to_story_id: v } = d;
    // Arc u→v est transitif s'il existe un voisin intermédiaire w de u (w≠v)
    // depuis lequel v est atteignable.
    for (const w of (adj[u] ?? [])) {
      if (w !== v && canReach(w, v)) return false;
    }
    return true;
  });
}

// ══════════════════════════════════════════════════════════════
function buildGraph({ stories, deps, epicColorMap, epicIdxMap, focusedId, depth }) {
  // 1. Réduction transitive
  const reducedDeps = transitiveReduction(deps);

  // 2. Rangs topologiques (longest-path depuis les racines)
  const storyIds = stories.map(s => String(s.db_id));
  const ranks    = computeRanks(reducedDeps, storyIds);
  const maxRank  = Math.max(0, ...Object.values(ranks));

  // 3. Degrés in/out pour pivots et arcs virtuels
  const inDeg = {}, outDeg = {};
  for (const d of reducedDeps) {
    outDeg[d.from_story_id] = (outDeg[d.from_story_id] || 0) + 1;
    inDeg[d.to_story_id]    = (inDeg[d.to_story_id]    || 0) + 1;
  }

  const visible = focusedId ? computeVisibleSet(focusedId, reducedDeps, depth) : null;

  // 4. Story nodes
  const storyNodes = stories.map(s => {
    const epicColor    = epicColorMap[s.epic_id] ?? EPIC_COLORS[0];
    const connectivity = (inDeg[s.db_id] || 0) + (outDeg[s.db_id] || 0);
    const isPivot      = connectivity >= PIVOT_THRESHOLD;
    const dim          = visible ? !visible.has(s.db_id) : false;
    const isFocus      = String(s.db_id) === focusedId;
    return {
      id:       String(s.db_id),
      type:     "story",
      position: { x: 0, y: 0 },
      data: { id: s.db_id, title: s.title, epicColor: epicColor.nodeStroke,
              epicBg: epicColor.node, epicIdx: epicIdxMap[s.epic_id] ?? 0,
              connectivity, isPivot, isFocus, dim },
    };
  });

  // 5. Arcs réels
  const realEdges = reducedDeps.map((d, i) => {
    const dim       = visible && (!visible.has(d.from_story_id) || !visible.has(d.to_story_id));
    const edgeColor = DEP_TYPE_STYLE[d.dependency_type]?.edge ?? "#94a3b8";
    return {
      id: `e${i}`, source: String(d.from_story_id), target: String(d.to_story_id),
      type: "default", label: d.relation_type, animated: !dim,
      style:        { stroke: dim ? "#cbd5e1" : edgeColor, strokeWidth: dim ? 1 : 2, opacity: dim ? 0.3 : 1 },
      labelStyle:   { fontSize: 10, fill: dim ? "#94a3b8" : edgeColor, fontWeight: 600 },
      labelBgStyle: { fill: "#fff", fillOpacity: dim ? 0.4 : 0.85 },
      markerEnd:    { type: MarkerType.ArrowClosed, color: dim ? "#cbd5e1" : edgeColor },
    };
  });

  // 6. Nœuds virtuels Début / Fin
  const startNode = { id: "__start__", type: "marker", position: { x: 0, y: 0 }, data: { role: "start" } };
  const endNode   = { id: "__end__",   type: "marker", position: { x: 0, y: 0 }, data: { role: "end" } };

  const vStyle = { stroke: "#94a3b8", strokeWidth: 1.5, strokeDasharray: "4 4" };
  const startEdges = stories.filter(s => !inDeg[s.db_id]).map(s => ({
    id: `start-${s.db_id}`, source: "__start__", target: String(s.db_id),
    type: "default", animated: false, style: vStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
  }));
  const endEdges = stories.filter(s => !outDeg[s.db_id]).map(s => ({
    id: `end-${s.db_id}`, source: String(s.db_id), target: "__end__",
    type: "default", animated: false, style: vStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
  }));

  // 7. Lane (couloir) nodes — un par rang, sauf en mode focus
  const byRank = {};
  for (const s of stories) {
    const r = ranks[String(s.db_id)] ?? 0;
    (byRank[r] ??= []).push(s);
  }
  const laneNodes = focusedId ? [] : Object.entries(byRank).map(([r, col]) => {
    const ri      = Number(r);
    const colH    = col.length * ROW_H;
    const palette = LANE_PALETTE[ri % LANE_PALETTE.length];
    return {
      id:       `lane-${ri}`,
      type:     "lane",
      position: { x: 0, y: 0 },
      data:     { rank: ri, rankIdx: ri, count: col.length,
                  width: NODE_W + LANE_PAD_X * 2, height: colH + LANE_PAD_Y * 2,
                  palette },
    };
  });

  return getLayoutedByRank(
    storyNodes,
    focusedId ? [] : [startNode, endNode],
    laneNodes,
    [...startEdges, ...realEdges, ...endEdges],
    ranks,
    maxRank,
  );
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
  stories, deps, epicColorMap, epicIdxMap,
  fullscreen = false, onToggleFullscreen,
  focusedId, setFocusedId, depth,
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const containerRef = useRef(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    const { nodes: n, edges: e } = buildGraph({
      stories, deps, epicColorMap, epicIdxMap, focusedId, depth,
    });
    setNodes(n);
    setEdges(e);
  }, [stories, deps, epicColorMap, epicIdxMap, focusedId, depth, setNodes, setEdges]);

  const onNodeClick = useCallback((_evt, node) => {
    if (node.id === "__start__" || node.id === "__end__") return;
    setFocusedId(prev => prev === node.id ? null : node.id);
  }, [setFocusedId]);

  const onPaneClick = useCallback(() => {
    setFocusedId(null);
  }, [setFocusedId]);

  const captureCanvas = async () => {
    if (!containerRef.current) return null;
    return html2canvas(containerRef.current, {
      backgroundColor: "#f8fafc",
      scale: 2,
      useCORS: true,
      logging: false,
    });
  };

  const exportPNG = async () => {
    setExporting(true);
    try {
      const canvas = await captureCanvas();
      const link = document.createElement("a");
      link.download = "graphe-dependances.png";
      link.href = canvas.toDataURL("image/png");
      link.click();
    } finally {
      setExporting(false);
    }
  };

  const exportGraphPDF = async () => {
    setExporting(true);
    try {
      const canvas = await captureCanvas();
      const imgData = canvas.toDataURL("image/png");
      const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
      const pageW = doc.internal.pageSize.getWidth();
      const pageH = doc.internal.pageSize.getHeight();
      const margin = 10;
      const maxW = pageW - margin * 2;
      const maxH = pageH - margin * 2 - 12;
      const ratio = canvas.width / canvas.height;
      const imgW = Math.min(maxW, maxH * ratio);
      const imgH = imgW / ratio;
      doc.setFontSize(11);
      doc.text("Graphe des dépendances — Stories", margin, margin + 4);
      doc.setFontSize(7);
      doc.setTextColor(120);
      doc.text(
        `Exporté le ${new Date().toLocaleDateString("fr-FR")} · ${stories.length} stories · ${deps.length} dépendances`,
        margin, margin + 9,
      );
      doc.addImage(imgData, "PNG", margin, margin + 12, imgW, imgH);
      doc.save("graphe-dependances.pdf");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className={clsx(
      "relative rounded-xl border border-slate-200 overflow-hidden bg-slate-50",
      fullscreen ? "h-full w-full" : "h-[600px]"
    )} ref={containerRef}>
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

      <div className="absolute top-3 right-3 z-10 flex items-center gap-1.5">
        <button
          onClick={exportPNG}
          disabled={exporting}
          className="flex items-center gap-1 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-sm transition-colors disabled:opacity-50"
          title="Exporter en PNG"
        >
          <Image size={13} /> PNG
        </button>
        <button
          onClick={exportGraphPDF}
          disabled={exporting}
          className="flex items-center gap-1 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-sm transition-colors disabled:opacity-50"
          title="Exporter en PDF"
        >
          <Download size={13} /> PDF
        </button>
        {onToggleFullscreen && (
          <button
            onClick={onToggleFullscreen}
            className="flex items-center gap-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-sm transition-colors"
            title={fullscreen ? "Quitter le plein écran (Échap)" : "Plein écran"}
          >
            {fullscreen ? <X size={13} /> : <Maximize2 size={13} />}
            {fullscreen ? "Fermer" : "Plein écran"}
          </button>
        )}
      </div>
      {exporting && (
        <div className="absolute inset-0 z-20 bg-white/60 flex items-center justify-center">
          <span className="text-xs text-slate-600 font-medium">Export en cours…</span>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Table view — Activity / Predecessors (modèle PMBOK)
// ══════════════════════════════════════════════════════════════
// Détecte si l'ajout d'un arc fromId → toId créerait un cycle dans `deps`.
function wouldCreateCycle(deps, fromId, toId) {
  if (fromId === toId) return true;
  const adj = {};
  for (const d of deps) (adj[d.from_story_id] ??= new Set()).add(d.to_story_id);
  // Cycle si toId peut atteindre fromId via le graphe existant
  const visited = new Set();
  const dfs = (n) => {
    if (n === fromId) return true;
    if (visited.has(n)) return false;
    visited.add(n);
    for (const next of (adj[n] ?? [])) if (dfs(next)) return true;
    return false;
  };
  return dfs(toId);
}

function TableView({
  stories, allStories, deps, allDeps, aiDeps, isModified,
  onUpdateDeps, epicColorMap, epicIdxMap,
}) {
  const [editing, setEditing] = useState(false);
  // Copie de travail des dépendances pendant l'édition
  const [draft, setDraft] = useState(allDeps);
  const [error, setError] = useState(null);

  // Resync quand les déps externes changent (et qu'on n'est pas en train d'éditer)
  useEffect(() => { if (!editing) setDraft(allDeps); }, [allDeps, editing]);

  // Le tableau affiche `draft` en mode édition, sinon les déps filtrées
  const displayDeps = editing ? draft : deps;

  const predMap = useMemo(() => {
    const m = {};
    for (const d of displayDeps) (m[d.to_story_id] ??= []).push(d);
    return m;
  }, [displayDeps]);

  const startEditing = () => { setDraft(allDeps); setEditing(true); setError(null); };
  const cancel       = () => { setDraft(allDeps); setEditing(false); setError(null); };
  const validate     = () => { onUpdateDeps(draft); setEditing(false); setError(null); };
  const resetToAI    = () => { setDraft(aiDeps); setError(null); };

  const removePred = (storyId, fromStoryId) => {
    setDraft(prev => prev.filter(d =>
      !(d.to_story_id === storyId && d.from_story_id === fromStoryId)
    ));
    setError(null);
  };

  const addPred = (storyId, fromStoryId) => {
    if (!fromStoryId) return;
    fromStoryId = Number(fromStoryId);
    // Doublon ?
    if (draft.some(d => d.to_story_id === storyId && d.from_story_id === fromStoryId)) {
      setError(`#${fromStoryId} est déjà prédécesseur de #${storyId}`);
      return;
    }
    // Cycle ?
    if (wouldCreateCycle(draft, fromStoryId, storyId)) {
      setError(`Impossible : #${fromStoryId} → #${storyId} créerait un cycle`);
      return;
    }
    const story     = allStories.find(s => s.db_id === storyId);
    const fromStory = allStories.find(s => s.db_id === fromStoryId);
    setDraft(prev => [...prev, {
      from_story_id:   fromStoryId,
      to_story_id:     storyId,
      relation_type:   "FS",
      dependency_type: "functional",
      reason:          "Ajouté manuellement par l'utilisateur",
      level: story?.epic_id === fromStory?.epic_id ? "intra_epic" : "inter_epic",
      _user_added:     true,
    }]);
    setError(null);
  };

  const exportPDF = () => {
    const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
    doc.setFontSize(14);
    doc.text("Tableau des dépendances — Stories", 14, 14);
    doc.setFontSize(8);
    doc.setTextColor(120);
    doc.text(`Exporté le ${new Date().toLocaleDateString("fr-FR")} · ${stories.length} stories · ${displayDeps.length} dépendances`, 14, 20);
    autoTable(doc, {
      startY: 26,
      head: [["ID", "Story", "Epic", "Prédécesseurs", "Types"]],
      body: stories.map(s => {
        const preds = predMap[s.db_id] ?? [];
        const epicIdx = epicIdxMap[s.epic_id] ?? 0;
        return [
          `#${s.db_id}`, s.title, `E${epicIdx + 1}`,
          preds.length === 0 ? "— (peut démarrer)" : preds.map(p => `#${p.from_story_id} ${p.relation_type}`).join(", "),
          preds.length === 0 ? "" : [...new Set(preds.map(p => p.dependency_type))].join(", "),
        ];
      }),
      styles: { fontSize: 8, cellPadding: 3 },
      headStyles: { fillColor: [30, 41, 59], textColor: 255, fontStyle: "bold" },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      columnStyles: { 0: { cellWidth: 14 }, 1: { cellWidth: 90 }, 2: { cellWidth: 14 }, 3: { cellWidth: 90 }, 4: { cellWidth: 28 } },
    });
    doc.save("dependances-stories.pdf");
  };

  return (
    <div className="space-y-2">
      {/* Barre d'actions */}
      <div className="flex items-center gap-2 flex-wrap">
        {isModified && !editing && (
          <span className="text-[11px] px-2 py-1 rounded-full bg-amber-100 text-amber-700 font-medium flex items-center gap-1">
            <AlertTriangle size={11} /> Dépendances modifiées manuellement
          </span>
        )}
        {editing && (
          <span className="text-[11px] px-2 py-1 rounded-full bg-blue-100 text-blue-700 font-medium">
            Mode édition · les modifications n'affectent le graphe qu'après validation
          </span>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          {!editing ? (
            <>
              <button
                onClick={startEditing}
                className="flex items-center gap-1.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium px-3 py-1.5 rounded-lg shadow-sm"
              >
                <Pencil size={13} /> Modifier
              </button>
              <button
                onClick={exportPDF}
                className="flex items-center gap-1.5 bg-navy text-white text-xs font-medium px-3 py-1.5 rounded-lg hover:bg-navy/90 shadow-sm"
              >
                <Download size={13} /> PDF
              </button>
            </>
          ) : (
            <>
              <button
                onClick={resetToAI}
                title="Restaurer les dépendances générées par l'agent"
                className="flex items-center gap-1.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-600 text-xs font-medium px-3 py-1.5 rounded-lg shadow-sm"
              >
                <RotateCcw size={13} /> Restaurer IA
              </button>
              <button
                onClick={cancel}
                className="flex items-center gap-1.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium px-3 py-1.5 rounded-lg shadow-sm"
              >
                <X size={13} /> Annuler
              </button>
              <button
                onClick={validate}
                className="flex items-center gap-1.5 bg-emerald-600 text-white text-xs font-medium px-3 py-1.5 rounded-lg hover:bg-emerald-700 shadow-sm"
              >
                <Check size={13} /> Valider
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 flex items-center gap-2">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      <div className={clsx(
        "rounded-xl border overflow-hidden bg-white transition-colors",
        editing ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200",
      )}>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-3 py-2 font-semibold w-16">ID</th>
              <th className="text-left px-3 py-2 font-semibold">Story</th>
              <th className="text-left px-3 py-2 font-semibold w-24">Epic</th>
              <th className="text-left px-3 py-2 font-semibold">Prédécesseurs</th>
            </tr>
          </thead>
          <tbody>
            {stories.map(s => {
              const preds = predMap[s.db_id] ?? [];
              const epicColor = epicColorMap[s.epic_id] ?? EPIC_COLORS[0];
              const epicIdx   = epicIdxMap[s.epic_id] ?? 0;
              const predIds   = new Set(preds.map(p => p.from_story_id));
              const candidates = allStories.filter(x =>
                x.db_id !== s.db_id && !predIds.has(x.db_id)
              );
              return (
                <tr key={s.db_id} className="border-t border-slate-100 hover:bg-slate-50/60 align-top">
                  <td className="px-3 py-2 font-mono text-xs text-slate-500">#{s.db_id}</td>
                  <td className="px-3 py-2 text-slate-800">{s.title}</td>
                  <td className="px-3 py-2">
                    <span className={clsx("text-[11px] px-1.5 py-0.5 rounded-full font-medium", epicColor.bg, epicColor.text)}>
                      E{epicIdx + 1}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1 items-center">
                      {preds.length === 0 && !editing && (
                        <span className="text-slate-400 italic text-xs">— (peut démarrer)</span>
                      )}
                      {preds.map((p, i) => {
                        const fromStory = allStories.find(x => x.db_id === p.from_story_id);
                        const style = DEP_TYPE_STYLE[p.dependency_type] ?? DEP_TYPE_STYLE.functional;
                        return (
                          <span
                            key={i}
                            title={`${fromStory?.title ?? ""} — ${REL_TYPE_LABEL[p.relation_type] ?? p.relation_type} (${style.label})${p._user_added ? " · ajouté manuellement" : ""}`}
                            className={clsx(
                              "text-[11px] px-1.5 py-0.5 rounded-md border font-mono inline-flex items-center gap-1",
                              style.color,
                              p._user_added && "ring-1 ring-amber-400",
                            )}
                          >
                            #{p.from_story_id}
                            <span className="font-sans font-semibold">{p.relation_type}</span>
                            {editing && (
                              <button
                                onClick={() => removePred(s.db_id, p.from_story_id)}
                                className="hover:bg-rose-100 rounded-full p-0.5 -mr-1"
                                title="Retirer ce prédécesseur"
                              >
                                <X size={10} />
                              </button>
                            )}
                          </span>
                        );
                      })}
                      {editing && (
                        <select
                          value=""
                          onChange={e => addPred(s.db_id, e.target.value)}
                          className="text-[11px] border border-slate-300 rounded-md px-1.5 py-0.5 bg-white text-slate-600 max-w-[180px]"
                        >
                          <option value="">+ Ajouter prédécesseur…</option>
                          {candidates.map(c => (
                            <option key={c.db_id} value={c.db_id}>
                              #{c.db_id} {c.title.slice(0, 40)}{c.title.length > 40 ? "…" : ""}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
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

  // Déps initiales venant de l'agent
  const aiDeps = useMemo(
    () => Array.isArray(aiOutput) ? aiOutput : (aiOutput?.story_dependencies ?? []),
    [aiOutput],
  );
  // Déps "vivantes" — éditables par l'utilisateur (Human-in-the-Loop)
  const [deps, setDeps] = useState(aiDeps);
  useEffect(() => { setDeps(aiDeps); }, [aiDeps]);
  const isModified = deps !== aiDeps;

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

  // Stories visibles : toutes celles du projet, filtrées par epic sélectionné si actif
  const visibleStories = useMemo(() => {
    if (selectedEpics.size === 0) return stories;
    return stories.filter(s => selectedEpics.has(s.epic_id));
  }, [stories, selectedEpics]);

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
          <button
            onClick={() => setView("table")}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
              view === "table" ? "bg-navy text-white" : "bg-white text-slate-600 hover:bg-slate-50"
            )}
          >
            <GitBranch size={13} /> Tableau
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
              Cliquez sur le fond pour réinitialiser. Les nœuds <strong>Début</strong> et <strong>Fin</strong> sont virtuels.
            </div>
          )}
          <GraphView
            stories={visibleStories}
            deps={filtered}
            epicColorMap={epicColorMap}
            epicIdxMap={epicIdxMap}
            focusedId={focusedId}
            setFocusedId={setFocusedId}
            depth={depth}
            onToggleFullscreen={() => setIsFullscreen(true)}
          />
        </>
      ) : view === "table" ? (
        <TableView
          stories={visibleStories}
          allStories={stories}
          deps={filtered}
          allDeps={deps}
          aiDeps={aiDeps}
          isModified={isModified}
          onUpdateDeps={setDeps}
          epicColorMap={epicColorMap}
          epicIdxMap={epicIdxMap}
        />
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
              stories={visibleStories}
              deps={filtered}
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
