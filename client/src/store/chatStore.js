// src/store/chatStore.js
import { create } from 'zustand'
import { sendMessageApi, getConversationsApi, getMessagesApi } from '../api/chat'

// ── Helpers ───────────────────────────────────────────────
const now = () =>
  new Date().toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })

const formatDate = (dateStr) =>
  new Date(dateStr).toLocaleDateString('fr')

const buildSteps = (data) => [
  { status: 'done', text: `Intention : ${data.intent}` },
  { status: 'done', text: `Agent : ${data.target_agent}` },
  ...(data.steps || []),
]

// ID temporaire = timestamp (> 1 trillion)
// ID réel = petit nombre PostgreSQL
const isTempId = (id) => id && id >= 1_000_000_000_000

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
        date: formatDate(c.created_at),
        agents: [],
        messageCount: 0,
        messages: [],
        loaded: false,
      }))
      set({ conversations })

      // Active la première conversation et charge ses messages
      if (conversations.length > 0) {
        set({ activeId: conversations[0].id })
        console.log("active id",conversations[0].id)
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
          hour: '2-digit', minute: '2-digit',
        }),
        steps:
          m.role === 'assistant' && m.intent
            ? [
                { status: 'done', text: `Intention : ${m.intent}` },
                { status: 'done', text: `Agent : ${m.target_agent}` },
              ]
            : [],
      }))

      set(s => ({
        conversations: s.conversations.map(c =>
          c.id === conversationId
            ? { ...c, messages, messageCount: messages.length, loaded: true }
            : c
        ),
      }))
    } catch (error) {
      console.error('Erreur chargement messages:', error)
    }
  },




  // ── Change de conversation active ─────────────────────
  setActive: async (id) => {
    set({ activeId: id })
    const conv = get().conversations.find(c => c.id === id)
    if (conv && !conv.loaded) {
      await get().loadMessages(id)
    }
  },




  // ── Nouvelle conversation ──────────────────────────────
  newConversation: () => {
    const { conversations } = get()

    // Réutilise une conversation vide si elle existe
    const emptyConv = conversations.find(c => c.loaded && c.messages.length === 0)
    if (emptyConv) {
      set({ activeId: emptyConv.id })
      return
    }

    const id = Date.now() // ID temporaire
    set(s => ({
      conversations: [
        {
          id,
          title: 'Nouvelle conversation',
          date: 'Maintenant',
          agents: [],
          messageCount: 0,
          messages: [],
          loaded: true,
        },
        ...s.conversations,
      ],
      activeId: id,
    }))
  },


  
  // ── Envoie un message ──────────────────────────────────
  sendMessage: async (text) => {
    const currentActiveId = get().activeId

    // 1. Ajoute le message user immédiatement (optimistic update)
    const userMsg = { role: 'user', content: text, time: now() }

    set(s => ({
      conversations: s.conversations.map(c =>
        c.id === currentActiveId
          ? {
              ...c,
              messages: [...c.messages, userMsg],
              title: c.messages.length === 0 ? text.slice(0, 40) : c.title,
            }
          : c
      ),
      isTyping: true,
    }))

    try {
      // 2. Envoie au backend
      const data = await sendMessageApi(text, currentActiveId)

      // 3. Ajoute la réponse assistant
      const assistantMsg = {
        role: 'assistant',
        content: data.response,
        time: now(),
        steps: buildSteps(data),
        ui_hint: data.ui_hint || null,
      }

      set(s => ({
        conversations: s.conversations.map(c =>
          c.id === currentActiveId
            ? {
                ...c,
                messages: [...c.messages, assistantMsg],
                messageCount: c.messages.length + 1,
                id: data.conversation_id, // remplace l'ID temp par le vrai
                loaded: true,
                agents: [...new Set([...c.agents, data.target_agent?.toUpperCase()])],
              }
            : c
        ),
        activeId: data.conversation_id,
        isTyping: false,
      }))
    } catch (error) {
      console.error('Chat error:', error)

      // En cas d'erreur, affiche un message d'erreur
      set(s => ({
        conversations: s.conversations.map(c =>
          c.id === currentActiveId
            ? {
                ...c,
                messages: [
                  ...c.messages,
                  {
                    role: 'assistant',
                    content: 'Erreur de connexion au serveur.',
                    time: now(),
                    steps: [],
                  },
                ],
              }
            : c
        ),
        isTyping: false,
      }))
    }
  },
}))