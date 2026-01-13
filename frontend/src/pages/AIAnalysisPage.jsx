import React, { useState } from 'react';
import { Sparkles, Clock, Loader2, Star, ThumbsDown, Crown, BarChart3, Quote, Lightbulb, Users, BrainCircuit, ShieldCheck, Heart, FileDown, Lock, Search, Sliders } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

const AIAnalysisPage = ({ user }) => {
    // State for Phase 1 (Check)
    const [sku, setSku] = useState('');
    const [checking, setChecking] = useState(false);
    const [productMeta, setProductMeta] = useState(null); // { name, image, feedbacks_count, rating }
    
    // State for Phase 2 (Analyze)
    const [parseLimit, setParseLimit] = useState(100);
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');
    const [result, setResult] = useState(null);
    
    // Other
    const [downloading, setDownloading] = useState(false);
    const [historyOpen, setHistoryOpen] = useState(false);

    // Step 1: Check Product info to setup Slider
    const checkProduct = async () => {
        if (!sku) return;
        setChecking(true);
        setProductMeta(null);
        setResult(null);
        try {
            const res = await fetch(`${API_URL}/api/ai/check/${sku}`, { headers: getTgHeaders() });
            if (!res.ok) throw new Error("Товар не найден");
            const data = await res.json();
            setProductMeta(data);
            
            // Защита: Если отзывов 0 или очень мало
            if (data.feedbacks_count > 0) {
                 setParseLimit(Math.min(100, data.feedbacks_count));
            } else {
                 setParseLimit(0);
            }
        } catch (e) {
            alert(e.message);
        } finally {
            setChecking(false);
        }
    };

    // Step 2: Run Analysis with limit
    const runAnalysis = async () => {
        setLoading(true);
        setResult(null);
        try {
            const res = await fetch(`${API_URL}/api/ai/analyze`, { 
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ sku: Number(sku), limit: parseLimit })
            });
            const data = await res.json();
            const taskId = data.task_id;
            
            let attempts = 0;
            // Увеличили таймаут ожидания, т.к. парсинг 5000 отзывов может занять время
            while(attempts < 120) {
                setStatus(`Парсинг отзывов... ${attempts * 2}s`);
                await new Promise(r => setTimeout(r, 2000));
                
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

    const handleDownloadPDF = async () => {
        const targetSku = sku || result?.sku;
        if (!targetSku) return;
        if (user?.plan === 'free') {
            alert("Скачивание PDF доступно только на тарифе PRO или Business");
            return;
        }
        try {
            const token = window.Telegram?.WebApp?.initData || "";
            const downloadUrl = `${API_URL}/api/report/ai-pdf/${targetSku}?x_tg_data=${encodeURIComponent(token)}`;
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
    
    // Рассчитываем реальный максимум для слайдера (защита от null)
    const sliderMax = productMeta ? Math.min(5000, productMeta.feedbacks_count) : 100;

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            {/* Header */}
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

            {/* Config Block */}
            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                <div className="relative mb-4">
                    <input 
                        type="number" 
                        value={sku} 
                        onChange={e => setSku(e.target.value)} 
                        placeholder="Артикул WB" 
                        className="w-full p-4 pr-14 bg-slate-50 rounded-2xl font-bold outline-none focus:ring-2 ring-violet-200 transition-all text-lg" 
                        onKeyDown={(e) => e.key === 'Enter' && checkProduct()}
                    />
                    <button 
                        onClick={checkProduct} 
                        disabled={checking || !sku}
                        className="absolute right-2 top-2 bottom-2 aspect-square bg-slate-200 rounded-xl flex items-center justify-center text-slate-500 hover:bg-violet-600 hover:text-white transition-colors disabled:opacity-50"
                    >
                        {checking ? <Loader2 className="animate-spin"/> : <Search size={20}/>}
                    </button>
                </div>

                {productMeta && (
                    <div className="animate-in fade-in slide-in-from-top-2 mb-4">
                        <div className="flex gap-3 mb-4 p-3 bg-slate-50 rounded-2xl border border-slate-100">
                             <img src={productMeta.image} className="w-12 h-16 object-cover rounded-lg bg-white" alt="preview"/>
                             <div className="min-w-0">
                                 <div className="font-bold text-sm truncate">{productMeta.name}</div>
                                 <div className="text-xs text-slate-500 flex items-center gap-2 mt-1">
                                     <span className="flex items-center gap-1 text-amber-500 font-bold"><Star size={10} fill="currentColor"/> {productMeta.rating}</span>
                                     <span>•</span>
                                     <span>Всего {productMeta.feedbacks_count} отзывов</span>
                                 </div>
                             </div>
                        </div>

                        {productMeta.feedbacks_count > 0 ? (
                            <div className="mb-4">
                                <div className="flex justify-between items-end mb-2">
                                    <label className="text-xs font-bold text-slate-400 uppercase flex items-center gap-1">
                                        <Sliders size={12}/> Глубина анализа
                                    </label>
                                    <span className="text-lg font-black text-violet-600">{parseLimit} шт.</span>
                                </div>
                                <input 
                                    type="range" 
                                    min="10" 
                                    max={Math.max(10, sliderMax)} // Защита: min=10, значит max должен быть >= 10
                                    step="10"
                                    value={parseLimit} 
                                    onChange={e => setParseLimit(Number(e.target.value))} 
                                    className="w-full accent-violet-600 h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer"
                                />
                                <div className="flex justify-between text-[10px] text-slate-400 mt-1 font-medium">
                                    <span>10</span>
                                    <span>{sliderMax}</span>
                                </div>
                            </div>
                        ) : (
                            <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-xl text-sm font-medium border border-red-100 flex items-center gap-2">
                                <ThumbsDown size={16}/>
                                Отзывы не найдены. Анализ невозможен.
                            </div>
                        )}

                        <button 
                            onClick={runAnalysis} 
                            disabled={loading || productMeta.feedbacks_count === 0} 
                            className="w-full bg-violet-600 text-white p-4 rounded-xl font-bold shadow-lg shadow-violet-200 active:scale-95 transition-transform flex justify-center items-center gap-2 disabled:opacity-50 disabled:active:scale-100"
                        >
                            {loading ? <><Loader2 className="animate-spin" /> {status}</> : 'Запустить анализ'}
                        </button>
                    </div>
                )}
            </div>

            {/* Results Block */}
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

                    {/* Global Summary */}
                    {result.ai_analysis.global_summary && (
                        <div className="bg-slate-800 text-slate-200 p-5 rounded-2xl text-sm italic border-l-4 border-violet-500 shadow-md">
                            "{result.ai_analysis.global_summary}"
                        </div>
                    )}

                    {/* Psychographics Block */}
                    {result.ai_analysis.audience_stats && (
                        <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                            <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                                <Users className="text-violet-600" size={20}/> 
                                Портрет аудитории
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
                                        
                                        <div className="h-2 w-full bg-slate-100 rounded-full mb-2 overflow-hidden">
                                            <div 
                                                className={`h-full rounded-full transition-all duration-1000 ${getScoreBarColor(aspect.sentiment_score)}`}
                                                style={{width: `${(aspect.sentiment_score / 9) * 100}%`}}
                                            ></div>
                                        </div>
                                        
                                        <div className="text-xs text-slate-400 italic mb-2 flex gap-1.5 items-start">
                                            <Quote size={10} className="mt-0.5 shrink-0 opacity-50"/> 
                                            <span>{aspect.snippet}</span>
                                        </div>

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
                                <Crown size={16} /> Точки роста
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