import { Folder, ChevronRight, Calendar, Zap } from "lucide-react";
import { PHASE_LABELS } from "../constants/phases";
import StatusBadge from "./StatusBadge";
import ProgressBar from "./ProgressBar";

export default function ProjectCard({ project, onClick }) {
  return (
    <button
      onClick={onClick}
      className="card p-5 text-left hover:shadow-md hover:border-cyan/30 border border-transparent
                 transition-all duration-200 w-full group"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="w-10 h-10 bg-navy/5 rounded-xl flex items-center justify-center shrink-0
                        group-hover:bg-cyan/10 transition-colors">
          <Folder size={18} className="text-navy group-hover:text-cyan transition-colors" />
        </div>
        <StatusBadge status={project.global_status} />
      </div>

      <h3 className="font-display font-bold text-navy text-sm leading-tight mb-1">
        {project.project_name}
      </h3>
      <p className="text-xs text-slate-500 mb-3">{project.client_name}</p>

      {project.global_status !== "completed" && project.current_phase && (
        <div className="flex items-center gap-1.5 mb-1">
          <Zap size={11} className="text-cyan shrink-0" />
          <span className="text-xs text-slate-600">
            {project.global_status === "pending_human" ? (
              <>Validation requise : <strong>{PHASE_LABELS[project.current_phase]}</strong></>
            ) : (
              <>Phase : <strong>{PHASE_LABELS[project.current_phase]}</strong></>
            )}
          </span>
        </div>
      )}

      <ProgressBar done={project.phases_done} total={project.phases_total} />

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
        <div className="flex items-center gap-1 text-xs text-slate-400">
          <Calendar size={11} />
          <span>
            {project.created_at
              ? new Date(project.created_at).toLocaleDateString("fr-FR")
              : "—"}
          </span>
        </div>
        <ChevronRight size={14} className="text-slate-300 group-hover:text-cyan transition-colors" />
      </div>
    </button>
  );
}
