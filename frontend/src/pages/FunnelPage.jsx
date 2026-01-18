import React, { useState, useEffect } from 'react';
import { 
    ArrowLeft, Filter, Eye, ShoppingCart, Package, CreditCard, 
    Calendar, Loader2, TrendingUp, Info, HelpCircle, X
} from 'lucide-react';
import { 
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';

const FunnelPage = ({ onBack }) => {
    const [period, setPeriod] = useState(30);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    
    // Новые стейты
    const [chartMode, setChartMode] = useState('orders'); // 'orders' | 'buyouts'
    const [nmIds, setNmIds] = useState('');
    const [isFilterOpen, setIsFilterOpen] = useState(false);

    useEffect(() => {
        fetchFunnelData();
    }, [period]); // nmIds добавим в зависимость от нажатия Enter или Blur

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

    const ConversionStep = ({ icon: Icon, label, value, subValue, color, percent, isLast }) => (
        <div className="relative z-10 flex-1 min-w-[140px]">
            {!isLast && (
                <div className="absolute top-8 left-1/2 w-full h-1 bg-slate-100 -z-10">
                    <div 
                        className={`h-full ${color.bg} opacity-30 transition-all duration-1000 origin-left`} 
                        style={{ width: `${percent}%` }}
                    ></div>
                </div>
            )}
            
            <div className="flex flex-col items-center group">
                <div className={`w-16 h-16 rounded-2xl ${color.bg} ${color.text} flex items-center justify-center shadow-lg mb-3 relative transition-transform group-hover:scale-110 duration-300`}>
                    <Icon size={32} />
                    <div className={`absolute -bottom-3 px-2 py-0.5 rounded-full text-[10px] font-bold bg-white border border-slate-100 shadow-sm ${percent < 5 ? 'text-rose-500' : 'text-slate-600'}`}>
                        {percent}%
                    </div>
                </div>

                <div className="text-center">
                    <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">{label}</div>
                    <div className="text-lg font-black text-slate-800">{formatNum(value)}</div>
                    {subValue && <div className="text-[10px] text-slate-400 font-medium">{subValue}</div>}
                </div>
            </div>
        </div>
    );

    // Цвета для заголовка
    const headerGradient = 'from-pink-600 to-rose-600';
    const headerShadow = 'shadow-rose-200';

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in bg-[#F4F4F9] min-h-screen">
            
            {/* Unified Header */}
            <div className="flex justify-between items-stretch h-24 mb-6">
                 {/* Main Header Card */}
                 <div className={`bg-gradient-to-r ${headerGradient} p-5 rounded-[28px] text-white shadow-xl ${headerShadow} relative overflow-hidden flex-1 mr-3 flex items-center justify-between transition-colors duration-500`}>
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <Filter size={24} className="text-white"/>
                            Воронка продаж
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            Конверсии и динамика
                        </p>
                    </div>

                    {/* Filter Button inside Header */}
                    <div className="relative z-10">
                         <button 
                            onClick={() => setIsFilterOpen(!isFilterOpen)}
                            className="bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm"
                            title="Фильтр товаров"
                        >
                           {isFilterOpen ? <X size={20} /> : <Filter size={20} />}
                        </button>
                    </div>
                    
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 {/* Right Sidebar Buttons */}
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button 
                        onClick={onBack} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                      >
                          <ArrowLeft size={24}/>
                      </button>
                      
                      <div className="group relative h-full">
                        <button className="bg-white h-full w-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95">
                            <HelpCircle size={24}/>
                        </button>
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
                        <button 
                            onClick={fetchFunnelData}
                            className="bg-rose-500 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-md hover:bg-rose-600 transition-colors"
                        >
                            ОК
                        </button>
                    </div>
                </div>
            )}

            {/* Фильтр Периода */}
            <div className="bg-white p-1.5 rounded-2xl flex shadow-sm border border-slate-100 overflow-x-auto">
                {[7, 14, 30, 60, 90].map(d => (
                    <button 
                        key={d}
                        onClick={() => setPeriod(d)}
                        className={`flex-1 min-w-[60px] py-2.5 rounded-xl text-xs font-bold transition-all ${
                            period === d 
                            ? 'bg-slate-900 text-white shadow-md' 
                            : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'
                        }`}
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
                    {/* Визуальная Воронка */}
                    <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-rose-500 opacity-20"></div>
                        
                        <div className="flex justify-between items-start gap-2 overflow-x-auto pb-4 px-2 no-scrollbar mt-4">
                            <ConversionStep 
                                icon={Eye} 
                                label="Просмотры" 
                                value={data.totals.visitors}
                                percent={100}
                                color={{bg: 'bg-indigo-100', text: 'text-indigo-600'}}
                            />
                            <ConversionStep 
                                icon={ShoppingCart} 
                                label="В корзину" 
                                value={data.totals.cart}
                                percent={data.conversions.view_to_cart}
                                color={{bg: 'bg-violet-100', text: 'text-violet-600'}}
                            />
                            <ConversionStep 
                                icon={Package} 
                                label="Заказы" 
                                value={data.totals.orders}
                                subValue={`${formatNum(data.totals.revenue)} ₽`}
                                percent={data.conversions.cart_to_order}
                                color={{bg: 'bg-amber-100', text: 'text-amber-600'}}
                            />
                            <ConversionStep 
                                icon={CreditCard} 
                                label="Выкупы" 
                                value={data.totals.buyouts}
                                subValue={`${formatNum(data.totals.buyouts_revenue || 0)} ₽`}
                                percent={data.conversions.order_to_buyout}
                                color={{bg: 'bg-emerald-100', text: 'text-emerald-600'}}
                                isLast={true}
                            />
                        </div>

                        <div className="mt-4 flex flex-col gap-2">
                            {data.limit_used < period && (
                                <div className="p-3 bg-amber-50 rounded-xl flex items-start gap-3 border border-amber-100">
                                    <Info size={16} className="text-amber-600 mt-0.5 shrink-0"/>
                                    <div className="text-xs text-amber-800">
                                        <span className="font-bold">Лимит тарифа:</span> Показаны данные только за {data.limit_used} дн.
                                    </div>
                                </div>
                            )}
                            {data.is_estimated && (
                                <div className="p-3 bg-indigo-50 rounded-xl flex items-start gap-3 border border-indigo-100">
                                    <Info size={16} className="text-indigo-600 mt-0.5 shrink-0"/>
                                    <div className="text-xs text-indigo-800">
                                        <span className="font-bold">Внимание:</span> Данные по дням усреднены, так как детальная история временно недоступна. Общие суммы точные.
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* График Динамики */}
                    <div className="bg-white rounded-3xl p-5 shadow-sm border border-slate-100 h-96">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <TrendingUp size={18} className="text-indigo-600"/>
                                Динамика
                            </h3>
                            
                            {/* Переключатель графика */}
                            <div className="bg-slate-100 p-1 rounded-xl flex text-[10px] font-bold">
                                <button 
                                    onClick={() => setChartMode('orders')}
                                    className={`px-3 py-1.5 rounded-lg transition-all ${chartMode === 'orders' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400'}`}
                                >
                                    Заказы
                                </button>
                                <button 
                                    onClick={() => setChartMode('buyouts')}
                                    className={`px-3 py-1.5 rounded-lg transition-all ${chartMode === 'buyouts' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-400'}`}
                                >
                                    Выкупы
                                </button>
                            </div>
                        </div>
                        
                        <ResponsiveContainer width="100%" height="85%">
                            <AreaChart data={data.chart}>
                                <defs>
                                    <linearGradient id="colorOrders" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.3}/>
                                        <stop offset="95%" stopColor="#4f46e5" stopOpacity={0}/>
                                    </linearGradient>
                                    <linearGradient id="colorBuyouts" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                                        <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
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
                                />
                                <YAxis hide={true} />
                                <Tooltip 
                                    contentStyle={{borderRadius: '16px', border: 'none', boxShadow: '0 10px 40px -10px rgba(0,0,0,0.1)'}}
                                    labelStyle={{color: '#64748b', marginBottom: '0.5rem', fontSize: '12px'}}
                                    formatter={(val, name) => {
                                        if (chartMode === 'orders') {
                                            return name === 'orders_sum' ? [`${formatNum(val)} ₽`, 'Сумма заказов'] : [val, 'Кол-во'];
                                        } else {
                                            return name === 'buyouts_sum' ? [`${formatNum(val)} ₽`, 'Сумма выкупов'] : [val, 'Кол-во'];
                                        }
                                    }}
                                />
                                <Area 
                                    type="monotone" 
                                    dataKey={chartMode === 'orders' ? 'orders_sum' : 'buyouts_sum'} 
                                    stroke={chartMode === 'orders' ? '#4f46e5' : '#10b981'}
                                    strokeWidth={3}
                                    fillOpacity={1} 
                                    fill={chartMode === 'orders' ? 'url(#colorOrders)' : 'url(#colorBuyouts)'}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </>
            ) : (
                <div className="text-center py-20 text-slate-400">Нет данных для воронки</div>
            )}
        </div>
    );
};

export default FunnelPage;