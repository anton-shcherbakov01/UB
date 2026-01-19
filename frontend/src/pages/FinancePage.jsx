import React, { useState, useEffect, useMemo } from 'react';
import { 
    Loader2, Calculator, DollarSign, Info, Truck, HelpCircle, 
    ArrowLeft, Download, RefreshCw, Calendar, Package, TrendingUp, AlertTriangle
} from 'lucide-react';
import { 
    BarChart, Bar, Tooltip as RechartsTooltip, ResponsiveContainer, 
    Cell, ReferenceLine, XAxis, YAxis, CartesianGrid
} from 'recharts';

// Предполагаем, что конфиг доступен в окружении. 
// Если вы используете локальные файлы, убедитесь, что пути верны.
const API_URL = ''; // Будет подставлено из окружения или внешней переменной
const getTgHeaders = () => ({
    'X-TG-DATA': window.Telegram?.WebApp?.initData || ''
});

// Заглушка модалки, если импорт недоступен
const CostEditModal = ({ item, onClose, onSave }) => (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
        <div className="bg-white rounded-3xl p-6 w-full max-w-sm shadow-2xl">
            <h3 className="text-lg font-bold mb-4">Редактировать затраты</h3>
            <p className="text-xs text-slate-500 mb-4">{item.meta?.name || item.sku}</p>
            <div className="space-y-4">
                <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Себестоимость (₽)</label>
                    <input id="cost_input" type="number" defaultValue={item.cost_price} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-sm outline-none focus:border-indigo-500" />
                </div>
                <div className="flex gap-3 mt-6">
                    <button onClick={onClose} className="flex-1 py-3 rounded-xl font-bold text-sm text-slate-500 bg-slate-100">Отмена</button>
                    <button 
                        onClick={() => {
                            const val = document.getElementById('cost_input').value;
                            onSave(item.sku, { cost_price: val });
                        }}
                        className="flex-1 py-3 rounded-xl font-bold text-sm text-white bg-indigo-600 shadow-lg shadow-indigo-200"
                    >
                        Сохранить
                    </button>
                </div>
            </div>
        </div>
    </div>
);

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
        setDateRange(prev => ({ ...prev, [field]: value, label: 'custom' }));
    };

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/internal/products`, { headers: getTgHeaders() });
            if (res.ok) {
                const data = await res.json();
                setProducts(data);
            }
        } catch(e) { console.error(e); } finally { setLoading(false); }
    };

    const fetchPnlData = async () => {
        setPnlLoading(true);
        setPnlError(null);
        try {
            const query = new URLSearchParams({
                date_from: dateRange.start,
                date_to: dateRange.end
            }).toString();
            const res = await fetch(`${API_URL}/api/finance/pnl?${query}`, { headers: getTgHeaders() });
            if (res.ok) {
                const json = await res.json();
                setPnlRawData(Array.isArray(json.data) ? json.data : []);
            } else {
                const errorData = await res.json().catch(() => ({ detail: 'Ошибка загрузки' }));
                setPnlError(errorData.detail || 'Данные P&L временно недоступны');
            }
        } catch(e) { 
            setPnlError('Ошибка соединения с сервером');
        } finally { setPnlLoading(false); }
    };

    useEffect(() => { fetchProducts(); }, []);
    useEffect(() => { if (viewMode === 'pnl') fetchPnlData(); }, [viewMode, dateRange.start, dateRange.end]);

    const handleSync = async () => {
        setSyncLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/finance/sync/pnl`, { method: 'POST', headers: getTgHeaders() });
            if (res.ok) {
                setTimeout(() => { if (viewMode === 'pnl') fetchPnlData(); }, 3000);
            }
        } catch (e) { console.error(e); } finally { setSyncLoading(false); }
    };

    const handleUpdateCost = async (sku, formData) => {
        try {
            await fetch(`${API_URL}/api/internal/cost/${sku}`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    cost_price: Number(formData.cost_price),
                    logistics: formData.logistics ? Number(formData.logistics) : null,
                    commission_percent: formData.commission_percent ? Number(formData.commission_percent) : null
                })
            });
            setEditingCost(null);
            fetchProducts();
        } catch(e) { console.error(e); }
    };

    const handleDownload = () => {
        const token = window.Telegram?.WebApp?.initData || '';
        const endpoint = viewMode === 'unit' ? '/api/finance/report/unit-economy-pdf' : '/api/finance/report/pnl-pdf';
        const query = viewMode === 'pnl' ? `&date_from=${dateRange.start}&date_to=${dateRange.end}` : '';
        window.open(`${API_URL}${endpoint}?x_tg_data=${encodeURIComponent(token)}${query}`, '_blank');
    };

    const pnlSummary = useMemo(() => {
        if (!pnlRawData.length) return null;
        const sum = pnlRawData.reduce((acc, item) => {
            acc.total_revenue += (item.gross_sales || 0);
            acc.total_transferred += (item.net_sales || 0); 
            // Берем только реальную комиссию из отчета (item.commission или ppvz_sales_commission если бекенд так мапит)
            acc.total_commission += (item.commission || 0);
            acc.total_cost_price += (item.cogs || 0);
            acc.total_logistics += (item.logistics || 0);
            acc.total_penalty += (item.penalties || 0);
            acc.net_profit += (item.cm3 || 0);
            return acc;
        }, {
            total_revenue: 0, total_transferred: 0, total_commission: 0,
            total_cost_price: 0, total_logistics: 0, total_penalty: 0, net_profit: 0
        });
        sum.roi = sum.total_cost_price > 0 ? (sum.net_profit / sum.total_cost_price) * 100 : 0;
        return sum;
    }, [pnlRawData]);

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
                             <button onClick={handleSync} disabled={syncLoading} className="bg-white/20 backdrop-blur-md h-10 w-10 rounded-full flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-lg disabled:opacity-50">
                                <RefreshCw size={18} className={syncLoading ? "animate-spin" : ""} />
                            </button>
                             <button onClick={handleDownload} disabled={pdfLoading} className="bg-white/20 backdrop-blur-md h-10 w-10 rounded-full flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-lg disabled:opacity-50">
                                {pdfLoading ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
                            </button>
                        </div>
                    </div>
                 </div>
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     {onNavigate && (
                         <button onClick={() => onNavigate('home')} className="bg-white h-full rounded-2xl shadow-sm border border-slate-100 text-slate-400 flex items-center justify-center active:scale-95">
                             <ArrowLeft size={24}/>
                         </button>
                     )}
                 </div>
            </div>

            {/* Switcher */}
            <div className="flex bg-white rounded-2xl p-1.5 shadow-sm border border-slate-100 w-full">
                <button onClick={() => setViewMode('unit')} className={`flex-1 py-2.5 rounded-xl text-xs font-bold transition-all ${viewMode === 'unit' ? 'bg-slate-900 text-white shadow-md transform scale-[1.02]' : 'text-slate-400'}`}>Unit Экономика</button>
                <button onClick={() => setViewMode('pnl')} className={`flex-1 py-2.5 rounded-xl text-xs font-bold transition-all ${viewMode === 'pnl' ? 'bg-slate-900 text-white shadow-md transform scale-[1.02]' : 'text-slate-400'}`}>P&L Отчет</button>
            </div>

            {viewMode === 'pnl' && (
                <div className="bg-white p-4 rounded-3xl border border-slate-100 shadow-sm animate-in slide-in-from-top-2">
                    <div className="flex justify-between items-center mb-3">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5"><Calendar size={14}/> Период анализа</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 mb-3">
                        {[{l: 'Неделя', d: 7}, {l: 'Месяц', d: 30}, {l: '90 Дней', d: 90}].map((opt) => (
                            <button key={opt.d} onClick={() => handleDatePreset(opt.d)} className={`py-2 px-2 rounded-xl text-xs font-bold border transition-colors ${dateRange.label === (opt.d === 7 ? 'week' : opt.d === 30 ? 'month' : '90') ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-50 text-slate-500 border-slate-100'}`}>{opt.l}</button>
                        ))}
                    </div>
                </div>
            )}

            {editingCost && <CostEditModal item={editingCost} onClose={() => setEditingCost(null)} onSave={handleUpdateCost} />}

            {loading ? (
                <div className="flex justify-center p-20"><Loader2 className="animate-spin text-emerald-600" size={32}/></div>
            ) : viewMode === 'pnl' ? (
                // --- P&L VIEW ---
                <div className="space-y-4 animate-in slide-in-from-right-8">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-bold text-lg text-slate-800">Финансовый результат</h3>
                        </div>

                        {pnlLoading ? (
                            <div className="flex flex-col items-center justify-center p-10 min-h-[300px]"><Loader2 className="animate-spin text-indigo-500 mb-2" size={32}/><span className="text-xs text-slate-400">Анализируем отчеты...</span></div>
                        ) : pnlError ? (
                            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-center text-amber-900">
                                <AlertTriangle className="mx-auto mb-3 text-amber-600" size={24} />
                                <div className="font-bold mb-1">Данные не загружены</div>
                                <p className="text-xs opacity-75">{pnlError}</p>
                            </div>
                        ) : pnlSummary ? (
                            <div className="space-y-1 bg-slate-50 p-4 rounded-3xl border border-slate-100">
                                <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                    <span className="text-sm text-slate-500 font-medium">Выручка <InfoTooltip text="Сумма продаж товаров за период." /></span>
                                    <span className="font-bold text-slate-800">{Math.round(pnlSummary.total_revenue).toLocaleString()} ₽</span>
                                </div>

                                {/* Убираем заглушку комиссии, показываем только если она есть в данных */}
                                {pnlSummary.total_commission !== 0 && (
                                    <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                        <span className="text-sm text-slate-500 font-medium">Комиссия WB <InfoTooltip text="Фактическое вознаграждение Wildberries из отчетов." /></span>
                                        <span className="font-bold text-purple-600">-{Math.round(pnlSummary.total_commission).toLocaleString()} ₽</span>
                                    </div>
                                )}

                                <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                    <span className="text-sm text-slate-500 font-medium">Логистика <InfoTooltip text="Доставка до клиента + возвраты." /></span>
                                    <span className="font-bold text-blue-500">-{Math.round(pnlSummary.total_logistics).toLocaleString()} ₽</span>
                                </div>

                                <div className="flex justify-between items-center py-3 my-1 bg-white rounded-xl px-3 border border-slate-200/60">
                                    <span className="text-sm font-bold text-indigo-600">К перечислению <InfoTooltip text="Сумма от WB после вычета комиссии и логистики." /></span>
                                    <span className="font-black text-indigo-600">{Math.round(pnlSummary.total_transferred).toLocaleString()} ₽</span>
                                </div>

                                <div className="flex justify-between items-center py-2.5 border-b border-slate-200/50">
                                    <span className="text-sm text-slate-500 font-medium">Себестоимость <InfoTooltip text="Закупочная стоимость реализованного товара." /></span>
                                    <span className="font-bold text-orange-500">-{Math.round(pnlSummary.total_cost_price).toLocaleString()} ₽</span>
                                </div>

                                <div className="flex justify-between items-center py-4 mt-2 bg-white rounded-2xl px-4 shadow-sm border border-slate-100">
                                    <span className="text-sm font-black text-slate-800">Чистая прибыль</span>
                                    <span className={`text-xl font-black ${pnlSummary.net_profit > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                        {Math.round(pnlSummary.net_profit).toLocaleString()} ₽
                                    </span>
                                </div>
                            </div>
                        ) : null}
                    </div>
                </div>
            ) : (
                // --- UNIT ECONOMY VIEW ---
                <div className="space-y-4 animate-in slide-in-from-left-8">
                    <div className="grid grid-cols-2 gap-3">
                        <MetricCard title="Артикулов" value={products.length} color="text-slate-800" icon={Package} />
                        <MetricCard title="Средний ROI" value={`${Math.round(products.reduce((acc, p) => acc + (p.unit_economy?.roi || 0), 0) / (products.length || 1))}%`} color="text-emerald-600" icon={TrendingUp} />
                    </div>

                    <div className="space-y-4">
                        {products.map((item) => {
                            const price = item.price_structure?.selling || 0;
                            // Исправлено: Берем реальную комиссию из API, если пусто - 0
                            const commPct = item.commission_percent ?? 0; 
                            const commVal = Math.round(price * (commPct / 100));
                            const logVal = Math.round(item.logistics || 50);
                            
                            const photoUrl = item.meta?.photo || (item.meta?.photos && item.meta?.photos[0]?.big) || null;
                            const name = item.meta?.name || `Товар ${item.sku}`;
                            
                            return (
                                <div key={item.sku} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm relative overflow-hidden">
                                    <div className="flex gap-4 mb-5">
                                        <div className="w-20 h-24 shrink-0 rounded-xl bg-slate-100 overflow-hidden relative border border-slate-200">
                                            {photoUrl && <img src={photoUrl} alt="" className="w-full h-full object-cover relative z-10" />}
                                            <div className="absolute inset-0 flex items-center justify-center text-slate-300 z-0"><Package size={24} /></div>
                                            <div className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[9px] text-center py-0.5 font-medium z-20">{item.quantity} шт</div>
                                        </div>
                                        
                                        <div className="flex-1 min-w-0 flex flex-col justify-between py-0.5">
                                            <div>
                                                <div className="flex justify-between items-start">
                                                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                                                        {item.meta?.brand} <span className="text-slate-300">•</span> {item.sku}
                                                    </div>
                                                    <button onClick={() => setEditingCost(item)} className="p-2 -mt-2 -mr-2 text-slate-300 hover:text-indigo-600 transition-colors">
                                                        <Calculator size={18} />
                                                    </button>
                                                </div>
                                                <div className="text-sm font-bold text-slate-800 leading-tight line-clamp-2">{name}</div>
                                            </div>
                                            <div className="text-xl font-black text-slate-800">{price} ₽</div>
                                        </div>
                                    </div>
                                    
                                    <div className="space-y-2.5 bg-slate-50/50 p-4 rounded-2xl border border-slate-100">
                                        <div className="flex justify-between items-center text-xs">
                                            <span className="text-slate-500 flex items-center gap-1.5"><div className="w-1.5 h-1.5 bg-purple-400 rounded-full"></div> Комиссия <span className="bg-purple-50 text-purple-600 px-1 rounded font-bold">{commPct}%</span></span>
                                            <span className="font-medium text-slate-700">-{commVal} ₽</span>
                                        </div>
                                        <div className="flex justify-between items-center text-xs">
                                            <span className="text-slate-500 flex items-center gap-1.5"><div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div> Логистика</span>
                                            <span className="font-medium text-slate-700">-{logVal} ₽</span>
                                        </div>
                                        <div className="flex justify-between items-center text-xs">
                                            <span className="text-slate-500 flex items-center gap-1.5"><div className="w-1.5 h-1.5 bg-orange-400 rounded-full"></div> Себестоимость</span>
                                            <span className="font-medium text-slate-700">-{item.cost_price} ₽</span>
                                        </div>
                                        <div className="border-t border-slate-200 my-2"></div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-sm font-bold text-slate-800">Прибыль с шт.</span>
                                            <span className={`text-base font-black ${item.unit_economy?.profit > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                                {item.unit_economy?.profit} ₽
                                            </span>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-2 mt-3">
                                        <div className={`text-center py-2.5 rounded-xl border bg-emerald-50 border-emerald-100 text-emerald-700`}>
                                            <div className="text-[9px] uppercase font-bold opacity-70 mb-0.5">ROI</div>
                                            <div className="text-sm font-black">{item.unit_economy?.roi}%</div>
                                        </div>
                                        <div className="text-center py-2.5 rounded-xl bg-white border border-slate-200 text-slate-600">
                                            <div className="text-[9px] uppercase font-bold opacity-60 mb-0.5">Маржа</div>
                                            <div className="text-sm font-black">{item.unit_economy?.margin}%</div>
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