import React, { useState } from 'react';
import { Sparkles, Clock, Loader2, Star, ThumbsDown, Crown, BarChart3, Quote, Lightbulb, TrendingUp } from 'lucide-react';
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
                setStatus('Декомпозиция аспектов...');
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

    const getScoreColor = (score) => {
        if (score >= 7) return 'bg-emerald-500 text-white';
        if (score >= 4.5) return 'bg-amber-400 text-amber-950';
        return 'bg-red-500 text-white';
    };

    const getScoreBarColor = (score) => {
        if (score >= 7) return 'bg-emerald-500';
        if (score >= 4.5) return 'bg-amber-400';
        return 'bg-red-500';
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
                <div className="bg-gradient-to-br from-violet-600 to-fuchsia-600 p-6 rounded-3xl text-white shadow-xl shadow-fuchsia-200 flex-1 mr-4">
                    <h1 className="text-2xl font-black flex items-center gap-2">
                        <Sparkles className="text-yellow-300" /> AI Стратег
                    </h1>
                    <p className="text-xs opacity-80 mt-1">DeepSeek ABSA Engine</p>
                </div>
                <button onClick={() => setHistoryOpen(true)} className="bg-white p-4 rounded-3xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors h-full"><Clock size={24}/></button>
            </div>
            
            <HistoryModule type="ai" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

            <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-100">
                <input type="number" value={sku} onChange={e => setSku(e.target.value)} placeholder="Артикул" className="w-full p-4 bg-slate-50 rounded-xl font-bold mb-3 outline-none focus:ring-2 ring-violet-200 transition-all" />
                <button onClick={runAnalysis} disabled={loading} className="w-full bg-violet-600 text-white p-4 rounded-xl font-bold shadow-lg active:scale-95 transition-transform flex justify-center items-center gap-2">
                    {loading ? <><Loader2 className="animate-spin" /> {status}</> : 'Запустить анализ'}
                </button>
            </div>

            {result && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8">
                    {/* Product Header */}
                    <div className="flex gap-4 items-center bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                        {result.image && <img src={result.image} className="w-16 h-20 object-cover rounded-lg bg-slate-100" alt="product" />}
                        <div>
                            <div className="flex items-center gap-1 text-amber-500 font-black mb-1 text-lg">
                                <Star size={18} fill="currentColor" /> {result.rating}
                            </div>
                            <p className="text-xs text-slate-400 font-bold uppercase tracking-wider">Датасет</p>
                            <p className="font-bold">{result.reviews_count} отзывов</p>
                        </div>
                    </div>

                    {/* Global Summary (New) */}
                    {result.ai_analysis.global_summary && (
                        <div className="bg-slate-800 text-slate-200 p-5 rounded-2xl text-sm italic border-l-4 border-violet-500 shadow-md">
                            "{result.ai_analysis.global_summary}"
                        </div>
                    )}

                    {/* ABSA Heatmap (New) */}
                    {result.ai_analysis.aspects && result.ai_analysis.aspects.length > 0 && (
                        <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                            <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                                <BarChart3 className="text-violet-600" size={20}/> 
                                Аспектный анализ
                            </h3>
                            <div className="space-y-6">
                                {result.ai_analysis.aspects.map((aspect, idx) => (
                                    <div key={idx} className="relative">
                                        <div className="flex justify-between items-center mb-1">
                                            <span className="font-bold text-sm text-slate-700">{aspect.aspect}</span>
                                            <span className={`text-[10px] font-black px-2 py-0.5 rounded-md ${getScoreColor(aspect.sentiment_score)}`}>
                                                {aspect.sentiment_score}/9.0
                                            </span>
                                        </div>
                                        
                                        {/* Progress Bar */}
                                        <div className="h-2 w-full bg-slate-100 rounded-full mb-2 overflow-hidden">
                                            <div 
                                                className={`h-full rounded-full transition-all duration-1000 ${getScoreBarColor(aspect.sentiment_score)}`}
                                                style={{width: `${(aspect.sentiment_score / 9) * 100}%`}}
                                            ></div>
                                        </div>
                                        
                                        {/* Snippet */}
                                        <div className="text-xs text-slate-400 italic mb-2 flex gap-1.5 items-start">
                                            <Quote size={10} className="mt-0.5 shrink-0 opacity-50"/> 
                                            <span>{aspect.snippet}</span>
                                        </div>

                                        {/* Specific Advice */}
                                        {aspect.actionable_advice && aspect.sentiment_score < 7.5 && (
                                            <div className="text-xs text-violet-700 bg-violet-50 p-2.5 rounded-xl flex gap-2 items-start border border-violet-100">
                                                <Lightbulb size={14} className="mt-0.5 shrink-0 text-violet-500"/> 
                                                <span className="font-medium">{aspect.actionable_advice}</span>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Legacy/Summary Blocks */}
                    <div className="grid grid-cols-1 gap-4">
                        <div className="bg-red-50 p-5 rounded-3xl border border-red-100">
                            <h3 className="text-red-600 font-black text-sm flex items-center gap-2 mb-3 uppercase tracking-wider">
                                <ThumbsDown size={16} /> Критические зоны
                            </h3>
                            <ul className="space-y-2">
                                {result.ai_analysis.flaws?.map((f, i) => (
                                    <li key={i} className="bg-white p-2.5 rounded-xl text-xs font-medium text-slate-700 shadow-sm border border-red-50">
                                        {f}
                                    </li>
                                ))}
                            </ul>
                        </div>

                        <div className="bg-emerald-50 p-5 rounded-3xl border border-emerald-100">
                            <h3 className="text-emerald-600 font-black text-sm flex items-center gap-2 mb-3 uppercase tracking-wider">
                                <TrendingUp size={16} /> Точки роста
                            </h3>
                            <ul className="space-y-2">
                                {result.ai_analysis.strategy?.map((s, i) => (
                                    <li key={i} className="bg-white p-2.5 rounded-xl text-xs font-medium text-slate-700 shadow-sm border-l-4 border-emerald-400">
                                        {s}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AIAnalysisPage;