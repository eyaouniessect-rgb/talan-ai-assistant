import { CheckCircle, Clock, Loader, AlertCircle } from "lucide-react";
import clsx from "clsx";
import { PHASES } from "../constants/phases";

function PhaseIcon({ status, isActive }) {
  if (status === "done")     return <CheckCircle size={16} className={isActive ? "text-green-300" : "text-green-500"} />;
  if (status === "active")   return <AlertCircle size={16} className={isActive ? "text-amber-200" : "text-amber-500"} />;
  if (status === "running")  return <Loader size={16} className={clsx("animate-spin", isActive ? "text-blue-300" : "text-blue-500")} />;
  if (status === "rejected") return <AlertCircle size={16} className={isActive ? "text-red-300" : "text-red-500"} />;
  return <Clock size={16} className="text-slate-300" />;
}

export default function PhaseList({ activePhase, getPhaseStatus, onSelect }) {
  return (
    <div className="card p-4">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
        Phases du pipeline
      </h3>
      <div className="space-y-1">
        {PHASES.map((phase, index) => {
          const status    = getPhaseStatus(phase.id);
          const isActive  = activePhase === phase.id;
          const clickable = status !== "pending";
          const Icon      = phase.icon;

          return (
            <button
              key={phase.id}
              onClick={() => clickable && onSelect(phase.id)}
              disabled={!clickable}
              className={clsx(
                "w-full flex items-center gap-3 p-2.5 rounded-xl text-left transition-all",
                isActive
                  ? "bg-navy text-white"
                  : status === "done"     ? "hover:bg-slate-50 text-slate-600"
                  : status === "active"   ? "hover:bg-amber-50 text-slate-700"
                  : status === "running"  ? "hover:bg-blue-50 text-slate-700"
                  : status === "rejected" ? "hover:bg-red-50 text-slate-600"
                  : "text-slate-300 cursor-default",
              )}
            >
              <div className="shrink-0">
                <PhaseIcon status={status} isActive={isActive} />
              </div>
              <div className="flex-1 min-w-0 flex items-center gap-1.5">
                <span className={clsx("text-xs font-bold", isActive ? "text-white/60" : "text-slate-400")}>
                  {index + 1}.
                </span>
                <span className={clsx("text-sm font-medium truncate", isActive ? "text-white" : "")}>
                  {phase.label}
                </span>
              </div>
              <Icon size={14} className={clsx("shrink-0", isActive ? "text-white/50" : "text-slate-300")} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
