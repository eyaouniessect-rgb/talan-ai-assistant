// src/api/auth.js
import axios from 'axios'

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