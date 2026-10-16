import { Bot, BookOpen, ClipboardCheck, LogOut, MessageSquareText, Radio } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../state/AuthContext'
import type { ReactNode } from 'react'

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Bot size={22}/></div><div><strong>MyTicket</strong><span>Agent Console</span></div></div>
      <nav>
        <NavLink to="/tickets"><MessageSquareText size={18}/>工单中心</NavLink>
        {user?.role === 'admin' && <>
          <NavLink to="/review"><ClipboardCheck size={18}/>人工审批</NavLink>
          <NavLink to="/knowledge"><BookOpen size={18}/>知识库</NavLink>
        </>}
      </nav>
      <div className="system-state"><span><Radio size={14}/> Agent Online</span><small>混合检索 · Memory · Tools</small></div>
      <div className="profile"><div className="avatar">{user?.email.slice(0, 1).toUpperCase()}</div><div><strong>{user?.email}</strong><span>{user?.role === 'admin' ? '管理员' : '客户'}</span></div><button onClick={logout} title="退出"><LogOut size={17}/></button></div>
    </aside>
    <main className="main">{children}</main>
  </div>
}
