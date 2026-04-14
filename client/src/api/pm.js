// src/api/pm.js
// Façade de compatibilité : ré-exporte les modules API refactorés.
// Les nouveaux imports recommandés sont:
// - ./crm
// - ./projects
// - ./pipeline

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
