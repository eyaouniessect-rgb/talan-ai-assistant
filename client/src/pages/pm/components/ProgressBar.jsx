import clsx from "clsx";

export default function ProgressBar({ done, total }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="mt-3">
      <div className="flex justify-between text-xs text-slate-400 mb-1.5">
        <span>Phase {done}/{total}</span>
        <span>{pct}%</span>
      </div>
      <div className="w-full bg-slate-100 rounded-full h-1.5">
        <div
          className={clsx("h-1.5 rounded-full transition-all", done === total && total > 0 ? "bg-green-500" : "bg-cyan")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
