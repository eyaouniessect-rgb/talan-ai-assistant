import { AlertCircle } from "lucide-react";

export default function ErrorBanner({ msg }) {
  if (!msg) return null;
  return (
    <div className="flex items-start gap-2.5 bg-red-50 border border-red-200 text-red-700
                    text-sm rounded-xl px-4 py-3 mt-4">
      <AlertCircle size={15} className="shrink-0 mt-0.5" />
      <span>{msg}</span>
    </div>
  );
}
