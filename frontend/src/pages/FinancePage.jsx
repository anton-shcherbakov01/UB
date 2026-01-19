import React, { useState, useEffect, useMemo } from 'react';
import { 
    Loader2, Calculator, DollarSign, Info, Truck, HelpCircle, ArrowLeft, Download, RefreshCw, Calendar, ChevronDown
} from 'lucide-react';
import { 
    BarChart, Bar, Tooltip as RechartsTooltip, ResponsiveContainer, 
    Cell, ReferenceLine, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';
import CostEditModal from '../components/CostEditModal';

// Компонент подсказки (Tooltip)
const InfoTooltip = ({ text }) => (
    <div className="group/tooltip relative inline-flex items-center ml-1.5 align-middle">
        <HelpCircle size={14} className="text-slate-300 cursor-help hover:text-indigo-400 transition-colors" />
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 bg-slate-800 text-white text-[11px] leading-relaxed rounded-xl opacity-0 group-hover/tooltip:opacity-100 pointer-events-none transition-all duration-200 z-50 shadow-xl border border-white/10">
            {text}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800"></div>
        </div>
    </div>
);

const FinancePage = ({ user, onNavigate }) => {
    // --- State ---
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingCost, setEditingCost] = useState(null);
    const [viewMode, setViewMode] = useState('unit'); // 'unit' | 'pnl'
    
    // Dates
    const [dateRange, setDateRange] = useState(() => {
        const end = new Date();
        const start = new Date();
        start.setDate(end.getDate() - 30);
        return {
            start: start.toISOString().split('T')[0],
            end: end.toISOString().split('T')[0],
            label: 'month' // 'week', 'month', '90', 'custom'
        };
    });

    // Data
    const [pnlData, setPnlData] = useState(null);
    const [pnlLoading, setPnlLoading] = useState(false);
    const [pnlError, setPnlError] = useState(null);
    
    // Status
    const [pdfLoading, setPdfLoading] = useState(false);
    const [syncLoading, setSyncLoading] = useState(false);

    // --- Helpers ---
    const handleDatePreset = (days) => {
        const end = new Date();
        const start = new Date();
        start.setDate(end.getDate() - days);
        setDateRange({
            start: start.toISOString().split('T')[0],
            end: end.toISOString().split('T')[0],
            label: days === 7 ? 'week' : days === 30 ? 'month' : '90'
        });
    };

    const handleDateChange = (field, value) => {
        setDateRange(prev => ({
            ...prev,
            [field]: value,
            label: 'custom'
        }));
    };

    // --- API Calls ---
    const fetchProducts = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/internal/products`, {
                headers: getTgHeaders()
            });
            if (res.ok) {
                const data = await res.json();
                setProducts(data);
            }
        } catch(e) { 
            console.error(e); 
        } finally { 
            setLoading(false); 
        }
    };

    useEffect(() => { fetchProducts(); }, []);
    
    const fetchPnlData = async () => {
        setPnlLoading(true);
        setPnlError(null);
        try {
            // Формируем query параметры с датами
            const query = new URLSearchParams({
                date_from: dateRange.start,
                date_to: dateRange.end
            }).toString();

            const res = await fetch(`${API_URL}/api/finance/pnl?${query}`, {
                headers: getTgHeaders()
            });
            
            if (res.ok) {
                const data = await res.json();
                setPnlData(data);
            } else {
                const errorData = await res.json().catch(() => ({ detail: 'Неизвестная ошибка' }));
                if (res.status === 403) {
                    setPnlError(errorData.detail || 'P&L недоступен на вашем тарифе.');
                } else {
                    setPnlError(errorData.detail || 'Ошибка загрузки данных P&L');
                }
                setPnlData(null);
            }
        } catch(e) { 
            console.error(e);
            setPnlError('Ошибка соединения с сервером');
            setPnlData(null);
        } finally {
            setPnlLoading(false);
        }
    };
    
    // Перезагружаем P&L при смене режима просмотра ИЛИ дат
    useEffect(() => {
        if (viewMode === 'pnl') {
            fetchPnlData();
        }
    }, [viewMode, dateRange.start, dateRange.end]);

    const handleSync = async () => {
        setSyncLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/finance/sync/pnl`, {
                method: 'POST',
                headers: getTgHeaders()
            });
            if (res.ok) {
                alert("Синхронизация запущена! Данные обновляются в фоне. Пожалуйста, подождите 1-2 минуты и обновите страницу.");
                // Авто-обновление через 5 секунд, вдруг быстро пролетит
                setTimeout(() => {
                    if (viewMode === 'pnl') fetchPnlData();
                }, 5000);
            } else {
                alert("Ошибка запуска синхронизации");
            }
        } catch (e) {
            console.error(e);
            alert("Ошибка сети");
        } finally {
            setSyncLoading(false);
        }
    };

    const handleUpdateCost = async (sku, formData) => {
        try {
            await fetch(`${API_URL}/api/internal/cost/${sku}`, {
                method: 'POST',
                headers: {
                    ...getTgHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    cost_price: Number(formData.cost_price),
                    logistics: formData.logistics ? Number(formData.logistics) : null,
                    commission_percent: formData.commission_percent ? Number(formData.commission_percent) : null
                })
            });
            setEditingCost(null);
            fetchProducts();
        } catch(e) { 
            alert("Ошибка обновления"); 
        }
    };

    const handleDownload = async () => {
        setPdfLoading(true);
        try {
            const token = window.Telegram?.WebApp?.initData || '';
            if (!token) {
                alert('Ошибка авторизации. Перезагрузите страницу.');
                return;
            }
            const endpoint = viewMode === 'unit' 
                ? '/api/finance/report/unit-economy-pdf'
                : '/api/finance/report/pnl-pdf';
            
            // Добавляем даты в параметры PDF
            const query = viewMode === 'pnl' 
                ? `&date_from=${dateRange.start}&date_to=${dateRange.end}`
                : '';

            const url = `${API_URL}${endpoint}?x_tg_data=${encodeURIComponent(token)}${query}`;
            window.open(url, '_blank');
        } catch (e) {
            alert('Не удалось скачать PDF: ' + (e.message || ''));
        } finally {
            setPdfLoading(false);
        }
    };

    // --- Calculations ---
    const pnlStats = useMemo(() => {
        // ... (расчет unit-экономики остается без изменений для режима Unit)
        let grossSales = 0;
        let cogs = 0;
        let logisticsTotal = 0; 
        let commissionTotal = 0; 
        
        products.forEach(p => {
            const velocity = p.supply?.metrics?.avg_daily_demand || 0;
            const monthlySales = velocity * 30;
            if (monthlySales > 0) {
                const price = p.price_structure?.selling || 0;
                grossSales += price * monthlySales;
                cogs += p.cost_price * monthlySales;
                const itemLogistics = p.logistics || 50; 
                logisticsTotal += itemLogistics * monthlySales;
                const commPct = p.commission_percent || 25;
                const itemCommission = price * (commPct / 100);
                commissionTotal += itemCommission * monthlySales;
            }
        });

        if (grossSales === 0 && cogs === 0) return [];
        const netSales = grossSales;
        const cm1 = netSales - cogs;
        const cm2 = cm1 - logisticsTotal - commissionTotal;
        const marketing = cm2 * 0.1; 
        const ebitda = cm2 - marketing;

        return [
            { name: 'Выручка (Seller)', value: Math.round(grossSales), type: 'income' },
            { name: 'Себестоимость', value: -Math.round(cogs), type: 'expense' },
            { name: 'Комиссия WB', value: -Math.round(commissionTotal), type: 'expense' },
            { name: 'Логистика', value: -Math.round(logisticsTotal), type: 'expense' },
            { name: 'Маркетинг (10%)', value: -Math.round(marketing), type: 'expense' },
            { name: 'EBITDA', value: Math.round(ebitda), type: 'total' }
        ];
    }, [products]);

    // Компонент карточки метрики
    const MetricCard = ({ title, value, subvalue, color }) => (
        <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">{title}</span>
            <div className={`text-xl font-black ${color}`}>{value}</div>
            {subvalue && <div className="text-[10px] text-slate-400 mt-1">{subvalue}</div>}
        </div>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            
            {/* Header */}
            <div className="flex justify-between items-stretch h-20">
                 <div className="bg-gradient-to-r from-emerald-500 to-teal-500 p-6 rounded-[28px] text-white shadow-xl shadow-emerald-200 relative overflow-hidden flex-1 mr-3 flex items-center justify-between">
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <DollarSign className="text-white" size={24} /> Финансы
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            {viewMode === 'unit' ? 'Unit-экономика товаров' : 'P&L Отчет о прибылях'}
                        </p>
                    </div>

                    <div className="relative z-10 flex gap-2">
                         {/* Sync Button */}
                         <button 
                            onClick={handleSync}
                            disabled={syncLoading}
                            className="bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm disabled:opacity-50"
                            title="Синхронизировать данные с WB (за 90 дней)"
                        >
                            <RefreshCw size={20} className={syncLoading ? "animate-spin" : ""} />
                        </button>

                         {/* Download Button */}
                         <button 
                            onClick={handleDownload}
                            disabled={pdfLoading}
                            className="bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm disabled:opacity-50"
                            title="Скачать PDF"
                        >
                            {pdfLoading ? <Loader2 size={20} className="animate-spin" /> : <Download size={20} />}
                        </button>
                    </div>
                    
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     {onNavigate && (
                         <button 
                            onClick={() => onNavigate('home')} 
                            className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                         >
                             <ArrowLeft size={24}/>
                         </button>
                     )}
                 </div>
            </div>

            {/* Controls: Toggle & Dates */}
            <div className="flex flex-col gap-4">
                {/* 1. Режимы */}
                <div className="flex bg-white rounded-xl p-1 shadow-sm border border-slate-100 mx-auto w-full max-w-sm">
                    <button
                        onClick={() => setViewMode('unit')}
                        className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${viewMode === 'unit' ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                    >
                        Unit Экономика
                    </button>
                    <button 
                        onClick={() => setViewMode('pnl')}
                        className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${viewMode === 'pnl' ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                    >
                        P&L Отчет
                    </button>
                </div>

                {/* 2. Даты (только для P&L) */}
                {viewMode === 'pnl' && (
                    <div className="bg-white p-3 rounded-2xl border border-slate-100 shadow-sm animate-in slide-in-from-top-2">
                        <div className="flex justify-between items-center mb-2 px-1">
                            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                                <Calendar size={12} /> Период анализа
                            </span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 mb-3">
                            <button 
                                onClick={() => handleDatePreset(7)}
                                className={`py-1.5 px-2 rounded-lg text-xs font-medium transition-colors ${dateRange.label === 'week' ? 'bg-indigo-100 text-indigo-700 border border-indigo-200' : 'bg-slate-50 text-slate-500 border border-slate-100'}`}
                            >
                                Неделя
                            </button>
                            <button 
                                onClick={() => handleDatePreset(30)}
                                className={`py-1.5 px-2 rounded-lg text-xs font-medium transition-colors ${dateRange.label === 'month' ? 'bg-indigo-100 text-indigo-700 border border-indigo-200' : 'bg-slate-50 text-slate-500 border border-slate-100'}`}
                            >
                                Месяц
                            </button>
                            <button 
                                onClick={() => handleDatePreset(90)}
                                className={`py-1.5 px-2 rounded-lg text-xs font-medium transition-colors ${dateRange.label === '90' ? 'bg-indigo-100 text-indigo-700 border border-indigo-200' : 'bg-slate-50 text-slate-500 border border-slate-100'}`}
                            >
                                90 Дней
                            </button>
                        </div>
                        <div className="flex gap-2 items-center bg-slate-50 p-2 rounded-xl border border-slate-100">
                            <input 
                                type="date" 
                                value={dateRange.start}
                                onChange={(e) => handleDateChange('start', e.target.value)}
                                className="bg-transparent text-xs font-bold text-slate-600 outline-none w-full text-center"
                            />
                            <span className="text-slate-300">-</span>
                            <input 
                                type="date" 
                                value={dateRange.end}
                                onChange={(e) => handleDateChange('end', e.target.value)}
                                className="bg-transparent text-xs font-bold text-slate-600 outline-none w-full text-center"
                            />
                        </div>
                    </div>
                )}
            </div>

            {editingCost && (
                <CostEditModal 
                    item={editingCost} 
                    onClose={() => setEditingCost(null)} 
                    onSave={handleUpdateCost} 
                />
            )}

            {/* CONTENT AREA */}
            {loading ? (
                <div className="flex justify-center p-20"><Loader2 className="animate-spin text-emerald-600" size={32}/></div>
            ) : viewMode === 'pnl' ? (
                <div className="space-y-4 animate-in slide-in-from-right-8">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <div>
                                <h3 className="font-bold text-lg text-slate-800">Финансовый результат</h3>
                                <p className="text-xs text-slate-400 mt-0.5">
                                    Данные из еженедельных отчетов WB
                                </p>
                            </div>
                            {user?.plan === 'start' && (
                                <span className="text-[10px] bg-amber-100 text-amber-700 px-2 py-1 rounded-lg font-bold">
                                    Демо-режим
                                </span>
                            )}
                        </div>

                        {pnlLoading ? (
                            <div className="flex flex-col items-center justify-center p-10 gap-3">
                                <Loader2 className="animate-spin text-indigo-500" size={32}/>
                                <span className="text-xs text-slate-400">Считаем прибыль...</span>
                            </div>
                        ) : pnlError ? (
                            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-center">
                                <div className="font-bold text-amber-900 mb-2">⚠️ {pnlError}</div>
                                {user?.plan === 'start' && (
                                    <div className="text-amber-700 mt-2 text-xs">
                                        <p>На тарифе Start доступен только демо-режим.</p>
                                    </div>
                                )}
                            </div>
                        ) : (pnlData?.data && pnlData.data.length > 0) ? (
                            <>
                                {/* --- ГРАФИК --- */}
                                <div className="h-64 w-full mb-6">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={pnlData.data} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                            <XAxis 
                                                dataKey="date" 
                                                tick={{fontSize: 10, fill: '#94a3b8'}} 
                                                tickFormatter={(val) => val.split('-').slice(1).join('.')} // MM.DD
                                                axisLine={false}
                                                tickLine={false}
                                                dy={10}
                                            />
                                            <YAxis 
                                                tick={{fontSize: 10, fill: '#94a3b8'}}
                                                axisLine={false}
                                                tickLine={false}
                                                tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                                            />
                                            <RechartsTooltip 
                                                cursor={{fill: '#f8fafc'}}
                                                contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.15)', fontSize: '12px'}}
                                                labelFormatter={(label) => `Дата: ${label}`}
                                            />
                                            <ReferenceLine y={0} stroke="#cbd5e1" />
                                            <Bar dataKey="cm3" name="Чистая прибыль" radius={[4, 4, 4, 4]}>
                                                {pnlData.data.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.cm3 > 0 ? '#10b981' : '#ef4444'} />
                                                ))}
                                            </Bar>
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>

                                {/* --- СВОДНАЯ ТАБЛИЦА С ПОДСКАЗКАМИ --- */}
                                <div className="space-y-1">
                                    {pnlData.summary && (
                                        <>
                                            {/* Выручка */}
                                            <div className="flex justify-between items-center py-2 border-b border-slate-50">
                                                <span className="text-sm text-slate-500 flex items-center">
                                                    Выручка 
                                                    <InfoTooltip text="Сумма продаж товаров по цене, установленной вами (до вычета СПП Wildberries). Это база для начисления комиссий." />
                                                </span>
                                                <span className="font-bold text-slate-800">
                                                    {Math.round(pnlData.summary.total_revenue).toLocaleString()} ₽
                                                </span>
                                            </div>

                                            {/* К перечислению (от WB) */}
                                            <div className="flex justify-between items-center py-2 border-b border-slate-50">
                                                <span className="text-sm text-slate-500 flex items-center">
                                                    К перечислению
                                                    <InfoTooltip text="Сумма, которую Wildberries фактически перечислил вам на счет за этот период (Выручка минус Комиссия WB, но до вычета Логистики и Штрафов в некоторых отчетах)." />
                                                </span>
                                                <span className="font-bold text-indigo-600">
                                                    {Math.round(pnlData.summary.total_transferred).toLocaleString()} ₽
                                                </span>
                                            </div>

                                            {/* Себестоимость */}
                                            <div className="flex justify-between items-center py-2 border-b border-slate-50">
                                                <span className="text-sm text-slate-500 flex items-center">
                                                    Себестоимость (COGS)
                                                    <InfoTooltip text="Закупочная стоимость проданных товаров. Рассчитывается как: (Кол-во продаж - Возвраты) * Ваша себестоимость." />
                                                </span>
                                                <span className="font-bold text-orange-500">
                                                    -{Math.round(pnlData.summary.total_cost_price).toLocaleString()} ₽
                                                </span>
                                            </div>

                                            {/* Логистика */}
                                            <div className="flex justify-between items-center py-2 border-b border-slate-50">
                                                <span className="text-sm text-slate-500 flex items-center">
                                                    Логистика
                                                    <InfoTooltip text="Сумма удержаний за доставку товаров до покупателя и за обратную логистику при возвратах." />
                                                </span>
                                                <span className="font-bold text-blue-500">
                                                    -{Math.round(pnlData.summary.total_logistics).toLocaleString()} ₽
                                                </span>
                                            </div>

                                            {/* Штрафы */}
                                            <div className="flex justify-between items-center py-2 border-b border-slate-50">
                                                <span className="text-sm text-slate-500 flex items-center">
                                                    Штрафы и доплаты
                                                    <InfoTooltip text="Штрафы, удержания и прочие доплаты, отраженные в еженедельных отчетах." />
                                                </span>
                                                <span className="font-bold text-red-500">
                                                    -{Math.round(pnlData.summary.total_penalty).toLocaleString()} ₽
                                                </span>
                                            </div>

                                            {/* ИТОГ */}
                                            <div className="flex justify-between items-center py-3 mt-2 bg-slate-50 rounded-xl px-3">
                                                <span className="text-sm font-bold text-slate-800 flex items-center">
                                                    Чистая прибыль (Net)
                                                    <InfoTooltip text="Финальный результат: К перечислению - Себестоимость - Логистика - Штрафы." />
                                                </span>
                                                <span className={`text-lg font-black ${pnlData.summary.net_profit > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                                    {Math.round(pnlData.summary.net_profit).toLocaleString()} ₽
                                                </span>
                                            </div>
                                            
                                            <div className="grid grid-cols-2 gap-2 mt-2">
                                                <div className="bg-emerald-50 rounded-lg p-2 text-center">
                                                    <div className="text-[10px] text-emerald-600 uppercase font-bold">Рентабельность</div>
                                                    <div className="text-sm font-black text-emerald-700">{pnlData.summary.roi?.toFixed(1)}% ROI</div>
                                                </div>
                                                <div className="bg-slate-100 rounded-lg p-2 text-center">
                                                    <div className="text-[10px] text-slate-500 uppercase font-bold">Продаж / Возвратов</div>
                                                    <div className="text-sm font-black text-slate-700">{pnlData.summary.sales_count} / {pnlData.summary.returns_count}</div>
                                                </div>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </>
                        ) : (
                            <div className="text-center text-slate-400 py-10 flex flex-col items-center gap-4">
                                <p className="text-sm">Нет данных за выбранный период ({dateRange.start} — {dateRange.end})</p>
                                <button 
                                    onClick={handleSync}
                                    disabled={syncLoading}
                                    className="bg-emerald-500 text-white px-6 py-3 rounded-xl font-bold text-sm hover:bg-emerald-600 transition-colors flex items-center gap-2 shadow-lg shadow-emerald-200"
                                >
                                    <RefreshCw size={18} className={syncLoading ? "animate-spin" : ""} />
                                    {syncLoading ? "Загружаем..." : "Загрузить данные с WB"}
                                </button>
                                <p className="text-[10px] max-w-[200px] leading-tight opacity-70">
                                    Нажмите кнопку, чтобы скачать архив финансовых отчетов за последние 90 дней.
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            ) : (
                /* --- UNIT ECONOMY VIEW (Остался без сильных изменений, только стиль карточек подправил) --- */
                <div className="space-y-4 animate-in slide-in-from-left-8">
                    <div className="grid grid-cols-2 gap-3">
                        <MetricCard title="Товаров в анализе" value={products.length} color="text-slate-800" />
                        <MetricCard 
                            title="Средний ROI" 
                            value={`${Math.round(products.reduce((acc, p) => acc + (p.unit_economy?.roi || 0), 0) / (products.length || 1))}%`} 
                            color="text-emerald-600" 
                        />
                    </div>

                    <div className="space-y-3">
                        {products.map((item) => {
                            const price = item.price_structure?.selling || 0;
                            const basicPrice = item.price_structure?.basic || 0;
                            const discount = item.price_structure?.discount || 0;
                            const commPct = item.commission_percent || 25;
                            const commVal = Math.round(price * (commPct / 100));
                            const logVal = Math.round(item.logistics || 50);
                            
                            return (
                                <div key={item.sku} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm relative group">
                                    {/* ... тут логика карточки товара осталась прежней ... */}
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="min-w-0">
                                            <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">SKU {item.sku}</div>
                                            <div className="flex flex-col relative">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm text-slate-400 line-through decoration-slate-300">{basicPrice} ₽</span>
                                                    <span className="text-[10px] font-bold bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded-md">-{discount}%</span>
                                                </div>
                                                <div className="flex items-baseline gap-2">
                                                    <div className="font-bold text-xl leading-tight text-slate-800">{price} ₽</div>
                                                </div>
                                                <div className="text-[9px] text-emerald-600 font-medium mt-0.5">База для выплат</div>
                                            </div>
                                        </div>
                                        <button onClick={() => setEditingCost(item)} className="p-3 bg-slate-50 text-slate-500 rounded-2xl hover:bg-indigo-50 hover:text-indigo-600 transition-colors">
                                            <Calculator size={20} />
                                        </button>
                                    </div>
                                    
                                    <div className="space-y-2 mb-4 relative">
                                        <div className="absolute left-[3px] top-2 bottom-2 w-0.5 bg-slate-100 rounded-full"></div>
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-purple-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-400 flex items-center gap-1">Комиссия WB <span className="text-[10px] bg-purple-50 text-purple-600 px-1 rounded">{commPct}%</span></span>
                                            <span className="text-purple-400">-{commVal} ₽</span>
                                        </div>
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-blue-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-400 flex items-center gap-1">Логистика <Truck size={10} /></span>
                                            <span className="text-blue-400">-{logVal} ₽</span>
                                        </div>
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-orange-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-400">Себестоимость</span>
                                            <span className="text-orange-400">-{item.cost_price} ₽</span>
                                        </div>
                                        <div className="flex justify-between items-center text-base pl-4 relative pt-1 border-t border-slate-50 mt-1">
                                            <div className={`w-2 h-2 rounded-full absolute -left-[4px] ${item.unit_economy.profit > 0 ? 'bg-emerald-500' : 'bg-red-500'}`}></div>
                                            <span className="font-bold text-slate-800">Чистая прибыль (Unit)</span>
                                            <span className={`font-black ${item.unit_economy.profit > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                                {item.unit_economy.profit} ₽
                                            </span>
                                        </div>
                                    </div>

                                    <div className="flex gap-2">
                                        <span className={`flex-1 text-center py-2 rounded-xl text-xs font-bold ${item.unit_economy.roi > 100 ? 'bg-emerald-100 text-emerald-700' : item.unit_economy.roi > 30 ? 'bg-blue-100 text-blue-700' : 'bg-red-50 text-red-600'}`}>
                                            ROI: {item.unit_economy.roi}%
                                        </span>
                                        <span className="flex-1 text-center py-2 rounded-xl text-xs font-bold bg-slate-50 text-slate-600">
                                            Маржа: {item.unit_economy.margin}%
                                        </span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

export default FinancePage;