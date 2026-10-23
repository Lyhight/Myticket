import { Bot, BookOpen, ClipboardCheck, Headphones, LogOut, MessageSquareText, Radio, RefreshCcw } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../state/AuthContext'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { subscribeEvents } from '../api/client'
import type { DomainEvent } from '../types'

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const [unread, setUnread] = useState(0)
  const [notice, setNotice] = useState('')
  const cursor = useRef(0)

  useEffect(() => {
    if (!user) return
    let stopped = false
    let controller: AbortController | undefined
    let retry: ReturnType<typeof setTimeout> | undefined
    const connect = async () => {
      controller = new AbortController()
      try {
        cursor.current = await subscribeEvents(
          cursor.current,
          controller.signal,
          (event: DomainEvent) => {
            cursor.current = event.id
            window.dispatchEvent(new CustomEvent('myticket:event', { detail: event }))
            if (event.type === 'ticket.escalated' || event.type === 'approval.requested') {
              setUnread(value => value + 1)
              setNotice(event.type === 'ticket.escalated' ? '收到新的人工工单' : '收到新的审批任务')
              window.setTimeout(() => setNotice(''), 4000)
            }
          },
        )
      } catch (error) {
        if (!stopped && !(error instanceof DOMException && error.name === 'AbortError')) {
          retry = setTimeout(connect, 2000)
        }
      }
    }
    connect()
    return () => {
      stopped = true
      controller?.abort()
      if (retry) clearTimeout(retry)
    }
  }, [user])

  const supportRole = !!user && ['agent', 'supervisor', 'admin'].includes(user.role)
  const reviewRole = !!user && ['supervisor', 'admin'].includes(user.role)
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Bot size={22}/></div><div><strong>MyTicket</strong><span>Agent Console</span></div></div>
      <nav>
        <NavLink to="/tickets"><MessageSquareText size={18}/>工单中心</NavLink>
        {supportRole && <NavLink to="/support" onClick={() => setUnread(0)}>
          <Headphones size={18}/>人工接待{unread > 0 && <b className="nav-count">{unread}</b>}
        </NavLink>}
        {reviewRole && <>
          <NavLink to="/review"><ClipboardCheck size={18}/>人工审批</NavLink>
          <NavLink to="/feedback"><RefreshCcw size={18}/>反馈闭环</NavLink>
        </>}
        {user?.role === 'admin' && <>
          <NavLink to="/knowledge"><BookOpen size={18}/>知识库</NavLink>
        </>}
      </nav>
      <div className="system-state"><span><Radio size={14}/> Agent Online</span><small>混合检索 · Memory · Tools</small></div>
      <div className="profile"><div className="avatar">{user?.email.slice(0, 1).toUpperCase()}</div><div><strong>{user?.email}</strong><span>{supportRole ? '客服工作台' : '客户'}</span></div><button onClick={logout} title="退出"><LogOut size={17}/></button></div>
    </aside>
    <main className="main">{children}</main>
    {notice && <div className="event-toast"><Radio size={16}/>{notice}</div>}
  </div>
}
