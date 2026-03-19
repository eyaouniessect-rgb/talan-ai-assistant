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

export const getConversationsApi = async () => {
  const response = await api.get('/chat/conversations')
  return response.data
}

export const getMessagesApi = async (conversationId) => {
  const response = await api.get(`/chat/conversations/${conversationId}/messages`)
  return response.data
}