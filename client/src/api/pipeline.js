// src/api/pipeline.js
// API pipeline PM

import api from './index'

export const getPipelineProjects = () =>
  api.get('/pipeline/projects').then(r => r.data)

export const startPipeline = (projectId, body) =>
  api.post(`/pipeline/${projectId}/start`, body).then(r => r.data)

export const getPipelineDetail = (projectId) =>
  api.get(`/pipeline/${projectId}`).then(r => r.data)

export const validatePhase = (projectId, body) =>
  api.post(`/pipeline/${projectId}/validate`, body).then(r => r.data)

export const getJiraConfig = () =>
  api.get('/pipeline/config').then(r => r.data)

// ── Epics CRUD ───────────────────────────────────────────────

export const getProjectEpics = (projectId) =>
  api.get(`/pipeline/${projectId}/epics`).then(r => r.data)

export const addEpic = (projectId, body) =>
  api.post(`/pipeline/${projectId}/epics`, body).then(r => r.data)

export const updateEpic = (epicId, body) =>
  api.put(`/pipeline/epics/${epicId}`, body).then(r => r.data)

export const deleteEpic = (epicId) =>
  api.delete(`/pipeline/epics/${epicId}`).then(r => r.data)

// ── Stories CRUD ──────────────────────────────────────────────

export const getProjectStories = (projectId) =>
  api.get(`/pipeline/${projectId}/stories`).then(r => r.data)

export const updateStory = (storyId, body) =>
  api.put(`/pipeline/stories/${storyId}`, body).then(r => r.data)

export const deleteStory = (storyId) =>
  api.delete(`/pipeline/stories/${storyId}`).then(r => r.data)

// ── Transition de statut manuel ──────────────────────────────
// pipeline_done → in_development → delivered

export const advanceProjectStatus = (projectId) =>
  api.patch(`/pipeline/${projectId}/status`).then(r => r.data)

// ── Sprints lifecycle ────────────────────────────────────────

export const getProjectSprints = (projectId) =>
  api.get(`/pipeline/${projectId}/sprints`).then(r => r.data)

// force=false (défaut) : si démarrage anticipé, l'API renvoie
// { requires_confirmation: true, message } sans démarrer.
// force=true : démarre malgré le warning de date.
export const startSprint = (projectId, sprintNumber, force = false) =>
  api.post(`/pipeline/${projectId}/sprints/${sprintNumber}/start`, { force })
    .then(r => r.data)

export const closeSprint = (projectId, sprintNumber) =>
  api.post(`/pipeline/${projectId}/sprints/${sprintNumber}/close`)
    .then(r => r.data)

// ── Archive / Delete ──────────────────────────────────────────

export const archiveProject = (projectId, reason) =>
  api.patch(`/pipeline/${projectId}/archive`, { reason }).then(r => r.data)

export const unarchiveProject = (projectId) =>
  api.patch(`/pipeline/${projectId}/unarchive`).then(r => r.data)

export const deleteProject = (projectId) =>
  api.delete(`/pipeline/${projectId}`).then(r => r.data)

export const getArchivedProjects = () =>
  api.get('/pipeline/projects', { params: { archived: true } }).then(r => r.data)

// ── Génère les stories manquantes (epics sans stories) ───────

export const restartMissingStories = (projectId) =>
  api.post(`/pipeline/${projectId}/stories/restart`).then(r => r.data)


// ── Jira re-sync ──────────────────────────────────────────────

export const resyncJira = (projectId, phase) =>
  api.post(`/pipeline/${projectId}/jira-resync`, { phase }).then(r => r.data)

// ── Stories CRUD (manuel) ─────────────────────────────────────

export const addStory = (projectId, body) =>
  api.post(`/pipeline/${projectId}/stories`, body).then(r => r.data)

// ── Relancer la priorisation ──────────────────────────────────

export const rerunPrioritization = (projectId) =>
  api.post(`/pipeline/${projectId}/prioritization/rerun`).then(r => r.data)

// ── Staffing — mise à jour manuelle des profils extraits ──────

export const updateStaffingProfiles = (projectId, storiesProfiles) =>
  api.patch(`/pipeline/${projectId}/staffing/profiles`, { stories_profiles: storiesProfiles }).then(r => r.data)

export const getStaffingAvailableProfiles = () =>
  api.get('/pipeline/staffing/available-profiles').then(r => r.data.profiles)

export const getStaffingAvailableSkills = () =>
  api.get('/pipeline/staffing/available-skills').then(r => r.data.skills)

export const updateNormalizationDecisions = (projectId, pmDecisions) =>
  api.patch(`/pipeline/${projectId}/staffing/normalization-decisions`, { pm_decisions: pmDecisions }).then(r => r.data)

export const restartStaffing = (projectId) =>
  api.post(`/pipeline/${projectId}/staffing/restart`).then(r => r.data)

export const updateSprintCapacities = (projectId, capacities) =>
  api.patch(`/pipeline/${projectId}/staffing/sprint-capacities`, { capacities }).then(r => r.data)

// ── Staffing — Step 5 Matching ────────────────────────────────

export const getStaffingMatching = (projectId) =>
  api.get(`/pipeline/${projectId}/staffing/matching`).then(r => r.data)

export const changeMatchingAssignment = (projectId, body) =>
  api.patch(`/pipeline/${projectId}/staffing/matching/change-assignment`, body).then(r => r.data)

export const sendRecruitmentRequest = (projectId, body) =>
  api.post(`/pipeline/${projectId}/staffing/recruitment-request`, body).then(r => r.data)

export const getHrContacts = () =>
  api.get('/pipeline/staffing/hr-contacts').then(r => r.data.contacts)

export const rerunMatching = (projectId) =>
  api.post(`/pipeline/${projectId}/staffing/matching/rerun`).then(r => r.data)

// ── Story Dependencies ────────────────────────────────────────

export const getStoryDependencies = (projectId) =>
  api.get(`/pipeline/${projectId}/story-dependencies`).then(r => r.data)

export const updateStoryDependencies = (projectId, dependencies) =>
  api.put(`/pipeline/${projectId}/story-dependencies`, { dependencies }).then(r => r.data)

// ── Export PDF ────────────────────────────────────────────────

export const exportBacklogPdf = (projectId) =>
  api.get(`/report/${projectId}/export/backlog`, { responseType: 'blob' }).then(r => r.data)
