import { useState, useRef, useEffect } from 'react'
import { useChatStore, useAuthStore } from '../store'
import { Send, Plus, ChevronDown, ChevronRight, Paperclip, Zap, CheckCircle, Loader } from 'lucide-react'
import clsx from 'clsx'

const AGENT_COLORS = { RH:'bg-green-100 text-green-700', CRM:'bg-blue-100 text-blue-700', Jira:'bg-orange-100 text-orange-700', Slack:'bg-purple-100 text-purple-700', Calendar:'bg-cyan-100 text-cyan-700' }

const QUICK_CONSULTANT = ['Créer un congé', 'Voir mes projets', 'Statut de mes tickets Jira', 'Mon calendrier cette semaine', 'Chercher dans la documentation']
const QUICK_PM = ['Créer un nouveau projet', 'Rapport client', 'Disponibilité de l\'équipe', 'Voir tous les tickets Jira', 'Uploader un CDC']

function ThinkingCard({ steps }) {
  const [open, setOpen] = useState(true)
  if (!steps || steps.length === 0) return null
  return (
    <div className="border border-cyan/30 bg-cyan/5 rounded-xl mb-3 overflow-hidden">
      <button onClick={()=>setOpen(!open)} className="flex items-center gap-2 w-full px-4 py-2.5 text-left hover:bg-cyan/10 transition-colors">
        {open ? <ChevronDown size={15} className="text-cyan shrink-0"/> : <ChevronRight size={15} className="text-cyan shrink-0"/>}
        <span className="text-xs font-semibold text-cyan">Étapes de traitement</span>
        <span className="ml-auto text-xs text-slate-400">{steps.filter(s=>s.status==='done').length}/{steps.length}</span>
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-1 border-t border-cyan/20">
          {steps.map((step, i) => (
            <div key={i} className="thinking-step">
              {step.status==='done'
                ? <CheckCircle size={13} className="text-green-500 shrink-0"/>
                : <Loader size={13} className="text-cyan animate-spin shrink-0"/>}
              <span className="text-xs text-slate-600">{step.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={clsx('flex gap-3 mb-4 fade-in-up', isUser && 'flex-row-reverse')}>
      {!isUser && (
        <div className="w-8 h-8 bg-cyan rounded-xl flex items-center justify-center shrink-0 mt-1">
          <Zap size={14} className="text-white"/>
        </div>
      )}
      <div className={clsx('flex flex-col max-w-2xl', isUser && 'items-end')}>
        {!isUser && <ThinkingCard steps={msg.steps}/>}
        <div className={isUser ? 'message-user' : 'message-assistant'}>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
        </div>
        <span className="text-xs text-slate-400 mt-1 px-1">{msg.time}</span>
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex gap-3 mb-4 fade-in-up">
      <div className="w-8 h-8 bg-cyan rounded-xl flex items-center justify-center shrink-0">
        <Zap size={14} className="text-white"/>
      </div>
      <div className="message-assistant flex items-center gap-1 py-4">
        <div className="dot-loading"><span/><span/><span/></div>
        <span className="text-xs text-slate-400 ml-2">L'assistant analyse votre demande...</span>
      </div>
    </div>
  )
}

export default function Chat() {
  const [input, setInput] = useState('')
  const user = useAuthStore(s => s.user)
  const { conversations, activeId, isTyping, setActive,
        newConversation, sendMessage, loadConversations } = useChatStore()
  const bottomRef = useRef()
  const inputRef = useRef()
  const isPM = user?.role === 'pm'
  const quick = isPM ? QUICK_PM : QUICK_CONSULTANT
  const active = conversations.find(c => c.id === activeId)

  // ── DEBUG ──────────────────────────────────────────────
  console.log('=== CHAT RENDER ===')
  console.log('activeId:', activeId)
  console.log('conversations count:', conversations.length)
  console.log('active conversation:', active)
  console.log('active messages:', active?.messages)
  console.log('isTyping:', isTyping)
  // ───────────────────────────────────────────────────────



// ← charge les conversations depuis le backend au démarrage
useEffect(() => {
  loadConversations()
}, [])

  useEffect(() => {
    console.log('useEffect messages changed — active messages:', active?.messages?.length)
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [active?.messages, isTyping])

  useEffect(() => {
    inputRef.current?.focus()
  }, [activeId])

  const handleSend = () => {
    if (!input.trim()) return
  console.log('=== SEND MESSAGE ===')
  console.log('activeId:', activeId)
  console.log('conversation_id réel:', active?.id)  // ← ajoute ça
    sendMessage(input.trim())
    setInput('')
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <div className="flex h-full">
      {/* Conversations list */}
      <div className="w-72 border-r border-slate-100 bg-white flex flex-col shrink-0 hidden md:flex">
        <div className="p-4 border-b border-slate-100">
          <button onClick={newConversation} className="btn-cyan w-full flex items-center justify-center gap-2 text-sm">
            <Plus size={16}/> Nouvelle conversation
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.map(conv => (
            <button key={conv.id} onClick={()=>setActive(conv.id)}
              className={clsx('w-full text-left p-3 rounded-xl mb-1 transition-all hover:bg-slate-50',
                activeId===conv.id ? 'bg-navy/5 border border-navy/10' : '')}>
              <div className="text-sm font-medium text-slate-800 truncate mb-1">{conv.title}</div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">{conv.date}</span>
                <span className="text-xs text-slate-400">{conv.messageCount} msg</span>
              </div>
              {conv.agents.length > 0 && (
                <div className="flex gap-1 mt-1.5 flex-wrap">
                  {conv.agents.map(a => (
                    <span key={a} className={clsx('text-xs px-1.5 py-0.5 rounded-md font-medium', AGENT_COLORS[a] || 'bg-slate-100 text-slate-600')}>
                      {a}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Main chat */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto p-6">

          {/* DEBUG VISIBLE à l'écran */}
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-3 mb-4 text-xs font-mono">
            <div><b>activeId:</b> {String(activeId)}</div>
            <div><b>conversations:</b> {conversations.length}</div>
            <div><b>messages:</b> {active?.messages?.length ?? 'undefined'}</div>
            <div><b>isTyping:</b> {String(isTyping)}</div>
          </div>

          {active?.messages?.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 bg-navy rounded-2xl flex items-center justify-center mb-4">
                <Zap size={28} className="text-cyan"/>
              </div>
              <h3 className="font-display text-xl font-bold text-navy mb-2">Comment puis-je vous aider ?</h3>
              <p className="text-slate-500 text-sm mb-8 max-w-sm">Posez-moi une question ou choisissez une action rapide ci-dessous</p>
              <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                {quick.map(q => (
                  <button key={q} onClick={()=>setInput(q)}
                    className="text-sm bg-white border border-slate-200 hover:border-cyan hover:text-cyan px-4 py-2 rounded-xl transition-all">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {active?.messages?.map((msg, i) => {
            console.log(`Rendering message ${i}:`, msg)
            return <Message key={i} msg={msg}/>
          })}

          {isTyping && <TypingIndicator/>}
          <div ref={bottomRef}/>
        </div>

        {active?.messages?.length > 0 && (
          <div className="px-6 pb-2 flex gap-2 overflow-x-auto">
            {quick.slice(0,4).map(q => (
              <button key={q} onClick={()=>setInput(q)}
                className="shrink-0 text-xs bg-white border border-slate-200 hover:border-cyan hover:text-cyan px-3 py-1.5 rounded-lg transition-all whitespace-nowrap">
                {q}
              </button>
            ))}
          </div>
        )}

        <div className="p-4 border-t border-slate-100 bg-white">
          <div className="flex items-end gap-3 bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 focus-within:border-cyan focus-within:ring-2 focus-within:ring-cyan/10 transition-all">
            {isPM && (
              <button className="text-slate-400 hover:text-navy shrink-0 mb-0.5 transition-colors">
                <Paperclip size={19}/>
              </button>
            )}
            <textarea ref={inputRef} value={input} onChange={e=>setInput(e.target.value)} onKeyDown={handleKey}
              placeholder="Posez votre question..." rows={1}
              className="flex-1 bg-transparent outline-none text-sm text-slate-800 placeholder:text-slate-400 resize-none leading-relaxed"
              style={{ maxHeight:'120px', overflowY:'auto' }}
              onInput={e => { e.target.style.height='auto'; e.target.style.height=e.target.scrollHeight+'px' }}
            />
            <button onClick={handleSend} disabled={!input.trim() || isTyping}
              className={clsx('w-9 h-9 rounded-xl flex items-center justify-center shrink-0 transition-all',
                input.trim() && !isTyping ? 'bg-navy hover:bg-navy-light text-white' : 'bg-slate-200 text-slate-400 cursor-not-allowed')}>
              <Send size={16}/>
            </button>
          </div>
          <p className="text-xs text-slate-400 text-center mt-2">Entrée pour envoyer · Shift+Entrée pour nouvelle ligne</p>
        </div>
      </div>
    </div>
  )
}