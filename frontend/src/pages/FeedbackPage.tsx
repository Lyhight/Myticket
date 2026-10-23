import { Check, RefreshCcw, RotateCw, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { KnowledgeGap } from '../types'

const reasonLabels: Record<string, string> = {
  negative_feedback: '用户差评',
  reply_review_failed: '安全审查未通过',
  agent_handoff: 'Agent 转人工',
  no_knowledge_evidence: '缺少知识依据',
}

export default function FeedbackPage() {
  const [gaps, setGaps] = useState<KnowledgeGap[]>([])
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const next = await api<KnowledgeGap[]>('/feedback/gaps?status=PENDING')
      setGaps(next)
      setAnswers(current => Object.fromEntries(next.map(gap => [gap.id, current[gap.id] ?? gap.suggested_answer ?? ''])))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '知识缺口加载失败')
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function approve(gap: KnowledgeGap) {
    const approvedAnswer = answers[gap.id]?.trim()
    if (!approvedAnswer) return
    setBusy(gap.id)
    setError('')
    try {
      await api(`/feedback/gaps/${gap.id}/approve`, {
        method: 'POST',
        body: JSON.stringify({
          approved_answer: approvedAnswer,
          title: `已审核知识：${gap.question.slice(0, 60)}`,
          reviewer_note: '由反馈闭环审核并回灌',
        }),
      })
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '回灌失败')
    } finally {
      setBusy(null)
    }
  }

  async function reject(gap: KnowledgeGap) {
    const note = window.prompt('请填写驳回原因（至少 2 个字）')?.trim()
    if (!note || note.length < 2) return
    setBusy(gap.id)
    setError('')
    try {
      await api(`/feedback/gaps/${gap.id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reviewer_note: note }),
      })
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '驳回失败')
    } finally {
      setBusy(null)
    }
  }

  return <div className="page">
    <header className="page-head">
      <div><span className="eyebrow">HUMAN-IN-THE-LOOP LEARNING</span><h1>反馈闭环</h1><p>把差评、转人工和低证据回答沉淀为可审核的知识，而不是让模型自行学习错误内容。</p></div>
      <button className="secondary" onClick={load}><RotateCw/>刷新</button>
    </header>
    {error && <div className="chat-error">{error}</div>}
    <section className="gap-list">
      {gaps.map(gap => <article className="gap-card" key={gap.id}>
        <header>
          <div><RefreshCcw/><strong>知识缺口 #{gap.id}</strong><span>{reasonLabels[gap.reason] ?? gap.reason}</span></div>
          <b>出现 {gap.occurrence_count} 次</b>
        </header>
        <div className="gap-context"><span>原始问题</span><p>{gap.question}</p><small>来源：{gap.source} · 工单 #{gap.ticket_id ?? '—'}</small></div>
        <label>审核后的标准答案
          <textarea rows={5} value={answers[gap.id] ?? ''} onChange={event => setAnswers(current => ({ ...current, [gap.id]: event.target.value }))} placeholder="填写准确、可复用、可被检索的答案…"/>
        </label>
        <footer>
          <button className="secondary" disabled={busy === gap.id} onClick={() => reject(gap)}><X/>驳回</button>
          <button className="primary" disabled={busy === gap.id || !answers[gap.id]?.trim()} onClick={() => approve(gap)}><Check/>审核并回灌知识库</button>
        </footer>
      </article>)}
      {!gaps.length && !error && <div className="empty large"><RefreshCcw/><strong>暂无待审核知识缺口</strong><span>用户差评和 Agent 失败信号会自动进入这里</span></div>}
    </section>
  </div>
}
