// src/api/pm.js
// Façade de compatibilité : ré-exporte les modules API refactorés.

import api from './index'

export {
  getClients,
  createClient,
  getCrmProjects,
  createProject,
} from './crm'

export {
  uploadDocument,
  getDocument,
} from './projects'

export {
  getPipelineProjects,
  startPipeline,
  getPipelineDetail,
  validatePhase,
} from './pipeline'

// ── Dashboard PM ──────────────────────────────────────────────
export const getPMDashboard = () =>
  api.get('/dashboard/pm').then(r => r.data)

export const getPMEvents = () =>
  api.get('/dashboard/pm/events').then(r => r.data)

// Section "Pilotage des livraisons" du dashboard PM
// (KPIs portefeuille + projets actifs + projets à risque + distribution + vélocité)
export const getPMDelivery = () =>
  api.get('/dashboard/pm/delivery').then(r => r.data)

// Détail sprint par sprint pour l'onglet Monitoring du projet (phase 8)
export const getProjectMonitoringDelivery = (projectId) =>
  api.get(`/pipeline/${projectId}/monitoring/delivery`).then(r => r.data)

// ── Dashboard Consultant ──────────────────────────────────────
// Liste des projets actifs avec compteurs to_do/in_progress/done
export const getConsultantDashboard = () =>
  api.get('/dashboard/consultant').then(r => r.data)

// Tous les tickets du consultant, groupés par projet → sprint.
// Utilisé par la page "Mes tickets" (sidebar consultant).
export const getConsultantTickets = () =>
  api.get('/dashboard/consultant/tickets').then(r => r.data)

// Met à jour le progress_status d'UN ticket (= une StaffingAssignment) du consultant.
// On cible l'assignment_id et non le story_id : une story splittée frontend/backend
// possède plusieurs assignments, chacune avec son propre progress_status.
// status ∈ {to_do, in_progress, done}
export const updateConsultantTicketStatus = (assignmentId, status) =>
  api.patch(`/dashboard/consultant/tickets/${assignmentId}`, { progress_status: status })
     .then(r => r.data)
