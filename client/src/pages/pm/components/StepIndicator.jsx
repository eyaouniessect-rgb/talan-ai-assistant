import { Check, ChevronRight } from "lucide-react";
import clsx from "clsx";

const STEPS = ["Client", "Projet", "CDC", "Lancement"];

export default function StepIndicator({ current }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {STEPS.map((label, i) => {
        const done   = current > i + 1;
        const active = current === i + 1;
        return (
          <div key={label} className="flex items-center gap-2">
            <div className={clsx(
              "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all",
              done ? "bg-green-500 text-white" : active ? "bg-navy text-white" : "bg-slate-200 text-slate-400",
            )}>
              {done ? <Check size={13} /> : i + 1}
            </div>
            <span className={clsx(
              "text-sm font-medium",
              active ? "text-navy" : done ? "text-slate-600" : "text-slate-300",
            )}>
              {label}
            </span>
            {i < STEPS.length - 1 && <ChevronRight size={15} className="text-slate-200 mx-1" />}
          </div>
        );
      })}
    </div>
  );
}
