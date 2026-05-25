import {
  FileText, Layers, ListChecks,
  GitBranch, BarChart2, TrendingUp,
  Users, Activity,
} from "lucide-react";

// La phase "sprints" a été fusionnée dans le staffing (Step 3 — Répartition
// initiale). Les anciennes valeurs PHASE_7_SPRINT_PLANNING / phase_*_sprint_planning
// sont conservées dans le mapping pour compatibilité ascendante avec les anciens
// records DB, mais ne sont plus exposées dans PHASES / PHASE_LABELS.
export const PHASE_KEY_MAP = {
  // Valeurs courantes (8 phases — sprints fusionnée dans staffing)
  PHASE_1_EXTRACTION:      "extract",
  PHASE_2_EPICS:           "epics",
  PHASE_3_STORIES:         "stories",
  PHASE_4_STORY_DEPS:      "story_deps",
  PHASE_5_PRIORITIZATION:  "prioritization",
  PHASE_6_CRITICAL_PATH:   "cpm",
  PHASE_8_STAFFING:        "staffing",
  PHASE_9_MONITORING:      "monitoring",
  // Lowercase fallback
  phase_1_extraction:      "extract",
  phase_2_epics:           "epics",
  phase_3_stories:         "stories",
  phase_4_story_deps:      "story_deps",
  phase_5_prioritization:  "prioritization",
  phase_6_critical_path:   "cpm",
  phase_8_staffing:        "staffing",
  phase_9_monitoring:      "monitoring",
  // DEPRECATED — ancienne phase sprints standalone (fusionnée dans staffing)
  PHASE_7_SPRINT_PLANNING: "staffing",
  phase_7_sprint_planning: "staffing",
  PHASE_7_STAFFING:        "staffing",   // ancien ordre swappé
  PHASE_8_SPRINT_PLANNING: "staffing",   // ancien ordre swappé
  phase_7_staffing:        "staffing",
  phase_8_sprint_planning: "staffing",
};

export const PHASES = [
  { id: "extract",        label: "Extraction CDC",       icon: FileText,   desc: "Extraction du texte brut du cahier des charges" },
  { id: "epics",          label: "Epics",                icon: Layers,     desc: "Génération des epics avec stratégie de découpage" },
  { id: "stories",        label: "User Stories",         icon: ListChecks, desc: "Découpage en stories + critères d'acceptation" },
  { id: "story_deps",     label: "Dépendances Stories",  icon: GitBranch,  desc: "Analyse des dépendances entre User Stories" },
  { id: "cpm",            label: "Chemin Critique",      icon: TrendingUp, desc: "Critical Path Method sur les stories" },
  { id: "prioritization", label: "Priorisation MoSCoW",  icon: BarChart2,  desc: "Classement valeur métier × effort" },
  { id: "staffing",       label: "Staffing",             icon: Users,      desc: "Répartition en sprints + affectation aux membres de l'équipe" },
  { id: "monitoring",     label: "Monitoring",           icon: Activity,   desc: "KPIs, alertes et synchronisation Jira" },
];

export const PHASE_LABELS = {
  extract:        "Extraction CDC",
  epics:          "Epics",
  stories:        "User Stories",
  story_deps:     "Dépendances Stories",
  prioritization: "Priorisation MoSCoW",
  cpm:            "Chemin Critique (CPM)",
  staffing:       "Staffing",
  monitoring:     "Monitoring",
};
