// src/api/crm.js
// API CRM : clients et projets

import api from './index'

// CRM — Clients
export const getClients = () =>
  api.get('/crm/clients').then(r => r.data)

export const createClient = (body) =>
  api.post('/crm/clients', body).then(r => r.data)

// CRM — Projets
export const getCrmProjects = (clientId = null) =>
  api.get('/crm/projects', { params: clientId ? { client_id: clientId } : {} }).then(r => r.data)

export const createProject = (body) =>
  api.post('/crm/projects', body).then(r => r.data)
