import React, { useState } from 'react';
import { Sparkles, Clock, Loader2, Star, ThumbsDown, Crown } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

const AIAnalysisPage = () => {
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');
    const [result, setResult] = useState(null);
    const [historyOpen, setHistoryOpen] = useState(false);

    const runAnalysis = async () => {
        if(!sku) return;
        setLoading(true);
        setResult(null);
        try {
            const res = await fetch(`${API_URL}/api/ai/analyze/${sku}`, { 
                method: 'POST',
                headers: getTgHeaders()
            });
            const data = await res.json();
            const taskId = data.task_id;
            
            let attempts = 0;
            while(attempts < 60) {
                setStatus('Анализ отзывов...');
                await new Promise(r => setTimeout(r, 4000));
                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`);
                const sData = await sRes.json();
                
                if (sData.status === 'SUCCESS') {
                    setResult(sData.data);
                    break;
                }
                if (sData.status === 'FAILURE') throw new Error(sData.error || "Ошибка ИИ");
                if (sData.info) setStatus(sData.info);
                attempts++;
            }
        } catch(e) {
            alert(e.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
                <div className="bg-gradient-to-br from-violet-600 to-fuchsia-600 p-6 rounded-3xl text-white shadow-xl shadow-fuchsia-200 flex-1 mr-4">
                    <h1 className="text-2xl font-black flex items-center gap-2">
                        <Sparkles className="text-yellow-300" /> AI Стратег
                    </h1>
                </div>
                <button onClick={() => setHistoryOpen(true)} className="bg-white p-4 rounded-3xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors h-full"><Clock size={24}/></button>
            </div>
            
            <HistoryModule type="ai" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

            <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-100">
                <input type="number" value={sku} onChange={e => setSku(e.target.value)} placeholder="Артикул" className="w-full p-4 bg-slate-50 rounded-xl font-bold mb-3 outline-none" />
                <button onClick={runAnalysis} disabled={loading} className="w-full bg-violet-600 text-white p-4 rounded-xl font-bold shadow-lg">{loading ? <Loader2 className="animate-spin mx-auto"/> : 'Анализировать'}</button>
            </div>

            {result && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8">
                    <div className="flex gap-4 items-center bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                        {result.image && <img src={result.image} className="w-16 h-20 object-cover rounded-lg bg-slate-100" alt="product" />}
                        <div>
                            <div className="flex items-center gap-1 text-amber-500 font-black mb-1">
                                <Star size={16} fill="currentColor" /> {result.rating}
                            </div>
                            <p className="text-xs text-slate-400 font-bold uppercase tracking-wider">Проанализировано</p>
                            <p className="font-bold">{result.reviews_count} отзывов</p>
                        </div>
                    </div>

                    <div className="bg-red-50 p-6 rounded-3xl border border-red-100">
                        <h3 className="text-red-600 font-black text-lg flex items-center gap-2 mb-4">
                            <ThumbsDown size={20} /> ТОП Жалоб
                        </h3>
                        <ul className="space-y-3">
                            {result.ai_analysis.flaws?.map((f, i) => (
                                <li key={i} className="bg-white p-3 rounded-xl text-sm font-medium text-slate-700 shadow-sm">
                                    ⛔ {f}
                                </li>
                            ))}
                        </ul>
                    </div>

                    <div className="bg-indigo-50 p-6 rounded-3xl border border-indigo-100">
                        <h3 className="text-indigo-600 font-black text-lg flex items-center gap-2 mb-4">
                            <Crown size={20} /> Стратегия победы
                        </h3>
                        <ul className="space-y-3">
                            {result.ai_analysis.strategy?.map((s, i) => (
                                <li key={i} className="bg-white p-4 rounded-xl text-sm font-medium text-slate-700 shadow-sm border-l-4 border-indigo-500">
                                    {s}
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AIAnalysisPage;