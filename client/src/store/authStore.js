// src/store/authStore.js
import { create } from 'zustand'
import { loginApi } from '../api/auth'

// ── Helpers ───────────────────────────────────────────────
const getInitials = (name) =>
  name?.split(' ').map(n => n[0]).join('') || 'U'

const decodeJWT = (token) => {
  try {
    return JSON.parse(atob(token.split('.')[1]))
  } catch {
    return null
  }
}

// ── Auth Store ────────────────────────────────────────────
export const useAuthStore = create((set) => ({
  user: null,
  token: null,

  login: async (email, password) => {
    const data = await loginApi(email, password)
    localStorage.setItem('token', data.access_token)
    set({
      user: {
        ...data.user,
        initials: getInitials(data.user.name),
      },
      token: data.access_token,
    })
  },

  logout: () => {
    localStorage.removeItem('token')
    set({ user: null, token: null })
  },

  restoreSession: () => {
    const token = localStorage.getItem('token')
    if (!token) return

    const payload = decodeJWT(token)
    if (!payload) {
      localStorage.removeItem('token')
      return
    }

    // Token expiré ?
    if (payload.exp * 1000 < Date.now()) {
      localStorage.removeItem('token')
      return
    }

    set({
      token,
      user: {
        id: parseInt(payload.sub),
        name: payload.name,
        role: payload.role,
        initials: getInitials(payload.name),
      },
    })
  },
}))