import {
  FileText, Layers, ListChecks,
  GitBranch, BarChart2, TrendingUp,
  Calendar, Users, Activity,
} from "lucide-react";

export const PHASE_KEY_MAP = {
  // Uppercase (SQLAlchemy 2.0 member names — valeurs normales après migration)
  PHASE_1_EXTRACTION:      "extract",
  PHASE_2_EPICS:           "epics",
  PHASE_3_STORIES:         "stories",
  PHASE_4_STORY_DEPS:      "story_deps",
  PHASE_5_PRIORITIZATION:  "prioritization",
  PHASE_6_CRITICAL_PATH:   "cpm",
  PHASE_7_STAFFING:        "staffing",
  PHASE_8_SPRINT_PLANNING: "sprints",
  PHASE_9_MONITORING:      "monitoring",
  // Anciens noms uppercase (DB records créés avant le swap staffing/sprints)
  PHASE_7_SPRINT_PLANNING: "sprints",
  PHASE_8_STAFFING:        "staffing",
  // Lowercase fallback (anciennes valeurs, migration en cours ou pas encore appliquée)
  phase_1_extraction:      "extract",
  phase_2_epics:           "epics",
  phase_3_stories:         "stories",
  phase_4_story_deps:      "story_deps",
  phase_5_prioritization:  "prioritization",
  phase_6_critical_path:   "cpm",
  phase_7_staffing:        "staffing",
  phase_7_sprint_planning: "sprints",
  phase_8_staffing:        "staffing",
  phase_8_sprint_planning: "sprints",
  phase_9_monitoring:      "monitoring",
};

export const PHASES = [
  { id: "extract",        label: "Extraction CDC",       icon: FileText,   desc: "Extraction du texte brut du cahier des charges" },
  { id: "epics",          label: "Epics",                icon: Layers,     desc: "Génération des epics avec stratégie de découpage" },
  { id: "stories",        label: "User Stories",         icon: ListChecks, desc: "Découpage en stories + critères d'acceptation" },
  { id: "story_deps",     label: "Dépendances Stories",  icon: GitBranch,  desc: "Analyse des dépendances entre User Stories" },
  { id: "cpm",            label: "Chemin Critique",      icon: TrendingUp, desc: "Critical Path Method sur les stories" },
  { id: "prioritization", label: "Priorisation MoSCoW",  icon: BarChart2,  desc: "Classement valeur métier × effort" },
  { id: "staffing",       label: "Staffing",             icon: Users,      desc: "Affectation des stories aux membres de l'équipe" },
  { id: "sprints",        label: "Sprint Planning",      icon: Calendar,   desc: "Répartition des stories par sprint" },
  { id: "monitoring",     label: "Monitoring",           icon: Activity,   desc: "KPIs, alertes et synchronisation Jira" },
];

export const PHASE_LABELS = {
  extract:        "Extraction CDC",
  epics:          "Epics",
  stories:        "User Stories",
  story_deps:     "Dépendances Stories",
  prioritization: "Priorisation MoSCoW",
  cpm:            "Chemin Critique (CPM)",
  sprints:        "Sprint Planning",
  staffing:       "Staffing",
  monitoring:     "Monitoring",
};
