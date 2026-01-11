import React, { useState } from 'react';
import { Wand2, Clock, Loader2, Sparkles, Copy, X } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

const SeoGeneratorPage = () => {
    const [step, setStep] = useState(1);
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [keywords, setKeywords] = useState([]);
    const [newKeyword, setNewKeyword] = useState('');
    const [tone, setTone] = useState('Продающий');
    const [titleLen, setTitleLen] = useState(100);
    const [descLen, setDescLen] = useState(1000);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [historyOpen, setHistoryOpen] = useState(false);

    const toneOptions = ["Продающий", "Информативный", "Дерзкий", "Формальный", "Дружелюбный"];

    const fetchKeywords = async () => {
        if (!sku) return;
        setLoading(true); setError('');
        try {
            const res = await fetch(`${API_URL}/api/seo/parse/${sku}`, { headers: getTgHeaders() });
            const data = await res.json();
            if (res.status !== 200) throw new Error(data.detail || data.message);
            setKeywords(data.keywords || []); setStep(2);
        } catch (e) { setError(e.message); } finally { setLoading(false); }
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

    const copyKeywords = () => {
        const text = keywords.join(', ');
        navigator.clipboard.writeText(text);
        alert("Ключевые слова скопированы!");
    };

    const generateContent = async () => {
        setLoading(true);
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
        } catch (e) { setError(e.message); } finally { setLoading(false); }
    };

    const CopyButton = ({ text }) => (
        <button onClick={() => {navigator.clipboard.writeText(text); alert("Скопировано!");}} className="p-2 text-slate-400 hover:text-indigo-600 transition-colors">
            <Copy size={18} />
        </button>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
                <div className="bg-gradient-to-r from-orange-500 to-pink-500 p-6 rounded-3xl text-white shadow-xl shadow-orange-200 flex-1 mr-4">
                    <h1 className="text-2xl font-black flex items-center gap-2"><Wand2 className="text-yellow-200" /> SEO Gen</h1>
                    <p className="text-sm opacity-90 mt-2">Генератор описаний</p>
                </div>
                <button onClick={() => setHistoryOpen(true)} className="bg-white p-4 rounded-3xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors h-full"><Clock size={24}/></button>
            </div>
            
            <HistoryModule type="seo" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

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

            {step === 2 && (
                <div className="space-y-4 animate-in fade-in">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-4">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="font-bold text-lg">Шаг 2. Настройки</h3>
                            <button onClick={copyKeywords} className="text-xs font-bold text-indigo-600 bg-indigo-50 px-3 py-1 rounded-lg active:scale-95">
                                Копировать всё
                            </button>
                        </div>
                        
                        <div className="flex flex-wrap gap-2 mb-4">
                            {keywords.map((k, i) => (
                                <div key={i} className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-xl text-sm font-medium flex items-center gap-2">
                                    {k}
                                    <button onClick={() => removeKeyword(k)} className="text-slate-400 hover:text-red-500"><X size={14} /></button>
                                </div>
                            ))}
                        </div>

                        <div className="flex gap-2 mb-6">
                            <input 
                                value={newKeyword}
                                onChange={e => setNewKeyword(e.target.value)}
                                placeholder="Добавить свой ключ..."
                                className="flex-1 bg-slate-50 rounded-xl px-4 py-2 text-sm outline-none"
                            />
                            <button onClick={addKeyword} className="bg-slate-900 text-white px-4 rounded-xl font-bold text-xl">+</button>
                        </div>
                        
                        <div>
                            <label className="text-xs font-bold text-slate-400 uppercase">Длина заголовка: {titleLen}</label>
                            <input type="range" min="40" max="150" value={titleLen} onChange={e=>setTitleLen(Number(e.target.value))} className="w-full accent-indigo-600"/>
                        </div>
                        <div>
                            <label className="text-xs font-bold text-slate-400 uppercase">Длина описания: {descLen}</label>
                            <input type="range" min="500" max="3000" step="100" value={descLen} onChange={e=>setDescLen(Number(e.target.value))} className="w-full accent-indigo-600"/>
                        </div>

                        <h3 className="font-bold text-lg mb-3">Настроение текста</h3>
                        <div className="grid grid-cols-2 gap-2 mb-6">
                            {toneOptions.map(t => (
                                <button 
                                    key={t}
                                    onClick={() => setTone(t)}
                                    className={`p-3 rounded-xl text-sm font-bold border transition-all ${tone === t ? 'border-orange-500 bg-orange-50 text-orange-600' : 'border-slate-100 bg-white text-slate-500'}`}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>

                        {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

                        <div className="flex gap-3">
                            <button onClick={() => setStep(1)} className="flex-1 bg-slate-100 text-slate-600 p-4 rounded-xl font-bold">Назад</button>
                            <button onClick={generateContent} disabled={loading} className="flex-[2] bg-gradient-to-r from-orange-500 to-pink-500 text-white p-4 rounded-xl font-bold shadow-lg shadow-orange-200 active:scale-95 transition-all flex justify-center gap-2">
                                {loading ? <Loader2 className="animate-spin" /> : <><Sparkles size={18} /> Генерировать</>}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {step === 3 && result && (
                <div className="space-y-4 animate-in fade-in">
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

                    <button onClick={() => setStep(1)} className="w-full bg-slate-900 text-white p-4 rounded-xl font-bold">Новый поиск</button>
                </div>
            )}
        </div>
    );
};

export default SeoGeneratorPage;