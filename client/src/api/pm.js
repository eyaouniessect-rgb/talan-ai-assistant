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
