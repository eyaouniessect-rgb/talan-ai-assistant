// src/store/chatStore.js
import { create } from 'zustand'
import { sendMessageStream, getConversationsApi, getMessagesApi } from '../api/chat'

// ── Helpers ───────────────────────────────────────────────
const now = () =>
  new Date().toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })

const formatDate = (dateStr) =>
  new Date(dateStr).toLocaleDateString('fr')

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
        console.log("active id", conversations[0].id)
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


  // ── Envoie un message (streaming) ─────────────────────
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

    // 2. Ajoute un message assistant placeholder avec streaming: true
    const placeholderMsg = {
      role: 'assistant',
      content: '',
      time: now(),
      steps: [],
      ui_hint: null,
      streaming: true,
    }

    set(s => ({
      conversations: s.conversations.map(c =>
        c.id === currentActiveId
          ? { ...c, messages: [...c.messages, placeholderMsg] }
          : c
      ),
    }))

    // Helper pour mettre à jour le dernier message assistant
    const updateLastMsg = (updater) => {
      set(s => ({
        conversations: s.conversations.map(c => {
          if (c.id !== currentActiveId) return c
          const msgs = [...c.messages]
          if (msgs.length === 0) return c
          msgs[msgs.length - 1] = updater(msgs[msgs.length - 1])
          return { ...c, messages: msgs }
        }),
      }))
    }

    try {
      // 3. Consomme le flux SSE
      for await (const event of sendMessageStream(text, currentActiveId)) {
        console.log('[SSE event]', event)

        switch (event.type) {
          case 'step_start':
            // Ajoute une nouvelle étape en statut 'running'
            updateLastMsg(msg => ({
              ...msg,
              steps: [
                ...msg.steps,
                { step_id: event.step_id, status: 'running', text: event.text, agent: event.agent },
              ],
            }))
            break

          case 'step_done':
            // Met à jour le statut de l'étape et ajoute le résultat au contenu
            updateLastMsg(msg => ({
              ...msg,
              steps: msg.steps.map(s =>
                s.step_id === event.step_id
                  ? { ...s, status: 'done' }
                  : s
              ),
              content: msg.content
                ? msg.content + (event.result ? '\n\n' + event.result : '')
                : (event.result || ''),
            }))
            break

          case 'step_unavailable':
            // Met à jour le statut de l'étape et ajoute le message d'indisponibilité
            updateLastMsg(msg => ({
              ...msg,
              steps: msg.steps.map(s =>
                s.step_id === event.step_id
                  ? { ...s, status: 'unavailable' }
                  : s
              ),
              content: msg.content
                ? msg.content + (event.text ? '\n\n' + event.text : '')
                : (event.text || ''),
            }))
            break

          case 'step_skipped':
            // Met à jour le statut de l'étape sans ajouter au contenu
            updateLastMsg(msg => ({
              ...msg,
              steps: msg.steps.map(s =>
                s.step_id === event.step_id
                  ? { ...s, status: 'skipped' }
                  : s
              ),
            }))
            break

          case 'step_progress':
            // Met à jour le texte affiché de l'étape en cours (tool calls internes de l'agent)
            updateLastMsg(msg => ({
              ...msg,
              steps: msg.steps.map(s =>
                s.step_id === event.step_id
                  ? { ...s, text: event.text }
                  : s
              ),
            }))
            break

          case 'needs_input':
            // Définit le contenu comme la question posée, arrête le streaming
            updateLastMsg(msg => ({
              ...msg,
              content: event.text || '',
              ui_hint: event.ui_hint || null,
              streaming: false,
              steps: msg.steps.map(s =>
                s.step_id === event.step_id
                  ? { ...s, status: 'waiting' }
                  : s
              ),
            }))
            set({ isTyping: false })
            break

          case 'done': {
            // Finalise le message : arrête le streaming, met à jour conv_id
            const realConvId = event.conversation_id
            updateLastMsg(msg => ({
              ...msg,
              streaming: false,
              ui_hint: event.ui_hint || msg.ui_hint || null,
            }))
            set(s => ({
              conversations: s.conversations.map(c => {
                if (c.id !== currentActiveId) return c
                return {
                  ...c,
                  id: realConvId,
                  loaded: true,
                  messageCount: c.messages.length,
                }
              }),
              activeId: realConvId,
              isTyping: false,
            }))
            break
          }

          case 'error':
            // Affiche l'erreur dans le message assistant
            updateLastMsg(msg => ({
              ...msg,
              content: event.text || 'Une erreur est survenue.',
              streaming: false,
            }))
            set({ isTyping: false })
            break

          default:
            console.warn('[SSE] Événement inconnu:', event.type)
        }
      }
    } catch (error) {
      console.error('Streaming error:', error)

      // En cas d'erreur réseau, affiche un message d'erreur
      updateLastMsg(msg => ({
        ...msg,
        content: 'Erreur de connexion au serveur.',
        streaming: false,
      }))
      set({ isTyping: false })
    }
  },
}))
