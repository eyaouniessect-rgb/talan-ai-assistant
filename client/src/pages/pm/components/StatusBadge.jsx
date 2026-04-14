import { Clock, Loader, AlertCircle, CheckCircle } from "lucide-react";
import clsx from "clsx";

const STATUS_CONFIG = {
  not_started:   { label: "Non démarré",   icon: Clock,        cls: "bg-slate-100 text-slate-500" },
  in_progress:   { label: "En cours",      icon: Loader,       cls: "bg-blue-50 text-blue-600" },
  pending_human: { label: "Validation PM", icon: AlertCircle,  cls: "bg-amber-50 text-amber-600" },
  completed:     { label: "Terminé",       icon: CheckCircle,  cls: "bg-green-50 text-green-600" },
};

export default function StatusBadge({ status }) {
  const { label, icon: Icon, cls } = STATUS_CONFIG[status] ?? STATUS_CONFIG.in_progress;
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full", cls)}>
      <Icon size={11} className={status === "in_progress" ? "animate-spin" : ""} />
      {label}
    </span>
  );
}
