import { create } from 'zustand'
import { loginApi } from '../api/auth'
import { sendMessageApi, getConversationsApi, getMessagesApi } from '../api/chat'

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

  // ── Charge les conversations depuis le backend ─────────
  loadConversations: async () => {
    try {
      const data = await getConversationsApi()
      const conversations = data.map(c => ({
        id: c.id,
        title: c.title,
        date: new Date(c.created_at).toLocaleDateString('fr'),
        agents: [],
        messageCount: 0,
        messages: [],        // ← vide au départ
        loaded: false,       // ← messages pas encore chargés
      }))
      set({ conversations })

      // Active la première conversation si elle existe
      if (conversations.length > 0) {
        set({ activeId: conversations[0].id })
        await get().loadMessages(conversations[0].id)
      }
    } catch (error) {
      console.error('Erreur chargement conversations:', error)
    }
  },

  // ── Charge les messages d'une conversation ─────────────
loadMessages: async (conversationId) => {
  try {
    const data = await getMessagesApi(conversationId)
    const messages = data.map(m => ({
      role: m.role,
      content: m.content,
      time: new Date(m.timestamp).toLocaleTimeString('fr', {
        hour: '2-digit', minute: '2-digit'
      }),
      // ← reconstruit les steps depuis intent + target_agent
      steps: m.role === 'assistant' && m.intent ? [
        { status: 'done', text: `Intention : ${m.intent}` },
        { status: 'done', text: `Agent : ${m.target_agent}` },
      ] : [],
    }))
    set(s => ({
      conversations: s.conversations.map(c =>
        c.id === conversationId
          ? { ...c, messages, messageCount: messages.length, loaded: true }
          : c
      )
    }))
  } catch (error) {
    console.error('Erreur chargement messages:', error)
  }
},

  // ── Change de conversation active ─────────────────────
  setActive: async (id) => {
    set({ activeId: id })
    const conv = get().conversations.find(c => c.id === id)
    // Charge les messages si pas encore chargés
    if (conv && !conv.loaded) {
      await get().loadMessages(id)
    }
  },

  // ── Nouvelle conversation ──────────────────────────────
  newConversation: () => {
    const { conversations } = get()
    const hasEmpty = conversations.some(c => c.messages.length === 0)
    if (hasEmpty) {
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
        messages: [],
        loaded: true,
      }, ...s.conversations],
      activeId: id
    }))
  },

  // ── Envoie un message ──────────────────────────────────
  sendMessage: async (text) => {
    const currentActiveId = get().activeId

    const userMsg = {
      role: 'user',
      content: text,
      time: new Date().toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })
    }

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
      const data = await sendMessageApi(text, currentActiveId)

      const assistantMsg = {
        role: 'assistant',
        content: data.response,
        time: new Date().toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' }),
        steps: [
          { status: 'done', text: `Intention : ${data.intent}` },
          { status: 'done', text: `Agent : ${data.target_agent}` },
        ]
      }

      set(s => ({
        conversations: s.conversations.map(c =>
          c.id === currentActiveId ? {
            ...c,
            messages: [...c.messages, assistantMsg],
            messageCount: c.messages.length + 1,
            id: data.conversation_id,
            loaded: true,
            agents: [...new Set([...c.agents, data.target_agent?.toUpperCase()])]
          } : c
        ),
        activeId: data.conversation_id,
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