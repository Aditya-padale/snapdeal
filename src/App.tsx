import { useEffect, useMemo, useRef, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, Bell, Bot, ChevronDown, CircleDollarSign, Clock3, Gauge, Mic, Package, RotateCcw, Send, Sparkles, Square, Target, TrendingDown, Volume2 } from 'lucide-react'

type Seller = { id: string; name: string; category: string; location: string; synthetic: boolean }
type SellerData = { seller: Seller & Record<string, number | string | boolean>; trend: { day: string; revenue: number }[]; sales_change: number; avg_competitor_gap: number; observations: { impressions_stable: boolean; conversion_decline: number; top_product: string } }
type Product = { id: string; name: string; price: number; competitor_price: number; conversion: number; previous_conversion: number; inventory: number; velocity: number; rating: number; views: number; orders: number; margin: number }

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
  const audioChunks = useRef<Blob[]>([])
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const seller = data?.seller
  const topProduct = products[0]

  useEffect(() => { fetch(`${API}/sellers`).then(r => r.json()).then(setSellers).catch(() => setSellers([{ id: 'SEL-10482', name: 'Aarav Threads', category: 'Fashion & Apparel', location: 'Jaipur, Rajasthan', synthetic: true }])) }, [])
  useEffect(() => {
    Promise.all([fetch(`${API}/sellers/${sellerId}/analytics`).then(r => r.json()), fetch(`${API}/sellers/${sellerId}/products`).then(r => r.json())]).then(([analytics, productList]) => { setData(analytics); setProducts(productList) }).catch(() => undefined)
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
  const statCards = useMemo(() => seller ? [{ label: 'Revenue · 14 days', value: money(Number(seller.revenue)), change: '-28.0%', icon: CircleDollarSign, tone: 'red' }, { label: 'Orders', value: Number(seller.orders).toLocaleString('en-IN'), change: '-24.6%', icon: Package, tone: 'amber' }, { label: 'Conversion rate', value: `${Number(seller.conversion).toFixed(2)}%`, change: '-1.76 pts', icon: Target, tone: 'red' }, { label: 'Average order value', value: money(Number(seller.aov)), change: '+4.2%', icon: Gauge, tone: 'green' }] : [], [seller])

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-mark"><Sparkles size={18} /></div><div><strong>virtual<span>KAM</span></strong><small>seller growth autopilot</small></div></div><div className="workspace-label">WORKSPACE</div><div className="seller-select"><div className="avatar">{seller?.name?.slice(0, 1) || 'A'}</div><div><b>{seller?.name || 'Loading seller...'}</b><small>{seller?.id || 'Seller profile'}</small></div><ChevronDown size={16} /></div><nav><a className="active"><BarChart3 size={18} /> Overview</a><a><Bot size={18} /> Virtual KAM <i>live</i></a><a><Clock3 size={18} /> Growth memory</a></nav><div className="sidebar-bottom"><div className="system-status"><span></span><div><b>Demo workspace</b><small>All data is synthetic</small></div></div><div className="side-note">Built for seller decisions.<br />Grounded in measurable signals.</div></div></aside>
    <main className="main"><header className="topbar"><div><div className="eyebrow">{seller?.category || 'Seller workspace'} / {seller?.location || 'India'}</div><h1>Good morning, {seller?.name?.split(' ')[0] || 'seller'}.</h1></div><div className="top-actions"><div className="data-pill"><span className="dot"></span> Synthetic data <span className="divider"></span> Updated just now</div><button className="icon-button" aria-label="Notifications"><Bell size={18} /><span className="notification-dot"></span></button><div className="user-chip">AK</div></div></header>
      <section className="hero-row"><div><p className="section-kicker">SELLER PERFORMANCE</p><h2>Your business, at a glance.</h2><p className="muted">A calm view of what changed, what matters, and what to do next.</p></div><div className="seller-switcher"><label>Viewing seller</label><select value={sellerId} onChange={event => setSellerId(event.target.value)}>{sellers.map(item => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}</select></div></section>
      <section className="stat-grid">{statCards.map(card => <div className="stat-card" key={card.label}><div className={`stat-icon ${card.tone}`}><card.icon size={18} /></div><div className="stat-label">{card.label}</div><div className="stat-value">{card.value}</div><div className={`stat-change ${card.tone === 'green' ? 'positive' : 'negative'}`}>{card.tone === 'green' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{card.change}<span>vs previous 14 days</span></div></div>)}</section>
      <section className="dashboard-grid"><div className="panel trend-panel"><div className="panel-head"><div><h3>Revenue trend</h3><span className="panel-sub">Daily revenue · last 14 days</span></div><div className="trend-callout"><TrendingDown size={15} /><b>28%</b><span>decline detected</span></div></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data?.trend || []}><defs><linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#e56b4f" stopOpacity={0.25} /><stop offset="100%" stopColor="#e56b4f" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e7e9e3" /><XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fill: '#8b9188', fontSize: 11 }} interval={2} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#8b9188', fontSize: 11 }} tickFormatter={value => `₹${Math.round(value / 1000)}k`} /><Tooltip formatter={value => [money(Number(value)), 'Revenue']} contentStyle={{ border: '1px solid #e8ebe4', borderRadius: 8, boxShadow: '0 8px 24px #17211912' }} /><Area type="monotone" dataKey="revenue" stroke="#d85e44" strokeWidth={2.5} fill="url(#revenueFill)" /></AreaChart></ResponsiveContainer></div></div>
        <div className="panel kam-panel"><div className="panel-head"><div><p className="section-kicker">VOICE-FIRST</p><h3>Your Virtual KAM</h3></div><span className="live-badge"><span></span> ready</span></div><div className={`voice-orb ${status.toLowerCase()}`}><div className="orb-ring ring-one"></div><div className="orb-ring ring-two"></div><div className="orb-core">{status === 'LISTENING' ? <Activity size={29} /> : status === 'THINKING' ? <Sparkles size={29} /> : status === 'SPEAKING' ? <Volume2 size={29} /> : <Mic size={29} />}</div></div><div className="voice-state">{status === 'IDLE' ? 'Ask me about your business' : status === 'LISTENING' ? 'Listening...' : status === 'THINKING' ? 'Analysing your numbers...' : 'Speaking...'}</div><div className="voice-transcript">{transcript.length ? <><b>{transcript[transcript.length - 1].role === 'seller' ? 'You' : 'Virtual KAM'}</b><p>{transcript[transcript.length - 1].text}</p></> : <p>“My sales have dropped. Can you help?”</p>}</div><div className="voice-actions"><button className={`mic-button ${status === 'LISTENING' ? 'recording' : ''}`} onClick={status === 'LISTENING' ? stopRecording : startRecording}>{status === 'LISTENING' ? <Square size={17} /> : <Mic size={21} />}</button><button className="replay-button" onClick={() => transcript.length && setStatus('SPEAKING')}><RotateCcw size={15} /> Replay</button></div><div className="text-input"><input value={message} onChange={event => setMessage(event.target.value)} onKeyDown={event => event.key === 'Enter' && sendMessage()} placeholder="Or type to your KAM..." /><button onClick={() => sendMessage()} aria-label="Send message"><Send size={16} /></button></div></div></section>
      <footer><span>Virtual KAM · internal demo</span><span>Metrics are synthetic and decisions are simulated</span></footer>
    </main>
  </div>
}

export default App
