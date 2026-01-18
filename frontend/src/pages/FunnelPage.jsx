import React, { useState, useEffect } from 'react';
import { 
    ArrowLeft, Filter, Eye, ShoppingCart, Package, CreditCard, 
    Calendar, Loader2, TrendingUp, Info 
} from 'lucide-react';
import { 
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';

const FunnelPage = ({ onBack }) => {
    const [period, setPeriod] = useState(30); // 7, 14, 30, 60, 90
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        fetchFunnelData();
    }, [period]);

    const fetchFunnelData = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/analytics/funnel?days=${period}`, { 
                headers: getTgHeaders() 
            });
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

    const formatNum = (num) => new Intl.NumberFormat('ru-RU').format(num);

    // --- Компонент "Красивая корзина" ---
    const ConversionStep = ({ icon: Icon, label, value, subValue, color, percent, prevPercent, isLast }) => (
        <div className="relative z-10 flex-1 min-w-[140px]">
            {/* Соединительная линия */}
            {!isLast && (
                <div className="absolute top-8 left-1/2 w-full h-1 bg-slate-100 -z-10">
                    <div 
                        className={`h-full ${color.bg} opacity-30 transition-all duration-1000 origin-left`} 
                        style={{ width: `${percent}%` }}
                    ></div>
                </div>
            )}
            
            <div className="flex flex-col items-center group">
                {/* Иконка с пульсацией */}
                <div className={`w-16 h-16 rounded-2xl ${color.bg} ${color.text} flex items-center justify-center shadow-lg mb-3 relative transition-transform group-hover:scale-110 duration-300`}>
                    <Icon size={32} />
                    <div className={`absolute -bottom-3 px-2 py-0.5 rounded-full text-[10px] font-bold bg-white border border-slate-100 shadow-sm ${percent < 5 ? 'text-rose-500' : 'text-slate-600'}`}>
                        {percent}%
                    </div>
                </div>

                {/* Данные */}
                <div className="text-center">
                    <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">{label}</div>
                    <div className="text-lg font-black text-slate-800">{formatNum(value)}</div>
                    {subValue && <div className="text-[10px] text-slate-400 font-medium">{subValue}</div>}
                </div>
            </div>
        </div>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in bg-[#F4F4F9] min-h-screen">
            
            {/* Header */}
            <div className="flex items-center gap-3 mb-6">
                <button onClick={onBack} className="p-2.5 bg-white rounded-xl border border-slate-200 shadow-sm active:scale-95 transition-transform">
                    <ArrowLeft size={20} className="text-slate-500"/>
                </button>
                <div className="flex-1">
                    <h1 className="text-2xl font-black text-slate-900 leading-none">Воронка продаж</h1>
                    <div className="flex items-center gap-1.5 mt-1">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                        <span className="text-xs font-bold text-slate-400">Данные за {period} дн.</span>
                    </div>
                </div>
            </div>

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
                    {/* Визуальная Воронка ("Красивая корзина") */}
                    <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-rose-500 opacity-20"></div>
                        
                        <h3 className="font-bold text-slate-800 mb-8 flex items-center gap-2">
                            <Filter size={18} className="text-indigo-600"/>
                            Конверсия покупателя
                        </h3>

                        <div className="flex justify-between items-start gap-2 overflow-x-auto pb-4 px-2 no-scrollbar">
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
                                percent={data.conversions.order_to_buyout}
                                color={{bg: 'bg-emerald-100', text: 'text-emerald-600'}}
                                isLast={true}
                            />
                        </div>

                        {data.limit_used < period && (
                            <div className="mt-4 p-3 bg-amber-50 rounded-xl flex items-start gap-3 border border-amber-100">
                                <Info size={16} className="text-amber-600 mt-0.5 shrink-0"/>
                                <div className="text-xs text-amber-800">
                                    <span className="font-bold">Лимит тарифа:</span> Показаны данные только за {data.limit_used} дн. Обновите тариф для доступа к истории до {data.max_limit} дн.
                                </div>
                            </div>
                        )}
                    </div>

                    {/* График Динамики */}
                    <div className="bg-white rounded-3xl p-5 shadow-sm border border-slate-100 h-80">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <TrendingUp size={18} className="text-indigo-600"/>
                                Динамика заказов
                            </h3>
                            <div className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-lg">
                                +{formatNum(data.totals.revenue)} ₽
                            </div>
                        </div>
                        
                        <ResponsiveContainer width="100%" height="85%">
                            <AreaChart data={data.chart}>
                                <defs>
                                    <linearGradient id="colorOrders" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.3}/>
                                        <stop offset="95%" stopColor="#4f46e5" stopOpacity={0}/>
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
                                    formatter={(val, name) => [
                                        name === 'orders_sum' ? `${formatNum(val)} ₽` : val, 
                                        name === 'orders_sum' ? 'Сумма' : 
                                        name === 'orders' ? 'Заказы' :
                                        name === 'cart' ? 'Корзины (расч.)' : name
                                    ]}
                                />
                                <Area 
                                    type="monotone" 
                                    dataKey="orders_sum" 
                                    stroke="#4f46e5" 
                                    strokeWidth={3}
                                    fillOpacity={1} 
                                    fill="url(#colorOrders)" 
                                />
                                {/* Можно добавить линию корзин, но она расчетная, лучше не путать */}
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