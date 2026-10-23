import { Check, ClipboardCheck, Clock3, ShieldAlert, Wrench, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AgentRun, DomainEvent, Ticket } from '../types'
import Badge from '../components/Badge'

export default function ReviewPage() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [runs, setRuns] = useState<Record<number, AgentRun | undefined>>({})
  const [busyId, setBusyId] = useState<number | null>(null)

  async function load() {
    const pending = await api<Ticket[]>('/tickets/pending')
    setTickets(pending)
    const entries = await Promise.all(pending.map(async ticket => {
      const history = await api<AgentRun[]>(`/tickets/${ticket.id}/agent-runs`)
      return [ticket.id, history.at(-1)] as const
    }))
    setRuns(Object.fromEntries(entries))
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    const listener = (raw: Event) => {
      const event = (raw as CustomEvent<DomainEvent>).detail
      if (event.type === 'approval.requested') load().catch(() => undefined)
    }
    window.addEventListener('myticket:event', listener)
    return () => window.removeEventListener('myticket:event', listener)
  }, [])

  async function action(id: number, approve: boolean) {
    setBusyId(id)
    try {
      await api(`/tickets/${id}/${approve ? 'approve' : 'reject'}`, {
        method: 'POST',
        body: approve ? undefined : JSON.stringify({
          content: '您的问题已由人工客服复核，暂时无法自动处理，我们将继续跟进。',
        }),
      })
      await load()
    } finally {
      setBusyId(null)
    }
  }

  return <div className="page">
    <header className="page-head"><div><span className="eyebrow">HUMAN IN THE LOOP</span><h1>人工审批</h1><p>查看 Agent 的建议、业务依据与风险，再决定是否向用户发送。</p></div></header>
    <section className="review-summary">
      <ShieldAlert/><div><strong>{tickets.length} 个请求等待决策</strong><span>高风险操作不会绕过人工直接执行</span></div>
    </section>
    <section className="review-list">
      {tickets.length === 0
        ? <div className="panel empty large"><ClipboardCheck/><strong>没有待审批工单</strong><span>所有 Agent 运行均处于安全状态</span></div>
        : tickets.map(ticket => {
            const run = runs[ticket.id]
            const result = run?.tool_result as any
            const amount = result?.amount || result?.refund?.amount
            return <article className="review-detail-card" key={ticket.id}>
              <div className="review-detail-head">
                <div><span>工单 #{ticket.id}</span><h3>{ticket.title}</h3><p>{ticket.intent || '待识别'} · {ticket.route_to || '待分派'}</p></div>
                <Badge tone="danger">{ticket.priority}</Badge>
              </div>
              <div className="review-facts">
                <div><ShieldAlert/><span>Agent 建议</span><strong>{run?.action || '等待记录'}</strong></div>
                <div><Wrench/><span>调用工具</span><strong>{run?.tool_name || '未调用'}</strong></div>
                <div><Clock3/><span>处理耗时</span><strong>{run?.total_latency_ms ? `${run.total_latency_ms.toFixed(0)} ms` : '—'}</strong></div>
                {amount && <div><span>涉及金额</span><strong>¥{amount}</strong></div>}
              </div>
              <div className="review-reason"><span>判断依据</span><p>{run?.action_reason || '暂无判断依据'}</p></div>
              <div className="review-draft"><span>准备发送给用户的回复</span><p>{run?.final_reply || '暂无回复草稿'}</p></div>
              <div className="review-actions">
                <button className="secondary danger-text" disabled={busyId === ticket.id} onClick={() => action(ticket.id, false)}><X/>驳回并转人工</button>
                <button className="primary" disabled={busyId === ticket.id} onClick={() => action(ticket.id, true)}><Check/>{busyId === ticket.id ? '处理中...' : '批准并发送'}</button>
              </div>
            </article>
          })}
    </section>
  </div>
}
