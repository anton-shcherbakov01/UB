import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Clock, Loader2, Star, ThumbsDown, BarChart3, Users, BrainCircuit, ShieldCheck, Heart, FileDown, Lock, Settings2, Search, RotateCcw, ChevronDown, ChevronUp, ArrowLeft } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

// --- Мини-компонент для раскрывающегося текста ---
const ExpandableText = ({ text, colorClass = "text-slate-700", borderClass = "border-slate-200" }) => {
    const [expanded, setExpanded] = useState(false);
    const isLong = text.length > 60; // Условие "длинного" текста

    return (
        <li 
            className={`bg-white p-2.5 rounded-xl text-xs font-medium shadow-sm border ${borderClass} transition-all duration-300 ${expanded ? '' : 'hover:bg-slate-50'}`}
            onClick={() => isLong && setExpanded(!expanded)}
        >
            <div className={`flex justify-between items-start gap-2 ${isLong ? 'cursor-pointer' : ''}`}>
                <span className={`${colorClass} ${expanded ? '' : 'line-clamp-2'}`}>
                    {text}
                </span>
                {isLong && (
                    <button className="text-slate-400 mt-0.5 shrink-0">
                        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                )}
            </div>
        </li>
    );
};
// ------------------------------------------------

const AIAnalysisPage = ({ user, onUserUpdate }) => {
    const navigate = useNavigate();
    const [sku, setSku] = useState('');
    const [step, setStep] = useState('input'); // input | config | analyzing | result
    
    // Product Stats
    const [productMeta, setProductMeta] = useState(null);
    const [metaLoading, setMetaLoading] = useState(false);
    
    // Analysis Config
    const [reviewLimit, setReviewLimit] = useState(100);
    const [loading, setLoading] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [status, setStatus] = useState('');
    const [result, setResult] = useState(null);
    const [historyOpen, setHistoryOpen] = useState(false);
    const cancelTokenRef = useRef(false); // Flag to cancel polling (useRef for immediate access in loop)

    // СБРОС СОСТОЯНИЯ
    const handleReset = () => {
        cancelTokenRef.current = true; // Cancel any ongoing polling
        setSku('');
        setStep('input');
        setProductMeta(null);
        setResult(null);
        setReviewLimit(100);
        setStatus('');
        setLoading(false);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handleCheckProduct = async () => {
        if (!sku) return;
        setMetaLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/ai/check/${sku}`, { 
                method: 'GET', 
                headers: getTgHeaders() 
            });
            const data = await res.json();
            
            if (res.status !== 200) throw new Error(data.detail || "Ошибка проверки");
            
            setProductMeta(data);
            
            const total = data.total_reviews || 0;
            
            let safeLimit = 100;
            if (total > 0 && total < 100) safeLimit = total;
            if (total === 0) safeLimit = 50; 
            
            setReviewLimit(safeLimit);
            setStep('config');
        } catch (e) {
            alert(e.message);
        } finally {
            setMetaLoading(false);
        }
    };

    const runAnalysis = async () => {
        cancelTokenRef.current = false; // Reset cancel flag
        setLoading(true);
        setStep('analyzing');
        setResult(null);
        
        try {
            const res = await fetch(`${API_URL}/api/ai/analyze/${sku}?limit=${reviewLimit}`, { 
                method: 'POST', 
                headers: getTgHeaders() 
            });
            
            // Проверяем HTTP статус
            if (!res.ok) {
                let errorData;
                try {
                    errorData = await res.json();
                } catch {
                    errorData = { detail: 'Неизвестная ошибка' };
                }
                setLoading(false);
                setStep('config');
                alert(errorData.detail || `Ошибка ${res.status}: Не удалось запустить анализ`);
                return; // Exit immediately, don't start polling
            }
            
            const data = await res.json();
            
            // Проверяем статус в JSON ответе (может быть ошибка даже при 200 OK)
            if (data.status && data.status !== "accepted") {
                setLoading(false);
                setStep('config');
                alert(data.error || data.detail || "Ошибка запуска анализа");
                return; // Exit immediately
            }
            
            // Проверяем наличие и валидность task_id
            const taskId = data.task_id;
            if (!taskId || typeof taskId !== 'string') {
                setLoading(false);
                setStep('config');
                alert('Не получен корректный task_id от сервера');
                console.error("Invalid task_id received:", data);
                return; // Exit immediately
            }
            
            // Update user info after successful task creation (to reflect updated limits)
            if (onUserUpdate) {
                onUserUpdate();
            }
            
            // Get queue information
            const queueInfo = {
                queue: data.queue || "normal",
                position: data.position || 0,
                is_priority: data.is_priority || false
            };

            // Only start polling if we have a valid taskId and no cancel flag
            let attempts = 0;
            while(attempts < 120 && !cancelTokenRef.current) {
                // Check cancel flag before each iteration
                if (cancelTokenRef.current) {
                    setLoading(false);
                    return;
                }
                
                // Check queue position
                try {
                    const queueRes = await fetch(`${API_URL}/api/ai/queue/${taskId}`, { headers: getTgHeaders() });
                    if (queueRes.ok) {
                        const queueData = await queueRes.json();
                        if (queueData.position !== null && queueData.position !== undefined) {
                            queueInfo.position = queueData.position;
                            queueInfo.queue = queueData.queue || queueInfo.queue;
                            queueInfo.is_priority = queueData.is_priority || queueInfo.is_priority;
                        }
                    }
                } catch (e) {
                    // Ignore queue check errors
                }
                
                // Update status with queue info
                if (queueInfo.is_priority) {
                    setStatus(`⚡ Приоритетная очередь: позиция ${queueInfo.position}... (${attempts*2}s)`);
                } else if (queueInfo.position > 0) {
                    setStatus(`⏳ Ваше место в очереди: ${queueInfo.position}... (${attempts*2}s)`);
                } else {
                    setStatus(`Парсинг ${reviewLimit} последних отзывов... (${attempts*2}s)`);
                }
                
                await new Promise(r => setTimeout(r, 2000));
                
                // Double-check cancel flag after delay
                if (cancelTokenRef.current) {
                    setLoading(false);
                    return;
                }
                
                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`, { headers: getTgHeaders() });
                const sData = await sRes.json();
                
                if (sData.status === 'SUCCESS') {
                    if (sData.data?.ai_analysis?._error) {
                        setStatus(`⚠️ Ошибка AI: ${sData.data.ai_analysis._error}`);
                    }
                    setResult(sData.data);
                    setStep('result');
                    setLoading(false);
                    // Update user info after successful analysis completion (to reflect updated limits)
                    if (onUserUpdate) {
                        onUserUpdate();
                    }
                    break;
                }
                if (sData.status === 'FAILURE') {
                    const errorMsg = sData.error || sData.data?.error || "Ошибка ИИ";
                    throw new Error(errorMsg);
                }
                if (sData.info) setStatus(sData.info);
                
                attempts++;
            }
            
            // If we exit loop due to attempts limit
            if (attempts >= 120 && !cancelTokenRef.current) {
                setLoading(false);
                setStep('config');
                alert('Превышено время ожидания результата анализа');
            }
        } catch(e) {
            setLoading(false);
            setStep('config');
            const errorMsg = e.message || "Неизвестная ошибка при запуске анализа";
            alert(errorMsg);
            console.error("Analysis start error:", e);
        } finally {
            // Ensure loading is false even if something unexpected happens
            setLoading(false);
        }
    };

    const handleDownloadPDF = async () => {
        if (!sku && !result?.sku) return;
        const targetSku = sku || result.sku;
        if (user?.plan === 'start') {
            alert("Скачивание PDF доступно только на тарифе Аналитик или выше");
            return;
        }
        try {
            const token = window.Telegram?.WebApp?.initData || "";
            const downloadUrl = `${API_URL}/api/report/ai-pdf/${targetSku}?x_tg_data=${encodeURIComponent(token)}`;
            window.open(downloadUrl, '_blank');
        } catch (e) {
            alert("Ошибка скачивания: " + e.message);
        }
    };

    const getScoreColor = (score) => {
        if (score >= 7) return 'bg-emerald-500 text-white';
        if (score >= 4.5) return 'bg-amber-400 text-amber-950';
        return 'bg-red-500 text-white';
    };

    const getTypeIcon = (type) => {
        if (!type) return <Users size={18} />;
        const t = type.toLowerCase();
        if (t.includes('rational')) return <BrainCircuit size={18} className="text-blue-500" />;
        if (t.includes('emotional')) return <Heart size={18} className="text-pink-500" />;
        if (t.includes('skeptic')) return <ShieldCheck size={18} className="text-slate-500" />;
        return <Users size={18} />;
    };

    const getSliderParams = () => {
        if (!productMeta) return { max: 100, min: 10, step: 10 };
        const total = productMeta.total_reviews || 0;
        const max = total > 0 ? total : 200;
        let min = 10;
        if (max < 10) min = 1;
        let step = 10;
        if (max > 1000) step = 50;
        if (max < 50) step = 1;
        return { max, min, step };
    };

    const sParams = getSliderParams();

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            {/* HEADER */}
            <div className="flex justify-between items-stretch h-20">
                <div className="bg-gradient-to-br from-violet-600 to-fuchsia-600 p-4 rounded-3xl text-white shadow-xl shadow-fuchsia-200 flex-1 mr-3 flex flex-col justify-center">
                    <h1 className="text-xl font-black flex items-center gap-2">
                        <Sparkles className="text-yellow-300" size={20} /> AI Стратег
                    </h1>
                    <p className="text-[10px] opacity-80 mt-1">DeepSeek ABSA + Psychographics</p>
                </div>
                
                <div className="flex flex-col gap-2 h-full">
                    <button 
                        onClick={() => navigate('/')} 
                        className="bg-white p-3 rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex-1 flex items-center justify-center active:scale-95"
                        title="Назад на главную"
                    >
                        <ArrowLeft size={20}/>
                    </button>
                    
                    <button 
                        onClick={() => setHistoryOpen(true)} 
                        className="bg-white p-3 rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex-1 flex items-center justify-center active:scale-95"
                    >
                        <Clock size={20}/>
                    </button>
                    
                    {step !== 'input' && (
                        <button 
                            onClick={handleReset}
                            className="bg-slate-100 p-3 rounded-2xl shadow-sm text-slate-500 hover:text-red-500 transition-colors flex-1 flex items-center justify-center active:scale-95"
                            title="Новый поиск"
                        >
                            <RotateCcw size={20}/>
                        </button>
                    )}
                </div>
            </div>

            <HistoryModule type="ai" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

            {/* MAIN INPUT CARD */}
            {step !== 'result' && (
                <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-100 transition-all">
                    
                    {/* Step 1: Input */}
                    {step === 'input' && (
                        <>
                            <input 
                                type="number" 
                                value={sku} 
                                onChange={e => setSku(e.target.value)} 
                                placeholder="Введите Артикул WB" 
                                className="w-full p-4 bg-slate-50 rounded-xl font-bold mb-4 outline-none focus:ring-2 ring-violet-200 transition-all text-lg"
                                onKeyDown={(e) => e.key === 'Enter' && handleCheckProduct()}
                            />
                            <button 
                                onClick={handleCheckProduct} 
                                disabled={metaLoading}
                                className="w-full bg-slate-900 text-white p-4 rounded-xl font-bold shadow-lg active:scale-95 transition-transform flex justify-center items-center gap-2 text-lg"
                            >
                                {metaLoading ? <Loader2 className="animate-spin" /> : <><Search size={20}/> Найти товар</>}
                            </button>
                        </>
                    )}

                    {/* Step 2: Configuration */}
                    {step === 'config' && productMeta && (
                        <div className="animate-in fade-in zoom-in-95 duration-300">
                            <div className="flex gap-4 mb-6 bg-slate-50 p-3 rounded-2xl">
                                {productMeta.image && <img src={productMeta.image} className="w-16 h-20 object-cover rounded-lg bg-white shadow-sm" alt="product"/>}
                                <div>
                                    <h3 className="font-bold text-sm leading-tight mb-1 line-clamp-2">{productMeta.name}</h3>
                                    {productMeta.total_reviews > 0 && (
                                        <div className="text-xs text-slate-500 font-medium bg-white px-2 py-1 rounded-md inline-block shadow-sm">
                                            Доступно: <span className="text-violet-600 font-black">{productMeta.total_reviews}</span> отзывов
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="mb-6 px-2">
                                {/* Quota Display with Plan Info */}
                                {user?.ai_requests_limit > 0 && (
                                    <div className="mb-4 p-4 bg-gradient-to-br from-indigo-50 to-violet-50 rounded-xl border-2 border-indigo-100">
                                        <div className="flex items-center justify-between mb-3">
                                            <div className="flex items-center gap-2">
                                                <BrainCircuit className="text-indigo-600" size={18} />
                                                <span className="text-xs font-bold text-indigo-700 uppercase tracking-wide">AI запросы</span>
                                            </div>
                                            <span className="text-xs font-black bg-white px-2 py-1 rounded-lg text-indigo-900 border border-indigo-200">
                                                {user.ai_requests_used || 0} / {user.ai_requests_limit}
                                                {user?.extra_ai_balance > 0 && (
                                                    <span className="text-emerald-600 ml-1">+{user.extra_ai_balance}</span>
                                                )}
                                            </span>
                                        </div>
                                        <div className="h-2.5 bg-indigo-100 rounded-full overflow-hidden mb-2">
                                            <div 
                                                className="h-full bg-gradient-to-r from-indigo-600 to-violet-600 transition-all"
                                                style={{ 
                                                    width: `${Math.min(100, ((user.ai_requests_used || 0) / user.ai_requests_limit) * 100)}%` 
                                                }}
                                            />
                                        </div>
                                        {user?.extra_ai_balance > 0 && (
                                            <p className="text-xs text-indigo-600 font-medium">Дополнительный баланс: {user.extra_ai_balance} запросов</p>
                                        )}
                                        {((user.ai_requests_used || 0) / user.ai_requests_limit) >= 0.8 && (
                                            <p className="text-xs text-amber-600 font-medium mt-1">⚠️ Осталось мало запросов. Рассмотрите обновление тарифа.</p>
                                        )}
                                    </div>
                                )}
                                
                                {/* Available Features Info */}
                                {user && (
                                    <div className="mb-4 p-3 bg-slate-50 rounded-xl border border-slate-100">
                                        <div className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Доступные функции</div>
                                        <div className="space-y-1.5">
                                            <div className="flex items-center gap-2 text-xs">
                                                <Check size={12} className="text-emerald-600" />
                                                <span className="text-slate-600">Анализ отзывов AI</span>
                                            </div>
                                            {user?.plan === 'start' ? (
                                                <div className="flex items-center gap-2 text-xs">
                                                    <Lock size={12} className="text-amber-500" />
                                                    <span className="text-slate-500">PDF экспорт (доступен на тарифе <strong>Аналитик</strong>+)</span>
                                                </div>
                                            ) : (
                                                <div className="flex items-center gap-2 text-xs">
                                                    <Check size={12} className="text-emerald-600" />
                                                    <span className="text-slate-600">PDF экспорт доступен</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                                
                                <div className="flex justify-between items-center mb-4">
                                    <label className="text-xs font-bold text-slate-400 uppercase flex items-center gap-1">
                                        <Settings2 size={12}/> Глубина анализа
                                    </label>
                                    <span className="text-xs font-black text-white bg-violet-600 px-3 py-1 rounded-full shadow-md shadow-violet-200">
                                        {reviewLimit} шт.
                                    </span>
                                </div>
                                
                                <input 
                                    type="range" 
                                    min={sParams.min}
                                    max={sParams.max}
                                    step={sParams.step}
                                    value={reviewLimit} 
                                    onChange={(e) => setReviewLimit(Number(e.target.value))}
                                    className="w-full h-2 bg-slate-200 rounded-lg cursor-pointer accent-violet-600"
                                />
                                <div className="flex justify-between text-[10px] text-slate-400 mt-2 font-bold px-1">
                                    <span>{sParams.min}</span>
                                    <span>{sParams.max} (Max)</span>
                                </div>
                            </div>

                            <div className="flex gap-2">
                                <button 
                                    onClick={() => setStep('input')}
                                    className="flex-1 bg-slate-100 text-slate-500 p-4 rounded-xl font-bold active:scale-95 transition-transform"
                                >
                                    Назад
                                </button>
                                <button 
                                    onClick={runAnalysis} 
                                    className="flex-[2] bg-violet-600 text-white p-4 rounded-xl font-bold shadow-lg shadow-violet-200 active:scale-95 transition-transform flex justify-center items-center gap-2"
                                >
                                    <Sparkles size={18}/> Анализ
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Loading State */}
                    {step === 'analyzing' && (
                        <div className="py-8 text-center animate-pulse">
                            <Loader2 size={48} className="animate-spin text-violet-600 mx-auto mb-4" />
                            <p className="text-slate-500 font-medium text-sm">{status}</p>
                        </div>
                    )}
                </div>
            )}

            {/* Step 3: Result */}
            {step === 'result' && result && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8">
                    
                    {/* Кнопки действий */}
                    <div className="flex justify-between items-center bg-slate-50 p-2 rounded-2xl">
                         <button onClick={() => setStep('config')} className="text-xs font-bold text-slate-400 hover:text-violet-600 px-3 py-2">
                            ← Настройки
                         </button>
                        <button 
                            onClick={handleDownloadPDF} 
                            disabled={downloading}
                            className={`
                                flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all active:scale-95
                                ${user?.plan === 'start' ? 'bg-white text-slate-400 border border-slate-200' : 'bg-slate-900 text-white shadow-lg'}
                            `}
                        >
                            {downloading ? <Loader2 size={14} className="animate-spin"/> : (user?.plan === 'start' ? <Lock size={14}/> : <FileDown size={14}/>)}
                            {user?.plan === 'start' ? 'PDF (PRO)' : 'Скачать PDF'}
                        </button>
                    </div>

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

                    {result.ai_analysis.global_summary && (
                        <div className={`p-5 rounded-2xl text-sm border-l-4 shadow-md ${
                            result.ai_analysis._error 
                                ? 'bg-red-50 text-red-800 border-red-500' 
                                : 'bg-slate-800 text-slate-200 border-violet-500 italic'
                        }`}>
                            {result.ai_analysis._error ? (
                                <div>
                                    <div className="font-bold mb-1">⚠️ Ошибка AI</div>
                                    <div>{result.ai_analysis.global_summary}</div>
                                </div>
                            ) : (
                                `"${result.ai_analysis.global_summary}"`
                            )}
                        </div>
                    )}

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
                                                className={`h-full rounded-full transition-all duration-1000 ${getScoreColor(aspect.sentiment_score).split(' ')[0]}`} 
                                                style={{width: `${(aspect.sentiment_score / 9) * 100}%`}}
                                            ></div>
                                        </div>
                                        {aspect.actionable_advice && (
                                            <div className="flex gap-2 items-start text-xs text-slate-500 bg-slate-50 p-2 rounded-lg">
                                                <div className="min-w-[4px] h-4 bg-amber-400 rounded-full mt-0.5"></div>
                                                <span className="font-medium">{aspect.actionable_advice}</span>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                     <div className="grid grid-cols-1 gap-4">
                        {/* Блок критических зон (с раскрытием) */}
                        <div className="bg-red-50 p-5 rounded-3xl border border-red-100">
                            <h3 className="text-red-600 font-black text-sm flex items-center gap-2 mb-3 uppercase tracking-wider">
                                <ThumbsDown size={16} /> Критические зоны
                            </h3>
                            <ul className="space-y-2">
                                {result.ai_analysis.flaws?.map((f, i) => (
                                    <ExpandableText 
                                        key={i} 
                                        text={f} 
                                        colorClass="text-slate-700" 
                                        borderClass="border-red-50" 
                                    />
                                ))}
                            </ul>
                        </div>

                        {/* Блок точек роста (с раскрытием) */}
                        <div className="bg-emerald-50 p-5 rounded-3xl border border-emerald-100">
                            <h3 className="text-emerald-600 font-black text-sm flex items-center gap-2 mb-3 uppercase tracking-wider">
                                <Sparkles size={16} /> Точки роста
                            </h3>
                            <ul className="space-y-2">
                                {result.ai_analysis.strategy?.map((s, i) => (
                                    <ExpandableText 
                                        key={i} 
                                        text={s} 
                                        colorClass="text-slate-700" 
                                        borderClass="border-emerald-100 border-l-4 border-l-emerald-400" 
                                    />
                                ))}
                            </ul>
                        </div>
                    </div>

                    <button 
                        onClick={handleReset}
                        className="w-full bg-slate-100 text-slate-500 p-4 rounded-2xl font-bold active:scale-95 transition-all hover:bg-slate-200 hover:text-slate-700 flex items-center justify-center gap-2"
                    >
                        <RotateCcw size={18}/> Проверить другой товар
                    </button>

                </div>
            )}
        </div>
    );
};

export default AIAnalysisPage;