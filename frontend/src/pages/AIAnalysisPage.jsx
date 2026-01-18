import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Clock, Loader2, Star, ThumbsDown, BarChart3, Users, BrainCircuit, ShieldCheck, Heart, FileDown, Lock, Settings2, Search, RotateCcw, ChevronDown, ChevronUp, ArrowLeft, Check, AlertCircle } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

// --- Мини-компонент для раскрывающегося текста ---
const ExpandableText = ({ text, colorClass = "text-slate-700", borderClass = "border-slate-200" }) => {
    const [expanded, setExpanded] = useState(false);
    const safeText = typeof text === 'string' ? text : String(text ?? '');
    const isLong = safeText.length > 60;

    return (
        <li 
            className={`bg-white p-2.5 rounded-xl text-xs font-medium shadow-sm border ${borderClass} transition-all duration-300 ${expanded ? '' : 'hover:bg-slate-50'}`}
            onClick={() => isLong && setExpanded(!expanded)}
        >
            <div className={`flex justify-between items-start gap-2 ${isLong ? 'cursor-pointer' : ''}`}>
                <span className={`${colorClass} ${expanded ? '' : 'line-clamp-2'}`}>
                    {safeText}
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

// Лимиты отзывов по тарифам (дублируем логику фронтенда для UX)
const PLAN_REVIEW_LIMITS = {
    'start': 30,
    'analyst': 100,
    'strategist': 200
};

const AIAnalysisPage = ({ user: propUser, onUserUpdate }) => {
    const navigate = useNavigate();
    
    // --- INTEGRATION FIX: Локальное состояние юзера ---
    const [currentUser, setCurrentUser] = useState(propUser || null);
    const [userLoading, setUserLoading] = useState(!propUser);

    useEffect(() => {
        fetchUser();
    }, []);

    const fetchUser = async () => {
        try {
            const res = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
            if (res.ok) {
                const data = await res.json();
                setCurrentUser(data);
                if (onUserUpdate) onUserUpdate(data);
            }
        } catch (e) {
            console.error("User fetch error:", e);
        } finally {
            setUserLoading(false);
        }
    };
    // --------------------------------------------------

    const [sku, setSku] = useState('');
    const [step, setStep] = useState('input'); // input | config | analyzing | result
    
    // Product Stats
    const [productMeta, setProductMeta] = useState(null);
    const [metaLoading, setMetaLoading] = useState(false);
    
    // Analysis Config
    const [reviewLimit, setReviewLimit] = useState(30); // Default to min
    const [loading, setLoading] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [status, setStatus] = useState('');
    const [result, setResult] = useState(null);
    const [historyOpen, setHistoryOpen] = useState(false);
    const cancelTokenRef = useRef(false);

    // Получаем лимит юзера
    const userMaxLimit = PLAN_REVIEW_LIMITS[currentUser?.plan] || 30;

    // СБРОС СОСТОЯНИЯ
    const handleReset = () => {
        cancelTokenRef.current = true;
        setSku('');
        setStep('input');
        setProductMeta(null);
        setResult(null);
        setReviewLimit(userMaxLimit); // Reset to plan max
        setStatus('');
        setLoading(false);
        window.scrollTo({ top: 0, behavior: 'smooth' });
        fetchUser(); 
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
            
            if (!res.ok) throw new Error(data.detail || "Ошибка проверки");
            if (data.status === 'error') throw new Error(data.message || "Товар не найден");
            
            setProductMeta(data);
            
            const total = data.total_reviews || 0;
            
            // Умная установка лимита: не больше чем есть отзывов, и не больше чем тариф
            let safeLimit = userMaxLimit;
            if (total < safeLimit) safeLimit = total;
            if (total === 0) safeLimit = 0; // No reviews
            
            setReviewLimit(safeLimit);
            setStep('config');
        } catch (e) {
            alert(e.message);
        } finally {
            setMetaLoading(false);
        }
    };

    const runAnalysis = async () => {
        cancelTokenRef.current = false;
        setLoading(true);
        setStep('analyzing');
        setResult(null);
        setStatus('Инициализация...');
        
        try {
            const res = await fetch(`${API_URL}/api/ai/analyze/${sku}?limit=${reviewLimit}`, { 
                method: 'POST', 
                headers: getTgHeaders() 
            });
            
            if (!res.ok) {
                let errorData;
                try { errorData = await res.json(); } catch { errorData = { detail: `Ошибка ${res.status}` }; }
                setLoading(false);
                setStep('config');
                alert(errorData.detail || "Не удалось запустить анализ");
                return;
            }
            
            const data = await res.json();
            
            if (data.status && data.status !== "accepted" && data.status !== "success") {
                setLoading(false);
                setStep('config');
                alert(data.error || data.detail || "Ошибка запуска анализа");
                return;
            }
            
            const taskId = data.task_id;
            if (!taskId || typeof taskId !== 'string') {
                setLoading(false);
                setStep('config');
                alert('Не получен корректный task_id от сервера');
                return;
            }
            
            if (onUserUpdate) onUserUpdate();
            
            const queueInfo = {
                queue: data.queue || "normal",
                position: data.position || 0,
                is_priority: data.is_priority || false
            };

            // POLLING LOOP
            let attempts = 0;
            while(attempts < 120 && !cancelTokenRef.current) {
                if (cancelTokenRef.current) {
                    setLoading(false);
                    return;
                }
                
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
                } catch (e) {}
                
                if (queueInfo.is_priority) {
                    setStatus(`⚡ Приоритетная очередь: позиция ${queueInfo.position}... (${attempts*2}s)`);
                } else if (queueInfo.position > 0) {
                    setStatus(`⏳ Ваше место в очереди: ${queueInfo.position}... (${attempts*2}s)`);
                } else {
                    setStatus(`Парсинг ${reviewLimit} последних отзывов... (${attempts*2}s)`);
                }
                
                await new Promise(r => setTimeout(r, 2000));
                
                if (cancelTokenRef.current) {
                    setLoading(false);
                    return;
                }
                
                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`, { headers: getTgHeaders() });
                
                if (!sRes.ok) {
                    attempts++;
                    continue;
                }

                let sData;
                try { sData = await sRes.json(); } catch { attempts++; continue; }
                
                const status = (sData.status || "").toUpperCase();
                
                if (status === 'SUCCESS') {
                    const resultData = sData.data || sData.result;

                    if (!resultData) {
                        setLoading(false);
                        setStep('config');
                        alert('Ошибка: получены пустые данные от сервера');
                        return;
                    }
                    
                    if (resultData.status === 'error') {
                        setLoading(false);
                        setStep('config');
                        alert(`Ошибка анализа: ${resultData.error || resultData.message || 'Неизвестная ошибка'}`);
                        return;
                    }
                    
                    if (!resultData.ai_analysis || typeof resultData.ai_analysis !== 'object') {
                        resultData.ai_analysis = {
                            _error: 'Данные анализа отсутствуют',
                            aspects: [],
                            audience_stats: { rational_percent: 0, emotional_percent: 0, skeptic_percent: 0 },
                            global_summary: 'Ошибка при получении данных анализа',
                            strategy: [],
                            flaws: []
                        };
                    }
                    
                    if (resultData.ai_analysis?._error) {
                        setStatus(`⚠️ Ошибка AI: ${resultData.ai_analysis._error}`);
                    }
                    
                    setResult(resultData);
                    setStep('result');
                    setLoading(false);
                    fetchUser();
                    return;
                }
                
                if (status === 'FAILURE' || status === 'REVOKED') {
                    const errorMsg = sData.error || sData.result?.error || "Ошибка выполнения задачи";
                    throw new Error(errorMsg);
                }
                if (sData.info) setStatus(sData.info);
                
                attempts++;
            }
            
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
            if (!result) setLoading(false);
        }
    };

    const handleDownloadPDF = async () => {
        if (!sku && !result?.sku) return;
        const targetSku = sku || result?.sku;
        
        if (currentUser?.plan === 'start') {
            alert("Скачивание PDF доступно только на тарифе Аналитик или выше");
            return;
        }
        try {
            setDownloading(true);
            const token = window.Telegram?.WebApp?.initData || "";
            const downloadUrl = `${API_URL}/api/report/ai-pdf/${targetSku}?x_tg_data=${encodeURIComponent(token)}`;
            window.open(downloadUrl, '_blank');
        } catch (e) {
            alert("Ошибка скачивания: " + e.message);
        } finally {
            setDownloading(false);
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
        if (!productMeta) return { max: userMaxLimit, min: 10, step: 10 };
        const total = productMeta.total_reviews || 0;
        // Лимит = минимум из (всего отзывов, лимит тарифа)
        const max = Math.min(total > 0 ? total : userMaxLimit, userMaxLimit);
        
        let min = 1;
        if (max < 1) min = 0;
        else if (max >= 10) min = 10;
        
        let step = 10;
        if (max < 50) step = 1;
        
        return { max, min, step };
    };

    const sParams = getSliderParams();

    if (userLoading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-[#F7F9FC]">
                <Loader2 className="animate-spin text-violet-600" size={32} />
            </div>
        );
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4 bg-[#F7F9FC] min-h-screen">
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
                        >
                            <RotateCcw size={20}/>
                        </button>
                    )}
                </div>
            </div>

            <HistoryModule type="ai" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} onSelect={(item) => {
                setSku(item.sku);
                setHistoryOpen(false);
                handleCheckProduct();
            }} />

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
                                            Всего: <span className="text-violet-600 font-black">{productMeta.total_reviews}</span> отзывов
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="mb-6 px-2">
                                {/* Лимиты пользователя */}
                                {currentUser?.ai_requests_limit > 0 && (
                                    <div className="mb-4 p-4 bg-gradient-to-br from-indigo-50 to-violet-50 rounded-xl border-2 border-indigo-100">
                                        <div className="flex items-center justify-between mb-3">
                                            <div className="flex items-center gap-2">
                                                <BrainCircuit className="text-indigo-600" size={18} />
                                                <span className="text-xs font-bold text-indigo-700 uppercase tracking-wide">AI запросы</span>
                                            </div>
                                            <span className="text-xs font-black bg-white px-2 py-1 rounded-lg text-indigo-900 border border-indigo-200">
                                                {currentUser.ai_requests_used || 0} / {currentUser.ai_requests_limit}
                                            </span>
                                        </div>
                                        <div className="h-2.5 bg-indigo-100 rounded-full overflow-hidden mb-2">
                                            <div 
                                                className="h-full bg-gradient-to-r from-indigo-600 to-violet-600 transition-all"
                                                style={{ 
                                                    width: `${Math.min(100, ((currentUser.ai_requests_used || 0) / currentUser.ai_requests_limit) * 100)}%` 
                                                }}
                                            />
                                        </div>
                                    </div>
                                )}
                                
                                {/* Слайдер глубины анализа */}
                                <div className="flex justify-between items-center mb-4">
                                    <label className="text-xs font-bold text-slate-400 uppercase flex items-center gap-1">
                                        <Settings2 size={12}/> Глубина анализа
                                    </label>
                                    <div className="flex items-center gap-2">
                                        {userMaxLimit < (productMeta.total_reviews || 9999) && (
                                            <span className="text-[10px] text-amber-600 bg-amber-50 px-2 py-0.5 rounded border border-amber-100">
                                                Лимит тарифа: {userMaxLimit}
                                            </span>
                                        )}
                                        <span className="text-xs font-black text-white bg-violet-600 px-3 py-1 rounded-full shadow-md shadow-violet-200">
                                            {reviewLimit} шт.
                                        </span>
                                    </div>
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
                                <p className="text-[10px] text-slate-400 text-center mt-2">
                                    Больше отзывов = точнее результат, но дольше ожидание
                                </p>
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

            {/* Step 3: Result (Same as before) */}
            {step === 'result' && result && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8">
                    
                    <div className="flex justify-between items-center bg-slate-50 p-2 rounded-2xl">
                         <button onClick={() => setStep('config')} className="text-xs font-bold text-slate-400 hover:text-violet-600 px-3 py-2">
                           ← Настройки
                         </button>
                        <button 
                            onClick={handleDownloadPDF} 
                            disabled={downloading}
                            className={`
                                flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all active:scale-95
                                ${currentUser?.plan === 'start' ? 'bg-white text-slate-400 border border-slate-200' : 'bg-slate-900 text-white shadow-lg'}
                            `}
                        >
                            {downloading ? <Loader2 size={14} className="animate-spin"/> : (currentUser?.plan === 'start' ? <Lock size={14}/> : <FileDown size={14}/>)}
                            {currentUser?.plan === 'start' ? 'PDF (PRO)' : 'Скачать PDF'}
                        </button>
                    </div>

                    {/* --- Result Components (Stats, Summary, Aspects, etc.) --- */}
                    {/* (Код отображения результатов оставлен без изменений для краткости, он работает корректно) */}
                    <div className="flex gap-4 items-center bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                        {result?.image && <img src={result.image} className="w-16 h-20 object-cover rounded-lg bg-slate-100" alt="product" />}
                        <div>
                            <div className="flex items-center gap-1 text-amber-500 font-black mb-1 text-lg">
                                <Star size={18} fill="currentColor" /> {result?.rating ?? 0}
                            </div>
                            <p className="text-xs text-slate-400 font-bold uppercase tracking-wider">Датасет</p>
                            <p className="font-bold">{result?.reviews_count ?? 0} отзывов</p>
                        </div>
                    </div>

                    {result?.ai_analysis?.global_summary && (
                        <div className={`p-5 rounded-2xl text-sm border-l-4 shadow-md ${
                            result?.ai_analysis?._error 
                                ? 'bg-red-50 text-red-800 border-red-500' 
                                : 'bg-slate-800 text-slate-200 border-violet-500 italic'
                        }`}>
                             {result?.ai_analysis?._error ? (
                                <div>
                                    <div className="font-bold mb-1 flex items-center gap-2"><AlertCircle size={16}/> Ошибка AI</div>
                                    <div>{result.ai_analysis.global_summary}</div>
                                </div>
                            ) : (
                                `"${result.ai_analysis.global_summary}"`
                            )}
                        </div>
                    )}
                    
                    {/* Audience Stats */}
                    {result?.ai_analysis?.audience_stats && (
                        <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                            <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                                <Users className="text-violet-600" size={20}/> Портрет аудитории
                            </h3>
                            <div className="grid grid-cols-3 gap-2 mb-6">
                                <div className="bg-blue-50 p-3 rounded-2xl text-center border border-blue-100">
                                    <BrainCircuit className="mx-auto text-blue-500 mb-1" size={20}/>
                                    <div className="text-xl font-black text-blue-700">{result?.ai_analysis?.audience_stats?.rational_percent ?? 0}%</div>
                                    <div className="text-[10px] uppercase font-bold text-blue-400">Рационал</div>
                                </div>
                                <div className="bg-pink-50 p-3 rounded-2xl text-center border border-pink-100">
                                    <Heart className="mx-auto text-pink-500 mb-1" size={20}/>
                                    <div className="text-xl font-black text-pink-700">{result?.ai_analysis?.audience_stats?.emotional_percent ?? 0}%</div>
                                    <div className="text-[10px] uppercase font-bold text-pink-400">Эмоционал</div>
                                </div>
                                <div className="bg-slate-50 p-3 rounded-2xl text-center border border-slate-200">
                                    <ShieldCheck className="mx-auto text-slate-500 mb-1" size={20}/>
                                    <div className="text-xl font-black text-slate-700">{result?.ai_analysis?.audience_stats?.skeptic_percent ?? 0}%</div>
                                    <div className="text-[10px] uppercase font-bold text-slate-400">Скептик</div>
                                </div>
                            </div>
                            {result?.ai_analysis?.infographic_recommendation && (
                                <div className="bg-violet-50 border border-violet-100 p-4 rounded-2xl flex gap-3 items-start">
                                    <div className="bg-white p-2 rounded-xl shadow-sm shrink-0">
                                        {getTypeIcon(result?.ai_analysis?.dominant_type)}
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
                    
                    {/* Aspects */}
                    {result?.ai_analysis?.aspects && Array.isArray(result.ai_analysis.aspects) && result.ai_analysis.aspects.length > 0 && (
                        <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                             <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                                <BarChart3 className="text-violet-600" size={20}/> Аспектный анализ
                            </h3>
                            <div className="space-y-6">
                                {result.ai_analysis.aspects.map((aspect, idx) => {
                                    if (!aspect || typeof aspect !== 'object') return null;
                                    const sentimentScore = aspect.sentiment_score ?? 0;
                                    return (
                                        <div key={idx} className="relative">
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="font-bold text-sm text-slate-700">{aspect.aspect ?? 'Неизвестный аспект'}</span>
                                                <span className={`text-[10px] font-black px-2 py-0.5 rounded-md ${getScoreColor(sentimentScore)}`}>
                                                    {sentimentScore}/9.0
                                                </span>
                                            </div>
                                            <div className="h-2 w-full bg-slate-100 rounded-full mb-2 overflow-hidden">
                                                <div 
                                                    className={`h-full rounded-full transition-all duration-1000 ${getScoreColor(sentimentScore).split(' ')[0]}`} 
                                                    style={{width: `${(sentimentScore / 9) * 100}%`}}
                                                ></div>
                                            </div>
                                            {aspect.actionable_advice && (
                                                <div className="flex gap-2 items-start text-xs text-slate-500 bg-slate-50 p-2 rounded-lg">
                                                    <div className="min-w-[4px] h-4 bg-amber-400 rounded-full mt-0.5"></div>
                                                    <span className="font-medium">{aspect.actionable_advice}</span>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                    
                    <div className="grid grid-cols-1 gap-4">
                        <div className="bg-red-50 p-5 rounded-3xl border border-red-100">
                            <h3 className="text-red-600 font-black text-sm flex items-center gap-2 mb-3 uppercase tracking-wider">
                                <ThumbsDown size={16} /> Критические зоны
                            </h3>
                            <ul className="space-y-2">
                                {(result?.ai_analysis?.flaws || result?.ai_analysis?.negatives || [])?.length > 0 ? (
                                    (result?.ai_analysis?.flaws || result?.ai_analysis?.negatives).map((f, i) => (
                                        <ExpandableText key={i} text={String(f)} colorClass="text-slate-700" borderClass="border-red-50" />
                                    ))
                                ) : (
                                    <li className="text-xs text-slate-400 italic">Критические зоны не обнаружены</li>
                                )}
                            </ul>
                        </div>
                        <div className="bg-emerald-50 p-5 rounded-3xl border border-emerald-100">
                            <h3 className="text-emerald-600 font-black text-sm flex items-center gap-2 mb-3 uppercase tracking-wider">
                                <Sparkles size={16} /> Точки роста
                            </h3>
                             <ul className="space-y-2">
                                {Array.isArray(result?.ai_analysis?.strategy) && result.ai_analysis.strategy.length > 0 ? (
                                    result.ai_analysis.strategy.map((s, i) => (
                                        <ExpandableText key={i} text={String(s)} colorClass="text-slate-700" borderClass="border-emerald-100 border-l-4 border-l-emerald-400" />
                                    ))
                                ) : (
                                    <li className="text-xs text-slate-400 italic">Точки роста не обнаружены</li>
                                )}
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