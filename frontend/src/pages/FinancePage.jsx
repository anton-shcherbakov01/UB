import React, { useState, useEffect, useMemo } from 'react';
import { 
    Loader2, Calculator, DollarSign, Info, Truck, HelpCircle, 
    ArrowLeft, Download, RefreshCw, Calendar, Package, TrendingUp, AlertTriangle
} from 'lucide-react';
import { 
    BarChart, Bar, Tooltip as RechartsTooltip, ResponsiveContainer, 
    Cell, ReferenceLine, XAxis, YAxis, CartesianGrid
} from 'recharts';

// Конфигурация (предполагаем наличие в глобальном скоупе или определяем здесь)
const API_URL = typeof window !== 'undefined' ? (window.API_URL || '') : ''; 
const getTgHeaders = () => ({
    'Content-Type': 'application/json',
    'x-tg-data': window.Telegram?.WebApp?.initData || ''
});

// --- Вспомогательные компоненты ---

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

// Модальное окно редактирования затрат (встроено в файл)
const CostEditModal = ({ item, onClose, onSave }) => {
    const [formData, setFormData] = useState({
        cost_price: item.cost_price || 0,
        logistics: item.logistics || 0,
        commission_percent: item.commission_percent || 0
    });

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-white rounded-[32px] p-8 w-full max-w-sm shadow-2xl animate-in zoom-in-95 duration-250">
                <div className="flex justify-between items-start mb-6">
                    <div>
                        <h3 className="text-xl font-black text-slate-800">Затраты</h3>
                        <p className="text-[11px] text-slate-400 mt-1 uppercase tracking-widest font-bold">Редактирование SKU: {item.sku}</p>
                    </div>
                    <button onClick={onClose} className="text-slate-300 hover:text-slate-500 transition-colors">
                        <ArrowLeft size={20} className="rotate-90" />
                    </button>
                </div>
                
                <div className="space-y-5">
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-wider ml-1">Себестоимость (₽)</label>
                        <div className="relative">
                            <input 
                                type="number" 
                                value={formData.cost_price} 
                                onChange={(e) => setFormData({...formData, cost_price: e.target.value})}
                                className="w-full bg-slate-50 border-2 border-slate-100 rounded-2xl px-5 py-4 text-sm font-bold outline-none focus:border-indigo-500 focus:bg-white transition-all" 
                            />
                            <DollarSign className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-300" size={18} />
                        </div>
                    </div>
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-wider ml-1">Логистика (₽)</label>
                        <div className="relative">
                            <input 
                                type="number" 
                                value={formData.logistics} 
                                onChange={(e) => setFormData({...formData, logistics: e.target.value})}
                                className="w-full bg-slate-50 border-2 border-slate-100 rounded-2xl px-5 py-4 text-sm font-bold outline-none focus:border-indigo-500 focus:bg-white transition-all" 
                            />
                            <Truck className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-300" size={18} />
                        </div>
                    </div>
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-wider ml-1">Комиссия (%)</label>
                        <div className="relative">
                            <input 
                                type="number" 
                                value={formData.commission_percent} 
                                onChange={(e) => setFormData({...formData, commission_percent: e.target.value})}
                                className="w-full bg-slate-50 border-2 border-slate-100 rounded-2xl px-5 py-4 text-sm font-bold outline-none focus:border-indigo-500 focus:bg-white transition-all" 
                            />
                            <span className="absolute right-5 top-1/2 -translate-y-1/2 font-bold text-slate-300">%</span>
                        </div>
                    </div>
                </div>

                <div className="flex gap-3 mt-10">
                    <button onClick={onClose} className="flex-1 py-4 rounded-2xl font-bold text-sm text-slate-500 bg-slate-50 hover:bg-slate-100 active:scale-95 transition-all">Отмена</button>
                    <button 
                        onClick={() => onSave(item.sku, formData)}
                        className="flex-1 py-4 rounded-2xl font-bold text-sm text-white bg-slate-900 shadow-xl shadow-slate-200 active:scale-95 transition-all"
                    >
                        Сохранить
                    </button>
                </div>
            </div>
        </div>
    );
};

