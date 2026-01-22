import React, { useState, useEffect } from 'react';
import { 
    ArrowLeft, Filter, Eye, ShoppingCart, Package, CreditCard, 
    Calendar, Loader2, TrendingUp, Info, HelpCircle, X, ChevronDown, Activity
} from 'lucide-react';
import { 
    ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';

// --- Компоненты ---

// Трапеция воронки
const FunnelStage = ({ label, value, percentNext, color, isLast, widthPercent, icon: Icon }) => (
    <div className="flex flex-col items-center w-full relative group">
        {/* Трапеция */}
        <div 
            className={`h-16 ${color} relative flex items-center justify-center shadow-lg transition-all duration-300 group-hover:brightness-110`}
            style={{ 
                width: `${widthPercent}%`,
                clipPath: isLast 
                    ? 'polygon(0 0, 100% 0, 100% 100%, 0 100%)' // Прямоугольник для последнего
                    : 'polygon(0 0, 100% 0, 85% 100%, 15% 100%)', // Трапеция
                borderRadius: '8px'
            }}
        >
            <Icon className="text-white drop-shadow-md" size={24} />
        </div>

        {/* Данные */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-white font-black text-lg drop-shadow-md pointer-events-none">
            {/* Иконка уже есть, цифры ниже */}
        </div>

        <div className="mt-2 text-center">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">{label}</div>
            <div className="text-lg font-black text-slate-800">{new Intl.NumberFormat('ru-RU').format(value)}</div>
        </div>

        {/* Конверсия в следующий шаг */}
        {!isLast && (
            <div className="mt-1 bg-slate-100 text-slate-500 text-[10px] font-bold px-2 py-0.5 rounded-full border border-slate-200">
                CR: {percentNext}%
            </div>
        )}
    </div>
);

const FunnelPage = ({ onBack }) => {
    const [period, setPeriod] = useState(30);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    
    const [nmIds, setNmIds] = useState('');
    const [isFilterOpen, setIsFilterOpen] = useState(false);
    const [showHelp, setShowHelp] = useState(false); // FIX: State для подсказки

    useEffect(() => {
        fetchFunnelData();
    }, [period]);

    const fetchFunnelData = async () => {
        setLoading(true);
        try {
            let url = `${API_URL}/api/analytics/funnel?days=${period}`;
            if (nmIds.trim()) {
                url += `&nm_ids=${encodeURIComponent(nmIds.trim())}`;
            }
            
            const res = await fetch(url, { headers: getTgHeaders() });
            if (res.ok) {
                const result = await res.json();
                setData(result);
            }
        } catch (e) {
            console.error("Funnel fetch error:", e);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') {
            fetchFunnelData();
            setIsFilterOpen(false);
        }
    };

    const formatNum = (num) => new Intl.NumberFormat('ru-RU').format(num);

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            // Ищем данные из массива payload
            const visitors = payload.find(p => p.dataKey === 'visitors')?.value || 0;
            const orders = payload.find(p => p.dataKey === 'orders')?.value || 0;
            const revenue = payload.find(p => p.dataKey === 'orders')?.payload?.orders_sum || 0;

            return (
                <div className="bg-white/95 backdrop-blur shadow-xl rounded-2xl p-4 border border-slate-100 text-xs z-50">
                    <p className="font-bold text-slate-500 mb-2 border-b border-slate-100 pb-1">{label}</p>
                    <p className="text-indigo-600 font-bold mb-1">👁 Просмотры: {formatNum(visitors)}</p>
                    <p className="text-amber-500 font-bold mb-1">📦 Заказы: {formatNum(orders)}</p>
                    <p className="text-emerald-500 font-bold">💰 Выручка: {formatNum(revenue)} ₽</p>
                </div>
            );
        }
        return null;
    };

    // Цвета для заголовка
    const headerGradient = 'from-rose-500 to-pink-600';
    const headerShadow = 'shadow-rose-200';

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in bg-[#F4F4F9] min-h-screen">
            
            {/* Header */}
            <div className="flex justify-between items-stretch h-24 mb-6">
                 <div className={`bg-gradient-to-r ${headerGradient} p-5 rounded-[28px] text-white shadow-xl ${headerShadow} relative overflow-hidden flex-1 mr-3 flex items-center justify-between transition-colors duration-500`}>
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <Activity size={24} className="text-white"/>
                            Воронка
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            Конверсии и Аналитика
                        </p>
                    </div>

                    <div className="relative z-10">
                         <button 
                            onClick={() => setIsFilterOpen(!isFilterOpen)}
                            className={`bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm ${isFilterOpen ? 'bg-white text-rose-500' : ''}`}
                        >
                           {isFilterOpen ? <X size={20} /> : <Filter size={20} />}
                        </button>
                    </div>
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button 
                        onClick={onBack} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                      >
                          <ArrowLeft size={24}/>
                      </button>
                      <div className="relative h-full">
                        <button 
                            onClick={() => setShowHelp(!showHelp)}
                            className={`h-full w-full rounded-2xl shadow-sm transition-colors flex items-center justify-center active:scale-95 ${showHelp ? 'bg-indigo-50 border-indigo-200 text-indigo-600' : 'bg-white text-slate-400 hover:text-indigo-600'}`}
                        >
                            <HelpCircle size={24}/>
                        </button>
                        
                        {/* FIX: Tooltip с явным состоянием */}
                        {showHelp && (
                            <div className="absolute top-full right-0 mt-2 w-64 p-4 bg-slate-900 text-white text-xs rounded-xl shadow-xl z-[60] animate-in fade-in zoom-in-95">
                                <div className="font-bold mb-2 text-rose-300">Как читать воронку?</div>
                                <ul className="space-y-1.5 list-disc pl-3 mb-2">
                                    <li><span className="text-slate-300">Просмотры:</span> Уникальные открытия карточки.</li>
                                    <li><span className="text-slate-300">Корзина:</span> Конверсия (CR) в добавление.</li>
                                    <li><span className="text-slate-300">Заказы:</span> Оформленные покупки.</li>
                                    <li><span className="text-slate-300">Выкупы:</span> Товар фактически выкуплен.</li>
                                </ul>
                                <div className="text-[10px] text-slate-400 leading-tight border-t border-slate-700 pt-2">
                                    Данные по заказам и выкупам - точные (из финансового отчета). Просмотры и корзины - распределенные.
                                </div>
                                <button onClick={() => setShowHelp(false)} className="mt-3 w-full bg-slate-800 py-1.5 rounded-lg text-slate-300 font-bold hover:bg-slate-700">Понятно</button>
                            </div>
                        )}
                      </div>
                 </div>
            </div>

            {/* Filter Input */}
            {isFilterOpen && (
                <div className="bg-white p-3 rounded-2xl border border-slate-200 shadow-sm animate-in slide-in-from-top-2">
                    <div className="text-xs font-bold text-slate-400 mb-2 uppercase">Фильтр по артикулам</div>
                    <div className="flex gap-2">
                        <input 
                            type="text" 
                            placeholder="12345678, 87654321..." 
                            value={nmIds}
                            onChange={(e) => setNmIds(e.target.value)}
                            onKeyDown={handleKeyDown}
                            className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-200"
                        />
                        <button onClick={fetchFunnelData} className="bg-rose-500 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-md">ОК</button>
                    </div>
                </div>
            )}

            {/* Period Selector */}
            <div className="bg-white p-1.5 rounded-2xl flex shadow-sm border border-slate-100 overflow-x-auto">
                {[7, 14, 30, 60, 90].map(d => (
                    <button 
                        key={d}
                        onClick={() => setPeriod(d)}
                        className={`flex-1 min-w-[60px] py-2.5 rounded-xl text-xs font-bold transition-all ${period === d ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'}`}
                    >
                        {d} дн
                    </button>
                ))}
            </div>

            {loading ? (
                <div className="h-64 flex items-center justify-center">
                    <Loader2 className="animate-spin text-indigo-600" size={40}/>
                </div>
            ) : data ? (
                <>
                    {/* 1. VISUAL FUNNEL */}
                    <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100 flex flex-col items-center gap-2">
                        <h3 className="font-bold text-lg text-slate-800 self-start mb-2">Воронка конверсий</h3>
                        
                        <FunnelStage 
                            label="Просмотры" value={data.totals.visitors} percentNext={data.conversions.view_to_cart} 
                            widthPercent={100} color="bg-indigo-500" icon={Eye}
                        />
                        <FunnelStage 
                            label="В корзину" value={data.totals.cart} percentNext={data.conversions.cart_to_order} 
                            widthPercent={80} color="bg-violet-500" icon={ShoppingCart}
                        />
                        <FunnelStage 
                            label="Заказы" value={data.totals.orders} percentNext={data.conversions.order_to_buyout} 
                            widthPercent={60} color="bg-amber-500" icon={Package}
                        />
                        <FunnelStage 
                            label="Выкупы" value={data.totals.buyouts} percentNext={0} 
                            widthPercent={40} color="bg-emerald-500" icon={CreditCard} isLast={true}
                        />
                    </div>

                    {/* 2. METRICS CARDS */}
                    <div className="grid grid-cols-2 gap-3">
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <div className="text-[10px] text-slate-400 font-bold uppercase mb-1">Выручка (Заказы)</div>
                            <div className="text-xl font-black text-slate-800">{formatNum(data.totals.revenue)} ₽</div>
                        </div>
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <div className="text-[10px] text-slate-400 font-bold uppercase mb-1">Средний чек</div>
                            <div className="text-xl font-black text-slate-800">
                                {data.totals.orders > 0 ? formatNum(Math.round(data.totals.revenue / data.totals.orders)) : 0} ₽
                            </div>
                        </div>
                        <div className="bg-emerald-50 p-4 rounded-2xl border border-emerald-100">
                            <div className="text-[10px] text-emerald-600 font-bold uppercase mb-1">Выкупы (Руб)</div>
                            <div className="text-xl font-black text-emerald-700">{formatNum(data.totals.buyouts_revenue)} ₽</div>
                        </div>
                        <div className="bg-indigo-50 p-4 rounded-2xl border border-indigo-100">
                            <div className="text-[10px] text-indigo-600 font-bold uppercase mb-1">CR Общий</div>
                            <div className="text-xl font-black text-indigo-700">
                                {data.totals.visitors > 0 ? ((data.totals.orders / data.totals.visitors) * 100).toFixed(2) : 0}%
                            </div>
                        </div>
                    </div>

                    {/* 3. ADVANCED CHART (Traffic vs Orders) */}
                    {/* FIX: Изменили верстку на Flexbox, чтобы легенда не уезжала */}
                    <div className="bg-white rounded-3xl p-5 shadow-sm border border-slate-100 h-[450px] flex flex-col">
                        <div className="flex justify-between items-center mb-4 shrink-0">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <TrendingUp size={18} className="text-indigo-600"/>
                                Динамика (Трафик vs Заказы)
                            </h3>
                        </div>
                        
                        <div className="flex-1 w-full min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={data.chart}>
                                    <defs>
                                        <linearGradient id="colorVis" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9"/>
                                    <XAxis 
                                        dataKey="date" 
                                        tickFormatter={(str) => {
                                            const d = new Date(str);
                                            return `${d.getDate()}.${d.getMonth()+1}`;
                                        }}
                                        tick={{fontSize: 10, fill: '#94a3b8'}} 
                                        axisLine={false} 
                                        tickLine={false}
                                        minTickGap={15}
                                    />
                                    <YAxis yAxisId="left" orientation="left" hide />
                                    <YAxis yAxisId="right" orientation="right" hide />
                                    <Tooltip content={<CustomTooltip />} cursor={{fill: '#f8fafc', opacity: 0.5}} />
                                    
                                    {/* Area: Просмотры (Левая ось) */}
                                    <Area 
                                        yAxisId="left"
                                        type="monotone" 
                                        dataKey="visitors" 
                                        stroke="#6366f1" 
                                        strokeWidth={2}
                                        fill="url(#colorVis)" 
                                    />
                                    
                                    {/* Bar: Заказы (Правая ось - чтобы видеть пики) */}
                                    <Bar 
                                        yAxisId="right"
                                        dataKey="orders" 
                                        barSize={8}
                                        fill="#fbbf24" 
                                        radius={[4, 4, 4, 4]}
                                    />
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                        <div className="flex justify-center gap-4 text-[10px] mt-3 font-bold text-slate-400 shrink-0">
                            <div className="flex items-center gap-1"><div className="w-3 h-3 bg-indigo-500 rounded-full opacity-50"></div> Просмотры</div>
                            <div className="flex items-center gap-1"><div className="w-3 h-3 bg-amber-400 rounded-full"></div> Заказы</div>
                        </div>
                    </div>

                    {!data.is_exact && (
                        <div className="p-3 bg-amber-50 rounded-xl flex items-start gap-3 border border-amber-100 text-xs text-amber-800">
                            <Info size={16} className="mt-0.5 shrink-0"/>
                            <div>
                                <span className="font-bold">Внимание:</span> История заказов по дням недоступна в API. Показаны усредненные данные на основе общих итогов.
                            </div>
                        </div>
                    )}
                </>
            ) : (
                <div className="text-center py-20 text-slate-400">Нет данных</div>
            )}
        </div>
    );
};

export default FunnelPage;