import React, { useState, useEffect } from 'react';
import { 
    ArrowLeft, TrendingDown, Warehouse, Calendar, 
    DollarSign, AlertCircle, Search, Loader2, Info, X
} from 'lucide-react';
import { 
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';

const AdvancedAnalyticsPage = ({ onBack }) => {
    const [activeTab, setActiveTab] = useState('forensics'); // forensics | cashgap
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState(null);
    const [showInfo, setShowInfo] = useState(false); // Состояние для показа подсказки

    useEffect(() => {
        fetchData();
    }, [activeTab]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const endpoint = activeTab === 'forensics' 
                ? `${API_URL}/api/analytics/forensics/returns?days=30`
                : `${API_URL}/api/analytics/finance/cash-gap`;
            
            const res = await fetch(endpoint, { headers: getTgHeaders() });
            if (res.ok) {
                setData(await res.json());
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    // Тексты подсказок
    const getInfoContent = () => {
        if (activeTab === 'forensics') {
            return {
                title: "Зачем нужна Форензика?",
                text: "Этот инструмент ищет скрытые убытки. Если у размера низкий выкуп — возможно, проблема в лекалах. Если на складе высокий % возвратов — возможен брак партии или подмена товара. Исправив это, вы сохраните чистую прибыль."
            };
        }
        return {
            title: "Как работает прогноз разрывов?",
            text: "Мы анализируем скорость продаж и текущие остатки. Система рассчитывает точную дату, когда товар закончится (Out-of-Stock), и подсказывает сумму, которую нужно подготовить для закупки, чтобы не потерять позиции в выдаче."
        };
    };

    const info = getInfoContent();

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-right-4">
            {/* Header с кнопкой Инфо */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <button onClick={onBack} className="p-3 bg-white rounded-xl shadow-sm border border-slate-100 text-slate-500 hover:text-slate-800 active:scale-95 transition-transform">
                        <ArrowLeft size={20} />
                    </button>
                    <div>
                        <h2 className="text-xl font-black text-slate-800">Глубокая аналитика</h2>
                        <p className="text-xs text-slate-400">Поиск аномалий и планирование</p>
                    </div>
                </div>
                {/* Кнопка вызова подсказки */}
                <button 
                    onClick={() => setShowInfo(!showInfo)}
                    className={`p-3 rounded-xl transition-all ${showInfo ? 'bg-indigo-100 text-indigo-600' : 'bg-white text-slate-400 shadow-sm border border-slate-100'}`}
                >
                    <Info size={20} />
                </button>
            </div>

            {/* Блок с подсказкой (появляется при клике) */}
            {showInfo && (
                <div className="bg-indigo-50 p-4 rounded-2xl border border-indigo-100 relative animate-in fade-in zoom-in-95 shadow-sm">
                    <button onClick={() => setShowInfo(false)} className="absolute top-3 right-3 text-indigo-400 hover:text-indigo-700">
                        <X size={16} />
                    </button>
                    <h4 className="font-bold text-indigo-900 text-sm mb-2 flex items-center gap-2">
                        <Info size={16} className="text-indigo-600"/> 
                        {info.title}
                    </h4>
                    <p className="text-xs text-indigo-800 leading-relaxed opacity-90">
                        {info.text}
                    </p>
                </div>
            )}

            {/* Tabs */}
            <div className="bg-slate-100 p-1 rounded-xl flex">
                <button 
                    onClick={() => { setActiveTab('forensics'); setData(null); }}
                    className={`flex-1 py-2.5 rounded-lg text-xs font-bold transition-all ${activeTab === 'forensics' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400'}`}
                >
                    🕵️ Форензика
                </button>
                <button 
                    onClick={() => { setActiveTab('cashgap'); setData(null); }}
                    className={`flex-1 py-2.5 rounded-lg text-xs font-bold transition-all ${activeTab === 'cashgap' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400'}`}
                >
                    💰 Кассовые разрывы
                </button>
            </div>

            {loading ? (
                <div className="flex justify-center py-20"><Loader2 className="animate-spin text-indigo-600" size={32}/></div>
            ) : !data ? (
                <div className="text-center p-10 text-slate-400">Нет данных</div>
            ) : (
                <>
                    {activeTab === 'forensics' && <ForensicsView data={data} />}
                    {activeTab === 'cashgap' && <CashGapView data={data} />}
                </>
            )}
        </div>
    );
};

// --- Вкладка 1: Форензика (Возвраты) ---
const ForensicsView = ({ data }) => {
    return (
        <div className="space-y-6 animate-in fade-in">
            {/* Анализ Размеров */}
            <div className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm">
                <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                    <TrendingDown className="text-rose-500" size={20}/>
                    Проблемные размеры
                </h3>
                <div className="space-y-3">
                    {data.size_analysis?.map((item, i) => (
                        <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-2xl border border-slate-100">
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="bg-white px-2 py-0.5 rounded-md text-xs font-black border border-slate-200">{item.size}</span>
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${item.buyout_rate < 30 ? 'bg-rose-100 text-rose-600' : 'bg-amber-100 text-amber-600'}`}>
                                        Выкуп {item.buyout_rate}%
                                    </span>
                                </div>
                                <div className="text-[10px] text-slate-500 max-w-[180px] leading-tight">{item.verdict}</div>
                            </div>
                            <div className="text-right">
                                <div className="text-sm font-bold text-slate-700">{item.returns} возвр.</div>
                                <div className="text-[10px] text-rose-500 font-medium">-{item.loss_on_returns} ₽</div>
                            </div>
                        </div>
                    ))}
                    {(!data.size_analysis || data.size_analysis.length === 0) && 
                        <div className="text-center text-xs text-slate-400 py-4">
                            Проблем с размерами не выявлено 🎉
                        </div>
                    }
                </div>
            </div>

            {/* Анализ Складов */}
            <div className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm">
                <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-slate-800">
                    <Warehouse className="text-indigo-500" size={20}/>
                    Аномалии складов
                </h3>
                <div className="grid grid-cols-2 gap-3">
                    {data.warehouse_analysis?.map((wh, i) => (
                        <div key={i} className="bg-slate-50 p-3 rounded-2xl border border-slate-100">
                            <div className="text-xs font-bold text-slate-500 uppercase mb-1 truncate">{wh.warehouse}</div>
                            <div className="flex justify-between items-end">
                                <div className="text-lg font-black text-slate-800">{wh.return_rate}%</div>
                                <div className="text-[10px] text-slate-400 mb-1">{wh.returns_count} шт</div>
                            </div>
                            <div className="mt-2 h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${wh.return_rate > 20 ? 'bg-rose-500' : 'bg-indigo-500'}`} style={{width: `${Math.min(100, wh.return_rate)}%`}}></div>
                            </div>
                        </div>
                    ))}
                    {(!data.warehouse_analysis || data.warehouse_analysis.length === 0) && 
                         <div className="col-span-2 text-center text-xs text-slate-400 py-4">
                             Данных по складам пока нет
                         </div>
                    }
                </div>
            </div>
        </div>
    );
};

// --- Вкладка 2: Кассовые разрывы ---
const CashGapView = ({ data }) => {
    // Подготовка данных для графика
    const chartData = data.timeline?.slice(0, 14).map(t => ({
        date: new Date(t.date).toLocaleDateString('ru-RU', {day: 'numeric', month: 'short'}),
        amount: t.amount_needed
    })) || [];

    return (
        <div className="space-y-6 animate-in fade-in">
            {/* Сводка */}
            <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-900 text-white p-4 rounded-3xl shadow-lg relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-16 h-16 bg-white/10 rounded-full -mr-5 -mt-5 blur-xl"></div>
                    <div className="text-[10px] text-slate-400 font-bold uppercase mb-1">Нужно на закупку</div>
                    <div className="text-2xl font-black">{data.total_needed_soon?.toLocaleString()} ₽</div>
                </div>
                <div className={`p-4 rounded-3xl border-2 ${data.nearest_gap_date ? 'bg-rose-50 border-rose-100' : 'bg-emerald-50 border-emerald-100'}`}>
                    <div className="text-[10px] text-slate-500 font-bold uppercase mb-1">Ближайшая оплата</div>
                    <div className={`text-lg font-black ${data.nearest_gap_date ? 'text-rose-600' : 'text-emerald-600'}`}>
                        {data.nearest_gap_date ? new Date(data.nearest_gap_date).toLocaleDateString('ru-RU') : 'Нет'}
                    </div>
                </div>
            </div>

            {/* График потребностей */}
            {chartData.length > 0 && (
                <div className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm h-64">
                    <h3 className="font-bold text-sm mb-4 text-slate-800">Календарь выплат (14 дней)</h3>
                    <ResponsiveContainer width="100%" height="85%">
                        <BarChart data={chartData}>
                            <XAxis dataKey="date" tick={{fontSize: 10}} axisLine={false} tickLine={false} />
                            <Tooltip 
                                cursor={{fill: '#f1f5f9'}}
                                contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)'}}
                            />
                            <Bar dataKey="amount" radius={[4, 4, 4, 4]}>
                                {chartData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.amount > 100000 ? '#f43f5e' : '#6366f1'} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* Timeline */}
            <div className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm">
                <h3 className="font-bold text-lg mb-6 flex items-center gap-2 text-slate-800">
                    <Calendar className="text-indigo-500" size={20}/>
                    Детализация
                </h3>
                <div className="relative space-y-8 pl-4 border-l-2 border-slate-100">
                    {data.timeline?.map((event, i) => (
                        <div key={i} className="relative">
                            <div className={`absolute -left-[21px] top-1 w-3 h-3 rounded-full border-2 border-white shadow-sm ${event.status === 'GAP' ? 'bg-rose-500' : 'bg-emerald-500'}`}></div>
                            <div className="flex justify-between items-start mb-2">
                                <div>
                                    <div className="font-bold text-slate-800 text-sm">
                                        {new Date(event.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}
                                    </div>
                                    <div className="text-[10px] text-slate-400 font-medium">Заканчивается {event.items_count} SKU</div>
                                </div>
                                <div className="font-bold text-slate-700 bg-slate-50 px-2 py-1 rounded-lg text-xs">
                                    {event.amount_needed.toLocaleString()} ₽
                                </div>
                            </div>
                            {/* Список товаров внутри даты */}
                            <div className="bg-slate-50 rounded-xl p-2 space-y-1">
                                {event.details.slice(0, 3).map((item, idx) => (
                                    <div key={idx} className="flex justify-between text-[10px] text-slate-600">
                                        <span className="truncate max-w-[150px]">{item.name}</span>
                                        <span className="font-bold">{item.qty} шт</span>
                                    </div>
                                ))}
                                {event.details.length > 3 && (
                                    <div className="text-[10px] text-indigo-500 font-bold text-center pt-1">
                                        + еще {event.details.length - 3}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                    {data.timeline?.length === 0 && <div className="text-slate-400 text-xs">Платежей не предвидится</div>}
                </div>
            </div>
        </div>
    );
};

export default AdvancedAnalyticsPage;