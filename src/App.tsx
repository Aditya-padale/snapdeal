import { useEffect, useRef, useState } from 'react'
import { Check, Mic, Phone, Play, RotateCcw, Sparkles, Square, Volume2, X } from 'lucide-react'

type Seller = { id: string; name: string; category: string; location: string; synthetic: boolean }
type Radar = { opening_line: string; top_issue: string; decline_percent: number }
type Trace = { tool: string; result_summary: string; hypothesis: string; verdict: 'checking' | 'ruled out' | 'flagged' }
type Action = { id: string; type: string; status: 'proposed' | 'approved' | 'executed'; params?: Record<string, string | number>; estimated_impact?: Record<string, string | number> }
type Advance = { before: { orders: number; conversion: number }; after: { orders: number; conversion: number }; callback: string; assumptions: string[] }
type Recognition = { lang: string; start: () => void; stop: () => void; onresult: ((event: any) => void) | null; onerror: (() => void) | null; onend: (() => void) | null }

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
  const recognition = useRef<Recognition | null>(null)

  useEffect(() => {
    fetch(`${API}/sellers/${seller.id}/radar`).then(response => response.json()).then(setRadar)
    fetch(`${API}/sellers/${seller.id}/actions`).then(response => response.json()).then(setActions).catch(() => undefined)
  }, [])

  const speak = async (value: string) => {
    setLastSpoken(value); setCaption(value); setStatus('speaking')
    try {
      const result = await fetch(`${API}/voice/synthesize`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: value }) }).then(response => response.json())
      if (result.audio_url) {
        const audio = new Audio(`${API.replace(/\/api$/, '')}${result.audio_url}`)
        audio.onended = () => setStatus('idle')
        audio.onerror = () => setStatus('idle')
        await audio.play()
        return
      }
      if ('speechSynthesis' in window && result.speech_text) {
        window.speechSynthesis.cancel()
        const utterance = new SpeechSynthesisUtterance(result.speech_text)
        utterance.lang = language; utterance.onend = () => setStatus('idle'); window.speechSynthesis.speak(utterance)
        return
      }
    } catch {
      setStatus('idle')
      return
    }
    setStatus('idle')
  }
  const send = async (value: string) => {
    if (!value.trim() || status === 'thinking') return
    setStatus('thinking'); setCaption('Checking the business signals...'); setText('')
    const result = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seller_id: seller.id, message: value, history: [] }) }).then(response => response.json())
    setTrace(result.trace || []); setActions(result.actions || []); speak(result.response)
  }
  const listen = () => {
    const scope = window as Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }
    const RecognitionApi = scope.SpeechRecognition || scope.webkitSpeechRecognition
    if (!RecognitionApi) { setCaption('Voice input is not supported here. Use the text fallback below.'); return }
    const current = new RecognitionApi()
    current.lang = language; current.onresult = event => send(event.results[0][0].transcript); current.onerror = () => { setCaption('I could not hear that. Try again or use text.'); setStatus('idle') }; current.onend = () => { recognition.current = null; setStatus('idle') }
    recognition.current = current; current.start(); setStatus('listening'); setCaption('Listening...')
  }
  const accept = () => { setStage('call'); setTrace([]); if (radar) speak(radar.opening_line); void send('Please diagnose the sales drop and propose the next action.') }
  const advanceDays = async () => {
    const result = await fetch(`${API}/simulate/advance`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seller_id: seller.id, days: 3 }) }).then(response => response.json())
    setAdvance(result); setStage('callback'); speak(result.callback)
  }
  const replay = () => { if (lastSpoken) speak(lastSpoken) }

  if (stage === 'incoming') return <main className="incoming"><div className="incoming-glow" /><div className="caller-mark"><Sparkles size={26} /></div><p className="eyebrow">INCOMING BUSINESS CALL · SYNTHETIC DEMO</p><h1>Snapdeal Virtual KAM<br /><span>is calling.</span></h1><p className="incoming-line">{radar?.opening_line || 'I am checking your latest business signals now.'}</p><div className="caller-name"><b>{seller.name}</b><span>{seller.category} · {seller.location}</span></div><div className="call-actions"><button className="decline" onClick={() => setStage('call')}><X size={20} /> Decline</button><button className="accept" onClick={accept}><Phone size={20} /> Accept call</button></div><small>All metrics are synthetic. Marketplace actions are mock operations.</small></main>

  return <main className="workspace">
    <header className="topbar"><div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><b>virtual<span>KAM</span></b><small>seller ownership desk</small></div><div className="top-right"><span className="synthetic-dot" /> Synthetic seller data <select value={language} onChange={event => setLanguage(event.target.value)}><option value="en-IN">English · India</option><option value="hi-IN">Hindi · India</option></select></div></header>
    <section className="call-header"><div><p className="eyebrow">ACTIVE CASE · {seller.id}</p><h1>{stage === 'callback' ? 'The result is in.' : 'Let’s solve the drop.'}</h1><p>{stage === 'callback' ? 'Three days after the approved mock action.' : 'I am checking the evidence, then I will own the next action with you.'}</p></div><div className={`live-state ${status}`}><span /> {status === 'listening' ? 'Listening' : status === 'thinking' ? 'Analysing' : status === 'speaking' ? 'Speaking' : 'On the call'}</div></section>
    <section className="case-grid"><div className="evidence panel"><div className="panel-title"><div><p className="eyebrow">LIVE EVIDENCE BOARD</p><h2>What is driving the drop?</h2></div><span>{trace.length}/5 checks</span></div><div className="evidence-list">{hypotheses.map((name, index) => { const item = trace[index]; return <article className={`evidence-card ${item?.verdict || 'checking'}`} key={name}><div className="evidence-icon">{item?.verdict === 'ruled out' ? <X size={15} /> : item?.verdict === 'flagged' ? <span>!</span> : <span className="spinner" />}</div><div><b>{name}</b><p>{item?.result_summary || 'Checking the latest signal...'}</p></div><strong>{item?.verdict || 'checking'}</strong></article> })}</div></div><aside className="side-column"><div className="panel caption-panel"><p className="eyebrow">LIVE CAPTION</p><div className="caption">{caption || 'Your KAM is ready when you are.'}</div><div className="voice-controls"><button className={`mic ${status === 'listening' ? 'active' : ''}`} onClick={status === 'listening' ? () => recognition.current?.stop() : listen}>{status === 'listening' ? <Square size={18} /> : <Mic size={20} />}</button><button className="replay" onClick={replay}><RotateCcw size={15} /> Replay</button></div><div className="text-fallback"><input value={text} onChange={event => setText(event.target.value)} onKeyDown={event => event.key === 'Enter' && send(text)} placeholder="Text fallback" /><button onClick={() => send(text)}>Send</button></div></div><div className="panel ledger"><div className="panel-title"><div><p className="eyebrow">ACTION LEDGER</p><h2>Next action</h2></div><Check size={18} /></div>{actions.length === 0 ? <p className="empty">Evidence will unlock a concrete plan.</p> : actions.slice(0, 2).map(action => <div className="action" key={action.id}><div><b>{action.type === 'price_and_restock' ? 'Cut price + restock' : action.type}</b><p>{action.params?.new_price ? `₹${action.params.new_price} for ${action.params.days} days · ${action.params.restock_units} units` : 'Mock marketplace operation'}</p></div><span className={`chip ${action.status}`}>{action.status === 'executed' ? 'Executed · mock' : action.status}</span><small>{action.estimated_impact ? Object.values(action.estimated_impact).join(' · ') : ''}</small></div>)}</div></aside></section>
    <section className="bottom-bar"><div><span className="case-dot" /> {stage === 'callback' ? 'Measured result' : 'Diagnosis in progress'}<small>{stage === 'callback' && advance ? `${advance.before.conversion}% → ${advance.after.conversion}% conversion` : 'The board updates from real analytics tool calls.'}</small></div>{stage === 'callback' ? <button className="primary" onClick={replay}><Volume2 size={17} /> Hear callback again</button> : <button className="primary" onClick={advanceDays} disabled={!actions.some(action => action.status === 'executed')}><Play size={16} /> Fast-forward 3 days</button>}</section>
    {advance && <section className="result-strip"><b>Measured after 3 days</b><span>Orders {advance.before.orders} → {advance.after.orders}</span><span>Conversion {advance.before.conversion}% → {advance.after.conversion}%</span><small>{advance.assumptions.join(' · ')}</small></section>}
    <footer><span>Snapdeal Virtual KAM · internal demo</span><span>{seller.name} · synthetic data · mock actions</span></footer>
  </main>
}

export default App
