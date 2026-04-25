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

export const restartRefinement = (projectId) =>
  api.post(`/pipeline/${projectId}/refinement/restart`).then(r => r.data)

export const applyRefinementRound = (projectId, storyChoices, continueRefinement) =>
  api.post(`/pipeline/${projectId}/refinement/round/apply`, {
    story_choices:       storyChoices,
    continue_refinement: continueRefinement,
  }).then(r => r.data)

// ── Jira re-sync ──────────────────────────────────────────────

export const resyncJira = (projectId, phase) =>
  api.post(`/pipeline/${projectId}/jira-resync`, { phase }).then(r => r.data)

// ── Stories CRUD (manuel) ─────────────────────────────────────

export const addStory = (projectId, body) =>
  api.post(`/pipeline/${projectId}/stories`, body).then(r => r.data)

// ── Export PDF ────────────────────────────────────────────────

export const exportBacklogPdf = (projectId) =>
  api.get(`/report/${projectId}/export/backlog`, { responseType: 'blob' }).then(r => r.data)
