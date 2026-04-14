// src/api/chat.js
import api from './index'

export const sendMessageApi = async (message, conversationId = null) => {
  // Si l'ID est un timestamp (> 1 trillion) c'est temporaire → envoie null
  const realId = conversationId && conversationId < 1_000_000_000_000
    ? conversationId
    : null

  const response = await api.post('/chat/', {
    message,
    conversation_id: realId,
  })
  return response.data
}


/**
 * Générateur asynchrone SSE pour le streaming de réponses.
 * Yields parsed JSON event objects from the /chat/stream endpoint.
 *
 * Event types:
 *   { type: 'step_start',     step_id, agent, text }
 *   { type: 'step_done',      step_id, agent, result }
 *   { type: 'step_unavailable', step_id, agent, text }
 *   { type: 'step_skipped',   step_id, agent }
 *   { type: 'needs_input',    step_id, agent, text, ui_hint }
 *   { type: 'done',           conversation_id, ui_hint }
 *   { type: 'error',          text }
 */
export async function* sendMessageStream(message, conversationId) {
  const realId = conversationId && conversationId < 1_000_000_000_000
    ? conversationId
    : null

  const token = localStorage.getItem('token')

  const response = await fetch('http://localhost:8000/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, conversation_id: realId }),
  })

  if (!response.ok) {
    // Tenter de parser le corps pour récupérer le détail sécurité
    let detail = null
    try { detail = (await response.json()).detail } catch (_) {}
    const err = new Error(`HTTP ${response.status}`)
    err.securityBlock = detail?.blocked === true ? detail : null
    throw err
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Les messages SSE sont séparés par \n\n
      const parts = buffer.split('\n\n')
      buffer = parts.pop() // garde le dernier chunk incomplet

      for (const part of parts) {
        const line = part.trim()
        if (line.startsWith('data: ')) {
          const jsonStr = line.slice(6).trim()
          if (jsonStr) {
            try {
              yield JSON.parse(jsonStr)
            } catch (_) {
              // ignore les messages malformés
            }
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}


export const getConversationsApi = async () => {
  const response = await api.get('/chat/conversations')
  return response.data
}



export const getMessagesApi = async (conversationId) => {
  const response = await api.get(`/chat/conversations/${conversationId}/messages`)
  return response.data
}
