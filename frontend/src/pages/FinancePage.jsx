import React, { useState, useEffect, useMemo } from 'react';
import { 
    Loader2, Calculator, DollarSign, Info, Truck, HelpCircle, 
    ArrowLeft, Download, RefreshCw, Calendar, Package, TrendingUp, AlertTriangle
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
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-slate-800 text-white text-[11px] leading-relaxed rounded-xl opacity-0 group-hover/tooltip:opacity-100 pointer-events-none transition-all duration-200 z-50 shadow-xl border border-white/10">
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
    
    // Даты для P&L
    const [dateRange, setDateRange] = useState(() => {
        const end = new Date();
        const start = new Date();
        start.setDate(end.getDate() - 30);
        return {
            start: start.toISOString().split('T')[0],
            end: end.toISOString().split('T')[0],
            label: 'month' 
        };
    });

    // Данные P&L
    const [pnlRawData, setPnlRawData] = useState([]); 
    const [pnlLoading, setPnlLoading] = useState(false);
    const [pnlError, setPnlError] = useState(null);
    
    // Состояния загрузки UI
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
            const query = new URLSearchParams({
                date_from: dateRange.start,
                date_to: dateRange.end
            }).toString();

            const res = await fetch(`${API_URL}/api/finance/pnl?${query}`, {
                headers: getTgHeaders()
            });
            
            if (res.ok) {
                const json = await res.json();
                if (json.data && Array.isArray(json.data)) {
                    setPnlRawData(json.data);
                } else {
                    setPnlRawData([]);
                }
            } else {
                const errorData = await res.json().catch(() => ({ detail: 'Неизвестная ошибка' }));
                if (res.status === 403) {
                    setPnlError(errorData.detail || 'P&L недоступен на вашем тарифе.');
                } else {
                    setPnlError(errorData.detail || 'Ошибка загрузки данных P&L');
                }
                setPnlRawData([]);
            }
        } catch(e) { 
            console.error(e);
            setPnlError('Ошибка соединения с сервером');
            setPnlRawData([]);
        } finally {
            setPnlLoading(false);
        }
    };
    
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
                alert("Синхронизация запущена! Обновите страницу через минуту.");
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

    const MetricCard = ({ title, value, subvalue, color, icon: Icon }) => (
        <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm flex flex-col justify-between relative overflow-hidden">
            <div className="flex justify-between items-start z-10">
                <div>
                    <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">{title}</span>
                    <div className={`text-xl font-black ${color}`}>{value}</div>
                    {subvalue && <div className="text-[10px] text-slate-400 mt-1">{subvalue}</div>}
                </div>
                {Icon && <Icon className="text-slate-100" size={32} />}
            </div>
            {Icon && <Icon className="absolute -bottom-2 -right-2 text-slate-50 w-20 h-20 -z-0 transform rotate-12" />}
        </div>
    );

    // --- Расчет итогов P&L (Берем данные как есть от бэкенда) ---
    const pnlSummary = useMemo(() => {
        if (!pnlRawData || pnlRawData.length === 0) return null;

        const sum = pnlRawData.reduce((acc, item) => {
            acc.total_revenue += (item.gross_sales || 0);
            acc.total_transferred += (item.net_sales || 0); 
            acc.total_commission += (item.commission || 0); // Используем прямое поле без заглушек
            acc.total_cost_price += (item.cogs || 0);
            acc.total_logistics += (item.logistics || 0);
            acc.total_penalty += (item.penalties || 0);
            acc.net_profit += (item.cm3 || 0);
            return acc;
        }, {
            total_revenue: 0,
            total_transferred: 0,
            total_commission: 0,
            total_cost_price: 0,
            total_logistics: 0,
            total_penalty: 0,
            net_profit: 0
        });

        sum.roi = sum.total_cost_price > 0 ? (sum.net_profit / sum.total_cost_price) * 100 : 0;
        return sum;
    }, [pnlRawData]);

    const pnlChartData = useMemo(() => {
        return pnlRawData.map(item => ({
            ...item,
            date: item.date,
            profit: item.cm3 
        }));
    }, [pnlRawData]);

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            
            {/* Header */}
            <div className="flex justify-between items-stretch h-24 mb-2">
                 <div className="bg-gradient-to-r from-emerald-600 to-teal-500 p-5 rounded-[28px] text-white shadow-xl shadow-emerald-200/50 relative overflow-hidden flex-1 mr-3 flex flex-col justify-center">
                    <div className="relative z-10 flex justify-between items-center w-full">
                        <div>
                            <h1 className="text-xl font-black flex items-center gap-2 mb-1">
                                <DollarSign className="text-white fill-white/20" size={22} /> Финансы
                            </h1>
                            <p className="text-xs font-medium text-emerald-100/90">
                                {viewMode === 'unit' ? 'Unit-экономика товаров' : 'P&L Отчет о прибылях'}
                            </p>
                        </div>
                        <div className="flex gap-2">
                             <button 
                                onClick={handleSync}
                                disabled={syncLoading}
                                className="bg-white/20 backdrop-blur-md h-10 w-10 rounded-full hover:bg-white/30 transition-all flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-lg disabled:opacity-50"
                                title="Синхронизировать данные"
                            >
                                <RefreshCw size={18} className={syncLoading ? "animate-spin" : ""} />
                            </button>
                             <button 
                                onClick={handleDownload}
                                disabled={pdfLoading}
                                className="bg-white/20 backdrop-blur-md h-10 w-10 rounded-full hover:bg-white/30 transition-all flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-lg disabled:opacity-50"
                                title="Скачать PDF"
                            >
                                {pdfLoading ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
                            </button>
                        </div>
                    </div>
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                    <div className="absolute bottom-0 left-0 w-24 h-24 bg-black/5 rounded-full -ml-8 -mb-8 blur-2xl"></div>
                 </div>
                 
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     {onNavigate && (
                         <button 
                            onClick={() => onNavigate('home')} 
                            className="bg-white h-full rounded-2xl shadow-sm border border-slate-100 text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                         >
                             <ArrowLeft size={24}/>
                         </button>
                     )}
                 </div>
            </div>

            {/* View Mode Switcher */}
            <div className="flex bg-white rounded-2xl p-1.5 shadow-sm border border-slate-100 mx-auto w-full">
                <button
                    onClick={() => setViewMode('unit')}
                    className={`flex-1 py-2.5 rounded-xl text-xs font-bold transition-all duration-200 ${viewMode === 'unit' ? 'bg-slate-900 text-white shadow-md transform scale-[1.02]' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'}`}
                >
                    Unit Экономика
                </button>
                <button 
                    onClick={() => setViewMode('pnl')}
                    className={`flex-1 py-2.5 rounded-xl text-xs font-bold transition-all duration-200 ${viewMode === 'pnl' ? 'bg-slate-900 text-white shadow-md transform scale-[1.02]' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'}`}
                >
                    P&L Отчет
                </button>
            </div>

            {/* Dates (P&L only) */}
            {viewMode === 'pnl' && (
                <div className="bg-white p-4 rounded-3xl border border-slate-100 shadow-sm animate-in slide-in-from-top-2">
                    <div className="flex justify-between items-center mb-3">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                            <Calendar size={14} className="text-slate-300" /> Период анализа
                        </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 mb-3">
                        {[{l: 'Неделя', v: 'week', d: 7}, {l: 'Месяц', v: 'month', d: 30}, {l: '90 Дней', v: '90', d: 90}].map((opt) => (
                            <button 
                                key={opt.v}
                                onClick={() => handleDatePreset(opt.d)}
                                className={`py-2 px-2 rounded-xl text-xs font-bold transition-colors ${dateRange.label === opt.v ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-50 text-slate-500 border border-slate-100 hover:bg-slate-100'}`}
                            >
                                {opt.l}
                            </button>
                        ))}
                    </div>
                    <div className="flex gap-2 items-center bg-slate-50 p-2.5 rounded-2xl border border-slate-100">
                        <input 
                            type="date" 
                            value={dateRange.start}
                            onChange={(e) => handleDateChange('start', e.target.value)}
                            className="bg-transparent text-xs font-bold text-slate-600 outline-none w-full text-center"
                        />
                        <span className="text-slate-300 font-light px-1">→</span>
                        <input 
                            type="date" 
                            value={dateRange.end}
                            onChange={(e) => handleDateChange('end', e.target.value)}
                            className="bg-transparent text-xs font-bold text-slate-600 outline-none w-full text-center"
                        />
                    </div>
                </div>
            )}

            {editingCost && (
                <CostEditModal 
                    item={editingCost} 
                    onClose={() => setEditingCost(null)} 
                    onSave={handleUpdateCost} 
                />
            )}

            {loading ? (
                <div className="flex justify-center p-20"><Loader2 className="animate-spin text-emerald-600" size={32}/></div>
            ) : viewMode === 'pnl' ? (
                // --- P&L VIEW ---
                <div className="space-y-4 animate-in slide-in-from-right-8">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <div>
                                <h3 className="font-bold text-lg text-slate-800">Финансовый результат</h3>
                                <p className="text-[10px] text-slate-400 mt-0.5 uppercase tracking-wider font-bold">
                                    Net Profit & Loss
                                </p>
                            </div>
                            {user?.plan === 'start' && (
                                <span className="text-[10px] bg-amber-100 text-amber-700 px-2.5 py-1 rounded-full font-bold border border-amber-200">
                                    Демо-режим
                                </span>
                            )}
                        </div>

                        {pnlLoading ? (
                            <div className="flex flex-col items-center justify-center p-10 gap-3 min-h-[300px]">
                                <Loader2 className="animate-spin text-indigo-500" size={32}/>
                                <span className="text-xs text-slate-400 font-medium">Анализируем отчеты...</span>
                            </div>
                        ) : pnlError ? (
                            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-center">
                                <div className="bg-amber-100 w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3">
                                    <AlertTriangle className="text-amber-600" size={24} />
                                </div>
                                <div className="font-bold text-amber-900 mb-2">Данные не загружены</div>
                                <p className="text-xs text-amber-700 mb-4">{pnlError}</p>
                                {user?.plan === 'start' && (
                                    <div className="text-amber-800 text-xs bg-amber-100/50 p-3 rounded-xl">
                                        На тарифе Start доступен только демо-режим.
                                    </div>
                                )}
                            </div>
                        ) : (pnlChartData.length > 0 && pnlSummary) ? (
                            <>
                                {/* Graph */}
                                <div className="h-64 w-full mb-8">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={pnlChartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                            <XAxis 
                                                dataKey="date" 
                                                tick={{fontSize: 10, fill: '#94a3b8'}} 
                                                tickFormatter={(val) => val.split('-').slice(1).join('.')} 
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
                                                cursor={{fill: '#f8fafc', radius: 4}}
                                                contentStyle={{borderRadius: '16px', border: 'none', boxShadow: '0 20px 40px -5px rgba(0,0,0,0.1)', fontSize: '12px', padding: '12px'}}
                                                labelFormatter={(label) => `Дата: ${label}`}
                                            />
                                            <ReferenceLine y={0} stroke="#cbd5e1" />
                                            <Bar dataKey="profit" name="Чистая прибыль" radius={[6, 6, 6, 6]} barSize={20}>
                                                {pnlChartData.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.profit > 0 ? '#10b981' : '#ef4444'} />
                                                ))}
                                            </Bar>
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>

                                {/* Summary Table WITH Tooltips */}
                                <div className="space-y-1 bg-slate-50 p-4 rounded-3xl border border-slate-100">
                                    <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                        <span className="text-sm text-slate-500 font-medium flex items-center">
                                            Выручка 
                                            <InfoTooltip text="Сумма продаж товаров за период (продажи минус возвраты по розничной цене)." />
                                        </span>
                                        <span className="font-bold text-slate-800">
                                            {Math.round(pnlSummary.total_revenue).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                        <span className="text-sm text-slate-500 font-medium flex items-center">
                                            Комиссия WB
                                            <InfoTooltip text="Суммарное вознаграждение Wildberries (ppvz_sales_commission)." />
                                        </span>
                                        <span className="font-bold text-purple-600">
                                            -{Math.round(pnlSummary.total_commission).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                        <span className="text-sm text-slate-500 font-medium flex items-center">
                                            Логистика
                                            <InfoTooltip text="Доставка до клиента + Обратная логистика." />
                                        </span>
                                        <span className="font-bold text-blue-500">
                                            -{Math.round(pnlSummary.total_logistics).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                        <span className="text-sm text-slate-500 font-medium flex items-center">
                                            Штрафы
                                            <InfoTooltip text="Штрафы и прочие удержания." />
                                        </span>
                                        <span className="font-bold text-red-500">
                                            -{Math.round(pnlSummary.total_penalty).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center py-3 my-1 bg-white rounded-xl px-3 border border-slate-200/60">
                                        <span className="text-sm font-bold text-indigo-600 flex items-center">
                                            К перечислению
                                            <InfoTooltip text="Фактическая сумма от WB за реализованный товар (уже за вычетом комиссии)." />
                                        </span>
                                        <span className="font-black text-indigo-600">
                                            {Math.round(pnlSummary.total_transferred).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                        <span className="text-sm text-slate-500 font-medium flex items-center">
                                            Себестоимость
                                            <InfoTooltip text="Закупочная стоимость реализованного товара." />
                                        </span>
                                        <span className="font-bold text-orange-500">
                                            -{Math.round(pnlSummary.total_cost_price).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    {/* Net Profit */}
                                    <div className="flex justify-between items-center py-4 mt-2 bg-white rounded-2xl px-4 shadow-sm border border-slate-100">
                                        <span className="text-sm font-black text-slate-800 flex items-center">
                                            Чистая прибыль
                                            <InfoTooltip text="Итоговый финансовый результат (К перечислению - Себестоимость - Логистика - Штрафы)." />
                                        </span>
                                        <span className={`text-xl font-black ${pnlSummary.net_profit > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                            {Math.round(pnlSummary.net_profit).toLocaleString()} ₽
                                        </span>
                                    </div>
                                    
                                    <div className="grid grid-cols-2 gap-2 mt-3">
                                        <div className="bg-emerald-100/50 border border-emerald-100 rounded-2xl p-3 text-center">
                                            <div className="text-[10px] text-emerald-600 uppercase font-bold tracking-wider mb-1">ROI</div>
                                            <div className="text-lg font-black text-emerald-700">{pnlSummary.roi?.toFixed(1)}%</div>
                                        </div>
                                        <div className="bg-white border border-slate-200 rounded-2xl p-3 text-center">
                                            <div className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-1">Маржинальность</div>
                                            <div className="text-sm font-bold text-slate-700">
                                                {pnlSummary.total_revenue > 0 
                                                    ? Math.round((pnlSummary.net_profit / pnlSummary.total_revenue) * 100) 
                                                    : 0}%
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="text-center text-slate-400 py-16 flex flex-col items-center gap-6">
                                <div className="bg-slate-50 p-4 rounded-full">
                                    <Package size={32} className="text-slate-300" />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-slate-600 mb-1">Нет данных за период</p>
                                    <p className="text-xs text-slate-400">{dateRange.start} — {dateRange.end}</p>
                                </div>
                                <button 
                                    onClick={handleSync}
                                    disabled={syncLoading}
                                    className="bg-slate-900 text-white px-6 py-3 rounded-xl font-bold text-sm hover:bg-slate-800 transition-all flex items-center gap-2 shadow-lg shadow-slate-200 active:scale-95"
                                >
                                    <RefreshCw size={18} className={syncLoading ? "animate-spin" : ""} />
                                    {syncLoading ? "Загружаем..." : "Загрузить отчеты с WB"}
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            ) : (
                // --- UNIT ECONOMY VIEW ---
                <div className="space-y-4 animate-in slide-in-from-left-8">
                    <div className="grid grid-cols-2 gap-3">
                        <MetricCard 
                            title="Артикулов" 
                            value={products.length} 
                            color="text-slate-800" 
                            icon={Package}
                        />
                        <MetricCard 
                            title="Средний ROI" 
                            value={`${Math.round(products.reduce((acc, p) => acc + (p.unit_economy?.roi || 0), 0) / (products.length || 1))}%`} 
                            color="text-emerald-600" 
                            icon={TrendingUp}
                        />
                    </div>

                    <div className="space-y-4">
                        {products.map((item) => {
                            const price = item.price_structure?.selling || 0;
                            const basicPrice = item.price_structure?.basic || 0;
                            const discount = item.price_structure?.discount || 0;
                            
                            // Исправленная комиссия: берем commission_percent из объекта или дефолт 25, если в API пусто
                            const commPct = item.commission_percent; 
                            const commVal = Math.round(price * (commPct / 100));
                            const logVal = Math.round(item.logistics || 50);
                            
                            // Safe Meta Extraction
                            const meta = item.meta || {};
                            const photoUrl = meta.photo || (meta.photos && meta.photos[0]?.big) || (meta.photos && meta.photos[0]?.c246x328) || null;
                            const brand = meta.brand || 'No Brand';
                            const name = meta.name || meta.imt_name || `Товар ${item.sku}`;
                            
                            return (
                                <div key={item.sku} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm relative group overflow-hidden">
                                    
                                    {/* Header: Photo & Title */}
                                    <div className="flex gap-4 mb-5">
                                        <div className="w-20 h-24 shrink-0 rounded-xl bg-slate-100 overflow-hidden relative border border-slate-200">
                                            {photoUrl && (
                                                <img 
                                                    src={photoUrl} 
                                                    alt="" 
                                                    className="w-full h-full object-cover relative z-10 bg-slate-100" 
                                                    onError={(e) => {
                                                        e.currentTarget.style.display = 'none';
                                                    }}
                                                />
                                            )}
                                            <div className="absolute inset-0 flex items-center justify-center text-slate-300 z-0">
                                                <Package size={24} />
                                            </div>

                                            <div className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[9px] text-center py-0.5 font-medium backdrop-blur-sm z-20">
                                                {item.quantity} шт
                                            </div>
                                        </div>
                                        
                                        <div className="flex-1 min-w-0 flex flex-col justify-between py-0.5">
                                            <div>
                                                <div className="flex justify-between items-start">
                                                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1">
                                                        {brand} 
                                                        <span className="text-slate-300">•</span>
                                                        <span className="font-mono">{item.sku}</span>
                                                    </div>
                                                    <button onClick={() => setEditingCost(item)} className="p-2 -mt-2 -mr-2 text-slate-300 hover:text-indigo-600 hover:bg-indigo-50 rounded-xl transition-colors">
                                                        <Calculator size={18} />
                                                    </button>
                                                </div>
                                                <div className="text-sm font-bold text-slate-800 leading-tight line-clamp-2" title={name}>
                                                    {name}
                                                </div>
                                            </div>

                                            <div className="flex items-end gap-2 mt-2">
                                                <div className="flex flex-col">
                                                    <span className="text-[10px] text-slate-400 line-through">{basicPrice} ₽</span>
                                                    <div className="text-xl font-black text-slate-800 leading-none">
                                                        {price} ₽
                                                    </div>
                                                </div>
                                                <span className="text-[10px] font-bold bg-rose-100 text-rose-600 px-1.5 py-0.5 rounded-md mb-0.5">
                                                    -{discount}%
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    {/* Waterfall */}
                                    <div className="space-y-2.5 relative bg-slate-50/50 p-4 rounded-2xl border border-slate-100">
                                        {/* Комиссия */}
                                        <div className="flex justify-between items-center text-xs relative">
                                            <span className="text-slate-500 flex items-center gap-1.5">
                                                <div className="w-1.5 h-1.5 bg-purple-400 rounded-full"></div>
                                                Комиссия <span className="bg-purple-50 text-purple-600 px-1 rounded font-bold">{commPct}%</span>
                                            </span>
                                            <span className="font-medium text-slate-700">-{commVal} ₽</span>
                                        </div>

                                        {/* Логистика */}
                                        <div className="flex justify-between items-center text-xs relative">
                                            <span className="text-slate-500 flex items-center gap-1.5">
                                                <div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div>
                                                Логистика
                                            </span>
                                            <span className="font-medium text-slate-700">-{logVal} ₽</span>
                                        </div>

                                        {/* Себестоимость */}
                                        <div className="flex justify-between items-center text-xs relative">
                                            <span className="text-slate-500 flex items-center gap-1.5">
                                                <div className="w-1.5 h-1.5 bg-orange-400 rounded-full"></div>
                                                Себестоимость
                                            </span>
                                            <span className="font-medium text-slate-700">-{item.cost_price} ₽</span>
                                        </div>

                                        <div className="border-t border-slate-200 my-2"></div>

                                        {/* ИТОГ */}
                                        <div className="flex justify-between items-center">
                                            <span className="text-sm font-bold text-slate-800">Прибыль с шт.</span>
                                            <span className={`text-base font-black ${item.unit_economy.profit > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                                {item.unit_economy.profit} ₽
                                            </span>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-2 mt-3">
                                        <div className={`text-center py-2.5 rounded-xl border ${item.unit_economy.roi > 100 ? 'bg-emerald-50 border-emerald-100 text-emerald-700' : item.unit_economy.roi > 30 ? 'bg-blue-50 border-blue-100 text-blue-700' : 'bg-red-50 border-red-100 text-red-700'}`}>
                                            <div className="text-[9px] uppercase font-bold opacity-70 mb-0.5">ROI</div>
                                            <div className="text-sm font-black">{item.unit_economy.roi}%</div>
                                        </div>
                                        <div className="text-center py-2.5 rounded-xl bg-white border border-slate-200 text-slate-600">
                                            <div className="text-[9px] uppercase font-bold opacity-60 mb-0.5">Маржа</div>
                                            <div className="text-sm font-black">{item.unit_economy.margin}%</div>
                                        </div>
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