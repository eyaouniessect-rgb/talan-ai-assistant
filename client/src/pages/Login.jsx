import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store";
import { Eye, EyeOff, Zap } from "lucide-react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const login = useAuthStore((s) => s.login);
  const nav = useNavigate();

  const handle = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      const { user } = useAuthStore.getState()
      nav(user?.role === 'rh' ? '/rh' : '/dashboard')
    } catch (err) {
      setError("Email ou mot de passe incorrect.");
    } finally {
      setLoading(false);
    }
  };

  const DEMO_PASSWORD = "Talan2026!";
  const DEMO_ACCOUNTS = {
    rh:         "ons.rh.talan@gmail.com",
    consultant: "eyaouniessect@gmail.com",
    manager:    "imen.ayari@talan.tn",
  };

  const quickLogin = async (role) => {
    const demoEmail = DEMO_ACCOUNTS[role] || "";
    setError("");
    setLoading(true);
    try {
      await login(demoEmail, DEMO_PASSWORD);
      const { user } = useAuthStore.getState();
      nav(user?.role === "rh" ? "/rh" : "/dashboard");
    } catch {
      setError("Connexion demo échouée — vérifiez que ce compte existe en base.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-slate-50">
      {/* Left panel */}
      <div className="hidden lg:flex w-1/2 bg-navy flex-col justify-between p-12 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="absolute border border-cyan rounded-full"
              style={{
                width: `${(i + 1) * 180}px`,
                height: `${(i + 1) * 180}px`,
                top: "50%",
                left: "50%",
                transform: "translate(-50%,-50%)",
                opacity: 1 / (i + 1),
              }}
            />
          ))}
        </div>
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-16">
            <div className="w-10 h-10 bg-cyan rounded-xl flex items-center justify-center">
              <Zap size={20} className="text-navy" />
            </div>
            <span className="font-display text-white text-2xl font-bold tracking-tight">
              TALAN
            </span>
          </div>
          <h1 className="font-display text-white text-5xl font-bold leading-tight mb-6">
            Votre assistant
            <br />
            <span className="text-cyan">intelligent</span>
            <br />
            d'entreprise
          </h1>
          <p className="text-slate-300 text-lg leading-relaxed max-w-md">
            Centralisez vos outils RH, CRM, Jira et Slack dans une interface
            conversationnelle unifiée.
          </p>
        </div>
        <div className="relative z-10 flex gap-6">
          {["RH", "CRM", "Jira", "Slack", "Calendar"].map((t) => (
            <div
              key={t}
              className="bg-white/10 backdrop-blur px-3 py-1.5 rounded-lg"
            >
              <span className="text-white/80 text-sm font-medium">{t}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 mb-10 lg:hidden">
            <div className="w-8 h-8 bg-navy rounded-lg flex items-center justify-center">
              <Zap size={16} className="text-cyan" />
            </div>
            <span className="font-display text-navy text-xl font-bold">
              TALAN
            </span>
          </div>

          <h2 className="font-display text-navy text-3xl font-bold mb-2">
            Connexion
          </h2>
          <p className="text-slate-500 mb-8">Bienvenue sur Talan Assistant</p>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-xl mb-5">
              {error}
            </div>
          )}

          <form onSubmit={handle} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Email
              </label>
              <input
                className="input-field"
                type="email"
                placeholder="votre@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Mot de passe
              </label>
              <div className="relative">
                <input
                  className="input-field pr-12"
                  type={showPw ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Connexion...
                </>
              ) : (
                "Se connecter"
              )}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-slate-100">
            <p className="text-xs text-slate-400 mb-3 text-center">
              Comptes de démonstration
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <button
                onClick={() => quickLogin("rh")}
                className="text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-100 px-3 py-2.5 rounded-xl transition-colors text-left"
              >
                <div className="font-medium mb-0.5">RH</div>
                <div className="text-emerald-500 font-mono">
                  ons.rh.talan@gmail.com
                </div>
              </button>
              <button
                onClick={() => quickLogin("consultant")}
                className="text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-100 px-3 py-2.5 rounded-xl transition-colors text-left"
              >
                <div className="font-medium mb-0.5">Consultant</div>
                <div className="text-blue-500 font-mono">
                  eyaouniessect@gmail.com
                </div>
              </button>
              <button
                onClick={() => quickLogin("manager")}
                className="text-xs bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-100 px-3 py-2.5 rounded-xl transition-colors text-left"
              >
                <div className="font-medium mb-0.5">Manager</div>
                <div className="text-purple-500 font-mono">
                  imen.ayari@talan.tn
                </div>
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-2 text-center">
              Mot de passe : <span className="font-mono">Talan2026!</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
