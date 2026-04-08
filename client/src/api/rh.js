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

export const getEmployeesApi = async ({ department, team, seniority, excludeManagement } = {}) => {
  const params = {}
  if (department)        params.department         = department
  if (team)              params.team               = team
  if (seniority)         params.seniority          = seniority
  if (excludeManagement) params.exclude_management = true
  const response = await api.get('/rh/employees', { params })
  return response.data
}

export const toggleUserActiveApi = async (userId) => {
  const response = await api.patch(`/rh/users/${userId}/toggle-active`)
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

export const getDirectorApi = async () => {
  const response = await api.get('/rh/director')
  return response.data
}

export const getEmployeeByIdApi = async (employeeId) => {
  const response = await api.get(`/rh/employees/${employeeId}`)
  return response.data
}

export const updateEmployeeApi = async (employeeId, data) => {
  const response = await api.patch(`/rh/employees/${employeeId}`, data)
  return response.data
}

export const contactEmployeeApi = async (employeeId, { subject, body, cc_emails = [] }) => {
  const response = await api.post(`/rh/employees/${employeeId}/contact`, { subject, body, cc_emails })
  return response.data
}

export const getLeavesFilteredApi = async ({ status, department, team, employee_name, start_date, end_date } = {}) => {
  const params = {}
  if (status)        params.status        = status
  if (department)    params.department    = department
  if (team)          params.team          = team
  if (employee_name) params.employee_name = employee_name
  if (start_date)    params.start_date    = start_date
  if (end_date)      params.end_date      = end_date
  const response = await api.get('/rh/leaves', { params })
  return response.data
}
