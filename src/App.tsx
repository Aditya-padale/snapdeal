import { useEffect, useMemo, useRef, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, Bell, Bot, Check, ChevronDown, CircleDollarSign, Clock3, Gauge, Mic, Package, RotateCcw, Send, Sparkles, Square, Target, TrendingDown, Volume2 } from 'lucide-react'

type Seller = { id: string; name: string; category: string; location: string; synthetic: boolean }
type SellerData = { seller: Seller & Record<string, number | string | boolean>; trend: { day: string; revenue: number }[]; sales_change: number; avg_competitor_gap: number; changes: { revenue: number; orders: number; conversion: number; aov: number }; observations: { impressions_stable: boolean; conversion_decline: number; top_product: string } }
type Product = { id: string; name: string; price: number; competitor_price: number; conversion: number; previous_conversion: number; inventory: number; velocity: number; rating: number; views: number; orders: number; margin: number }
type Signal = { id: string; label: string; value: number; unit: string; direction: string; priority: string }
type Approval = { id: string; product_id: string; action: string; status: string; created_at: string }
type MemoryEntry = { id: string; role: string; content: string; created_at: string }

const API = `${import.meta.env.VITE_API_URL || '/api'}`.replace(/\/$/, '')
const apiOrigin = API.endsWith('/api') ? API.slice(0, -4) : API
const money = (value: number) => `₹${Math.round(value).toLocaleString('en-IN')}`
const pct = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}%`

function App() {
  const [sellers, setSellers] = useState<Seller[]>([])
  const [sellerId, setSellerId] = useState('SEL-10482')
  const [data, setData] = useState<SellerData | null>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [message, setMessage] = useState('')
  const [transcript, setTranscript] = useState<{ role: string; text: string }[]>([])
  const [status, setStatus] = useState<'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING'>('IDLE')
  const [recording, setRecording] = useState<MediaRecorder | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [view, setView] = useState<'overview' | 'radar' | 'memory' | 'approvals' | 'simulator'>('overview')
  const [signals, setSignals] = useState<Signal[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [memory, setMemory] = useState<MemoryEntry[]>([])
  const [simulation, setSimulation] = useState<Record<string, string | number> | null>(null)
  const [simProductId, setSimProductId] = useState('')
  const [simPrice, setSimPrice] = useState('')
  const [simDays, setSimDays] = useState('7')
  const audioChunks = useRef<Blob[]>([])
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const seller = data?.seller
  const topProduct = products[0]

  useEffect(() => { fetch(`${API}/sellers`).then(r => r.json()).then(setSellers).catch(() => setSellers([{ id: 'SEL-10482', name: 'Aarav Threads', category: 'Fashion & Apparel', location: 'Jaipur, Rajasthan', synthetic: true }])) }, [])
  useEffect(() => {
    Promise.all([fetch(`${API}/sellers/${sellerId}/analytics`).then(r => r.json()), fetch(`${API}/sellers/${sellerId}/products`).then(r => r.json())]).then(([analytics, productList]) => { setData(analytics); setProducts(productList) }).catch(() => undefined)
    Promise.all([fetch(`${API}/sellers/${sellerId}/growth-radar`).then(r => r.json()), fetch(`${API}/sellers/${sellerId}/approvals`).then(r => r.json()), fetch(`${API}/sellers/${sellerId}/conversations`).then(r => r.json())]).then(([radar, approvalList, conversations]) => {
      setSignals(radar.signals || []); setApprovals(approvalList); setMemory(conversations); setTranscript(conversations.map((entry: MemoryEntry) => ({ role: entry.role === 'user' ? 'seller' : 'ai', text: entry.content })))
    }).catch(() => undefined)
  }, [sellerId])

  const sendMessage = async (text = message) => {
    if (!text.trim() || isSending) return
    const history = transcript.map(turn => ({ role: turn.role === 'seller' ? 'user' : 'assistant', content: turn.text }))
    setIsSending(true); setStatus('THINKING'); setTranscript(old => [...old, { role: 'seller', text }]); setMessage('')
    try { const result = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seller_id: sellerId, message: text, history }) }).then(r => r.json()); setTranscript(old => [...old, { role: 'ai', text: result.response }]); setStatus('SPEAKING'); const speech = await fetch(`${API}/voice/synthesize`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: result.response }) }).then(r => r.json()); if (speech.audio_url) { audioRef.current?.pause(); const audio = new Audio(`${apiOrigin}${speech.audio_url}`); audioRef.current = audio; audio.onended = () => setStatus('IDLE'); await audio.play().catch(() => undefined) } else { window.setTimeout(() => setStatus('IDLE'), 3200) } } catch { setTranscript(old => [...old, { role: 'ai', text: 'I cannot reach the KAM service right now. You can still explore the seller analytics and simulator.' }]); setStatus('IDLE') } finally { setIsSending(false) }
  }
  const startRecording = async () => {
    audioRef.current?.pause();
    if (!navigator.mediaDevices) { setMessage('Microphone access is not available in this browser.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type)) || '';
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      audioChunks.current = [];
      recorder.ondataavailable = event => audioChunks.current.push(event.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop()); setStatus('THINKING');
        const blob = new Blob(audioChunks.current, { type: recorder.mimeType || 'audio/webm' });
        const extension = blob.type.includes('ogg') ? 'ogg' : 'webm';
        const audio = new File([blob], `seller-voice.${extension}`, { type: blob.type });
        const form = new FormData(); form.append('file', audio);
        try { const result = await fetch(`${API}/voice/transcribe`, { method: 'POST', body: form }).then(r => r.json()); if (result.text) sendMessage(result.text); else { setMessage(result.message || 'No speech was detected. Try again or use the text fallback.'); setStatus('IDLE') } } catch { setMessage('Voice upload failed. Try the text fallback.'); setStatus('IDLE') }
      };
      recorder.start(); setRecording(recorder); setStatus('LISTENING'); setMessage('');
    } catch { setMessage('Microphone permission was denied or is unavailable.'); setStatus('IDLE') }
  }
  const stopRecording = () => { recording?.stop(); setRecording(null) }
  const statCards = useMemo(() => seller && data ? [{ label: 'Revenue · 14 days', value: money(Number(seller.revenue)), change: pct(data.changes.revenue), positive: data.changes.revenue >= 0, icon: CircleDollarSign }, { label: 'Orders', value: Number(seller.orders).toLocaleString('en-IN'), change: pct(data.changes.orders), positive: data.changes.orders >= 0, icon: Package }, { label: 'Conversion rate', value: `${Number(seller.conversion).toFixed(2)}%`, change: `${data.changes.conversion > 0 ? '+' : ''}${data.changes.conversion.toFixed(2)} pts`, positive: data.changes.conversion >= 0, icon: Target }, { label: 'Average order value', value: money(Number(seller.aov)), change: pct(data.changes.aov), positive: data.changes.aov >= 0, icon: Gauge }] : [], [seller, data])
  const runSimulation = async () => {
    const product = products.find(item => item.id === simProductId) || products[0]
    if (!product) return
    const result = await fetch(`${API}/sellers/${sellerId}/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_id: product.id, new_price: Number(simPrice || product.price), days: Number(simDays) }) }).then(response => response.json())
    setSimulation(result)
  }
  const requestApproval = async () => {
    if (!simulation) return
    const result = await fetch(`${API}/sellers/${sellerId}/approvals`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_id: simulation.product_id, action: `Test ₹${simulation.new_price} price for ${simulation.days} days` }) }).then(response => response.json())
    setApprovals(old => [result, ...old]); setView('approvals')
  }
  const updateApproval = async (id: string, status: string) => {
    await fetch(`${API}/approvals/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
    setApprovals(old => old.map(item => item.id === id ? { ...item, status } : item))
  }

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-mark"><Sparkles size={18} /></div><div><strong>virtual<span>KAM</span></strong><small>seller growth autopilot</small></div></div><div className="workspace-label">WORKSPACE</div><div className="seller-select"><div className="avatar">{seller?.name?.slice(0, 1) || 'A'}</div><div><b>{seller?.name || 'Loading seller...'}</b><small>{seller?.id || 'Seller profile'}</small></div><ChevronDown size={16} /></div><nav><a className={view === 'overview' ? 'active' : ''} onClick={() => setView('overview')}><BarChart3 size={18} /> Overview</a><a className={view === 'radar' ? 'active' : ''} onClick={() => setView('radar')}><Bot size={18} /> Growth Radar</a><a className={view === 'simulator' ? 'active' : ''} onClick={() => setView('simulator')}><Target size={18} /> Price simulator</a><a className={view === 'approvals' ? 'active' : ''} onClick={() => setView('approvals')}><Check size={18} /> Approvals</a><a className={view === 'memory' ? 'active' : ''} onClick={() => setView('memory')}><Clock3 size={18} /> Growth memory</a></nav><div className="sidebar-bottom"><div className="system-status"><span></span><div><b>Demo workspace</b><small>All data is synthetic</small></div></div><div className="side-note">Built for seller decisions.<br />Grounded in measurable signals.</div></div></aside>
    <main className="main"><header className="topbar"><div><div className="eyebrow">{seller?.category || 'Seller workspace'} / {seller?.location || 'India'}</div><h1>Good morning, {seller?.name?.split(' ')[0] || 'seller'}.</h1></div><div className="top-actions"><div className="data-pill"><span className="dot"></span> Synthetic data <span className="divider"></span> Updated just now</div><button className="icon-button" aria-label="Notifications"><Bell size={18} /><span className="notification-dot"></span></button><div className="user-chip">AK</div></div></header>
      <section className="hero-row"><div><p className="section-kicker">SELLER PERFORMANCE</p><h2>Your business, at a glance.</h2><p className="muted">A calm view of what changed, what matters, and what to do next.</p></div><div className="seller-switcher"><label>Viewing seller</label><select value={sellerId} onChange={event => setSellerId(event.target.value)}>{sellers.map(item => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}</select></div></section>
      {view !== 'overview' && <section className="panel tool-panel"><div className="panel-head"><div><p className="section-kicker">SELLER TOOLS</p><h3>{view === 'radar' ? 'Growth Radar' : view === 'simulator' ? 'Price simulator' : view === 'approvals' ? 'Approval workflow' : 'Growth memory'}</h3></div><span className="panel-sub">{seller?.name}</span></div>{view === 'radar' && <div className="tool-grid">{signals.map(signal => <div className="tool-item" key={signal.id}><div><b>{signal.label}</b><span className={`priority ${signal.priority}`}>{signal.priority}</span></div><strong>{signal.value > 0 ? '+' : ''}{signal.value}{signal.unit}</strong><small>{signal.direction === 'down' ? 'Needs attention' : 'Positive movement'}</small></div>)}</div>}{view === 'simulator' && <div className="simulator-form"><label>Product<select value={simProductId || products[0]?.id || ''} onChange={event => setSimProductId(event.target.value)}>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label><label>Test price<input type="number" value={simPrice} placeholder={String(products.find(item => item.id === (simProductId || products[0]?.id))?.price || '')} onChange={event => setSimPrice(event.target.value)} /></label><label>Days<input type="number" min="1" max="30" value={simDays} onChange={event => setSimDays(event.target.value)} /></label><button className="primary-button" onClick={runSimulation}>Run simulation</button>{simulation && <div className="simulation-result"><b>{simulation.product}</b><span>{money(Number(simulation.projected_revenue))} projected revenue · {simulation.projected_orders} orders · {simulation.projected_margin}% margin</span><small>{simulation.assumption}</small><button className="secondary-button" onClick={requestApproval}>Request approval</button></div>}</div>}{view === 'approvals' && <div className="memory-list">{approvals.length ? approvals.map(item => <div className="memory-entry" key={item.id}><div><b>{item.action}</b><small>{item.product_id} · {new Date(item.created_at).toLocaleString()}</small></div>{item.status === 'pending' ? <span className="approval-actions"><button onClick={() => updateApproval(item.id, 'approved')} aria-label="Approve"><Check size={15} /></button><button onClick={() => updateApproval(item.id, 'rejected')} aria-label="Reject">×</button></span> : <span className={`status ${item.status}`}>{item.status}</span>}</div>) : <p className="muted">No approval requests yet. Run a price simulation to create one.</p>}</div>}{view === 'memory' && <div className="memory-list">{memory.length ? memory.map(entry => <div className="memory-entry" key={entry.id}><div><b>{entry.role === 'user' ? 'You' : 'Virtual KAM'}</b><p>{entry.content}</p></div><small>{new Date(entry.created_at).toLocaleString()}</small></div>) : <p className="muted">Your KAM conversations will appear here after the first message.</p>}</div>}</section>}
      <section className={view === 'overview' ? 'stat-grid' : 'stat-grid hidden'}>{statCards.map(card => <div className="stat-card" key={card.label}><div className={`stat-icon ${card.positive ? 'green' : 'red'}`}><card.icon size={18} /></div><div className="stat-label">{card.label}</div><div className="stat-value">{card.value}</div><div className={`stat-change ${card.positive ? 'positive' : 'negative'}`}>{card.positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{card.change}<span>vs previous 14 days</span></div></div>)}</section>
      <section className={view === 'overview' ? 'dashboard-grid' : 'dashboard-grid hidden'}><div className="panel trend-panel"><div className="panel-head"><div><h3>Revenue trend</h3><span className="panel-sub">Daily revenue · last 14 days</span></div><div className="trend-callout">{(data?.sales_change || 0) < 0 ? <TrendingDown size={15} /> : <ArrowUpRight size={15} />}<b>{Math.abs(data?.sales_change || 0).toFixed(1)}%</b><span>{(data?.sales_change || 0) < 0 ? 'decline detected' : 'growth detected'}</span></div></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data?.trend || []}><defs><linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#e56b4f" stopOpacity={0.25} /><stop offset="100%" stopColor="#e56b4f" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e7e9e3" /><XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fill: '#8b9188', fontSize: 11 }} interval={2} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#8b9188', fontSize: 11 }} tickFormatter={value => `₹${Math.round(value / 1000)}k`} /><Tooltip formatter={value => [money(Number(value)), 'Revenue']} contentStyle={{ border: '1px solid #e8ebe4', borderRadius: 8, boxShadow: '0 8px 24px #17211912' }} /><Area type="monotone" dataKey="revenue" stroke="#d85e44" strokeWidth={2.5} fill="url(#revenueFill)" /></AreaChart></ResponsiveContainer></div></div>
        <div className="panel kam-panel"><div className="panel-head"><div><p className="section-kicker">VOICE-FIRST</p><h3>Your Virtual KAM</h3></div><span className="live-badge"><span></span> ready</span></div><div className={`voice-orb ${status.toLowerCase()}`}><div className="orb-ring ring-one"></div><div className="orb-ring ring-two"></div><div className="orb-core">{status === 'LISTENING' ? <Activity size={29} /> : status === 'THINKING' ? <Sparkles size={29} /> : status === 'SPEAKING' ? <Volume2 size={29} /> : <Mic size={29} />}</div></div><div className="voice-state">{status === 'IDLE' ? 'Ask me about your business' : status === 'LISTENING' ? 'Listening...' : status === 'THINKING' ? 'Analysing your numbers...' : 'Speaking...'}</div><div className="voice-transcript">{transcript.length ? <><b>{transcript[transcript.length - 1].role === 'seller' ? 'You' : 'Virtual KAM'}</b><p>{transcript[transcript.length - 1].text}</p></> : <p>“My sales have dropped. Can you help?”</p>}</div><div className="voice-actions"><button className={`mic-button ${status === 'LISTENING' ? 'recording' : ''}`} onClick={status === 'LISTENING' ? stopRecording : startRecording}>{status === 'LISTENING' ? <Square size={17} /> : <Mic size={21} />}</button><button className="replay-button" onClick={() => transcript.length && setStatus('SPEAKING')}><RotateCcw size={15} /> Replay</button></div><div className="text-input"><input value={message} onChange={event => setMessage(event.target.value)} onKeyDown={event => event.key === 'Enter' && sendMessage()} placeholder="Or type to your KAM..." /><button onClick={() => sendMessage()} aria-label="Send message"><Send size={16} /></button></div></div></section>
      <footer><span>Virtual KAM · internal demo</span><span>Metrics are synthetic and decisions are simulated</span></footer>
    </main>
  </div>
}

export default App
