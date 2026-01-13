import React, { useState } from 'react';
import { Sparkles, Clock, Loader2, Star, ThumbsDown, Crown, BarChart3, Quote, Lightbulb, TrendingUp, Users, BrainCircuit, ShieldCheck, Heart, FileDown, Lock, Settings2 } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

const AIAnalysisPage = ({ user }) => {
    const [sku, setSku] = useState('');
    const [reviewLimit, setReviewLimit] = useState(100);
    const [loading, setLoading] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [status, setStatus] = useState('');
    const [result, setResult] = useState(null);
    const [historyOpen, setHistoryOpen] = useState(false);

    const runAnalysis = async () => {
        if(!sku) return;
        setLoading(true);
        setResult(null);
        
        try {
            // Pass the limit query param
            const res = await fetch(`${API_URL}/api/ai/analyze/${sku}?limit=${reviewLimit}`, { 
                method: 'POST', 
                headers: getTgHeaders() 
            });
            const data = await res.json();
            const taskId = data.task_id;

            let attempts = 0;
            while(attempts < 60) {
                setStatus(`Парсинг ${reviewLimit} отзывов... (${attempts*2}s)`);
                await new Promise(r => setTimeout(r, 2000));
                
                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`, { headers: getTgHeaders() });
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

    const handleDownloadPDF = async () => {
        if (!sku && !result?.sku) return;
        const targetSku = sku || result.sku;
        
        if (user?.plan === 'free') {
            alert("Скачивание PDF доступно только на тарифе PRO или Business");
            return;
        }

        // Прямое скачивание через URL для поддержки мобильных устройств
        try {
            const token = window.Telegram?.WebApp?.initData || "";
            // Формируем URL с токеном в query параметрах
            const downloadUrl = `${API_URL}/api/report/ai-pdf/${targetSku}?x_tg_data=${encodeURIComponent(token)}`;
            // Открываем в новом окне - это инициирует нативную загрузку
            window.open(downloadUrl, '_blank');
        } catch (e) {
            alert("Не удалось скачать отчет: " + e.message);
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

    const getTypeIcon = (type) => {
        if (!type) return <Users size={18} />;
        const t = type.toLowerCase();
        if (t.includes('rational')) return <BrainCircuit size={18} className="text-blue-500" />;
        if (t.includes('emotional')) return <Heart size={18} className="text-pink-500" />;
        if (t.includes('skeptic')) return <ShieldCheck size={18} className="text-slate-500" />;
        return <Users size={18} />;
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
                <div className="bg-gradient-to-br from-violet-600 to-fuchsia-600 p-6 rounded-3xl text-white shadow-xl shadow-fuchsia-200 flex-1 mr-4">
                    <h1 className="text-2xl font-black flex items-center gap-2">
                        <Sparkles className="text-yellow-300" /> AI Стратег
                    </h1>
                    <p className="text-xs opacity-80 mt-1">DeepSeek ABSA + Psychographics</p>
                </div>
                <button onClick={() => setHistoryOpen(true)} className="bg-white p-4 rounded-3xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors h-full"><Clock size={24}/></button>
            </div>

            <HistoryModule type="ai" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

            <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-100">
                <input 
                    type="number" 
                    value={sku} 
                    onChange={e => setSku(e.target.value)} 
                    placeholder="Артикул WB" 
                    className="w-full p-4 bg-slate-50 rounded-xl font-bold mb-4 outline-none focus:ring-2 ring-violet-200 transition-all"
                />
                
                {/* Review Limit Slider */}
                <div className="mb-4 px-2">
                    <div className="flex justify-between items-center mb-2">
                        <label className="text-xs font-bold text-slate-400 uppercase flex items-center gap-1">
                            <Settings2 size={12}/> Глубина парсинга
                        </label>
                        <span className="text-xs font-black text-violet-600 bg-violet-50 px-2 py-1 rounded-lg">
                            {reviewLimit === 5000 ? "ВСЕ (Max)" : `${reviewLimit} отзывов`}
                        </span>
                    </div>
                    <input 
                        type="range" 
                        min="50" 
                        max="5000" 
                        step="50" 
                        value={reviewLimit} 
                        onChange={(e) => setReviewLimit(Number(e.target.value))}
                        className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-violet-600"
                    />
                    <div className="flex justify-between text-[10px] text-slate-300 mt-1 font-bold px-1">
                        <span>50</span>
                        <span>2500</span>
                        <span>MAX</span>
                    </div>
                </div>

                <button 
                    onClick={runAnalysis} 
                    disabled={loading}
                    className="w-full bg-violet-600 text-white p-4 rounded-xl font-bold shadow-lg active:scale-95 transition-transform flex justify-center items-center gap-2"
                >
                    {loading ? <><Loader2 className="animate-spin" /> {status}</> : 'Запустить анализ'}
                </button>
            </div>

            {result && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8">
                    
                    {/* Actions Header */}
                    <div className="flex justify-end">
                        <button 
                            onClick={handleDownloadPDF} 
                            disabled={downloading}
                            className={`
                                flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all active:scale-95
                                ${user?.plan === 'free' ? 'bg-slate-100 text-slate-400' : 'bg-slate-900 text-white shadow-lg'}
                            `}
                        >
                            {downloading ? <Loader2 size={14} className="animate-spin"/> : (user?.plan === 'free' ? <Lock size={14}/> : <FileDown size={14}/>)}
                            {user?.plan === 'free' ? 'PDF (доступно в PRO)' : 'Скачать PDF'}
                        </button>
                    </div>

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

                    {/* Global Summary */}
                    {result.ai_analysis.global_summary && (
                        <div className="bg-slate-800 text-slate-200 p-5 rounded-2xl text-sm italic border-l-4 border-violet-500 shadow-md">
                            "{result.ai_analysis.global_summary}"
                        </div>
                    )}

                    {/* Psychographics Block (NEW) */}
                    {result.ai_analysis.audience_stats && (
                        <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                            <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                                <Users className="text-violet-600" size={20}/> Портрет аудитории
                            </h3>
                            <div className="grid grid-cols-3 gap-2 mb-6">
                                <div className="bg-blue-50 p-3 rounded-2xl text-center border border-blue-100">
                                    <BrainCircuit className="mx-auto text-blue-500 mb-1" size={20}/>
                                    <div className="text-xl font-black text-blue-700">{result.ai_analysis.audience_stats.rational_percent}%</div>
                                    <div className="text-[10px] uppercase font-bold text-blue-400">Рационал</div>
                                </div>
                                <div className="bg-pink-50 p-3 rounded-2xl text-center border border-pink-100">
                                    <Heart className="mx-auto text-pink-500 mb-1" size={20}/>
                                    <div className="text-xl font-black text-pink-700">{result.ai_analysis.audience_stats.emotional_percent}%</div>
                                    <div className="text-[10px] uppercase font-bold text-pink-400">Эмоционал</div>
                                </div>
                                <div className="bg-slate-50 p-3 rounded-2xl text-center border border-slate-200">
                                    <ShieldCheck className="mx-auto text-slate-500 mb-1" size={20}/>
                                    <div className="text-xl font-black text-slate-700">{result.ai_analysis.audience_stats.skeptic_percent}%</div>
                                    <div className="text-[10px] uppercase font-bold text-slate-400">Скептик</div>
                                </div>
                            </div>
                            
                            {result.ai_analysis.infographic_recommendation && (
                                <div className="bg-violet-50 border border-violet-100 p-4 rounded-2xl flex gap-3 items-start">
                                    <div className="bg-white p-2 rounded-xl shadow-sm shrink-0">
                                        {getTypeIcon(result.ai_analysis.dominant_type)}
                                    </div>
                                    <div>
                                        <div className="text-xs font-bold text-violet-400 uppercase mb-1">Совет для инфографики</div>
                                        <div className="text-sm font-medium text-violet-900 leading-snug">
                                            {result.ai_analysis.infographic_recommendation}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* ABSA Heatmap */}
                    {result.ai_analysis.aspects && result.ai_analysis.aspects.length > 0 && (
                        <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                            <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                                <BarChart3 className="text-violet-600" size={20}/> Аспектный анализ
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
                                        <div className="h-2 w-full bg-slate-100 rounded-full mb-2 overflow-hidden">
                                            <div 
                                                className={`h-full rounded-full transition-all duration-1000 ${getScoreBarColor(aspect.sentiment_score)}`} 
                                                style={{width: `${(aspect.sentiment_score / 9) * 100}%`}}
                                            ></div>
                                        </div>
                                        {aspect.actionable_advice && (
                                            <div className="flex gap-2 items-start text-xs text-slate-500 bg-slate-50 p-2 rounded-lg">
                                                <Lightbulb size={14} className="shrink-0 text-amber-400 mt-0.5"/>
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