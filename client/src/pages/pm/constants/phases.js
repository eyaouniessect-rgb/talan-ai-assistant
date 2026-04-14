import {
  FileText, Layers, ListChecks, RefreshCw,
  GitBranch, BarChart2, Network, TrendingUp,
  Calendar, Users, Activity,
} from "lucide-react";

export const PHASE_KEY_MAP = {
  phase_1_extraction: "extract",
  phase_2_epics: "epics",
  phase_3_stories: "stories",
  phase_4_refinement: "refinement",
  phase_5_story_deps: "story_deps",
  phase_6_prioritization: "prioritization",
  phase_7_tasks: "tasks",
  phase_8_task_deps: "task_deps",
  phase_9_critical_path: "cpm",
  phase_10_sprint_planning: "sprints",
  phase_11_staffing: "staffing",
  phase_12_monitoring: "monitoring",
};

export const PHASES = [
  { id: "extract",        label: "Extraction CDC",       icon: FileText,   desc: "Extraction du texte brut du cahier des charges" },
  { id: "epics",          label: "Epics",                icon: Layers,     desc: "Génération des epics avec stratégie de découpage" },
  { id: "stories",        label: "User Stories",         icon: ListChecks, desc: "Découpage en stories + critères d'acceptation" },
  { id: "refinement",     label: "Raffinement",          icon: RefreshCw,  desc: "Débat PO ↔ Tech Lead (3 rounds + arbitre)" },
  { id: "story_deps",     label: "Dépendances Stories",  icon: GitBranch,  desc: "Analyse des dépendances entre User Stories" },
  { id: "prioritization", label: "Priorisation MoSCoW",  icon: BarChart2,  desc: "Classement valeur métier × effort" },
  { id: "tasks",          label: "Tasks",                icon: ListChecks, desc: "Décomposition des stories en tâches techniques" },
  { id: "task_deps",      label: "Dépendances Tasks",    icon: Network,    desc: "Graphe de dépendances entre tâches" },
  { id: "cpm",            label: "Chemin Critique",      icon: TrendingUp, desc: "Critical Path Method sur toutes les tâches" },
  { id: "sprints",        label: "Sprint Planning",      icon: Calendar,   desc: "Répartition des stories/tasks par sprint" },
  { id: "staffing",       label: "Staffing",             icon: Users,      desc: "Affectation des tâches aux membres de l'équipe" },
  { id: "monitoring",     label: "Monitoring",           icon: Activity,   desc: "KPIs, alertes et synchronisation Jira" },
];

export const PHASE_LABELS = {
  extract:        "Extraction CDC",
  epics:          "Epics",
  stories:        "User Stories",
  refinement:     "Raffinement PO/TL",
  story_deps:     "Dépendances Stories",
  prioritization: "Priorisation MoSCoW",
  tasks:          "Tasks",
  task_deps:      "Dépendances Tasks",
  cpm:            "Chemin Critique (CPM)",
  sprints:        "Sprint Planning",
  staffing:       "Staffing",
  monitoring:     "Monitoring",
};
