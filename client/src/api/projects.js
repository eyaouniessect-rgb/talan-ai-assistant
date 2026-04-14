// src/api/projects.js
// API projets : documents CDC

import api from './index'

export const uploadDocument = (projectId, file) => {
  const form = new FormData()
  form.append('file', file)

  return api.post(`/projects/${projectId}/document`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}

export const getDocument = (projectId) =>
  api.get(`/projects/${projectId}/document`).then(r => r.data)
