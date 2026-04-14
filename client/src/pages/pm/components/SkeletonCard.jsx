export default function SkeletonCard() {
  return (
    <div className="card p-5 animate-pulse">
      <div className="flex justify-between mb-3">
        <div className="w-10 h-10 bg-slate-100 rounded-xl" />
        <div className="w-20 h-6 bg-slate-100 rounded-full" />
      </div>
      <div className="h-4 bg-slate-100 rounded w-3/4 mb-2" />
      <div className="h-3 bg-slate-100 rounded w-1/2 mb-4" />
      <div className="h-1.5 bg-slate-100 rounded-full" />
    </div>
  );
}
