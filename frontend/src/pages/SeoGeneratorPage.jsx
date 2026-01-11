import React, { useState } from 'react';
import { Wand2, Clock, Loader2, Sparkles, Copy, X, BrainCircuit, Layers, Table, HelpCircle, FileText, Download } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

const SeoGeneratorPage = () => {
    const [step, setStep] = useState(1);
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');
    
    // Keywords State
    const [keywords, setKeywords] = useState([]);
    const [newKeyword, setNewKeyword] = useState('');
    const [clusters, setClusters] = useState(null); // { topic: string, keywords: [] }[]
    
    // Config State
    const [tone, setTone] = useState('Продающий');
    const [titleLen, setTitleLen] = useState(100);
    const [descLen, setDescLen] = useState(1000);
    
    // Result State
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [historyOpen, setHistoryOpen] = useState(false);
    const [pdfLoading, setPdfLoading] = useState(false);

    const toneOptions = ["Продающий", "Информативный", "Дерзкий", "Формальный", "Дружелюбный"];

    const fetchKeywords = async () => {
        if (!sku) return;
        setLoading(true); setError('');
        try {
            const res = await fetch(`${API_URL}/api/seo/parse/${sku}`, { headers: getTgHeaders() });
            const data = await res.json();
            if (res.status !== 200) throw new Error(data.detail || data.message);
            setKeywords(data.keywords || []); 
            setClusters(null);
            setStep(2);
        } catch (e) { setError(e.message); } finally { setLoading(false); }
    };

    const handleClusterKeywords = async () => {
        setLoading(true);
        setStatus('Загрузка BERT модели...');
        try {
            const res = await fetch(`${API_URL}/api/seo/cluster`, { 
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ sku: Number(sku), keywords })
            });
            const data = await res.json();
            const taskId = data.task_id;
            
            let attempts = 0;
            while(attempts < 30) {
                await new Promise(r => setTimeout(r, 2000));
                const sRes = await fetch(`${API_URL}/api/monitor/status/${taskId}`);
                const sData = await sRes.json();
                
                if (sData.status === 'SUCCESS') {
                    setClusters(sData.data.clusters);
                    setLoading(false);
                    return;
                }
                if (sData.status === 'FAILURE') throw new Error(sData.error);
                if (sData.info) setStatus(sData.info);
                attempts++;
            }
        } catch (e) {
            setError('Ошибка кластеризации: ' + e.message);
        } finally {
            setLoading(false);
            setStatus('');
        }
    };

    const addKeyword = () => {
        if (newKeyword.trim() && !keywords.includes(newKeyword.trim())) {
            setKeywords([...keywords, newKeyword.trim()]);
            setNewKeyword('');
        }
    };

    const removeKeyword = (k) => {
        setKeywords(keywords.filter(w => w !== k));
    };

    const generateContent = async () => {
        setLoading(true);
        setStatus('Генерация GEO контента...');
        try {
            const res = await fetch(`${API_URL}/api/seo/generate`, { method: 'POST', headers: getTgHeaders(), body: JSON.stringify({ sku: Number(sku), keywords, tone, title_len: titleLen, desc_len: descLen }) });
            const data = await res.json();
            const taskId = data.task_id;
            let attempts = 0;
            while(attempts < 60) {
                await new Promise(r => setTimeout(r, 3000));
                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`);
                const sData = await sRes.json();
                if (sData.status === 'SUCCESS') { setResult(sData.data.generated_content); setStep(3); break; }
                if (sData.status === 'FAILURE') throw new Error(sData.error);
                attempts++;
            }
        } catch (e) { setError(e.message); } finally { setLoading(false); setStatus(''); }
    };

    const downloadPdf = async () => {
        if (!result) return;
        setPdfLoading(true);
        try {
            const payload = {
                sku: String(sku),
                title: result.title || "",
                description: result.description || "",
                features: result.structured_features || {},
                faq: result.faq || []
            };

            if (user?.plan === 'free') {
                alert("Скачивание PDF доступно только на тарифе PRO или Business");
                return;
            }

            const response = await fetch(`${API_URL}/api/report/seo-pdf/generate`, {
                method: 'POST',
                headers: {
                    ...getTgHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error("Ошибка генерации PDF");

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `SEO_Report_${sku}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (e) {
            alert("Не удалось скачать PDF: " + e.message);
        } finally {
            setPdfLoading(false);
        }
    };

    const CopyButton = ({ text }) => (
        <button onClick={() => {navigator.clipboard.writeText(text); alert("Скопировано!");}} className="p-2 text-slate-400 hover:text-indigo-600 transition-colors bg-slate-50 rounded-lg">
            <Copy size={16} />
        </button>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
                <div className="bg-gradient-to-r from-orange-500 to-pink-500 p-6 rounded-3xl text-white shadow-xl shadow-orange-200 flex-1 mr-4">
                    <h1 className="text-2xl font-black flex items-center gap-2"><Wand2 className="text-yellow-200" /> SEO Gen</h1>
                    <p className="text-sm opacity-90 mt-2">GEO-оптимизация 2026</p>
                </div>
                <button onClick={() => setHistoryOpen(true)} className="bg-white p-4 rounded-3xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors h-full"><Clock size={24}/></button>
            </div>
            
            <HistoryModule type="seo" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

            {/* STEP 1: Import */}
            {step === 1 && (
                 <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                    <h3 className="font-bold text-lg mb-4">Шаг 1. Импорт данных</h3>
                    <div className="relative mb-4">
                        <input
                            type="number"
                            placeholder="Артикул WB (SKU)"
                            className="w-full bg-slate-50 border-none rounded-2xl p-4 pl-4 font-bold outline-none focus:ring-2 ring-orange-200 transition-all text-slate-800"
                            value={sku}
                            onChange={(e) => setSku(e.target.value)}
                        />
                    </div>
                    {error && <p className="text-red-500 text-sm mb-4 bg-red-50 p-3 rounded-xl">{error}</p>}
                    <button onClick={fetchKeywords} disabled={loading} className="w-full bg-slate-900 text-white p-4 rounded-xl font-bold active:scale-95 transition-all flex justify-center">
                        {loading ? <Loader2 className="animate-spin" /> : 'Получить ключевые слова'}
                    </button>
                 </div>
            )}

            {/* STEP 2: Clustering & Settings */}
            {step === 2 && (
                <div className="space-y-4 animate-in fade-in">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-4">
                        <div className="flex justify-between items-center">
                            <h3 className="font-bold text-lg">Шаг 2. Семантика</h3>
                            <button 
                                onClick={handleClusterKeywords} 
                                disabled={loading || clusters}
                                className={`text-xs font-bold px-3 py-2 rounded-xl flex items-center gap-2 transition-all ${clusters ? 'bg-emerald-100 text-emerald-700' : 'bg-indigo-600 text-white shadow-lg shadow-indigo-200'}`}
                            >
                                {loading ? <Loader2 size={14} className="animate-spin"/> : <BrainCircuit size={14}/>}
                                {clusters ? 'Сгруппировано' : 'AI Кластеризация'}
                            </button>
                        </div>

                        {status && <div className="text-xs text-indigo-600 font-medium bg-indigo-50 p-2 rounded-lg text-center">{status}</div>}
                        
                        {clusters ? (
                            <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                                {clusters.map((c, i) => (
                                    <div key={i} className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                                        <div className="flex items-center gap-2 mb-2">
                                            <Layers size={14} className="text-indigo-500"/>
                                            <span className="font-bold text-sm capitalize">{c.topic}</span>
                                            <span className="text-[10px] bg-white px-2 rounded-full text-slate-400 border border-slate-200">{c.count}</span>
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                            {c.keywords.map((k, j) => (
                                                <span key={j} className="text-[10px] bg-white text-slate-600 px-2 py-1 rounded-md border border-slate-200">{k}</span>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="flex flex-wrap gap-2 mb-4 max-h-[200px] overflow-y-auto">
                                {keywords.map((k, i) => (
                                    <div key={i} className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-xl text-sm font-medium flex items-center gap-2">
                                        {k}
                                        <button onClick={() => removeKeyword(k)} className="text-slate-400 hover:text-red-500"><X size={14} /></button>
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className="flex gap-2 mb-6">
                            <input 
                                value={newKeyword}
                                onChange={e => setNewKeyword(e.target.value)}
                                placeholder="Добавить ключ..."
                                className="flex-1 bg-slate-50 rounded-xl px-4 py-2 text-sm outline-none"
                            />
                            <button onClick={addKeyword} className="bg-slate-900 text-white px-4 rounded-xl font-bold text-xl">+</button>
                        </div>
                        
                        <div className="pt-4 border-t border-slate-100">
                            <div className="mb-4">
                                <label className="text-xs font-bold text-slate-400 uppercase mb-2 block">Размер текста</label>
                                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                                    <span>Заголовок: {titleLen}</span>
                                    <span>Описание: {descLen}</span>
                                </div>
                                <input type="range" min="40" max="150" value={titleLen} onChange={e=>setTitleLen(Number(e.target.value))} className="w-full accent-indigo-600 mb-2 h-1 bg-slate-100 rounded-lg appearance-none cursor-pointer"/>
                                <input type="range" min="500" max="3000" step="100" value={descLen} onChange={e=>setDescLen(Number(e.target.value))} className="w-full accent-indigo-600 h-1 bg-slate-100 rounded-lg appearance-none cursor-pointer"/>
                            </div>

                            <h3 className="font-bold text-sm mb-3">Tone of Voice</h3>
                            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                                {toneOptions.map(t => (
                                    <button 
                                        key={t}
                                        onClick={() => setTone(t)}
                                        className={`px-4 py-2 rounded-xl text-xs font-bold border whitespace-nowrap transition-all ${tone === t ? 'border-orange-500 bg-orange-50 text-orange-600' : 'border-slate-100 bg-white text-slate-500'}`}
                                    >
                                        {t}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

                        <div className="flex gap-3 mt-4">
                            <button onClick={() => setStep(1)} className="flex-1 bg-slate-100 text-slate-600 p-4 rounded-xl font-bold">Назад</button>
                            <button onClick={generateContent} disabled={loading} className="flex-[2] bg-gradient-to-r from-orange-500 to-pink-500 text-white p-4 rounded-xl font-bold shadow-lg shadow-orange-200 active:scale-95 transition-all flex justify-center gap-2 items-center">
                                {loading ? <Loader2 className="animate-spin" /> : <><Sparkles size={18} /> Создать GEO</>}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* STEP 3: Result (GEO Content) */}
            {step === 3 && result && (
                <div className="space-y-4 animate-in fade-in">
                    
                    <button 
                        onClick={downloadPdf} 
                        disabled={pdfLoading}
                        className="w-full bg-slate-800 text-white p-3 rounded-xl font-bold flex items-center justify-center gap-2 active:scale-95 transition-all shadow-lg"
                    >
                        {pdfLoading ? <Loader2 size={16} className="animate-spin"/> : <Download size={16}/>}
                        Скачать PDF отчет
                    </button>

                    {/* Header */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <div className="flex justify-between items-center mb-2">
                            <h3 className="font-bold text-slate-400 text-xs uppercase">Заголовок</h3>
                            <CopyButton text={result.title} />
                        </div>
                        <textarea 
                            className="w-full bg-slate-50 p-3 rounded-xl text-sm font-bold text-slate-800 outline-none focus:ring-2 ring-indigo-100 min-h-[60px]"
                            value={result.title}
                            onChange={(e) => setResult({...result, title: e.target.value})}
                        />
                    </div>

                    {/* Features Table */}
                    {result.structured_features && Object.keys(result.structured_features).length > 0 && (
                        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                             <div className="flex justify-between items-center mb-3">
                                <h3 className="font-bold text-slate-700 text-sm flex items-center gap-2">
                                    <Table size={16} className="text-indigo-500"/> Характеристики
                                </h3>
                                <CopyButton text={Object.entries(result.structured_features).map(([k,v]) => `${k}: ${v}`).join('\n')} />
                            </div>
                            <div className="border border-slate-100 rounded-xl overflow-hidden text-sm">
                                {Object.entries(result.structured_features).map(([k, v], i) => (
                                    <div key={i} className="flex border-b border-slate-100 last:border-0">
                                        <div className="w-1/3 bg-slate-50 p-2 font-medium text-slate-500 border-r border-slate-100">{k}</div>
                                        <div className="w-2/3 p-2 text-slate-800">{v}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Description */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <div className="flex justify-between items-center mb-2">
                            <h3 className="font-bold text-slate-400 text-xs uppercase">Описание</h3>
                            <CopyButton text={result.description} />
                        </div>
                        <textarea 
                            className="w-full bg-slate-50 p-3 rounded-xl text-sm text-slate-700 outline-none focus:ring-2 ring-indigo-100 min-h-[300px] leading-relaxed"
                            value={result.description}
                            onChange={(e) => setResult({...result, description: e.target.value})}
                        />
                    </div>

                    {/* FAQ */}
                    {result.faq && result.faq.length > 0 && (
                         <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                            <div className="flex justify-between items-center mb-3">
                                <h3 className="font-bold text-slate-700 text-sm flex items-center gap-2">
                                    <HelpCircle size={16} className="text-orange-500"/> Часто задаваемые вопросы
                                </h3>
                                <CopyButton text={result.faq.map(f => `Q: ${f.question}\nA: ${f.answer}`).join('\n\n')} />
                            </div>
                            <div className="space-y-3">
                                {result.faq.map((item, i) => (
                                    <div key={i} className="bg-slate-50 p-3 rounded-xl">
                                        <div className="font-bold text-xs text-slate-700 mb-1">❓ {item.question}</div>
                                        <div className="text-xs text-slate-500 leading-relaxed">{item.answer}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <button onClick={() => setStep(1)} className="w-full bg-slate-900 text-white p-4 rounded-xl font-bold">Новый поиск</button>
                </div>
            )}
        </div>
    );
};

export default SeoGeneratorPage;