import { Clock, Loader, AlertCircle, CheckCircle, Code2, PackageCheck } from "lucide-react";
import clsx from "clsx";

const STATUS_CONFIG = {
  not_started:    { label: "Non démarré",     icon: Clock,        cls: "bg-slate-100 text-slate-500" },
  in_progress:    { label: "Pipeline IA",     icon: Loader,       cls: "bg-blue-50 text-blue-600",   spin: true },
  pending_human:  { label: "Validation PM",   icon: AlertCircle,  cls: "bg-amber-50 text-amber-600" },
  pipeline_done:  { label: "Pipeline terminé",icon: CheckCircle,  cls: "bg-violet-50 text-violet-600" },
  in_development: { label: "En développement",icon: Code2,        cls: "bg-cyan-50 text-cyan-700" },
  delivered:      { label: "Livré",           icon: PackageCheck, cls: "bg-green-50 text-green-600" },
};

export default function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.in_progress;
  const Icon = cfg.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full", cfg.cls)}>
      <Icon size={11} className={cfg.spin ? "animate-spin" : ""} />
      {cfg.label}
    </span>
  );
}
