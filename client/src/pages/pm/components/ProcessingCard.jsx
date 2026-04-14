import { useEffect, useState } from "react";
import { CheckCircle, Loader, Upload, Zap, RotateCcw } from "lucide-react";
import { PHASES } from "../constants/phases";

// Phases qui font un export Jira après validation
const JIRA_SYNC_PHASES = new Set(["epics", "stories", "tasks", "sprints"]);

function buildSteps(currentPhase, approved) {
  if (!approved) {
    return [
      {
        icon: RotateCcw,
        label: "Rejet enregistré",
        sublabel: "Votre feedback a été transmis à l'IA",
        color: "text-amber-600",
        bg: "bg-amber-50",
        durationMs: 2000,
      },
      {
        icon: Zap,
        label: `Relancement de la phase en cours...`,
        sublabel: "L'IA régénère les résultats en tenant compte de votre retour",
        color: "text-violet-600",
        bg: "bg-violet-50",
        durationMs: null, // reste jusqu'à la fin
      },
    ];
  }

  const currentIdx = PHASES.findIndex((p) => p.id === currentPhase);
  const nextPhase = PHASES[currentIdx + 1] ?? null;

  const steps = [
    {
      icon: CheckCircle,
      label: "Validation enregistrée",
      sublabel: "La phase a été approuvée avec succès",
      color: "text-green-600",
      bg: "bg-green-50",
      durationMs: 2500,
    },
  ];

  if (JIRA_SYNC_PHASES.has(currentPhase)) {
    const labels = {
      epics: "épics",
      stories: "user stories",
      tasks: "tâches",
      sprints: "sprints",
    };
    steps.push({
      icon: Upload,
      label: "Synchronisation Jira en cours...",
      sublabel: `Export des ${labels[currentPhase] ?? currentPhase} vers votre projet Jira`,
      color: "text-blue-600",
      bg: "bg-blue-50",
      durationMs: 5000,
    });
  }

  if (nextPhase) {
    steps.push({
      icon: Zap,
      label: `Génération des ${nextPhase.label} en cours...`,
      sublabel: "L'IA analyse le contexte et génère les résultats",
      color: "text-violet-600",
      bg: "bg-violet-50",
      durationMs: null,
    });
  }

  return steps;
}

export default function ProcessingCard({ currentPhase, approved }) {
  const steps = buildSteps(currentPhase, approved);
  const [stepIdx, setStepIdx] = useState(0);

  useEffect(() => {
    setStepIdx(0);
  }, [currentPhase, approved]);

  useEffect(() => {
    const step = steps[stepIdx];
    if (!step || step.durationMs === null) return;
    const t = setTimeout(
      () => setStepIdx((i) => Math.min(i + 1, steps.length - 1)),
      step.durationMs,
    );
    return () => clearTimeout(t);
  }, [stepIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  const step = steps[stepIdx];
  const Icon = step.icon;
  const isLast = stepIdx === steps.length - 1 && step.durationMs === null;

  return (
    <div className="card p-5 border-2 border-slate-200">
      {/* Barre de progression des étapes */}
      <div className="flex items-center gap-1.5 mb-5">
        {steps.map((s, i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-all duration-500 ${
              i < stepIdx
                ? "bg-green-400"
                : i === stepIdx
                  ? "bg-navy"
                  : "bg-slate-100"
            }`}
          />
        ))}
      </div>

      {/* Étape courante */}
      <div className={`flex items-start gap-3 rounded-xl p-4 ${step.bg}`}>
        <div className={`mt-0.5 ${step.color}`}>
          {isLast ? (
            <Loader size={18} className="animate-spin" />
          ) : (
            <Icon size={18} />
          )}
        </div>
        <div>
          <p className={`text-sm font-semibold ${step.color}`}>{step.label}</p>
          <p className="text-xs text-slate-500 mt-0.5">{step.sublabel}</p>
        </div>
      </div>

      {/* Étapes passées (mini résumé) */}
      {stepIdx > 0 && (
        <div className="mt-3 space-y-1">
          {steps.slice(0, stepIdx).map((s, i) => {
            const PastIcon = s.icon;
            return (
              <div key={i} className="flex items-center gap-2 text-xs text-slate-400">
                <CheckCircle size={12} className="text-green-400 shrink-0" />
                <span>{s.label}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
