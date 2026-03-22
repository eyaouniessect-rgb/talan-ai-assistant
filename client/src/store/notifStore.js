// src/store/notifStore.js
import { create } from 'zustand'

// ── Notifications Store ───────────────────────────────────
export const useNotifStore = create((set) => ({
  notifications: [],

  markRead: (id) =>
    set(s => ({
      notifications: s.notifications.map(n =>
        n.id === id ? { ...n, read: true } : n
      ),
    })),

  markAllRead: () =>
    set(s => ({
      notifications: s.notifications.map(n => ({ ...n, read: true })),
    })),
}))