import React, { useState, useEffect } from 'react';
import { 
    ArrowLeft, TrendingDown, Warehouse, Calendar, 
    DollarSign, AlertCircle, Search, Loader2, Info, X, Lock, Check,
    FileDown, HelpCircle
} from 'lucide-react';
import { 
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';

const AdvancedAnalyticsPage = ({ onBack, user }) => {
    const [activeTab, setActiveTab] = useState('forensics'); // forensics | cashgap
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [showInfo, setShowInfo] = useState(false); // Состояние для показа подсказки
    const [pdfLoading, setPdfLoading] = useState(false);

    useEffect(() => {
        fetchData();
    }, [activeTab]);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
            const endpoint = activeTab === 'forensics' 
                ? `${API_URL}/api/analytics/forensics/returns?days=30`
                : `${API_URL}/api/analytics/finance/cash-gap`;
            
            const res = await fetch(endpoint, { headers: getTgHeaders() });
            if (res.ok) {
                const result = await res.json();
                setData(result);
            } else {
                const errorData = await res.json().catch(() => ({ detail: 'Ошибка загрузки данных' }));
                if (res.status === 403) {
                    setError(errorData.detail || 'Эта функция недоступна на вашем тарифе');
                } else {
                    setError(errorData.detail || 'Ошибка загрузки данных');
                }
                setData(null);
            }
        } catch (e) {
            console.error(e);
            setError('Ошибка соединения с сервером');
            setData(null);
        } finally {
            setLoading(false);
        }
    };

    const handleDownloadPdf = async () => {
        setPdfLoading(true);
        try {
            const token = window.Telegram?.WebApp?.initData || '';
            if (!token) {
                alert('Ошибка авторизации. Перезагрузите страницу.');
                return;
            }
            // ИСПРАВЛЕНО: URL теперь указывают на /api/analytics, где смонтирован роутер
            const endpoint = activeTab === 'forensics' 
                ? '/api/analytics/report/forensics-pdf'
                : '/api/analytics/report/cashgap-pdf';
            const url = `${API_URL}${endpoint}?x_tg_data=${encodeURIComponent(token)}`;
            window.open(url, '_blank');
        } catch (e) {
            alert('Не удалось скачать PDF: ' + (e.message || ''));
        } finally {
            setPdfLoading(false);
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

    // Determine header style based on active tab
    const headerGradient = activeTab === 'forensics' 
        ? 'from-indigo-600 to-violet-600' 
        : 'from-rose-500 to-orange-500';
    
    const headerShadow = activeTab === 'forensics'
        ? 'shadow-indigo-200'
        : 'shadow-rose-200';

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-right-4">
            
            {/* Unified Header */}
            <div className="flex justify-between items-stretch h-24 mb-6">
                 {/* Main Header Card */}
                 <div className={`bg-gradient-to-r ${headerGradient} p-5 rounded-[28px] text-white shadow-xl ${headerShadow} relative overflow-hidden flex-1 mr-3 flex items-center justify-between transition-colors duration-500`}>
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            {activeTab === 'forensics' ? <Search size={24} className="text-white"/> : <DollarSign size={24} className="text-white"/>}
                            {activeTab === 'forensics' ? 'Форензика' : 'Cash Gap'}
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            {activeTab === 'forensics' ? 'Поиск аномалий' : 'Прогноз разрывов'}
                        </p>
                    </div>

                    {/* Download Button inside Header */}
                    <div className="relative z-10">
                         <button 
                            onClick={handleDownloadPdf}
                            disabled={pdfLoading || loading || !data}
                            className="bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm disabled:opacity-50"
                            title="Скачать отчет"
                        >
                            {pdfLoading ? <Loader2 size={20} className="animate-spin" /> : <FileDown size={20} />}
                        </button>
                    </div>
                    
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 {/* Right Sidebar Buttons */}
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button 
                        onClick={onBack} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                        title="Назад"
                      >
                          <ArrowLeft size={24}/>
                      </button>
                      
                      <div className="group relative h-full">
                        <button className="bg-white h-full w-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95">
                            <HelpCircle size={24}/>
                        </button>
                        {/* Tooltip */}
                        <div className="hidden group-hover:block absolute top-0 right-full mr-2 w-64 p-4 bg-slate-900 text-white text-xs rounded-xl shadow-xl z-50">
                            <div className="font-bold mb-2 text-indigo-300">{info.title}</div>
                            <p className="leading-relaxed">{info.text}</p>
                            <div className="absolute top-6 right-0 translate-x-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-l-slate-900"></div>
                        </div>
                      </div>
                 </div>
            </div>

            {/* Tabs */}
            <div className="bg-white p-1.5 rounded-2xl flex shadow-sm border border-slate-100">
                <button 
                    onClick={() => { setActiveTab('forensics'); setData(null); setError(null); }}
                    className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${activeTab === 'forensics' ? 'bg-indigo-600 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    <Search size={14}/> Форензика
                </button>
                <button 
                    onClick={() => { setActiveTab('cashgap'); setData(null); setError(null); }}
                    className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${activeTab === 'cashgap' ? 'bg-rose-500 text-white shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
                >
                    <TrendingDown size={14}/> Разрывы
                </button>
            </div>

            {/* Plan Info Banner */}
            {user && (
                <div className={`p-4 rounded-2xl border-2 ${
                    activeTab === 'forensics' 
                        ? (user?.plan === 'analyst' || user?.plan === 'strategist' 
                            ? 'bg-indigo-50 border-indigo-200' 
                            : 'bg-amber-50 border-amber-200')
                        : (user?.plan === 'strategist' 
                            ? 'bg-rose-50 border-rose-200' 
                            : 'bg-amber-50 border-amber-200')
                }`}>
                    <div className="flex items-start gap-3">
                        {activeTab === 'forensics' ? (
                            (user?.plan === 'analyst' || user?.plan === 'strategist') ? (
                                <>
                                    <Check className="text-indigo-600" size={20} />
                                    <div className="flex-1 text-sm">
                                        <div className="font-bold text-indigo-900 mb-1">Форензика возвратов доступна</div>
                                        <div className="text-indigo-700 text-xs">
                                            Доступен анализ проблемных размеров и складов. История: {user?.plan === 'analyst' ? '60 дней' : '365 дней'}.
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <Lock className="text-amber-600" size={20} />
                                    <div className="flex-1 text-sm">
                                        <div className="font-bold text-amber-900 mb-1">Форензика доступна на тарифе Аналитик+</div>
                                        <div className="text-amber-700 text-xs">
                                            Обновите тариф для доступа к анализу проблемных возвратов и аномалий складов.
                                        </div>
                                    </div>
                                </>
                            )
                        ) : (
                            user?.plan === 'strategist' ? (
                                <>
                                    <Check className="text-rose-600" size={20} />
                                    <div className="flex-1 text-sm">
                                        <div className="font-bold text-rose-900 mb-1">Cash Gap анализ доступен</div>
                                        <div className="text-rose-700 text-xs">
                                            Доступен прогноз кассовых разрывов на основе Supply Chain.
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <Lock className="text-amber-600" size={20} />
                                    <div className="flex-1 text-sm">
                                        <div className="font-bold text-amber-900 mb-1">Cash Gap доступен на тарифе Стратег</div>
                                        <div className="text-amber-700 text-xs">
                                            Обновите тариф для доступа к прогнозу кассовых разрывов и планированию закупок.
                                        </div>
                                    </div>
                                </>
                            )
                        )}
                    </div>
                </div>
            )}

            {error && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm">
                    <div className="font-bold text-amber-900 mb-2">⚠️ {error}</div>
                </div>
            )}

            {loading ? (
                <div className="flex justify-center py-20"><Loader2 className="animate-spin text-indigo-600" size={32}/></div>
            ) : !data ? (
                <div className="text-center p-10 text-slate-400">
                    {error ? 'Функция недоступна на вашем тарифе' : 'Нет данных'}
                </div>
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