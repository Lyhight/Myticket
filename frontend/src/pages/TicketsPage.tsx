import { ArrowRight, CirclePlus, Inbox, Search, TicketCheck, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Ticket } from '../types'
import Badge from '../components/Badge'

const tone = (value: string) =>
  value === 'URGENT' || value === 'PENDING_REVIEW' ? 'danger'
    : value === 'HIGH' ? 'warning'
      : value === 'OPEN' ? 'info' : 'success'

export default function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [deleting, setDeleting] = useState<Ticket | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const navigate = useNavigate()

  useEffect(() => { api<Ticket[]>('/tickets').then(setTickets) }, [])
  const filtered = useMemo(
    () => tickets.filter(ticket =>
      `${ticket.title}${ticket.category}${ticket.intent}`.toLowerCase().includes(search.toLowerCase())
    ),
    [tickets, search],
  )

  async function create(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const ticket = await api<Ticket>('/tickets', {
        method: 'POST',
        body: JSON.stringify({ title, content }),
      })
      navigate(`/tickets/${ticket.id}`)
    } finally {
      setBusy(false)
    }
  }

  async function confirmDelete() {
    if (!deleting) return
    setDeleteBusy(true)
    setDeleteError('')
    try {
      await api<void>(`/tickets/${deleting.id}`, { method: 'DELETE' })
      setTickets(current => current.filter(ticket => ticket.id !== deleting.id))
      setDeleting(null)
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : '删除失败，请稍后重试')
    } finally {
      setDeleteBusy(false)
    }
  }

  return <div className="page">
    <header className="page-head">
      <div><span className="eyebrow">CUSTOMER OPERATIONS</span><h1>工单中心</h1><p>与 AI Agent 协作处理每一次客户请求。</p></div>
      <button className="primary" onClick={() => setOpen(true)}><CirclePlus size={18}/>新建工单</button>
    </header>
    <section className="stats">
      <div><Inbox/><span>全部工单</span><strong>{tickets.length}</strong></div>
      <div><TicketCheck/><span>处理中</span><strong>{tickets.filter(ticket => ticket.status === 'OPEN').length}</strong></div>
      <div><div className="pulse-dot"/><span>待人工</span><strong>{tickets.filter(ticket => ticket.status === 'PENDING_REVIEW').length}</strong></div>
    </section>
    <section className="panel">
      <div className="panel-tools">
        <div className="search"><Search size={17}/><input placeholder="搜索标题、分类或意图" value={search} onChange={event => setSearch(event.target.value)}/></div>
        <span>{filtered.length} 条结果</span>
      </div>
      <div className="ticket-list">
        {filtered.map(ticket =>
          <div
            className="ticket-row"
            key={ticket.id}
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/tickets/${ticket.id}`)}
            onKeyDown={event => {
              if (event.key === 'Enter') navigate(`/tickets/${ticket.id}`)
            }}
          >
            <div className="ticket-id">#{String(ticket.id).padStart(4, '0')}</div>
            <div className="ticket-main"><strong>{ticket.title}</strong><span>{ticket.intent || '等待识别'} · {new Date(ticket.updated_at).toLocaleString('zh-CN')}</span></div>
            <Badge tone={tone(ticket.category)}>{ticket.category}</Badge>
            <Badge tone={tone(ticket.priority)}>{ticket.priority}</Badge>
            <Badge tone={tone(ticket.status)}>{ticket.status}</Badge>
            <div className="ticket-actions">
              <button
                className="delete-ticket"
                title="删除对话"
                aria-label={`删除工单 ${ticket.title}`}
                onClick={event => {
                  event.stopPropagation()
                  setDeleteError('')
                  setDeleting(ticket)
                }}
              ><Trash2 size={16}/></button>
              <ArrowRight size={18}/>
            </div>
          </div>
        )}
      </div>
    </section>

    {open && <div className="modal-backdrop" onMouseDown={() => setOpen(false)}>
      <div className="modal" onMouseDown={event => event.stopPropagation()}>
        <span className="kicker">NEW TICKET</span><h2>创建新工单</h2><p>提交后 Agent 会自动分类、检索知识并生成回复。</p>
        <form onSubmit={create}>
          <label>工单标题<input value={title} onChange={event => setTitle(event.target.value)} placeholder="例如：订单一直没有发货" required/></label>
          <label>问题描述<textarea value={content} onChange={event => setContent(event.target.value)} placeholder="请描述你遇到的问题..." rows={6} required/></label>
          <div className="modal-actions"><button type="button" className="secondary" onClick={() => setOpen(false)}>取消</button><button className="primary" disabled={busy}>{busy ? 'Agent 处理中...' : '提交给 Agent'}</button></div>
        </form>
      </div>
    </div>}

    {deleting && <div className="modal-backdrop" onMouseDown={() => !deleteBusy && setDeleting(null)}>
      <div className="modal delete-confirm" onMouseDown={event => event.stopPropagation()}>
        <div className="delete-warning"><Trash2/></div>
        <span className="kicker">DELETE CONVERSATION</span>
        <h2>删除这条对话？</h2>
        <p>“{deleting.title}”及其全部聊天记录和 Agent 运行轨迹都会被永久删除，此操作无法撤销。</p>
        {deleteError && <div className="form-error">{deleteError}</div>}
        <div className="modal-actions">
          <button className="secondary" disabled={deleteBusy} onClick={() => setDeleting(null)}>取消</button>
          <button className="danger-button" disabled={deleteBusy} onClick={confirmDelete}>{deleteBusy ? '正在删除...' : '确认删除'}</button>
        </div>
      </div>
    </div>}
  </div>
}
