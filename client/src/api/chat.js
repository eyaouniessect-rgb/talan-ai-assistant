// src/api/chat.js
import api from './index'

export const sendMessageApi = async (message, conversationId = null) => {
  const response = await api.post('/chat/', {
    message: message,
    // envoie null si c'est un timestamp local (pas encore en base)
    conversation_id: typeof conversationId === 'number' && conversationId < 1000000000000
      ? conversationId
      : null,
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