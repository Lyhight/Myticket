import { Bot, CheckCircle2, Database, GitBranch, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useAuth } from '../state/AuthContext'

export default function LoginPage() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login'|'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try { mode === 'login' ? await login(email, password) : await register(email, password) }
    catch (e) { setError(e instanceof Error ? e.message : '操作失败') }
    finally { setBusy(false) }
  }
  return <div className="login-page">
    <section className="login-story">
      <div className="eyebrow"><Sparkles size={15}/> AI CUSTOMER OPERATIONS</div>
      <h1>让每一次服务，<br/><em>都有迹可循。</em></h1>
      <p>分类、决策、工具调用、记忆与知识检索，在一个可观测的 Agent 工作台完成闭环。</p>
      <div className="feature-grid">
        <div><GitBranch/><strong>Agentic Workflow</strong><span>状态驱动的多步执行</span></div>
        <div><Database/><strong>Hybrid RAG</strong><span>关键词与语义混合检索</span></div>
        <div><CheckCircle2/><strong>Safety Review</strong><span>回复审核与人工兜底</span></div>
      </div>
    </section>
    <section className="login-panel"><div className="login-card">
      <div className="mobile-brand"><Bot/> MyTicket</div>
      <span className="kicker">WELCOME BACK</span><h2>{mode === 'login' ? '登录工作台' : '创建账户'}</h2><p>进入你的智能客服协作空间</p>
      <form onSubmit={submit}>
        <label>邮箱地址<input value={email} onChange={e=>setEmail(e.target.value)} type="email" required /></label>
        <label>登录密码<input value={password} onChange={e=>setPassword(e.target.value)} type="password" minLength={8} required /></label>
        {error && <div className="form-error">{error}</div>}
        <button className="primary wide" disabled={busy}>{busy ? '请稍候...' : mode === 'login' ? '登录 MyTicket' : '注册并登录'}</button>
      </form>
      <button className="text-button" onClick={()=>setMode(mode === 'login' ? 'register' : 'login')}>{mode === 'login' ? '没有账户？立即注册' : '已有账户？返回登录'}</button>
    </div></section>
  </div>
}