const FinancePage = ({ user, onNavigate }) => {
    // --- State ---
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingCost, setEditingCost] = useState(null);
    const [viewMode, setViewMode] = useState('unit'); // 'unit' | 'pnl'
    
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

    const [pnlRawData, setPnlRawData] = useState([]); 
    const [pnlLoading, setPnlLoading] = useState(false);
    const [pnlError, setPnlError] = useState(null);
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
                // Имитация задержки для пользователя
                setTimeout(() => {
                    if (viewMode === 'pnl') fetchPnlData();
                    setSyncLoading(false);
                }, 3000);
            } else {
                setSyncLoading(false);
            }
        } catch (e) {
            console.error(e);
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
            const endpoint = viewMode === 'unit' 
                ? '/api/finance/report/unit-economy-pdf'
                : '/api/finance/report/pnl-pdf';
            
            const query = viewMode === 'pnl' 
                ? `&date_from=${dateRange.start}&date_to=${dateRange.end}`
                : '';

            const url = `${API_URL}${endpoint}?x_tg_data=${encodeURIComponent(token)}${query}`;
            window.open(url, '_blank');
        } catch (e) {
            console.error(e);
        } finally {
            setPdfLoading(false);
        }
    };

    const MetricCard = ({ title, value, subvalue, color, icon: Icon }) => (
        <div className="bg-white p-5 rounded-[28px] border border-slate-100 shadow-sm flex flex-col justify-between relative overflow-hidden group hover:shadow-md transition-shadow">
            <div className="flex justify-between items-start z-10">
                <div>
                    <span className="text-[10px] text-slate-400 font-black uppercase tracking-widest block mb-1.5">{title}</span>
                    <div className={`text-2xl font-black ${color}`}>{value}</div>
                    {subvalue && <div className="text-[10px] text-slate-400 mt-1.5 font-bold uppercase tracking-tighter opacity-70">{subvalue}</div>}
                </div>
                <div className="p-3 bg-slate-50 rounded-2xl group-hover:bg-slate-100 transition-colors">
                    {Icon && <Icon className="text-slate-400" size={20} />}
                </div>
            </div>
            {Icon && <Icon className="absolute -bottom-4 -right-4 text-slate-50 w-24 h-24 -z-0 transform rotate-12 opacity-50" />}
        </div>
    );

    // --- Расчет итогов P&L ---
    const pnlSummary = useMemo(() => {
        if (!pnlRawData || pnlRawData.length === 0) return null;

        const sum = pnlRawData.reduce((acc, item) => {
            acc.total_revenue += (item.gross_sales || 0);
            acc.total_transferred += (item.net_sales || 0); 
            acc.total_commission += (item.commission || 0);
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
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4 duration-500">
            
            {/* Header Block */}
            <div className="flex justify-between items-stretch h-24 mb-2">
                 <div className="bg-gradient-to-br from-indigo-600 via-indigo-500 to-indigo-400 p-6 rounded-[32px] text-white shadow-xl shadow-indigo-100 relative overflow-hidden flex-1 mr-4 flex flex-col justify-center">
                    <div className="relative z-10 flex justify-between items-center w-full">
                        <div>
                            <h1 className="text-2xl font-black flex items-center gap-2 mb-0.5">
                                <DollarSign className="text-white fill-white/20" size={24} /> Финансы
                            </h1>
                            <p className="text-[11px] font-bold text-indigo-100/80 uppercase tracking-widest">
                                {viewMode === 'unit' ? 'Unit-экономика' : 'P&L Отчетность'}
                            </p>
                        </div>
                        <div className="flex gap-2.5">
                             <button 
                                onClick={handleSync}
                                disabled={syncLoading}
                                className="bg-white/20 backdrop-blur-xl h-11 w-11 rounded-2xl hover:bg-white/30 transition-all flex items-center justify-center text-white border border-white/10 active:scale-90 shadow-lg disabled:opacity-50"
                            >
                                <RefreshCw size={20} className={syncLoading ? "animate-spin" : ""} />
                            </button>
                             <button 
                                onClick={handleDownload}
                                disabled={pdfLoading}
                                className="bg-white/20 backdrop-blur-xl h-11 w-11 rounded-2xl hover:bg-white/30 transition-all flex items-center justify-center text-white border border-white/10 active:scale-90 shadow-lg disabled:opacity-50"
                            >
                                {pdfLoading ? <Loader2 size={20} className="animate-spin" /> : <Download size={20} />}
                            </button>
                        </div>
                    </div>
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-12 -mt-12 blur-2xl"></div>
                 </div>
                 
                 <div className="flex flex-col gap-2 w-16 shrink-0">
                     {onNavigate && (
                         <button 
                            onClick={() => onNavigate('home')} 
                            className="bg-white h-full rounded-[24px] shadow-sm border border-slate-100 text-slate-400 hover:text-indigo-600 transition-all flex items-center justify-center active:scale-90"
                         >
                             <ArrowLeft size={28}/>
                         </button>
                     )}
                 </div>
            </div>

            {/* View Mode Tabs */}
            <div className="flex bg-slate-100/50 rounded-[24px] p-1.5 shadow-inner border border-slate-200/50 mx-auto w-full">
                <button
                    onClick={() => setViewMode('unit')}
                    className={`flex-1 py-3.5 rounded-[20px] text-xs font-black uppercase tracking-widest transition-all duration-300 ${viewMode === 'unit' ? 'bg-white text-slate-900 shadow-md transform scale-[1.01]' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    Unit-Экономика
                </button>
                <button 
                    onClick={() => setViewMode('pnl')}
                    className={`flex-1 py-3.5 rounded-[20px] text-xs font-black uppercase tracking-widest transition-all duration-300 ${viewMode === 'pnl' ? 'bg-white text-slate-900 shadow-md transform scale-[1.01]' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    P&L Отчет
                </button>
            </div>

            {/* Date Selection Panel (P&L ONLY) */}
            {viewMode === 'pnl' && (
                <div className="bg-white p-5 rounded-[32px] border border-slate-100 shadow-sm animate-in slide-in-from-top-4 duration-300">
                    <div className="flex justify-between items-center mb-4">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2">
                            <Calendar size={14} className="text-slate-300" /> Временной период
                        </span>
                    </div>
                    <div className="grid grid-cols-3 gap-3 mb-4">
                        {[{l: 'Неделя', v: 'week', d: 7}, {l: 'Месяц', v: 'month', d: 30}, {l: '90 Дней', v: '90', d: 90}].map((opt) => (
                            <button 
                                key={opt.v}
                                onClick={() => handleDatePreset(opt.d)}
                                className={`py-3 px-2 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all ${dateRange.label === opt.v ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'bg-slate-50 text-slate-400 border border-slate-100 hover:bg-slate-100'}`}
                            >
                                {opt.l}
                            </button>
                        ))}
                    </div>
                    <div className="flex gap-3 items-center bg-slate-50 p-4 rounded-2xl border border-slate-100">
                        <input 
                            type="date" 
                            value={dateRange.start}
                            onChange={(e) => handleDateChange('start', e.target.value)}
                            className="bg-transparent text-xs font-black text-slate-700 outline-none w-full text-center"
                        />
                        <span className="text-slate-300 font-bold px-2">→</span>
                        <input 
                            type="date" 
                            value={dateRange.end}
                            onChange={(e) => handleDateChange('end', e.target.value)}
                            className="bg-transparent text-xs font-black text-slate-700 outline-none w-full text-center"
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
                <div className="flex flex-col items-center justify-center py-32 gap-4">
                    <Loader2 className="animate-spin text-indigo-500" size={48}/>
                    <p className="text-[10px] font-black text-slate-300 uppercase tracking-[0.3em]">Загрузка данных</p>
                </div>
            ) : viewMode === 'pnl' ? (
                // --- P&L VIEW CONTENT ---
                <div className="space-y-6 animate-in slide-in-from-right-8 duration-500">
                    <div className="bg-white p-6 rounded-[32px] shadow-sm border border-slate-100">
                        <div className="flex justify-between items-center mb-8">
                            <div>
                                <h3 className="font-black text-xl text-slate-800 tracking-tight">Финансовый результат</h3>
                                <div className="flex items-center gap-2 mt-1">
                                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                                    <p className="text-[10px] text-slate-400 uppercase tracking-widest font-black">Обновлено в реальном времени</p>
                                </div>
                            </div>
                            {user?.plan === 'start' && (
                                <div className="bg-amber-50 text-amber-600 px-4 py-2 rounded-2xl font-black text-[9px] uppercase tracking-widest border border-amber-100">
                                    Демо
                                </div>
                            )}
                        </div>

                        {pnlLoading ? (
                            <div className="flex flex-col items-center justify-center py-20 gap-4 min-h-[300px]">
                                <Loader2 className="animate-spin text-indigo-400" size={32}/>
                                <span className="text-[10px] text-slate-300 font-black uppercase tracking-[0.2em]">Считаем прибыль...</span>
                            </div>
                        ) : pnlError ? (
                            <div className="bg-rose-50 border-2 border-rose-100 rounded-[32px] p-8 text-center">
                                <div className="bg-rose-100 w-16 h-16 rounded-3xl flex items-center justify-center mx-auto mb-4">
                                    <AlertTriangle className="text-rose-600" size={32} />
                                </div>
                                <div className="font-black text-slate-800 text-lg mb-2">Ошибка доступа</div>
                                <p className="text-xs text-slate-500 leading-relaxed max-w-[240px] mx-auto">{pnlError}</p>
                            </div>
                        ) : (pnlChartData.length > 0 && pnlSummary) ? (
                            <>
                                {/* Graph Area */}
                                <div className="h-72 w-full mb-10 mt-2">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={pnlChartData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                                            <defs>
                                                <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="0%" stopColor="#10b981" stopOpacity={1} />
                                                    <stop offset="100%" stopColor="#34d399" stopOpacity={0.8} />
                                                </linearGradient>
                                                <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="0%" stopColor="#ef4444" stopOpacity={1} />
                                                    <stop offset="100%" stopColor="#f87171" stopOpacity={0.8} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="6 6" vertical={false} stroke="#f1f5f9" />
                                            <XAxis 
                                                dataKey="date" 
                                                tick={{fontSize: 10, fontWeight: 800, fill: '#cbd5e1'}} 
                                                tickFormatter={(val) => val.split('-').slice(2).join('/')} 
                                                axisLine={false}
                                                tickLine={false}
                                                dy={15}
                                            />
                                            <YAxis 
                                                tick={{fontSize: 10, fontWeight: 800, fill: '#cbd5e1'}}
                                                axisLine={false}
                                                tickLine={false}
                                                tickFormatter={(val) => val === 0 ? '0' : `${(val / 1000).toFixed(0)}k`}
                                            />
                                            <RechartsTooltip 
                                                cursor={{fill: '#f8fafc', radius: 12}}
                                                contentStyle={{borderRadius: '24px', border: 'none', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.15)', fontSize: '11px', fontWeight: 'bold', padding: '16px'}}
                                                labelStyle={{color: '#94a3b8', marginBottom: '8px'}}
                                                formatter={(value) => [`${value.toLocaleString()} ₽`, 'Прибыль']}
                                            />
                                            <ReferenceLine y={0} stroke="#e2e8f0" strokeWidth={2} />
                                            <Bar dataKey="profit" radius={[8, 8, 8, 8]} barSize={24}>
                                                {pnlChartData.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.profit > 0 ? 'url(#profitGrad)' : 'url(#lossGrad)'} />
                                                ))}
                                            </Bar>
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>

                                {/* Detailed Summary Breakdown */}
                                <div className="space-y-2 bg-slate-50/50 p-6 rounded-[32px] border border-slate-100">
                                    <div className="flex justify-between items-center py-3.5 border-b border-slate-200/40">
                                        <span className="text-[11px] text-slate-500 font-black uppercase tracking-widest flex items-center">
                                            Выручка (Гросс) 
                                            <InfoTooltip text="Суммарная стоимость проданных товаров до всех вычетов и возвратов." />
                                        </span>
                                        <span className="font-black text-slate-900">
                                            {Math.round(pnlSummary.total_revenue).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    {/* FIXED: HIDE COMMISSION IF 0 */}
                                    {pnlSummary.total_commission !== 0 && (
                                        <div className="flex justify-between items-center py-3.5 border-b border-slate-200/40">
                                            <span className="text-[11px] text-slate-500 font-black uppercase tracking-widest flex items-center">
                                                Комиссия WB
                                                <InfoTooltip text="Вознаграждение маркетплейса за реализацию товара." />
                                            </span>
                                            <span className="font-black text-rose-500">
                                                -{Math.round(pnlSummary.total_commission).toLocaleString()} ₽
                                            </span>
                                        </div>
                                    )}

                                    <div className="flex justify-between items-center py-3.5 border-b border-slate-200/40">
                                        <span className="text-[11px] text-slate-500 font-black uppercase tracking-widest flex items-center">
                                            Логистика
                                            <InfoTooltip text="Затраты на доставку до ПВЗ и обратные перевозки при возвратах." />
                                        </span>
                                        <span className="font-black text-blue-500">
                                            -{Math.round(pnlSummary.total_logistics).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    {pnlSummary.total_penalty > 0 && (
                                        <div className="flex justify-between items-center py-3.5 border-b border-slate-200/40">
                                            <span className="text-[11px] text-slate-500 font-black uppercase tracking-widest flex items-center">
                                                Штрафы / Удержания
                                            </span>
                                            <span className="font-black text-rose-600">
                                                -{Math.round(pnlSummary.total_penalty).toLocaleString()} ₽
                                            </span>
                                        </div>
                                    )}

                                    <div className="flex justify-between items-center py-5 my-3 bg-white rounded-2xl px-5 border-2 border-indigo-50 shadow-sm shadow-indigo-50/50">
                                        <span className="text-xs font-black text-indigo-600 uppercase tracking-widest flex items-center">
                                            К перечислению
                                            <InfoTooltip text="Фактический денежный поток от WB на ваш счет." />
                                        </span>
                                        <span className="text-lg font-black text-indigo-600">
                                            {Math.round(pnlSummary.total_transferred).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center py-3.5 border-b border-slate-200/40">
                                        <span className="text-[11px] text-slate-500 font-black uppercase tracking-widest flex items-center">
                                            Себестоимость
                                            <InfoTooltip text="Закупочная стоимость проданных товаров (COGS)." />
                                        </span>
                                        <span className="font-black text-orange-500">
                                            -{Math.round(pnlSummary.total_cost_price).toLocaleString()} ₽
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center py-6 mt-6 bg-slate-900 rounded-[24px] px-6 text-white shadow-xl shadow-slate-200">
                                        <span className="text-sm font-black uppercase tracking-[0.2em] flex items-center">
                                            Чистая прибыль
                                            <InfoTooltip text="Ваш итоговый доход после вычета себестоимости и всех комиссий." />
                                        </span>
                                        <span className={`text-2xl font-black ${pnlSummary.net_profit > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                            {Math.round(pnlSummary.net_profit).toLocaleString()} ₽
                                        </span>
                                    </div>
                                    
                                    <div className="grid grid-cols-2 gap-3 mt-4">
                                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-2xl p-4 text-center">
                                            <div className="text-[9px] text-emerald-600 uppercase font-black tracking-widest mb-1.5">ROI</div>
                                            <div className="text-xl font-black text-emerald-600">{pnlSummary.roi?.toFixed(1)}%</div>
                                        </div>
                                        <div className="bg-slate-100/80 border border-slate-200/50 rounded-2xl p-4 text-center">
                                            <div className="text-[9px] text-slate-400 uppercase font-black tracking-widest mb-1.5">Маржа</div>
                                            <div className="text-xl font-black text-slate-700">
                                                {pnlSummary.total_revenue > 0 
                                                    ? Math.round((pnlSummary.net_profit / pnlSummary.total_revenue) * 100) 
                                                    : 0}%
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="text-center text-slate-400 py-24 flex flex-col items-center gap-8 animate-in zoom-in-95 duration-500">
                                <div className="bg-slate-50 p-6 rounded-[40px] shadow-inner">
                                    <Package size={48} className="text-slate-200" />
                                </div>
                                <div className="space-y-2">
                                    <p className="text-sm font-black text-slate-600 uppercase tracking-widest">Нет финансовых записей</p>
                                    <p className="text-[10px] text-slate-400 font-bold">{dateRange.start} — {dateRange.end}</p>
                                </div>
                                <button 
                                    onClick={handleSync}
                                    disabled={syncLoading}
                                    className="bg-indigo-600 text-white px-8 py-4 rounded-[20px] font-black text-xs uppercase tracking-[0.2em] hover:bg-indigo-700 transition-all flex items-center gap-3 shadow-xl shadow-indigo-100 active:scale-95"
                                >
                                    <RefreshCw size={18} className={syncLoading ? "animate-spin" : ""} />
                                    {syncLoading ? "Загружаем..." : "Синхронизировать с WB"}
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            ) : (
                // --- UNIT ECONOMY VIEW CONTENT ---
                <div className="space-y-6 animate-in slide-in-from-left-8 duration-500">
                    <div className="grid grid-cols-2 gap-4">
                        <MetricCard 
                            title="Артикулов" 
                            value={products.length} 
                            color="text-slate-800" 
                            icon={Package}
                        />
                        <MetricCard 
                            title="Средний ROI" 
                            value={`${products.length > 0 ? Math.round(products.reduce((acc, p) => acc + (p.unit_economy?.roi || 0), 0) / products.length) : 0}%`} 
                            color="text-emerald-600" 
                            icon={TrendingUp}
                        />
                    </div>

                    <div className="space-y-5">
                        {products.map((item) => {
                            const price = item.price_structure?.selling || 0;
                            const basicPrice = item.price_structure?.basic || 0;
                            const discount = item.price_structure?.discount || 0;
                            
                            // FIXED: Use actual commission from item
                            const commPct = item.commission_percent || 0; 
                            const commVal = Math.round(price * (commPct / 100));
                            const logVal = Math.round(item.logistics || 0);
                            
                            const meta = item.meta || {};
                            const photoUrl = meta.photo || (meta.photos && meta.photos[0]?.big) || null;
                            const brand = meta.brand || 'No Brand';
                            const name = meta.name || meta.imt_name || `Артикул ${item.sku}`;
                            
                            return (
                                <div key={item.sku} className="bg-white p-6 rounded-[32px] border border-slate-100 shadow-sm relative group hover:shadow-md transition-all">
                                    
                                    <div className="flex gap-5 mb-6">
                                        <div className="w-24 h-32 shrink-0 rounded-2xl bg-slate-50 overflow-hidden relative border border-slate-100 shadow-inner">
                                            {photoUrl && (
                                                <img 
                                                    src={photoUrl} 
                                                    alt="" 
                                                    className="w-full h-full object-cover relative z-10" 
                                                    onError={(e) => e.currentTarget.style.display = 'none'}
                                                />
                                            )}
                                            <div className="absolute inset-0 flex items-center justify-center text-slate-200 z-0">
                                                <Package size={28} />
                                            </div>
                                            <div className="absolute bottom-2 inset-x-2 bg-slate-900/80 text-white text-[8px] font-black uppercase tracking-widest text-center py-1 rounded-lg backdrop-blur-md z-20">
                                                {item.quantity} В наличии
                                            </div>
                                        </div>
                                        
                                        <div className="flex-1 min-w-0 flex flex-col justify-between py-1">
                                            <div>
                                                <div className="flex justify-between items-start">
                                                    <div className="text-[9px] font-black text-slate-400 uppercase tracking-[0.2em] mb-1.5 flex items-center gap-1.5">
                                                        <span className="bg-slate-100 px-2 py-0.5 rounded-full text-slate-500">{brand}</span>
                                                        <span className="font-mono opacity-50">#{item.sku}</span>
                                                    </div>
                                                    <button 
                                                        onClick={() => setEditingCost(item)} 
                                                        className="p-2.5 bg-slate-50 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-xl transition-all active:scale-90"
                                                    >
                                                        <Calculator size={18} />
                                                    </button>
                                                </div>
                                                <h4 className="text-sm font-black text-slate-800 leading-[1.4] line-clamp-2 pr-2" title={name}>
                                                    {name}
                                                </h4>
                                            </div>

                                            <div className="flex items-end gap-3 mt-4">
                                                <div className="flex flex-col">
                                                    {discount > 0 && <span className="text-[10px] font-bold text-slate-300 line-through mb-0.5">{basicPrice.toLocaleString()} ₽</span>}
                                                    <div className="text-2xl font-black text-slate-900 leading-none tracking-tighter">
                                                        {price.toLocaleString()} <span className="text-sm font-bold opacity-30">₽</span>
                                                    </div>
                                                </div>
                                                {discount > 0 && (
                                                    <span className="text-[9px] font-black bg-rose-500 text-white px-2 py-1 rounded-lg mb-1">
                                                        -{discount}%
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    
                                    {/* Financial Waterfall Visual */}
                                    <div className="space-y-3 bg-slate-50 p-5 rounded-[24px] border border-slate-100">
                                        <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-wider">
                                            <span className="text-slate-400 flex items-center gap-2">
                                                <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full"></span>
                                                Комиссия <span className="text-indigo-600">({commPct}%)</span>
                                            </span>
                                            <span className="text-slate-700">-{commVal} ₽</span>
                                        </div>

                                        <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-wider">
                                            <span className="text-slate-400 flex items-center gap-2">
                                                <span className="w-1.5 h-1.5 bg-blue-400 rounded-full"></span>
                                                Логистика (Ед.)
                                            </span>
                                            <span className="text-slate-700">-{logVal} ₽</span>
                                        </div>

                                        <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-wider">
                                            <span className="text-slate-400 flex items-center gap-2">
                                                <span className="w-1.5 h-1.5 bg-orange-400 rounded-full"></span>
                                                Себестоимость
                                            </span>
                                            <span className="text-slate-700">-{item.cost_price || 0} ₽</span>
                                        </div>

                                        <div className="border-t border-slate-200/50 my-1 pt-3 flex justify-between items-center">
                                            <span className="text-xs font-black text-slate-900 uppercase tracking-widest">Прибыль / шт</span>
                                            <span className={`text-lg font-black ${item.unit_economy?.profit > 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                                {item.unit_economy?.profit > 0 ? '+' : ''}{item.unit_economy?.profit} ₽
                                            </span>
                                        </div>
                                    </div>

                                    {/* Health Indicators */}
                                    <div className="grid grid-cols-2 gap-3 mt-4">
                                        <div className={`text-center py-4 rounded-2xl border-2 transition-all ${item.unit_economy?.roi > 100 ? 'bg-emerald-50 border-emerald-100' : item.unit_economy?.roi > 30 ? 'bg-indigo-50 border-indigo-100' : 'bg-rose-50 border-rose-100'}`}>
                                            <div className={`text-[9px] uppercase font-black tracking-widest mb-1 ${item.unit_economy?.roi > 100 ? 'text-emerald-600' : item.unit_economy?.roi > 30 ? 'text-indigo-600' : 'text-rose-600'}`}>ROI</div>
                                            <div className={`text-lg font-black ${item.unit_economy?.roi > 100 ? 'text-emerald-700' : item.unit_economy?.roi > 30 ? 'text-indigo-700' : 'text-rose-700'}`}>{item.unit_economy?.roi}%</div>
                                        </div>
                                        <div className="text-center py-4 rounded-2xl bg-white border-2 border-slate-100 text-slate-600">
                                            <div className="text-[9px] uppercase font-black tracking-widest text-slate-400 mb-1">Маржа</div>
                                            <div className="text-lg font-black text-slate-800">{item.unit_economy?.margin}%</div>
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