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

// ── Stories CRUD ──────────────────────────────────────────────

export const getProjectStories = (projectId) =>
  api.get(`/pipeline/${projectId}/stories`).then(r => r.data)

export const updateStory = (storyId, body) =>
  api.put(`/pipeline/stories/${storyId}`, body).then(r => r.data)

export const deleteStory = (storyId) =>
  api.delete(`/pipeline/stories/${storyId}`).then(r => r.data)

// ── Jira re-sync ──────────────────────────────────────────────

export const resyncJira = (projectId, phase) =>
  api.post(`/pipeline/${projectId}/jira-resync`, { phase }).then(r => r.data)
