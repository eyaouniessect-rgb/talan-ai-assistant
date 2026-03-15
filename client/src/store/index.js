// src/store/index.js
import { create } from 'zustand'
import { loginApi } from '../api/auth'
import { sendMessageApi } from '../api/chat'

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
        initials: data.user.name?.split(' ').map(n => n[0]).join('') || 'U',
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
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      if (payload.exp * 1000 > Date.now()) {
        set({
          token,
          user: {
            id: parseInt(payload.sub),
            name: payload.name,
            role: payload.role,
            initials: payload.name?.split(' ').map(n => n[0]).join('') || 'U',
          }
        })
      } else {
        localStorage.removeItem('token')
      }
    } catch {
      localStorage.removeItem('token')
    }
  }
}))

// ── Chat Store ────────────────────────────────────────────
export const useChatStore = create((set, get) => ({
  conversations: [],
  activeId: null,
  isTyping: false,

  setActive: (id) => set({ activeId: id }),

  getActive: () => {
    const { conversations, activeId } = get()
    return conversations.find(c => c.id === activeId)
  },

newConversation: () => {
  const { conversations } = get()
  // Ne crée pas si une conversation vide existe déjà
  const hasEmpty = conversations.some(c => c.messages.length === 0)
  if (hasEmpty) {
    // Active la première conversation vide
    const empty = conversations.find(c => c.messages.length === 0)
    set({ activeId: empty.id })
    return
  }
  const id = Date.now()
  set(s => ({
    conversations: [{
      id,
      title: 'Nouvelle conversation',
      date: 'Maintenant',
      agents: [],
      messageCount: 0,
      messages: []
    }, ...s.conversations],
    activeId: id
  }))
},

  sendMessage: async (text) => {
    // ← capture l'ID AVANT tout appel async
    const currentActiveId = get().activeId

    const userMsg = {
      role: 'user',
      content: text,
      time: new Date().toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })
    }

    // Ajoute le message utilisateur + active le typing
    set(s => ({
      conversations: s.conversations.map(c =>
        c.id === currentActiveId ? {
          ...c,
          messages: [...c.messages, userMsg],
          title: c.messages.length === 0 ? text.slice(0, 40) : c.title
        } : c
      ),
      isTyping: true
    }))

    try {
      const data = await sendMessageApi(text)

      const assistantMsg = {
        role: 'assistant',
        content: data.response,
        time: new Date().toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' }),
        steps: [
          { status: 'done', text: `Intention : ${data.intent}` },
          { status: 'done', text: `Agent : ${data.target_agent}` },
        ]
      }

      // ← utilise currentActiveId partout
      set(s => ({
        conversations: s.conversations.map(c =>
          c.id === currentActiveId ? {
            ...c,
            messages: [...c.messages, assistantMsg],
            messageCount: c.messages.length + 1,
            agents: [...new Set([...c.agents, data.target_agent?.toUpperCase()])]
          } : c
        ),
        isTyping: false
      }))

    } catch (error) {
      console.error('Chat error:', error)
      set(s => ({
        conversations: s.conversations.map(c =>
          c.id === currentActiveId ? {
            ...c,
            messages: [...c.messages, {
              role: 'assistant',
              content: 'Erreur de connexion au serveur.',
              time: new Date().toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' }),
              steps: []
            }]
          } : c
        ),
        isTyping: false
      }))
    }
  }
}))

// ── Notifications Store ───────────────────────────────────
export const useNotifStore = create((set) => ({
  notifications: [],
  markRead: (id) => set(s => ({
    notifications: s.notifications.map(n =>
      n.id === id ? { ...n, read: true } : n
    )
  })),
  markAllRead: () => set(s => ({
    notifications: s.notifications.map(n => ({ ...n, read: true }))
  })),
}))