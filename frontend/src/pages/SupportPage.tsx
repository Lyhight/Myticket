import { Headphones, Inbox, RefreshCw, UserCheck } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import Badge from '../components/Badge'
import type { DomainEvent, Ticket } from '../types'

type Queue = { waiting: Ticket[]; assigned: Ticket[] }

export default function SupportPage() {
  const navigate = useNavigate()
  const [queue, setQueue] = useState<Queue>({ waiting: [], assigned: [] })
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setQueue(await api<Queue>('/tickets/handoff'))
  }, [])

  useEffect(() => { load().catch(error => setError(error.message)) }, [load])
  useEffect(() => {
    const listener = (raw: Event) => {
      const event = (raw as CustomEvent<DomainEvent>).detail
      if (['ticket.escalated', 'ticket.claimed', 'ticket.resolved', 'message.created'].includes(event.type)) {
        load().catch(() => undefined)
      }
    }
    window.addEventListener('myticket:event', listener)
    return () => window.removeEventListener('myticket:event', listener)
  }, [load])

  async function claim(ticket: Ticket) {
    setBusyId(ticket.id)
    setError('')
    try {
      await api<Ticket>(`/tickets/${ticket.id}/claim`, { method: 'POST' })
      navigate(`/tickets/${ticket.id}`)
    } catch (error) {
      setError(error instanceof Error ? error.message : '领取失败')
      await load()
    } finally {
      setBusyId(null)
    }
  }

  return <div className="page">
    <header className="page-head">
      <div><span className="kicker">HUMAN HANDOFF</span><h1>人工接待工作台</h1><p>Agent 无法安全处理的请求会进入队列；领取操作具有并发保护。</p></div>
      <button className="secondary" onClick={load}><RefreshCw size={16}/>刷新</button>
    </header>
    {error && <div className="form-error">{error}</div>}
    <section className="support-columns">
      <QueuePanel icon={<Inbox/>} title="等待领取" count={queue.waiting.length}>
        {queue.waiting.map(ticket => <article className="support-ticket" key={ticket.id}>
          <div><span>#{ticket.id} · {ticket.priority}</span><strong>{ticket.title}</strong><p>{ticket.escalation_reason || 'Agent 请求人工介入'}</p></div>
          <button className="primary" disabled={busyId === ticket.id} onClick={() => claim(ticket)}><UserCheck size={15}/>领取</button>
        </article>)}
        {!queue.waiting.length && <Empty text="目前没有等待工单"/>}
      </QueuePanel>
      <QueuePanel icon={<Headphones/>} title="我的处理中" count={queue.assigned.length}>
        {queue.assigned.map(ticket => <article className="support-ticket clickable" key={ticket.id} onClick={() => navigate(`/tickets/${ticket.id}`)}>
          <div><span>#{ticket.id} · 客户 {ticket.user_id}</span><strong>{ticket.title}</strong><p>{ticket.escalation_reason}</p></div>
          <Badge tone="info">处理中</Badge>
        </article>)}
        {!queue.assigned.length && <Empty text="你还没有领取工单"/>}
      </QueuePanel>
    </section>
  </div>
}

function QueuePanel({ icon, title, count, children }: { icon: ReactNode; title: string; count: number; children: ReactNode }) {
  return <section className="panel support-panel"><div className="panel-title"><div>{icon}<strong>{title}</strong></div><Badge>{count}</Badge></div><div>{children}</div></section>
}

function Empty({ text }: { text: string }) {
  return <div className="empty"><Headphones/><span>{text}</span></div>
}
