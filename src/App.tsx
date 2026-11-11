import { useEffect, useRef, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Check, Mic, Phone, Play, RotateCcw, Sparkles, Square, Volume2, X } from 'lucide-react'

type BrowserSpeechRecognition = { continuous: boolean; interimResults: boolean; lang: string; onresult: ((event: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null; onerror: ((event: { error: string }) => void) | null; onend: (() => void) | null; start: () => void; stop: () => void }
type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition
declare global { interface Window { SpeechRecognition?: BrowserSpeechRecognitionConstructor; webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor } }

type Seller = { id: string; name: string; category: string; location: string; synthetic: boolean }
type Radar = { opening_line: string; top_issue: string; decline_percent: number }
type Trace = { tool: string; args?: Record<string, string | number>; result_summary: string; hypothesis: string; verdict: 'checking' | 'ruled out' | 'flagged' }
type Action = { id: string; type: string; status: 'proposed' | 'approved' | 'executed'; params?: Record<string, string | number>; estimated_impact?: Record<string, string | number> }
type Advance = { before: { orders: number; conversion: number }; after: { orders: number; conversion: number }; callback: string; assumptions: string[] }
type TrendPoint = { day: string; revenue: number }

const API = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
const seller: Seller = { id: 'SEL-10482', name: 'Aarav Threads', category: 'Fashion & Apparel', location: 'Jaipur, Rajasthan', synthetic: true }
const hypotheses = ['traffic', 'conversion', 'price', 'inventory', 'ratings']

function App() {
  const [radar, setRadar] = useState<Radar | null>(null)
  const [stage, setStage] = useState<'incoming' | 'call' | 'callback'>('incoming')
  const [status, setStatus] = useState<'idle' | 'listening' | 'thinking' | 'speaking'>('idle')
  const [caption, setCaption] = useState('')
  const [text, setText] = useState('')
  const [trace, setTrace] = useState<Trace[]>([])
  const [actions, setActions] = useState<Action[]>([])
  const [lastSpoken, setLastSpoken] = useState('')
  const [language, setLanguage] = useState('en-IN')
  const [advance, setAdvance] = useState<Advance | null>(null)
  const [trend, setTrend] = useState<TrendPoint[]>([])
  const [history, setHistory] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [audioError, setAudioError] = useState('')
  const recorder = useRef<MediaRecorder | null>(null)
  const recognition = useRef<BrowserSpeechRecognition | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    fetch(`${API}/sellers/${seller.id}/radar`).then(response => response.json()).then(setRadar)
    fetch(`${API}/sellers/${seller.id}/analytics`).then(response => response.json()).then(result => setTrend(result.trend || []))
    fetch(`${API}/sellers/${seller.id}/actions`).then(response => response.json()).then(setActions).catch(() => undefined)
  }, [])

  const speak = async (value: string) => {
    setLastSpoken(value); setCaption(value); setStatus('speaking'); setAudioError('')
    audioRef.current?.pause(); audioRef.current = null
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    try {
      const response = await fetch(`${API}/voice/synthesize`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: value, language }) })
      const result = await response.json()
      if (result.audio_base64) {
        const audio = new Audio(`data:audio/${result.audio_format || 'wav'};base64,${result.audio_base64}`)
        audioRef.current = audio; audio.onended = () => setStatus('idle'); audio.onerror = () => setStatus('idle')
        try { await audio.play() } catch { setAudioError('Tap to hear the latest reply.'); setStatus('idle') }
        return
      }
      if ('speechSynthesis' in window && result.speech_text) {
        const utterance = new SpeechSynthesisUtterance(result.speech_text)
        utterance.lang = language
        await new Promise<void>(resolve => { utterance.onend = () => { setStatus('idle'); resolve() }; utterance.onerror = () => { setStatus('idle'); resolve() }; window.speechSynthesis.speak(utterance) })
        return
      }
    } catch (error) { setAudioError(error instanceof Error ? error.message : 'Voice playback failed. Tap to hear the reply.') }
    setStatus('idle')
  }

  const send = async (value: string) => {
    if (!value.trim() || status === 'thinking') return
    setStatus('thinking'); setCaption('Checking the business signals...'); setText('')
    try {
      const response = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seller_id: seller.id, message: value, history: history.slice(-10), language }) })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
      const result = await response.json()
      setTrace([])
      ;(result.trace || []).forEach((item: Trace, index: number) => window.setTimeout(() => setTrace(previous => [...previous, item]), index * 400))
      setActions(result.actions || [])
      const assistantResponse = String(result.response || '')
      setHistory(previous => [...previous, { role: 'user' as const, content: value }, { role: 'assistant' as const, content: assistantResponse }].slice(-10))
      await speak(assistantResponse)
    } catch (error) { setCaption(error instanceof Error ? error.message : 'The KAM could not reach the server. Try again.') } finally { setStatus(previous => previous === 'thinking' ? 'idle' : previous) }
  }

  const listen = async () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SpeechRecognition) {
      const current = new SpeechRecognition(); current.continuous = false; current.interimResults = true; current.lang = language
      current.onresult = event => {
        const transcript = Array.from({ length: event.results.length - event.resultIndex }, (_, index) => event.results[event.resultIndex + index][0].transcript).join(' ').trim()
        if (transcript) setCaption(transcript)
        const finalResult = event.results[event.results.length - 1]
        if (finalResult?.isFinal && transcript) void send(transcript)
      }
      current.onerror = event => { recognition.current = null; setCaption(event.error === 'not-allowed' ? 'Microphone access was blocked. Allow mic access or use text.' : 'I could not hear that. Try again or use text.'); setStatus('idle') }
      current.onend = () => { recognition.current = null; setStatus(previous => previous === 'listening' ? 'idle' : previous) }
      recognition.current = current; setStatus('listening'); setCaption('Listening...'); current.start(); return
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { setCaption('Voice input is not supported here. Use the text fallback below.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); const chunks: Blob[] = []; const current = new MediaRecorder(stream)
      current.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      current.onstop = async () => { stream.getTracks().forEach(track => track.stop()); const form = new FormData(); form.append('file', new Blob(chunks, { type: current.mimeType || 'audio/webm' }), 'recording.webm'); try { const result = await fetch(`${API}/voice/transcribe`, { method: 'POST', body: form }).then(response => response.json()); if (result.text) { await send(result.text); return }; setCaption(result.message || 'I could not hear that. Try again or use text.'); setStatus('idle') } catch { setCaption('Voice transcription failed. Use the text fallback below.'); setStatus('idle') } }
      recorder.current = current; current.start(); setStatus('listening'); setCaption('Listening...')
    } catch { setCaption('Microphone access was unavailable. Use the text fallback below.'); setStatus('idle') }
  }

  const accept = async () => { setStage('call'); setTrace([]); if (radar) await speak(radar.opening_line); await send('Please diagnose the sales drop and propose the next action.') }
  const advanceDays = async () => { try { const response = await fetch(`${API}/simulate/advance`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seller_id: seller.id, days: 3 }) }); if (!response.ok) throw new Error(`Simulation failed (${response.status})`); const result = await response.json(); setAdvance(result); setStage('callback'); await speak(result.callback) } catch (error) { setCaption(error instanceof Error ? error.message : 'Simulation failed. Try again.') } }
  const replay = () => { if (lastSpoken) void speak(lastSpoken) }

  if (stage === 'incoming') return <main className="incoming"><div className="incoming-glow" /><div className="caller-mark"><Sparkles size={26} /></div><p className="eyebrow">INCOMING BUSINESS CALL · SYNTHETIC DEMO</p><h1>Snapdeal Virtual KAM<br /><span>is calling.</span></h1><p className="incoming-line">{radar?.opening_line || 'I am checking your latest business signals now.'}</p><div className="caller-name"><b>{seller.name}</b><span>{seller.category} · {seller.location}</span></div><div className="call-actions"><button className="decline" onClick={() => setStage('call')}><X size={20} /> Decline</button><button className="accept" onClick={() => void accept()}><Phone size={20} /> Accept call</button></div><small>All metrics are synthetic. Marketplace actions are mock operations.</small></main>

  return <main className="workspace">
    <header className="topbar"><div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><b>virtual<span>KAM</span></b><small>seller ownership desk</small></div><div className="top-right"><span className="synthetic-dot" /> Synthetic seller data <select value={language} onChange={event => setLanguage(event.target.value)}><option value="en-IN">English · India</option><option value="hi-IN">Hindi · India</option></select></div></header>
    <section className="call-header"><div><p className="eyebrow">ACTIVE CASE · {seller.id}</p><h1>{stage === 'callback' ? 'The result is in.' : 'Let’s solve the drop.'}</h1><p>{stage === 'callback' ? 'Three days after the approved mock action.' : 'I am checking the evidence, then I will own the next action with you.'}</p></div><div className={`live-state ${status}`}><span /> {status === 'listening' ? 'Listening' : status === 'thinking' ? 'Analysing' : status === 'speaking' ? 'Speaking' : 'On the call'}</div></section>
    <section className="trend-panel panel"><div className="panel-title"><div><p className="eyebrow">14-DAY REVENUE TREND</p><h2>{radar ? `Down ${radar.decline_percent.toFixed(1)}%` : 'Loading trend'}</h2></div><span>Observed synthetic revenue</span></div><div className="trend-chart"><ResponsiveContainer width="100%" height={170}><LineChart data={trend}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dfe6dc" /><XAxis dataKey="day" hide /><YAxis hide /><Tooltip formatter={value => [`₹${String(value ?? '')}`, 'Revenue']} /><Line type="monotone" dataKey="revenue" stroke="#3d7658" strokeWidth={3} dot={false} /></LineChart></ResponsiveContainer>{advance && <span className="trend-overlay">After action: {advance.after.orders} simulated 3-day orders</span>}</div></section>
    <section className="case-grid"><div className="evidence panel"><div className="panel-title"><div><p className="eyebrow">LIVE EVIDENCE BOARD</p><h2>What is driving the drop?</h2></div><span>{trace.length}/5 checks</span></div><div className="evidence-list">{hypotheses.map((name, index) => { const item = trace[index]; return <article className={`evidence-card ${item?.verdict || 'checking'}`} key={name}><div className="evidence-icon">{item?.verdict === 'ruled out' ? <X size={15} /> : item?.verdict === 'flagged' ? <span>!</span> : <span className="spinner" />}</div><div><b>{name}</b><p>{item?.result_summary || 'Checking the latest signal...'}</p></div><strong>{item?.verdict || 'checking'}</strong></article> })}</div></div><aside className="side-column"><div className="panel caption-panel"><p className="eyebrow">LIVE CAPTION</p><div className="caption">{caption || 'Your KAM is ready when you are.'}</div>{audioError && <button className="audio-retry" onClick={() => void speak(lastSpoken)}>Tap to hear</button>}<div className="voice-controls"><button className={`mic ${status === 'listening' ? 'active' : ''}`} onClick={status === 'listening' ? () => { recognition.current?.stop(); recorder.current?.stop() } : listen}>{status === 'listening' ? <Square size={18} /> : <Mic size={20} />}</button><button className="replay" onClick={replay}><RotateCcw size={15} /> Replay</button></div><div className="text-fallback"><input value={text} onChange={event => setText(event.target.value)} onKeyDown={event => event.key === 'Enter' && void send(text)} placeholder="Text fallback" /><button onClick={() => void send(text)}>Send</button></div></div><div className="panel ledger"><div className="panel-title"><div><p className="eyebrow">ACTION LEDGER</p><h2>Next action</h2></div><Check size={18} /></div>{actions.length === 0 ? <p className="empty">Evidence will unlock a concrete plan.</p> : actions.slice(0, 2).map(action => <div className="action" key={action.id}><div><b>{action.type === 'price_and_restock' ? 'Cut price + restock' : action.type}</b><p>{action.params?.new_price ? `₹${action.params.new_price} for ${action.params.days} days · ${action.params.restock_units} units` : 'Mock marketplace operation'}</p></div><span className={`chip ${action.status}`}>{action.status === 'executed' ? 'Executed · mock' : action.status}</span><small>{action.estimated_impact ? Object.values(action.estimated_impact).join(' · ') : ''}</small></div>)}</div></aside></section>
    <section className="bottom-bar"><div><span className="case-dot" /> {stage === 'callback' ? 'Simulated result' : 'Diagnosis in progress'}<small>{stage === 'callback' && advance ? `${advance.before.conversion}% → ${advance.after.conversion}% conversion` : 'The board updates from real analytics tool calls.'}</small></div>{stage === 'callback' ? <button className="primary" onClick={replay}><Volume2 size={17} /> Hear callback again</button> : <button className="primary" onClick={() => void advanceDays()} disabled={!actions.some(action => action.status === 'executed')}><Play size={16} /> Fast-forward 3 days</button>}</section>
    {advance && <section className="result-strip"><b>Simulated 3-day outcome</b><span>Orders {advance.before.orders} → {advance.after.orders}</span><span>Conversion {advance.before.conversion}% → {advance.after.conversion}%</span><small>{advance.assumptions.join(' · ')}</small></section>}
    <footer><span>Snapdeal Virtual KAM · internal demo</span><span>{seller.name} · synthetic data · mock actions</span></footer>
  </main>
}

export default App
