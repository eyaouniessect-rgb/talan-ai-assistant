// src/api/rh.js
import api from './index'

export const createUserApi = async (data) => {
  const response = await api.post('/rh/users', data)
  return response.data
}

export const getSkillsApi = async () => {
  const response = await api.get('/rh/skills')
  return response.data
}

export const getUsersApi = async () => {
  const response = await api.get('/rh/users')
  return response.data
}

export const getDepartmentsApi = async () => {
  const response = await api.get('/rh/departments')
  return response.data
}

export const getTeamsApi = async () => {
  const response = await api.get('/rh/teams')
  return response.data
}

export const getEmployeesApi = async () => {
  const response = await api.get('/rh/employees')
  return response.data
}

export const getLeavesApi = async (status = null) => {
  const params = status ? { status } : {}
  const response = await api.get('/rh/leaves', { params })
  return response.data
}

export const approveLeaveApi = async (leaveId) => {
  const response = await api.post(`/rh/leaves/${leaveId}/approve`)
  return response.data
}

export const rejectLeaveApi = async (leaveId, reason = '') => {
  const response = await api.post(`/rh/leaves/${leaveId}/reject`, { reason })
  return response.data
}
