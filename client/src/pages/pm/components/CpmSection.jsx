import { useState, useEffect, useCallback, useRef } from "react";
import html2canvas from "html2canvas";
import {
  ReactFlow, Background, Controls, MiniMap,
  MarkerType, useNodesState, useEdgesState,
  Handle, Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import jsPDF from "jspdf";
import { Maximize2, X, Download, Image, Star, RotateCcw } from "lucide-react";
import clsx from "clsx";
import { getProjectStories, getProjectEpics, getStoryDependencies } from "../../../api/pipeline";

// ── Mêmes constantes que StoryDepsSection ────────────────────
const EPIC_COLORS = [
  { bg: "bg-indigo-100",  border: "border-indigo-400",  node: "#e0e7ff", nodeStroke: "#6366f1" },
  { bg: "bg-violet-100",  border: "border-violet-400",  node: "#ede9fe", nodeStroke: "#7c3aed" },
  { bg: "bg-sky-100",     border: "border-sky-400",     node: "#e0f2fe", nodeStroke: "#0284c7" },
  { bg: "bg-emerald-100", border: "border-emerald-400", node: "#d1fae5", nodeStroke: "#059669" },
  { bg: "bg-amber-100",   border: "border-amber-400",   node: "#fef3c7", nodeStroke: "#d97706" },
  { bg: "bg-rose-100",    border: "border-rose-400",    node: "#ffe4e6", nodeStroke: "#e11d48" },
  { bg: "bg-cyan-100",    border: "border-cyan-400",    node: "#cffafe", nodeStroke: "#0891b2" },
  { bg: "bg-orange-100",  border: "border-orange-400",  node: "#ffedd5", nodeStroke: "#ea580c" },
];

const NODE_W      = 280;
const NODE_H      = 200;   // plus grand que StoryDepsSection pour le panneau CPM
const MARKER_SIZE = 90;
const COL_W       = NODE_W + 130;
const ROW_H       = NODE_H + 60;
const LANE_PAD_X  = 24;
const LANE_PAD_Y  = 44;
const PIVOT_THRESHOLD = 4;

const LANE_PALETTE = [
  { bg: "rgba(224,231,255,0.55)", border: "#818cf8", text: "#4338ca" },
  { bg: "rgba(220,252,231,0.55)", border: "#4ade80", text: "#166534" },
  { bg: "rgba(254,243,199,0.55)", border: "#fbbf24", text: "#92400e" },
  { bg: "rgba(224,242,254,0.55)", border: "#38bdf8", text: "#075985" },
  { bg: "rgba(252,231,243,0.55)", border: "#f472b6", text: "#9d174d" },
  { bg: "rgba(237,233,254,0.55)", border: "#a78bfa", text: "#5b21b6" },
];

// ══════════════════════════════════════════════════════════════
// Custom node — même design que StoryNode + panneau CPM en bas
// ══════════════════════════════════════════════════════════════
function CpmStoryNode({ data }) {
  const {
    id, title, epicColor, epicBg, epicIdx,
    isPivot, connectivity,
    isCritical, dim, isFocus,
    es, ef, ls, lf, slack, duration,
  } = data;

  const fmt = (v) => (v == null ? "—" : Number(v).toFixed(0));

  const borderStyle = isFocus
    ? { border: "3px solid #f59e0b", boxShadow: "0 0 0 4px rgba(245,158,11,0.3)" }
    : isCritical
    ? { border: "3px solid #ef4444", boxShadow: "0 0 0 3px rgba(239,68,68,0.2)" }
    : { border: `2px solid ${epicColor}` };

  return (
    <>
      <Handle type="target" position={Position.Left}
        className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />

      <div
        className="rounded-lg shadow-md overflow-hidden transition-all"
        style={{ width: NODE_W, background: epicBg, opacity: dim ? 0.18 : 1, ...borderStyle }}
      >
        {/* Header epic — identique à StoryNode */}
        <div
          className="px-2.5 py-1.5 flex items-center gap-2 border-b"
          style={{ background: epicColor, borderColor: epicColor }}
        >
          <span className="text-[11px] font-mono font-bold text-white">
            #{data.userId ?? id}
          </span>
          <span className="text-[10px] font-semibold text-white/90 px-1.5 py-0.5 rounded bg-white/20">
            E{epicIdx + 1}
          </span>
          {isCritical && (
            <span className="ml-1 text-[10px] font-bold text-white bg-red-500 px-1.5 py-0.5 rounded">
              CRITIQUE
            </span>
          )}
          {isPivot && (
            <span className="ml-auto" title={`${connectivity} liens — story pivot`}>
              <Star size={13} className="text-yellow-200 fill-yellow-300" />
            </span>
          )}
        </div>

        {/* Titre — identique à StoryNode */}
        <div className="px-2.5 py-2 text-[12px] leading-snug font-medium text-slate-800">
          {title}
        </div>

        {/* Panneau CPM ─────────────────────────────────────── */}
        <div
          className="border-t mx-2 mb-2 rounded-md overflow-hidden"
          style={{
            borderColor: isCritical ? "#fca5a5" : "#e2e8f0",
            background: isCritical ? "#fef2f2" : "#f8fafc",
          }}
        >
          {/* ES | EF */}
          <div className="grid grid-cols-2 divide-x"
            style={{ borderBottom: `1px solid ${isCritical ? "#fca5a5" : "#e2e8f0"}`,
                     divideColor: isCritical ? "#fca5a5" : "#e2e8f0" }}>
            <CpmCell label="ES" value={fmt(es)} critical={isCritical} />
            <CpmCell label="EF" value={fmt(ef)} critical={isCritical} />
          </div>

          {/* Durée centrale */}
          <div
            className="text-center py-0.5 text-[10px] font-semibold"
            style={{ color: isCritical ? "#b91c1c" : "#64748b" }}
          >
            durée : {duration ?? "?"}sp
          </div>

          {/* LS | LF */}
          <div className="grid grid-cols-2 divide-x"
            style={{ borderTop: `1px solid ${isCritical ? "#fca5a5" : "#e2e8f0"}`,
                     borderBottom: `1px solid ${isCritical ? "#fca5a5" : "#e2e8f0"}` }}>
            <CpmCell label="LS" value={fmt(ls)} critical={isCritical} />
            <CpmCell label="LF" value={fmt(lf)} critical={isCritical} />
          </div>

          {/* Marge */}
          <div
            className="text-center py-0.5 text-[10px] font-bold"
            style={{ color: isCritical ? "#b91c1c" : "#475569" }}
          >
            marge = {fmt(slack)}
          </div>
        </div>
      </div>

      <Handle type="source" position={Position.Right}
        className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />
    </>
  );
}

function CpmCell({ label, value, critical }) {
  return (
    <div className="flex flex-col items-center py-1">
      <span className="text-[9px] uppercase tracking-wide"
        style={{ color: critical ? "#ef4444" : "#94a3b8" }}>
        {label}
      </span>
      <span className="font-bold text-xs"
        style={{ color: critical ? "#b91c1c" : "#1e293b" }}>
        {value}
      </span>
    </div>
  );
}

function MarkerNode({ data }) {
  const isStart = data.role === "start";
  return (
    <>
      {!isStart && <Handle type="target" position={Position.Left}
        className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />}
      <div
        className={clsx(
          "rounded-full shadow-md flex items-center justify-center font-display font-semibold text-white",
          isStart ? "bg-emerald-500" : "bg-rose-500"
        )}
        style={{ width: MARKER_SIZE, height: MARKER_SIZE }}
      >
        <span className="text-sm">{isStart ? "▶ Début" : "■ Fin"}</span>
      </div>
      {isStart && <Handle type="source" position={Position.Right}
        className="!bg-slate-400 !w-2.5 !h-2.5 !border-0" />}
    </>
  );
}

function LaneNode({ data }) {
  const palette = LANE_PALETTE[data.rankIdx % LANE_PALETTE.length];
  return (
    <div className="rounded-2xl flex flex-col pointer-events-none select-none"
      style={{ width: data.width, height: data.height,
               background: palette.bg, border: `2px dashed ${palette.border}` }}>
      <span className="px-3 pt-2 text-[11px] font-bold uppercase tracking-widest"
        style={{ color: palette.text }}>
        Vague {data.rankIdx + 1}
        <span className="ml-2 font-normal normal-case tracking-normal opacity-70">
          · {data.count} tâche{data.count > 1 ? "s" : ""}
        </span>
      </span>
    </div>
  );
}

const nodeTypes = { story: CpmStoryNode, marker: MarkerNode, lane: LaneNode };

// ── Fonctions de layout (identiques à StoryDepsSection) ──────

function computeRanks(reducedDeps, storyIds) {
  const idSet = new Set(storyIds);
  const adj = {}, inDeg = {};
  for (const id of storyIds) inDeg[id] = 0;
  for (const d of reducedDeps) {
    const u = String(d.from_story_id), v = String(d.to_story_id);
    if (!idSet.has(u) || !idSet.has(v)) continue;
    (adj[u] ??= []).push(v);
    inDeg[v] = (inDeg[v] || 0) + 1;
  }
  const rank = {}, queue = storyIds.filter(id => inDeg[id] === 0);
  for (const id of queue) rank[id] = 0;
  let qi = 0;
  while (qi < queue.length) {
    const u = queue[qi++];
    for (const v of (adj[u] ?? [])) {
      rank[v] = Math.max(rank[v] ?? 0, (rank[u] ?? 0) + 1);
      if (--inDeg[v] === 0) queue.push(v);
    }
  }
  for (const id of storyIds) if (rank[id] == null) rank[id] = 0;
  return rank;
}

function transitiveReduction(deps) {
  const adj = {};
  for (const d of deps) (adj[d.from_story_id] ??= new Set()).add(d.to_story_id);
  function canReach(start, target, visited = new Set()) {
    if (visited.has(start)) return false;
    visited.add(start);
    for (const next of (adj[start] ?? []))
      if (next === target || canReach(next, target, visited)) return true;
    return false;
  }
  return deps.filter(d => {
    const { from_story_id: u, to_story_id: v } = d;
    for (const w of (adj[u] ?? []))
      if (w !== v && canReach(w, v)) return false;
    return true;
  });
}

function getLayoutedByRank(storyNodes, markerNodes, laneNodes, edges, ranks, maxRank) {
  const colX = (rankIdx) => (rankIdx + 1) * COL_W;
  const byRank = {};
  for (const n of storyNodes) {
    const r = ranks[n.id] ?? 0;
    (byRank[r] ??= []).push(n);
  }
  const posStories = storyNodes.map(n => {
    const r = ranks[n.id] ?? 0;
    const col = byRank[r], idx = col.indexOf(n), colH = col.length * ROW_H;
    return { ...n, position: { x: colX(r), y: idx * ROW_H - colH / 2 + ROW_H / 2 - NODE_H / 2 }, zIndex: 10 };
  });
  const maxColH = Math.max(...Object.values(byRank).map(c => c.length)) * ROW_H;
  const posMarkers = markerNodes.map(n => ({
    ...n,
    position: {
      x: n.id === "__start__" ? colX(-1) + (COL_W - MARKER_SIZE) / 2 : colX(maxRank + 1) + (COL_W - MARKER_SIZE) / 2,
      y: -MARKER_SIZE / 2,
    },
    zIndex: 10,
  }));
  const posLanes = laneNodes.map(n => {
    const r = n.data.rank, col = byRank[r] ?? [], colH = col.length * ROW_H;
    return { ...n, position: { x: colX(r) - LANE_PAD_X, y: -(colH / 2) - LANE_PAD_Y + ROW_H / 2 - NODE_H / 2 }, zIndex: 0, selectable: false, draggable: false };
  });
  return { nodes: [...posLanes, ...posStories, ...posMarkers], edges };
}

// ══════════════════════════════════════════════════════════════
// Focus mode — identique à StoryDepsSection
// ══════════════════════════════════════════════════════════════
function computeVisibleSet(focusedId, deps, depth) {
  const root = Number(focusedId);
  const set = new Set([root]);
  const adj = {}, radj = {};
  for (const d of deps) {
    (adj[d.from_story_id]  ??= []).push(d.to_story_id);
    (radj[d.to_story_id]   ??= []).push(d.from_story_id);
  }
  const bfs = (start, graph) => {
    let frontier = [start];
    for (let i = 0; i < depth; i++) {
      const next = [];
      for (const n of frontier)
        for (const m of (graph[n] || []))
          if (!set.has(m)) { set.add(m); next.push(m); }
      frontier = next;
      if (!frontier.length) break;
    }
  };
  bfs(root, adj);
  bfs(root, radj);
  return set;
}

// ── Construire nodes + edges avec données CPM ─────────────────
function buildCpmGraph({ stories, deps, epicColorMap, epicIdxMap, userIdMap, cpmResult, criticalSet, focusedId, depth }) {
  const reducedDeps = transitiveReduction(deps);
  const storyIds    = stories.map(s => String(s.db_id));
  const ranks       = computeRanks(reducedDeps, storyIds);
  const maxRank     = Math.max(0, ...Object.values(ranks));

  const inDeg = {}, outDeg = {};
  for (const d of reducedDeps) {
    outDeg[d.from_story_id] = (outDeg[d.from_story_id] || 0) + 1;
    inDeg[d.to_story_id]    = (inDeg[d.to_story_id]    || 0) + 1;
  }

  const visible = focusedId ? computeVisibleSet(focusedId, reducedDeps, depth) : null;

  // Story nodes avec données CPM
  const storyNodes = stories.map(s => {
    const epicColor    = epicColorMap[s.epic_id] ?? EPIC_COLORS[0];
    const connectivity = (inDeg[s.db_id] || 0) + (outDeg[s.db_id] || 0);
    const isCritical   = criticalSet.has(String(s.db_id));
    const cpm          = cpmResult[String(s.db_id)] || cpmResult[s.db_id] || {};
    const dim          = visible ? !visible.has(s.db_id) : false;
    const isFocus      = String(s.db_id) === focusedId;
    return {
      id:       String(s.db_id),
      type:     "story",
      position: { x: 0, y: 0 },
      data: {
        id: s.db_id, userId: userIdMap[s.db_id] ?? s.db_id, title: s.title,
        epicColor: epicColor.nodeStroke, epicBg: epicColor.node,
        epicIdx: epicIdxMap[s.epic_id] ?? 0,
        connectivity, isPivot: connectivity >= PIVOT_THRESHOLD,
        isCritical, dim, isFocus,
        es: cpm.earliest_start, ef: cpm.earliest_finish,
        ls: cpm.latest_start,   lf: cpm.latest_finish,
        slack: cpm.slack,       duration: cpm.duration,
      },
    };
  });

  // Edges : critique si les deux endpoints sont critiques
  const realEdges = reducedDeps.map((d, i) => {
    const dim    = visible && (!visible.has(d.from_story_id) || !visible.has(d.to_story_id));
    const isCrit = !dim && criticalSet.has(String(d.from_story_id)) && criticalSet.has(String(d.to_story_id));
    const color  = dim ? "#cbd5e1" : isCrit ? "#ef4444" : "#94a3b8";
    return {
      id: `e${i}`, source: String(d.from_story_id), target: String(d.to_story_id),
      type: "default", animated: isCrit,
      label: d.relation_type,
      style:        { stroke: color, strokeWidth: isCrit ? 2.5 : 1.5, opacity: dim ? 0.25 : 1 },
      labelStyle:   { fontSize: 10, fill: color, fontWeight: 600 },
      labelBgStyle: { fill: "#fff", fillOpacity: dim ? 0.4 : 0.85 },
      markerEnd:    { type: MarkerType.ArrowClosed, color },
    };
  });

  const startNode = { id: "__start__", type: "marker", position: { x: 0, y: 0 }, data: { role: "start" } };
  const endNode   = { id: "__end__",   type: "marker", position: { x: 0, y: 0 }, data: { role: "end"   } };
  const vStyle    = { stroke: "#94a3b8", strokeWidth: 1.5, strokeDasharray: "4 4" };

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

  const byRank = {};
  for (const s of stories) {
    const r = ranks[String(s.db_id)] ?? 0;
    (byRank[r] ??= []).push(s);
  }
  const laneNodes = Object.entries(byRank).map(([r, col]) => {
    const ri = Number(r);
    return {
      id: `lane-${ri}`, type: "lane", position: { x: 0, y: 0 },
      data: { rank: ri, rankIdx: ri, count: col.length,
              width: NODE_W + LANE_PAD_X * 2, height: col.length * ROW_H + LANE_PAD_Y * 2 },
    };
  });

  return getLayoutedByRank(
    storyNodes, [startNode, endNode], laneNodes,
    [...startEdges, ...realEdges, ...endEdges],
    ranks, maxRank,
  );
}

// ══════════════════════════════════════════════════════════════
// Composant principal
// ══════════════════════════════════════════════════════════════
export default function CpmSection({ aiOutput, projectId }) {
  const {
    cpm_result         = {},
    critical_path      = [],
    story_dependencies = [],
    project_duration, critical_tasks, max_slack,
  } = aiOutput || {};

  const [stories,      setStories]      = useState([]);
  const [deps,         setDeps]         = useState([]);
  const [epicColorMap, setEpicColorMap] = useState({});
  const [epicIdxMap,   setEpicIdxMap]   = useState({});
  const [userIdMap,    setUserIdMap]    = useState({});
  const [fullscreen,   setFullscreen]   = useState(false);
  const [focusedId,    setFocusedId]    = useState(null);
  const [depth,        setDepth]        = useState(2);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const containerRef = useRef(null);
  const [exporting, setExporting] = useState(false);

  const criticalSet = new Set(critical_path.map(String));

  // Fetch stories + epics + dépendances
  // Les dépendances sont d'abord lues depuis aiOutput (si déjà sauvegardées),
  // sinon chargées depuis l'API pour les anciens pipelines.
  useEffect(() => {
    if (!projectId) return;
    const fetchList = [
      getProjectStories(projectId),
      getProjectEpics(projectId),
    ];
    if (!story_dependencies.length) {
      fetchList.push(getStoryDependencies(projectId));
    }
    Promise.all(fetchList)
      .then(([storiesData, epicsData, apiDeps]) => {
        setStories(storiesData);
        setDeps(story_dependencies.length ? story_dependencies : (apiDeps || []));
        const colorMap = {}, idxMap = {};
        epicsData.forEach((e, i) => {
          colorMap[e.db_id] = EPIC_COLORS[i % EPIC_COLORS.length];
          idxMap[e.db_id]   = i;
        });
        setEpicColorMap(colorMap);
        setEpicIdxMap(idxMap);
        setUserIdMap(Object.fromEntries(
          [...storiesData].sort((a, b) => a.db_id - b.db_id).map((s, i) => [s.db_id, i + 1])
        ));
      })
      .catch(console.error);
  }, [projectId]);

  // Build graph
  useEffect(() => {
    if (!stories.length) return;
    const { nodes: n, edges: e } = buildCpmGraph({
      stories, deps, epicColorMap, epicIdxMap, userIdMap,
      cpmResult: cpm_result, criticalSet,
      focusedId, depth,
    });
    setNodes(n);
    setEdges(e);
  }, [stories, deps, epicColorMap, epicIdxMap, cpm_result, focusedId, depth]);

  const onNodeClick = useCallback((_evt, node) => {
    if (node.id === "__start__" || node.id === "__end__") return;
    setFocusedId(prev => prev === node.id ? null : node.id);
  }, []);

  const onPaneClick = useCallback(() => setFocusedId(null), []);

  // Export PNG / PDF (identique à StoryDepsSection)
  const captureCanvas = async () => html2canvas(containerRef.current, {
    backgroundColor: "#f8fafc", scale: 2, useCORS: true, logging: false,
  });

  const exportPNG = async () => {
    setExporting(true);
    try {
      const canvas = await captureCanvas();
      const link = document.createElement("a");
      link.download = "chemin-critique.png";
      link.href = canvas.toDataURL("image/png");
      link.click();
    } finally { setExporting(false); }
  };

  const exportPDF = async () => {
    setExporting(true);
    try {
      const canvas = await captureCanvas();
      const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
      const pw = doc.internal.pageSize.getWidth(), ph = doc.internal.pageSize.getHeight();
      const m = 10, maxW = pw - m * 2, maxH = ph - m * 2 - 12;
      const ratio = canvas.width / canvas.height;
      const imgW = Math.min(maxW, maxH * ratio), imgH = imgW / ratio;
      doc.setFontSize(11);
      doc.text("Chemin Critique (CPM)", m, m + 4);
      doc.setFontSize(7); doc.setTextColor(120);
      doc.text(`Exporté le ${new Date().toLocaleDateString("fr-FR")} · ${stories.length} stories`, m, m + 9);
      doc.addImage(canvas.toDataURL("image/png"), "PNG", m, m + 12, imgW, imgH);
      doc.save("chemin-critique.pdf");
    } finally { setExporting(false); }
  };

  if (!Object.keys(cpm_result).length) {
    return <p className="text-sm text-slate-400 text-center py-8">Aucune donnée CPM disponible.</p>;
  }

  const graphContent = (
    <div className={clsx(
      "relative rounded-xl border border-slate-200 overflow-hidden bg-slate-50",
      fullscreen ? "h-full w-full" : "h-[620px]"
    )} ref={containerRef}>
      <ReactFlow
        nodes={nodes} edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        fitView fitViewOptions={{ padding: 0.2, minZoom: 0.3, maxZoom: 1 }}
        minZoom={0.2} maxZoom={2}
      >
        <Background color="#e2e8f0" gap={20} />
        <Controls />
        <MiniMap
          nodeColor={n => n.data?.isCritical ? "#fca5a5" : (n.data?.epicColor ?? "#cbd5e1")}
          nodeStrokeWidth={3} pannable zoomable
        />
      </ReactFlow>

      {/* Bannière focus */}
      {focusedId && (
        <div className="absolute top-3 left-3 z-10 flex items-center gap-2 bg-white/95 border border-amber-300 rounded-lg shadow-sm px-2.5 py-1.5">
          <span className="text-xs text-slate-700">
            <strong className="text-amber-700">Focus :</strong> story #{userIdMap[Number(focusedId)] ?? focusedId}
          </span>
          <span className="text-xs text-slate-500">· profondeur</span>
          <select
            value={depth}
            onChange={e => setDepth(Number(e.target.value))}
            className="text-xs border border-slate-200 rounded px-1 py-0.5 bg-white text-slate-700"
          >
            {[1, 2, 3, 4, 5].map(d => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <button
            onClick={() => setFocusedId(null)}
            className="text-slate-400 hover:text-slate-600 ml-1"
            title="Tout afficher"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      )}

      {/* Légende */}
      <div className="absolute bottom-3 left-3 z-10 flex items-center gap-3 bg-white/90 border border-slate-200 rounded-lg px-3 py-2 text-[11px] text-slate-500 shadow-sm">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded border-2 border-red-500 bg-red-50 inline-block" />
          Chemin critique
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded border-2 border-slate-300 bg-white inline-block" />
          Hors critique
        </span>
      </div>

      {/* Boutons export */}
      <div className="absolute top-3 right-3 z-10 flex items-center gap-1.5">
        <button onClick={exportPNG} disabled={exporting}
          className="flex items-center gap-1 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-sm transition-colors disabled:opacity-50">
          <Image size={13} /> PNG
        </button>
        <button onClick={exportPDF} disabled={exporting}
          className="flex items-center gap-1 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-sm transition-colors disabled:opacity-50">
          <Download size={13} /> PDF
        </button>
        <button onClick={() => setFullscreen(f => !f)}
          className="flex items-center gap-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-sm transition-colors">
          {fullscreen ? <><X size={13} /> Fermer</> : <><Maximize2 size={13} /> Plein écran</>}
        </button>
      </div>

      {exporting && (
        <div className="absolute inset-0 z-20 bg-white/60 flex items-center justify-center">
          <span className="text-xs text-slate-600 font-medium">Export en cours…</span>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-2 gap-3">
        {[
          ["Durée projet",     project_duration != null ? `${project_duration} sp` : "—", "text-navy"],
          ["Tâches critiques", critical_tasks   ?? "—",                                    "text-red-600"],
        ].map(([label, value, cls]) => (
          <div key={label} className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
            <div className={clsx("font-bold text-xl", cls)}>{value}</div>
            <div className="text-xs text-slate-400 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Graphe */}
      {fullscreen ? (
        <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4">
          <div className="w-full h-full">{graphContent}</div>
        </div>
      ) : graphContent}
    </div>
  );
}
