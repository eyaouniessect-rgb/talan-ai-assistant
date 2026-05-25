// src/api/auth.js
import axios from 'axios'
import api from './index'

export const loginApi = async (email, password) => {
  // OAuth2 form-data (requis par FastAPI)
  const formData = new FormData()
  formData.append('username', email)
  formData.append('password', password)

  const response = await axios.post(
    'http://localhost:8000/auth/login',
    formData
  )
  return response.data
}

// Récupère seniority / job_title / team_name / department_name de l'utilisateur connecté
export const getMyProfile = () =>
  api.get('/auth/me/profile').then(r => r.data)