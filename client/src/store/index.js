// src/store/index.js
// ═══════════════════════════════════════════════════════════
// Barrel file — réexporte tous les stores
// ═══════════════════════════════════════════════════════════
// Tous les imports existants continuent de fonctionner :
//   import { useAuthStore, useChatStore, useNotifStore } from '../store'
//
// Mais maintenant chaque store est dans son propre fichier.

export { useAuthStore } from './authStore'
export { useChatStore } from './chatStore'
export { useNotifStore } from './notifStore'