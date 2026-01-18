import React, { useState, useEffect } from 'react';
import { Wand2, Clock, Loader2, Sparkles, Copy, X, BrainCircuit, Layers, Table, HelpCircle, FileText, Download, Lock, CheckCircle, AlertCircle, XCircle, ArrowLeft } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

// Toast Notification Component
const Toast = ({ message, type = 'error', onClose }) => {
    useEffect(() => {
        const timer = setTimeout(() => onClose(), 5000);
        return () => clearTimeout(timer);
    }, [onClose]);

    const bgColor = type === 'success' ? 'bg-emerald-500' : type === 'info' ? 'bg-blue-500' : 'bg-red-500';
    const Icon = type === 'success' ? CheckCircle : type === 'info' ? AlertCircle : XCircle;

    return (
        <div className={`fixed top-4 right-4 ${bgColor} text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-3 z-50 animate-in slide-in-from-top-5 fade-in min-w-[300px] max-w-[90vw]`}>
            <Icon size={20} className="shrink-0" />
            <p className="flex-1 text-sm font-medium">{message}</p>
            <button onClick={onClose} className="shrink-0 hover:opacity-70 transition-opacity">
                <X size={16} />
            </button>
        </div>
    );
};

const SeoGeneratorPage = ({ user, onUserUpdate }) => {
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
    
    // Toast State
    const [toast, setToast] = useState(null);
    
    const showToast = (message, type = 'error') => {
        setToast({ message, type });
    };

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
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ sku: Number(sku), keywords })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.message || 'Ошибка запуска кластеризации');
            const taskId = data.task_id;
            if (!taskId) throw new Error('Не получен task_id');

            const queueInfo = { position: data.position ?? 0, is_priority: data.is_priority ?? false };
            let attempts = 0;
            while (attempts < 40) {
                await new Promise(r => setTimeout(r, 2000));
                try {
                    const qRes = await fetch(`${API_URL}/api/ai/queue/${taskId}`, { headers: getTgHeaders() });
                    if (qRes.ok) {
                        const q = await qRes.json();
                        if (q.position != null) queueInfo.position = q.position;
                        queueInfo.is_priority = q.is_priority ?? queueInfo.is_priority;
                    }
                } catch (_) {}
                const pos = queueInfo.position;
                setStatus(queueInfo.is_priority
                    ? `Приоритет: поз. ${pos}… (${attempts * 2}с)`
                    : pos > 0 ? `Очередь: поз. ${pos}… (${attempts * 2}с)` : `Кластеризация… (${attempts * 2}с)`);

                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`, { headers: getTgHeaders() });
                if (!sRes.ok) { attempts++; continue; }
                const sData = await sRes.json().catch(() => ({}));
                if ((sData.status || '').toUpperCase() === 'SUCCESS') {
                    const raw = sData.data || {};
                    if (raw.error) {
                        setError('Кластеризация: ' + raw.error);
                        showToast('Кластеризация: ' + raw.error, 'error');
                        return;
                    }
                    const clustersData = raw.clusters ?? (Array.isArray(raw) ? raw : []);
                    setClusters(Array.isArray(clustersData) ? clustersData : (clustersData?.clusters || []));
                    showToast(`Кластеризация завершена: ${clustersData.length || 0} групп`, 'success');
                    onUserUpdate?.();
                    return;
                }
                if ((sData.status || '').toUpperCase() === 'FAILURE') throw new Error(sData.error || 'Ошибка кластеризации');
                if (sData.info) setStatus(sData.info);
                attempts++;
            }
            throw new Error('Превышено время ожидания');
        } catch (e) {
            const errorMsg = e.message || 'Ошибка кластеризации';
            setError(errorMsg);
            showToast(errorMsg, 'error');
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
            const res = await fetch(`${API_URL}/api/seo/generate`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ sku: Number(sku), keywords, tone, title_len: titleLen, desc_len: descLen })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.message || 'Не удалось запустить генерацию');
            const taskId = data.task_id;
            if (!taskId) throw new Error('Не получен task_id');

            const queueInfo = { position: data.position ?? 0, is_priority: data.is_priority ?? false };
            let attempts = 0;
            while (attempts < 60) {
                await new Promise(r => setTimeout(r, 3000));
                try {
                    const qRes = await fetch(`${API_URL}/api/ai/queue/${taskId}`, { headers: getTgHeaders() });
                    if (qRes.ok) {
                        const q = await qRes.json();
                        if (q.position != null) queueInfo.position = q.position;
                        queueInfo.is_priority = q.is_priority ?? queueInfo.is_priority;
                    }
                } catch (_) {}
                const pos = queueInfo.position;
                setStatus(queueInfo.is_priority
                    ? `Приоритет: поз. ${pos}… (${attempts * 3}с)`
                    : pos > 0 ? `Очередь: поз. ${pos}… (${attempts * 3}с)` : `Генерация GEO… (${attempts * 3}с)`);

                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`, { headers: getTgHeaders() });
                if (!sRes.ok) { attempts++; continue; }
                const sData = await sRes.json().catch(() => ({}));
                if ((sData.status || '').toUpperCase() === 'SUCCESS') {
                    const payload = sData.data || sData.result;
                    if (payload?.generated_content?._error) setError(`⚠️ Ошибка AI: ${payload.generated_content._error}`);
                    setResult(payload?.generated_content || payload);
                    setStep(3);
                    onUserUpdate?.();
                    return;
                }
                if ((sData.status || '').toUpperCase() === 'FAILURE') throw new Error(sData.error || sData.data?.error || 'Ошибка генерации');
                if (sData.info) setStatus(sData.info);
                attempts++;
            }
            throw new Error('Превышено время ожидания');
        } catch (e) { setError(e.message || ''); } finally { setLoading(false); setStatus(''); }
    };

    const downloadPdf = async () => {
        if (!result || !sku) return;
        if (user?.plan === 'start') {
            showToast("Скачивание PDF доступно только на тарифе Аналитик или выше", 'info');
            return;
        }
        setPdfLoading(true);
        try {
            // Как в AIAnalysisPage: window.open для мобильных (blob+click часто не срабатывает)
            const token = window.Telegram?.WebApp?.initData || '';
            if (!token) {
                showToast("Ошибка авторизации. Перезагрузите страницу.", 'error');
                return;
            }
            const url = `${API_URL}/api/report/seo-pdf/${sku}?x_tg_data=${encodeURIComponent(token)}`;
            window.open(url, '_blank');
        } catch (e) {
            showToast("Не удалось скачать PDF: " + (e.message || ''), 'error');
        } finally {
            setPdfLoading(false);
        }
    };

    const CopyButton = ({ text, onCopy }) => {
        const handleCopy = () => {
            navigator.clipboard.writeText(text);
            if (onCopy) onCopy();
            else showToast("Скопировано!", 'success');
        };
        return (
            <button onClick={handleCopy} className="p-2 text-slate-400 hover:text-indigo-600 transition-colors bg-slate-50 rounded-lg">
                <Copy size={16} />
            </button>
        );
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
            
            {/* Header styled like SupplyPage */}
            <div className="flex justify-between items-stretch h-20 mb-6">
                 {/* Main Header Card */}
                 <div className="bg-gradient-to-r from-orange-500 to-pink-500 p-6 rounded-[28px] text-white shadow-xl shadow-orange-200 relative overflow-hidden flex-1 mr-3 flex items-center justify-between">
                    {/* Title Area */}
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <Wand2 className="text-yellow-200" size={24} /> SEO Gen
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">GEO-оптимизация 2026</p>
                    </div>

                    {/* History Button inside Header */}
                    <div className="relative z-10">
                         <button 
                            onClick={() => setHistoryOpen(true)}
                            className="bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm"
                            title="История"
                        >
                            <Clock size={20} />
                        </button>
                    </div>
                    
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 {/* Right Sidebar Buttons */}
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button 
                        onClick={() => window.history.length > 1 ? window.history.back() : window.location.href = '/'} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                        title="Назад"
                     >
                         <ArrowLeft size={24}/>
                     </button>
                     
                     <div className="group relative h-full">
                        <button className="bg-white h-full w-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95">
                            <HelpCircle size={24}/>
                        </button>
                        {/* Tooltip positioned to the left of the sidebar */}
                        <div className="hidden group-hover:block absolute top-0 right-full mr-2 w-72 p-3 bg-slate-900 text-white text-xs rounded-xl shadow-xl z-50 max-h-[80vh] overflow-y-auto">
                            <div className="font-bold mb-2">SEO Генератор</div>
                            <p className="mb-2">Создавайте оптимизированные описания товаров с помощью AI:</p>
                            <ul className="space-y-1 text-[10px] list-disc list-inside">
                                <li><strong>Кластеризация ключевых слов</strong> - группировка по темам (Аналитик+)</li>
                                <li><strong>Генерация контента</strong> - создание заголовков и описаний</li>
                                <li><strong>Выбор тона</strong> - продающий, информативный, дерзкий и др. (Аналитик+)</li>
                                <li><strong>Настройка длины</strong> - контроль размера заголовка и описания</li>
                            </ul>
                            <p className="mt-2 text-[10px]">Используйте кластеризацию для лучшей структуры ключевых слов перед генерацией.</p>
                            <div className="absolute top-6 right-0 translate-x-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-l-slate-900"></div>
                        </div>
                     </div>
                 </div>
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
                                disabled={loading || clusters || user?.plan === 'start'}
                                title={user?.plan === 'start' ? 'Доступно на тарифе Аналитик и выше' : ''}
                                className={`text-xs font-bold px-3 py-2 rounded-xl flex items-center gap-2 transition-all ${user?.plan === 'start' ? 'bg-slate-200 text-slate-500 cursor-not-allowed' : clusters ? 'bg-emerald-100 text-emerald-700' : 'bg-indigo-600 text-white shadow-lg shadow-indigo-200'}`}
                            >
                                {user?.plan === 'start' ? <Lock size={14}/> : loading ? <Loader2 size={14} className="animate-spin"/> : <BrainCircuit size={14}/>}
                                {clusters ? 'Сгруппировано' : user?.plan === 'start' ? 'AI Кластеризация (Аналитик+)' : 'AI Кластеризация'}
                            </button>
                        </div>

                        {user && (
                            <>
                                <div className="p-3 bg-gradient-to-br from-orange-50 to-pink-50 rounded-xl border border-orange-100">
                                    <div className="flex justify-between items-center text-xs">
                                        <span className="font-bold text-orange-800">AI запросы</span>
                                        <span className="font-black text-orange-900">{user.ai_requests_used ?? 0} / {user.ai_requests_limit ?? 0}</span>
                                    </div>
                                    <div className="h-1.5 bg-orange-100 rounded-full mt-1 overflow-hidden">
                                        <div className="h-full bg-orange-500 rounded-full" style={{ width: `${Math.min(100, ((user.ai_requests_used || 0) / (user.ai_requests_limit || 1)) * 100)}%` }} />
                                    </div>
                                </div>
                                {user.cluster_requests_limit !== undefined && user.cluster_requests_limit > 0 && (
                                    <div className="p-3 bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl border border-indigo-100">
                                        <div className="flex justify-between items-center text-xs">
                                            <span className="font-bold text-indigo-800">Кластеризация</span>
                                            <span className="font-black text-indigo-900">{user.cluster_requests_used ?? 0} / {user.cluster_requests_limit ?? 0}</span>
                                        </div>
                                        <div className="h-1.5 bg-indigo-100 rounded-full mt-1 overflow-hidden">
                                            <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min(100, ((user.cluster_requests_used || 0) / (user.cluster_requests_limit || 1)) * 100)}%` }} />
                                        </div>
                                    </div>
                                )}
                            </>
                        )}

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

                            <div className="flex items-center justify-between mb-2">
                                <h3 className="font-bold text-sm">Tone of Voice</h3>
                                {user?.plan === 'start' && <span className="text-[10px] text-amber-600 flex items-center gap-1"><Lock size={10}/> Выбор тона на Аналитик+</span>}
                            </div>
                            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                                {toneOptions.map(t => {
                                    const locked = user?.plan === 'start' && t !== 'Продающий';
                                    return (
                                        <button 
                                            key={t}
                                            onClick={() => !locked && setTone(t)}
                                            disabled={locked}
                                            title={locked ? 'Доступно на тарифе Аналитик+' : ''}
                                            className={`px-4 py-2 rounded-xl text-xs font-bold border whitespace-nowrap transition-all relative group ${
                                                locked 
                                                    ? 'border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50 text-amber-600 cursor-not-allowed shadow-sm' 
                                                    : tone === t 
                                                        ? 'border-orange-500 bg-orange-50 text-orange-600 shadow-md' 
                                                        : 'border-slate-100 bg-white text-slate-500 hover:border-orange-200 hover:bg-orange-50'
                                            }`}
                                        >
                                            {locked && (
                                                <Lock size={12} className="inline-block mr-1.5 opacity-70" />
                                            )}
                                            {t}
                                            {locked && (
                                                <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-slate-900 text-white text-[10px] rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
                                                    Доступно на тарифе Аналитик+
                                                    <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-slate-900"></div>
                                                </div>
                                            )}
                                        </button>
                                    );
                                })}
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
                    <div className={`p-6 rounded-3xl shadow-sm border-2 ${
                        result._error 
                            ? 'bg-red-50 border-red-200' 
                            : 'bg-white border-slate-100'
                    }`}>
                        {result._error && (
                            <div className="mb-4 p-3 bg-red-100 border border-red-300 rounded-xl text-sm text-red-800">
                                <div className="font-bold mb-1">⚠️ Ошибка AI</div>
                                <div>{result._error}</div>
                            </div>
                        )}
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