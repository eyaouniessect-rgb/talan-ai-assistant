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
