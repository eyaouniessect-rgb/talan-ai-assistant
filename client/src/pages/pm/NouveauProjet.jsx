import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store";
import { X } from "lucide-react";
import StepIndicator  from "./components/StepIndicator";
import StepClient     from "./steps/StepClient";
import StepProjet     from "./steps/StepProjet";
import StepCDC        from "./steps/StepCDC";
import StepLancement  from "./steps/StepLancement";

export default function NouveauProjet() {
  const user = useAuthStore((s) => s.user);
  const nav  = useNavigate();

  const [step,           setStep]           = useState(1);
  const [selectedClient, setSelectedClient] = useState(null);
  const [createdProject, setCreatedProject] = useState(null);
  const [uploadedDoc,    setUploadedDoc]    = useState(null);

  if (user?.role !== "pm")
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center card p-10 max-w-sm">
          <X size={24} className="text-red-500 mx-auto mb-3" />
          <h3 className="font-display font-bold text-navy text-lg mb-2">Accès refusé</h3>
          <p className="text-slate-500 text-sm mb-5">Réservé aux Project Managers.</p>
          <button onClick={() => nav("/dashboard")} className="btn-primary w-full">Retour au Dashboard</button>
        </div>
      </div>
    );

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <StepIndicator current={step} />

      {step === 1 && (
        <StepClient onNext={(client) => { setSelectedClient(client); setStep(2); }} />
      )}
      {step === 2 && (
        <StepProjet
          selectedClient={selectedClient}
          onNext={(project) => { setCreatedProject(project); setStep(3); }}
          onBack={() => setStep(1)}
        />
      )}
      {step === 3 && (
        <StepCDC
          createdProject={createdProject}
          onNext={(doc) => { setUploadedDoc(doc); setStep(4); }}
          onBack={() => setStep(2)}
        />
      )}
      {step === 4 && (
        <StepLancement
          selectedClient={selectedClient}
          createdProject={createdProject}
          uploadedDoc={uploadedDoc}
          onBack={() => setStep(3)}
        />
      )}
    </div>
  );
}
