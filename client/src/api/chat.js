// src/api/chat.js
import api from './index'

export const sendMessageApi = async (message, conversationId = null) => {
  const response = await api.post('/chat/', {
    message: message,
    conversation_id: conversationId,
  })
  return response.data
}