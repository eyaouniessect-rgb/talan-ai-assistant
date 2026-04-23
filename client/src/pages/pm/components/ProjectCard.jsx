import { useState, useRef, useEffect } from "react";
import { Folder, ChevronRight, Calendar, Zap, MoreVertical, Archive, ArchiveRestore, Trash2, Code2, PackageCheck } from "lucide-react";
import { PHASE_LABELS } from "../constants/phases";
import StatusBadge from "./StatusBadge";
import ProgressBar from "./ProgressBar";

const ADVANCE_CONFIG = {
  pipeline_done:  { label: "Lancer le développement", icon: Code2,        cls: "text-cyan-600 hover:bg-cyan-50" },
  in_development: { label: "Marquer comme livré",      icon: PackageCheck, cls: "text-green-600 hover:bg-green-50" },
};

export default function ProjectCard({ project, onClick, onAdvance, onArchive, onUnarchive, onDelete }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  // Fermer le menu si clic en dehors
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  return (
    <div className="card p-5 text-left hover:shadow-md hover:border-cyan/30 border border-transparent
                    transition-all duration-200 w-full group relative">
      {/* Menu 3 points */}
      <div ref={menuRef} className="absolute top-3 right-3 z-10">
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100
                     opacity-0 group-hover:opacity-100 transition-all"
          title="Actions"
        >
          <MoreVertical size={15} />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-7 w-52 bg-white border border-slate-200 rounded-xl shadow-lg
                          overflow-hidden text-sm z-20">
            {/* Transition de statut si applicable */}
            {onAdvance && ADVANCE_CONFIG[project.global_status] && (() => {
              const adv = ADVANCE_CONFIG[project.global_status];
              const AdvIcon = adv.icon;
              return (
                <button
                  onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onAdvance(project); }}
                  className={`flex items-center gap-2.5 w-full px-4 py-2.5 font-medium border-b border-slate-100 ${adv.cls}`}
                >
                  <AdvIcon size={14} /> {adv.label}
                </button>
              );
            })()}
            {onUnarchive ? (
              <button
                onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onUnarchive(project); }}
                className="flex items-center gap-2.5 w-full px-4 py-2.5 text-emerald-600 hover:bg-emerald-50"
              >
                <ArchiveRestore size={14} /> Désarchiver
              </button>
            ) : (
              <button
                onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onArchive?.(project); }}
                className="flex items-center gap-2.5 w-full px-4 py-2.5 text-amber-600 hover:bg-amber-50"
              >
                <Archive size={14} /> Archiver
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onDelete?.(project); }}
              className="flex items-center gap-2.5 w-full px-4 py-2.5 text-red-500 hover:bg-red-50"
            >
              <Trash2 size={14} /> Supprimer
            </button>
          </div>
        )}
      </div>

      {/* Corps de la carte — cliquable */}
      <button onClick={onClick} className="w-full text-left">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="w-10 h-10 bg-navy/5 rounded-xl flex items-center justify-center shrink-0
                          group-hover:bg-cyan/10 transition-colors">
            <Folder size={18} className="text-navy group-hover:text-cyan transition-colors" />
          </div>
          <StatusBadge status={project.global_status} />
        </div>

        <h3 className="font-display font-bold text-navy text-sm leading-tight mb-1 pr-4">
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
    </div>
  );
}
