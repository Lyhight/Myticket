import { ArrowLeft, Bot, BrainCircuit, Database, RefreshCw, Send, UserRound, Wrench } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, streamApi } from '../api/client'
import type { AgentRun, Message, Ticket } from '../types'
import Badge from '../components/Badge'

export default function TicketPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [sendError, setSendError] = useState('')
  const [agentStage, setAgentStage] = useState('正在理解问题并查询相关信息')
  const [streamedReply, setStreamedReply] = useState('')
  const [tab, setTab] = useState<'trace' | 'state'>('trace')
  const messagesRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    const [nextTicket, nextRuns] = await Promise.all([
      api<Ticket>(`/tickets/${id}`),
      api<AgentRun[]>(`/tickets/${id}/agent-runs`),
    ])
    setTicket(nextTicket)
    setRuns(nextRuns)
  }, [id])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const container = messagesRef.current
    if (!container) return
    const frame = requestAnimationFrame(() => {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
    })
    return () => cancelAnimationFrame(frame)
  }, [ticket?.messages?.length, busy])

  const latest = runs.at(-1)
  const awaitingReview = ticket?.status === 'PENDING_REVIEW'

  async function send(event: FormEvent) {
    event.preventDefault()
    const content = message.trim()
    if (!content || busy || !ticket) return

    const optimisticMessage: Message = {
      id: -Date.now(),
      ticket_id: ticket.id,
      sender_type: 'CUSTOMER',
      content,
      created_at: new Date().toISOString(),
    }

    setMessage('')
    setSendError('')
    setAgentStage('正在连接 Agent')
    setStreamedReply('')
    setBusy(true)
    setTicket(current => current ? {
      ...current,
      messages: [...(current.messages || []), optimisticMessage],
    } : current)

    try {
      for await (const event of streamApi(
        `/tickets/${id}/messages/stream`,
        { content },
      )) {
        if (event.type === 'status') setAgentStage(event.label)
        if (event.type === 'delta') {
          setAgentStage('正在生成回复')
          setStreamedReply(current => current + event.content)
        }
        if (event.type === 'error') throw new Error(event.message)
      }
      await load()
    } catch (error) {
      setSendError(error instanceof Error ? error.message : '消息发送失败，请重试')
      await load().catch(() => undefined)
    } finally {
      setBusy(false)
      setStreamedReply('')
    }
  }

  if (!ticket) return <div className="boot"><div className="loader"/></div>

  return <div className="workspace">
    <section className="conversation">
      <header className="conversation-head">
        <button className="icon-button" onClick={() => navigate('/tickets')}><ArrowLeft/></button>
        <div>
          <div className="ticket-title">
            <h2>{ticket.title}</h2>
            <Badge tone="info">{ticket.category}</Badge>
            <Badge>{ticket.status}</Badge>
          </div>
          <span>工单 #{ticket.id} · {ticket.route_to}</span>
        </div>
        <button className="icon-button" onClick={load} disabled={busy}><RefreshCw size={18}/></button>
      </header>

      <div className="messages" ref={messagesRef}>
        {ticket.messages?.map(item => <ChatMessage key={item.id} item={item}/>)}
        {busy && <div className="message agent thinking-message">
          <div className="message-avatar"><Bot/></div>
          <div>
            <span>MyTicket Agent · 正在处理</span>
            {streamedReply
              ? <p className="streaming-reply">{streamedReply}<b className="stream-caret"/></p>
              : <div className="thinking-bubble">
                  <i/><i/><i/><small>{agentStage}</small>
                </div>}
          </div>
        </div>}
        {sendError && <div className="chat-error">{sendError}</div>}
      </div>

      <form className="composer" onSubmit={send}>
        <textarea
          value={message}
          onChange={event => setMessage(event.target.value)}
          placeholder={awaitingReview ? '该工单正在等待人工审批' : busy ? 'Agent 正在思考，请稍候…' : '输入消息，继续与 Agent 对话…'}
          rows={2}
          disabled={busy || awaitingReview}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
        />
        <button className="send-button" disabled={busy || awaitingReview || !message.trim()}>
          {busy ? <span className="button-spinner"/> : <Send size={18}/>}
          {busy ? '思考中' : '发送'}
        </button>
      </form>
    </section>

    <aside className="trace-panel">
      <div className="trace-explainer">
        <strong>这次 Agent 做了什么？</strong>
        <span>这里记录它如何理解问题、查找知识、调用工具并生成回答。</span>
      </div>
      <div className="trace-tabs">
        <button className={tab === 'trace' ? 'active' : ''} onClick={() => setTab('trace')}>处理过程</button>
        <button className={tab === 'state' ? 'active' : ''} onClick={() => setTab('state')}>技术数据</button>
      </div>
      {!latest
        ? <div className="empty"><BrainCircuit/><strong>发送消息后显示处理过程</strong><span>你可以看到 Agent 的决策依据</span></div>
        : tab === 'state'
          ? <pre className="json">{JSON.stringify(latest, null, 2)}</pre>
          : <div className="trace-content">
              <div className="run-status">
                <div><span>最近一次处理 #{latest.id}</span><strong>{latest.checkpoint_status}</strong></div>
                <Badge tone={latest.review_approved === false ? 'danger' : 'success'}>
                  {latest.review_approved === false ? '需要人工检查' : '安全检查通过'}
                </Badge>
              </div>
              <TraceBlock icon={<BrainCircuit/>} title="理解与决策">
                <Key label="选择的动作" value={latest.action}/>
                <Key label="为什么这样做" value={latest.action_reason}/>
                <Key label="处理用时" value={latest.total_latency_ms ? `${latest.total_latency_ms.toFixed(0)} ms` : '—'}/>
              </TraceBlock>
              <TraceBlock icon={<Database/>} title="查询知识库">
                <Key label="检索方式" value={latest.rag_trace?.retrieval_method}/>
                <Key label="找到资料" value={`${latest.rag_trace?.result_count || 0} 条`}/>
                <Key label="检索用时" value={latest.rag_trace?.latency_ms ? `${latest.rag_trace.latency_ms} ms` : '—'}/>
                {latest.rag_trace?.results?.map((result: any) =>
                  <div className="rag-hit" key={result.chunk_id}>
                    <strong>{result.title}</strong><span>{result.source}</span>
                    <small>相关度 {Number(result.score).toFixed(3)}</small>
                  </div>
                )}
              </TraceBlock>
              <TraceBlock icon={<Wrench/>} title="工具、记忆与上下文">
                <Key label="调用工具" value={latest.tool_name || '没有调用'}/>
                <Key label="长期记忆" value={`${latest.memory_trace?.long_term_memory_count || 0} 条`}/>
                <Key label="本次上下文" value={`${latest.context_trace?.estimated_tokens || 0} tokens`}/>
              </TraceBlock>
            </div>}
    </aside>
  </div>
}

function ChatMessage({ item }: { item: Message }) {
  const isCustomer = item.sender_type === 'CUSTOMER'
  return <div className={`message ${isCustomer ? 'customer' : 'agent'}`}>
    <div className="message-avatar">{isCustomer ? <UserRound/> : <Bot/>}</div>
    <div>
      <span>{isCustomer ? '客户' : 'MyTicket Agent'} · {new Date(item.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
      <p>{item.content}</p>
    </div>
  </div>
}

function TraceBlock({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return <section className="trace-block"><h3>{icon}{title}</h3>{children}</section>
}

function Key({ label, value }: { label: string; value: unknown }) {
  return <div className="key"><span>{label}</span><strong>{String(value ?? '—')}</strong></div>
}
