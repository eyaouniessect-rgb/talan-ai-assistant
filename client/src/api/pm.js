// src/api/pm.js
// ─────────────────────────────────────────────────────────────
// Couche API pour le module Project Management (PM)
// Tous les appels passent par l'instance axios `api` qui injecte
// automatiquement le JWT Bearer depuis localStorage.
// ─────────────────────────────────────────────────────────────

import api from './index'

// ── CRM — Clients ─────────────────────────────────────────────

/** Retourne la liste de tous les clients CRM */
export const getClients = () =>
  api.get('/crm/clients').then(r => r.data)

/** Crée un nouveau client. body = { name, industry?, contact_email? } */
export const createClient = (body) =>
  api.post('/crm/clients', body).then(r => r.data)


// ── CRM — Projets ─────────────────────────────────────────────

/** Retourne les projets du PM connecté. clientId optionnel pour filtrer par client. */
export const getCrmProjects = (clientId = null) =>
  api.get('/crm/projects', { params: clientId ? { client_id: clientId } : {} }).then(r => r.data)

/** Crée un nouveau projet. body = { name, client_id } */
export const createProject = (body) =>
  api.post('/crm/projects', body).then(r => r.data)


// ── Documents CDC ─────────────────────────────────────────────

/**
 * Uploade le CDC d'un projet (1 seul par projet).
 * file = objet File du navigateur
 * Retourne { document_id, file_name, replaced, ... }
 */
export const uploadDocument = (projectId, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/projects/${projectId}/document`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}

/** Retourne les infos du CDC actuel d'un projet */
export const getDocument = (projectId) =>
  api.get(`/projects/${projectId}/document`).then(r => r.data)


// ── Pipeline ──────────────────────────────────────────────────

/**
 * Retourne la liste des projets du PM avec leur état pipeline (12 phases).
 * Utilisé par MesProjets.jsx
 */
export const getPipelineProjects = () =>
  api.get('/pipeline/projects').then(r => r.data)

/**
 * Lance le pipeline IA sur un projet.
 * body = { document_id, jira_project_key? }
 */
export const startPipeline = (projectId, body) =>
  api.post(`/pipeline/${projectId}/start`, body).then(r => r.data)

/** Retourne l'état détaillé des 12 phases d'un projet */
export const getPipelineDetail = (projectId) =>
  api.get(`/pipeline/${projectId}`).then(r => r.data)

/**
 * Valide ou rejette la phase courante d'un projet.
 * body = { approved: bool, feedback?: string }
 */
export const validatePhase = (projectId, body) =>
  api.post(`/pipeline/${projectId}/validate`, body).then(r => r.data)
