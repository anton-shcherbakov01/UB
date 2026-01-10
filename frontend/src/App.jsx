import React, { useState, useEffect } from 'react';
import { 
  Search, Wallet, CreditCard, AlertCircle, Loader2, Sparkles, BarChart3, 
  ArrowUpRight, Plus, User, Shield, Brain, Star, ThumbsDown, CheckCircle2, 
  Crown, LayoutGrid, Trash2, RefreshCw, X, History as HistoryIcon, 
  ChevronLeft, FileDown, LogOut, Receipt, Wand2, Copy, Edit2, Check, Hash,
  Key, TrendingUp, Package, Coins, Calculator, DollarSign, PieChart, Truck, Scale, Target, PlayCircle, ShieldCheck, Clock
} from 'lucide-react';
import { 
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area, CartesianGrid 
} from 'recharts';

const API_URL = "https://api.ulike-bot.ru"; 

// --- КОМПОНЕНТЫ UI ---

const TabNav = ({ active, setTab, isAdmin }) => (
  <div className="fixed bottom-0 left-0 right-0 bg-white/95 backdrop-blur-md border-t border-slate-100 px-2 py-3 flex justify-between items-end z-50 pb-8 safe-area-pb shadow-[0_-5px_20px_rgba(0,0,0,0.03)]">
    <button onClick={() => setTab('home')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'home' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <LayoutGrid size={22} strokeWidth={active === 'home' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">Главная</span>
    </button>
    <button onClick={() => setTab('monitor')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'monitor' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <BarChart3 size={22} strokeWidth={active === 'monitor' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">Цены</span>
    </button>
    
    <div className="relative -top-5 w-[20%] flex justify-center">
        <button 
            onClick={() => setTab('finance')} 
            className="bg-indigo-600 text-white w-14 h-14 rounded-full shadow-xl shadow-indigo-300 active:scale-95 transition-transform border-4 border-white flex items-center justify-center"
        >
            <DollarSign size={28} strokeWidth={3} />
        </button>
    </div>

    <button onClick={() => setTab('ai')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'ai' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <Brain size={22} strokeWidth={active === 'ai' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">ИИ</span>
    </button>
    
    <button onClick={() => setTab('profile')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'profile' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <User size={22} strokeWidth={active === 'profile' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">Профиль</span>
    </button>
  </div>
);

const StoriesBar = () => {
    const [stories, setStories] = useState([]);
    
    useEffect(() => {
        fetch(`${API_URL}/api/internal/stories`, {
             headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
        }).then(r => r.json()).then(setStories).catch(console.error);
    }, []);

    if (stories.length === 0) return null;

    return (
        <div className="flex gap-3 overflow-x-auto pb-4 px-2 scrollbar-hide">
            {stories.map(s => (
                <div key={s.id} className="flex flex-col items-center gap-1 min-w-[64px]">
                    <div className={`w-14 h-14 rounded-full p-[2px] ${s.color}`}>
                        <div className="w-full h-full rounded-full bg-white border-2 border-transparent flex items-center justify-center flex-col">
                             <span className="text-[10px] font-bold text-center leading-tight">{s.val}</span>
                        </div>
                    </div>
                    <span className="text-[9px] font-medium text-slate-500">{s.title}</span>
                </div>
            ))}
        </div>
    )
}

const TariffCard = ({ plan, onPay }) => (
  <div className={`p-6 rounded-3xl border-2 relative overflow-hidden transition-all ${plan.is_best ? 'border-indigo-600 bg-indigo-50/50 scale-[1.02] shadow-lg' : 'border-slate-100 bg-white'}`}>
    {plan.is_best && (
      <div className="absolute top-0 right-0 bg-indigo-600 text-white px-3 py-1 rounded-bl-xl text-[10px] font-black uppercase">
        ХИТ
      </div>
    )}
    <h3 className={`text-xl font-black uppercase ${plan.is_best ? 'text-indigo-700' : 'text-slate-800'}`}>{plan.name}</h3>
    <div className="flex items-baseline gap-2 mt-2 mb-4">
        <span className="text-3xl font-black text-slate-900">{plan.price}</span>
        {plan.stars > 0 && <span className="text-xs font-bold text-amber-500 bg-amber-100 px-2 py-0.5 rounded-full flex items-center gap-1"><Star size={10} fill="currentColor"/> {plan.stars} Stars</span>}
    </div>
    
    <ul className="space-y-3 mb-6">
      {plan.features.map((f, i) => (
        <li key={i} className="flex items-start gap-3 text-sm font-medium text-slate-600">
          <CheckCircle2 size={16} className={`mt-0.5 ${plan.is_best ? 'text-indigo-600' : 'text-slate-400'}`} />
          <span>{f}</span>
        </li>
      ))}
    </ul>
    
    <button 
        onClick={() => !plan.current && onPay(plan)}
        className={`w-full py-4 rounded-xl font-bold text-sm shadow-lg active:scale-95 transition-all flex justify-center items-center gap-2 ${plan.current ? 'bg-slate-200 text-slate-500 cursor-not-allowed' : plan.is_best ? 'bg-indigo-600 text-white shadow-indigo-200' : 'bg-slate-900 text-white'}`}
    >
      {plan.current ? 'Ваш текущий план' : <>{plan.stars > 0 && <Star size={16} fill="currentColor" className="text-amber-400"/>} Оплатить Stars</>}
    </button>
  </div>
);

const CostEditModal = ({ item, onClose, onSave }) => {
    const [cost, setCost] = useState(item.cost_price || 0);
    return (
        <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in">
            <div className="bg-white w-full max-w-sm rounded-[32px] p-6 shadow-2xl">
                <h3 className="font-bold text-lg mb-2">Себестоимость</h3>
                <p className="text-xs text-slate-400 mb-4">Для расчета чистой прибыли SKU {item.sku}</p>
                <input 
                    type="number" 
                    value={cost} 
                    onChange={e => setCost(e.target.value)}
                    className="w-full bg-slate-50 text-2xl font-black text-center p-4 rounded-2xl outline-none focus:ring-2 ring-indigo-500 mb-4"
                />
                <div className="flex gap-2">
                    <button onClick={onClose} className="flex-1 py-3 bg-slate-100 font-bold rounded-xl text-slate-600">Отмена</button>
                    <button onClick={() => onSave(item.sku, cost)} className="flex-1 py-3 bg-indigo-600 text-white font-bold rounded-xl shadow-lg shadow-indigo-200">Сохранить</button>
                </div>
            </div>
        </div>
    );
};

// --- NEW: History Modal Module ---
const HistoryModule = ({ type, isOpen, onClose }) => {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedItem, setSelectedItem] = useState(null);

    useEffect(() => {
        if (isOpen) {
            setLoading(true);
            fetch(`${API_URL}/api/user/history?request_type=${type}`, { 
                headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } 
            })
            .then(r => r.json())
            .then(data => { setHistory(data); setLoading(false); })
            .catch(() => setLoading(false));
        }
    }, [isOpen, type]);

    if (!isOpen) return null;

    const getTypeIcon = (t) => {
        switch(t) {
            case 'ai': return <Brain size={18}/>;
            case 'seo': return <Wand2 size={18}/>;
            default: return <Search size={18}/>;
        }
    };

    return (
        <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center animate-in fade-in duration-200">
            <div className="bg-white w-full max-w-lg sm:rounded-[32px] rounded-t-[32px] p-6 shadow-2xl relative max-h-[85vh] flex flex-col">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="font-bold text-lg">История запросов</h3>
                    <button onClick={onClose} className="p-2 bg-slate-100 rounded-full text-slate-500"><X size={20} /></button>
                </div>

                <div className="flex-1 overflow-y-auto space-y-3 pb-4">
                    {loading ? (
                        <div className="flex justify-center p-10"><Loader2 className="animate-spin text-slate-400"/></div>
                    ) : history.length === 0 ? (
                        <div className="text-center p-10 text-slate-400 border border-dashed border-slate-200 rounded-2xl">Пусто</div>
                    ) : (
                        history.map(h => (
                            <div key={h.id} onClick={() => setSelectedItem(h)} className="bg-slate-50 p-3 rounded-xl flex items-center gap-3 cursor-pointer active:scale-[0.99] transition-transform">
                                <div className="bg-white p-2 rounded-lg text-indigo-600 shadow-sm">{getTypeIcon(h.type)}</div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-bold text-sm truncate">{h.title || `SKU ${h.sku}`}</div>
                                    <div className="text-[10px] text-slate-400">{new Date(h.created_at).toLocaleString('ru-RU')}</div>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>
            
            {selectedItem && (
                <div className="absolute inset-0 z-[70] bg-white sm:rounded-[32px] rounded-t-[32px] p-6 overflow-y-auto">
                    <button onClick={() => setSelectedItem(null)} className="absolute top-4 right-4 p-2 bg-slate-100 rounded-full text-slate-500"><ChevronLeft size={20} /></button>
                    <h3 className="font-bold text-xl mb-4 mt-2">{selectedItem.title}</h3>
                    <div className="whitespace-pre-wrap text-sm text-slate-700">
                        {selectedItem.type === 'seo' && selectedItem.data.generated_content ? (
                            <>
                                <div className="font-bold mb-1">Заголовок:</div>
                                <div className="bg-slate-50 p-3 rounded-xl mb-3">{selectedItem.data.generated_content.title}</div>
                                <div className="font-bold mb-1">Описание:</div>
                                <div className="bg-slate-50 p-3 rounded-xl">{selectedItem.data.generated_content.description}</div>
                            </>
                        ) : (
                            <pre className="text-xs bg-slate-50 p-3 rounded-xl overflow-auto">{JSON.stringify(selectedItem.data, null, 2)}</pre>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

// --- СТРАНИЦЫ ---

const DashboardPage = ({ onNavigate, user }) => {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (user?.has_wb_token) {
            setLoading(true);
            fetch(`${API_URL}/api/internal/stats`, {
                headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
            })
            .then(r => r.json())
            .then(data => {
                setStats(data);
                setLoading(false);
            })
            .catch(() => setLoading(false));
        }
    }, [user]);

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in duration-500">
            <StoriesBar />

            <div className="bg-gradient-to-br from-indigo-600 to-violet-700 rounded-[32px] p-6 text-white shadow-xl shadow-indigo-200 relative overflow-hidden">
                <div className="relative z-10">
                    <div className="flex justify-between items-start mb-4">
                        <div className="flex items-center gap-2 opacity-80">
                            <Sparkles size={16} className="text-amber-300" />
                            <span className="text-xs font-bold uppercase tracking-widest">Мои Продажи</span>
                        </div>
                        {!user?.has_wb_token && (
                            <button onClick={() => onNavigate('profile')} className="bg-white/20 hover:bg-white/30 px-3 py-1 rounded-full text-xs font-bold transition-colors">
                                Подключить
                            </button>
                        )}
                    </div>

                    {!user?.has_wb_token ? (
                        <div className="text-center py-4">
                            <p className="font-bold text-lg mb-2">Подключите API</p>
                            <p className="text-xs opacity-70">Чтобы видеть реальные продажи</p>
                        </div>
                    ) : loading ? (
                        <div className="flex justify-center py-6"><Loader2 className="animate-spin" /></div>
                    ) : (
                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-white/10 p-3 rounded-2xl backdrop-blur-sm">
                                <p className="text-xs opacity-70 mb-1">Заказы сегодня</p>
                                <p className="text-2xl font-black">{stats?.orders_today?.sum?.toLocaleString() || 0} ₽</p>
                                <p className="text-xs opacity-70">{stats?.orders_today?.count || 0} шт</p>
                            </div>
                            <div className="bg-white/10 p-3 rounded-2xl backdrop-blur-sm">
                                <p className="text-xs opacity-70 mb-1">Остатки</p>
                                <p className="text-2xl font-black">{stats?.stocks?.total_quantity?.toLocaleString() || 0} шт</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                 <div onClick={() => onNavigate('finance')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer col-span-2">
                    <div className="bg-emerald-100 w-12 h-12 rounded-2xl flex items-center justify-center text-emerald-600">
                        <PieChart size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Unit-экономика</span>
                        <span className="text-xs text-slate-400">P&L, Маржа, ROI</span>
                    </div>
                </div>
                <div onClick={() => onNavigate('supply')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-orange-100 w-12 h-12 rounded-2xl flex items-center justify-center text-orange-600">
                        <Truck size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Поставки</span>
                        <span className="text-xs text-slate-400">Прогноз склада</span>
                    </div>
                </div>
                <div onClick={() => onNavigate('bidder')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-purple-100 w-12 h-12 rounded-2xl flex items-center justify-center text-purple-600">
                        <Target size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Биддер</span>
                        <span className="text-xs text-slate-400">Управление рекламой</span>
                    </div>
                </div>
                 <div onClick={() => onNavigate('seo_tracker')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-blue-100 w-12 h-12 rounded-2xl flex items-center justify-center text-blue-600">
                        <TrendingUp size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">SEO Трекер</span>
                        <span className="text-xs text-slate-400">Позиции (SERP)</span>
                    </div>
                </div>
                 <div onClick={() => onNavigate('scanner')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-slate-100 w-12 h-12 rounded-2xl flex items-center justify-center text-slate-600">
                        <Plus size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Сканер</span>
                        <span className="text-xs text-slate-400">Добавить</span>
                    </div>
                </div>
                 <div onClick={() => onNavigate('seo')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-yellow-100 w-12 h-12 rounded-2xl flex items-center justify-center text-yellow-600">
                        <Wand2 size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">SEO Gen</span>
                        <span className="text-xs text-slate-400">Генератор</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

const SupplyPage = () => {
    const [coeffs, setCoeffs] = useState([]);
    const [volume, setVolume] = useState(1000);
    const [calculation, setCalculation] = useState(null);
    const [loading, setLoading] = useState(false);
    
    useEffect(() => {
        fetch(`${API_URL}/api/internal/coefficients`, {
             headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
        }).then(r => r.json()).then(setCoeffs).catch(console.error);
    }, []);

    const handleCalculate = async () => {
        if (!volume) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/internal/transit_calc`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-TG-Data': window.Telegram?.WebApp?.initData || "" 
                },
                body: JSON.stringify({ volume: Number(volume), destination: "Koledino" })
            });
            setCalculation(await res.json());
        } catch(e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-orange-400 to-amber-500 p-6 rounded-3xl text-white shadow-xl shadow-orange-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <Truck className="text-white" /> Supply Chain
                </h1>
                <p className="text-sm opacity-90 mt-2">Управление поставками и коэффициенты складов.</p>
            </div>
            
            <h3 className="font-bold text-lg px-2">Приемка складов (Live)</h3>
            <div className="grid grid-cols-2 gap-3">
                {coeffs.map((c, i) => (
                    <div key={i} className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                        <div className="flex justify-between items-start mb-2">
                             <span className="font-bold text-sm truncate">{c.warehouse}</span>
                             <span className={`text-xs font-black px-2 py-0.5 rounded ${c.coefficient === 0 ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
                                x{c.coefficient}
                             </span>
                        </div>
                        <p className="text-[10px] text-slate-400">Транзит: {c.transit_time}</p>
                    </div>
                ))}
            </div>

            <div className="bg-blue-50 p-6 rounded-3xl border border-blue-100">
                 <h3 className="font-bold text-blue-800 mb-2 flex items-center gap-2"><Scale size={18}/> Калькулятор транзита</h3>
                 <p className="text-sm text-blue-600 mb-4">Сравнение: Прямая поставка vs Транзит через Казань.</p>
                 
                 <div className="mb-4 bg-white p-3 rounded-xl border border-blue-100">
                    <label className="text-[10px] font-bold text-slate-400 uppercase">Объем поставки (литры)</label>
                    <input 
                        type="number"
                        value={volume}
                        onChange={e => setVolume(e.target.value)}
                        className="w-full font-black text-lg outline-none text-slate-800"
                    />
                 </div>

                 <button 
                    onClick={handleCalculate} 
                    disabled={loading}
                    className="w-full bg-blue-600 text-white py-3 rounded-xl font-bold active:scale-95 transition-transform"
                 >
                    {loading ? <Loader2 className="animate-spin mx-auto"/> : 'Рассчитать выгоду'}
                 </button>

                 {calculation && (
                     <div className="mt-4 bg-white p-4 rounded-xl animate-in slide-in-from-top-2 border border-slate-100">
                         <div className="flex justify-between text-sm mb-1">
                             <span className="text-slate-500">Прямая (Коледино):</span>
                             <span className="font-bold">{calculation.direct_cost} ₽</span>
                         </div>
                         <div className="flex justify-between text-sm mb-3">
                             <span className="text-slate-500">Транзит (Казань):</span>
                             <span className="font-bold text-emerald-600">{calculation.transit_cost} ₽</span>
                         </div>
                         <div className={`text-xs font-bold p-3 rounded-lg text-center ${calculation.is_profitable ? 'bg-emerald-100 text-emerald-700' : 'bg-orange-100 text-orange-700'}`}>
                             {calculation.recommendation}
                             {calculation.is_profitable && <div className="mt-1">Выгода: {calculation.benefit} ₽</div>}
                         </div>
                     </div>
                 )}
            </div>
        </div>
    )
}

const BidderPage = () => {
    const [isSafeMode, setIsSafeMode] = useState(true);
    const [logs, setLogs] = useState([]);
    const [stats, setStats] = useState(null);

    const startSimulation = async () => {
        const res = await fetch(`${API_URL}/api/bidder/simulation`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } });
        const data = await res.json();
        setStats(data);
        setLogs(data.logs);
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-purple-600 to-indigo-600 p-6 rounded-3xl text-white shadow-xl shadow-purple-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <Target className="text-white" /> Автобиддер
                </h1>
                <p className="text-sm opacity-90 mt-2">Управление рекламой. Защита бюджета.</p>
            </div>

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="font-bold text-lg">Статус</h3>
                    <div className="flex items-center gap-2 bg-slate-100 px-3 py-1 rounded-full">
                        <div className={`w-2 h-2 rounded-full ${isSafeMode ? 'bg-emerald-500' : 'bg-red-500'}`}></div>
                        <span className="text-xs font-bold text-slate-600">{isSafeMode ? 'Safe Mode' : 'Active'}</span>
                    </div>
                </div>
                <div className="flex gap-2">
                     <button onClick={() => setIsSafeMode(true)} className={`flex-1 py-3 rounded-xl font-bold text-sm transition-all ${isSafeMode ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-50 text-slate-400'}`}>
                        <ShieldCheck size={16} className="inline mr-2"/> Safe Mode
                     </button>
                     <button onClick={() => setIsSafeMode(false)} className={`flex-1 py-3 rounded-xl font-bold text-sm transition-all ${!isSafeMode ? 'bg-red-500 text-white' : 'bg-slate-50 text-slate-400'}`}>
                        <PlayCircle size={16} className="inline mr-2"/> Run
                     </button>
                </div>
                <button onClick={startSimulation} className="w-full mt-4 bg-slate-900 text-white py-3 rounded-xl font-bold">Обновить отчет</button>
            </div>

            {stats && (
                <div className="bg-emerald-50 p-6 rounded-3xl border border-emerald-100 animate-in slide-in-from-bottom-4">
                    <h3 className="font-bold text-emerald-800">Экономия (Прогноз)</h3>
                    <p className="text-3xl font-black text-emerald-600 my-2">{stats.total_budget_saved} ₽</p>
                    <p className="text-xs text-emerald-700">За последние 24 часа в Safe Mode</p>
                </div>
            )}

            {logs.length > 0 && (
                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                    <h3 className="font-bold text-lg mb-4">Лог операций</h3>
                    <div className="space-y-3">
                        {logs.map((l, i) => (
                            <div key={i} className="text-xs border-b border-slate-50 pb-2 last:border-0">
                                <span className="font-bold text-slate-400 mr-2">{l.time}</span>
                                <span className="text-slate-700">{l.msg}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

const SeoTrackerPage = () => {
    const [positions, setPositions] = useState([]);
    const [sku, setSku] = useState('');
    const [keyword, setKeyword] = useState('');
    const [loading, setLoading] = useState(false);

    const loadPositions = () => {
        fetch(`${API_URL}/api/seo/positions`, {
             headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
        }).then(r => r.json()).then(setPositions).catch(console.error);
    }

    useEffect(() => { loadPositions(); }, []);

    const handleTrack = async () => {
        if(!sku || !keyword) return;
        setLoading(true);
        try {
             await fetch(`${API_URL}/api/seo/track`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || "" },
                body: JSON.stringify({sku: Number(sku), keyword})
             });
             alert("Задача добавлена! Обновите список через пару минут.");
             setSku(''); setKeyword('');
             loadPositions();
        } catch(e) { console.error(e); } finally { setLoading(false); }
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-blue-500 to-cyan-500 p-6 rounded-3xl text-white shadow-xl shadow-blue-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <TrendingUp className="text-white" /> SEO Tracker
                </h1>
                <p className="text-sm opacity-90 mt-2">Отслеживайте позиции товаров в поисковой выдаче WB.</p>
            </div>

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                 <div className="flex gap-2 mb-3">
                     <input value={sku} onChange={e => setSku(e.target.value)} placeholder="SKU" className="w-1/3 bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none"/>
                     <input value={keyword} onChange={e => setKeyword(e.target.value)} placeholder="Ключевой запрос" className="flex-1 bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none"/>
                 </div>
                 <button onClick={handleTrack} disabled={loading} className="w-full bg-slate-900 text-white py-3 rounded-xl font-bold text-sm">
                     {loading ? <Loader2 className="animate-spin mx-auto"/> : 'Отследить позицию'}
                 </button>
            </div>

            <div className="space-y-3">
                {positions.map(p => (
                    <div key={p.id} className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex items-center justify-between">
                         <div>
                             <div className="font-bold text-sm">{p.keyword}</div>
                             <div className="text-[10px] text-slate-400">SKU: {p.sku}</div>
                         </div>
                         <div className="text-right">
                             <div className={`font-black text-lg ${p.position > 0 && p.position <= 10 ? 'text-emerald-500' : 'text-slate-700'}`}>
                                 {p.position > 0 ? `#${p.position}` : '>100'}
                             </div>
                             <div className="text-[9px] text-slate-300">{new Date(p.last_check).toLocaleDateString()}</div>
                         </div>
                    </div>
                ))}
            </div>
        </div>
    )
}

const FinancePage = ({ onNavigate }) => {
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingCost, setEditingCost] = useState(null);

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/internal/products`, {
                headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
            });
            if (res.ok) setProducts(await res.json());
        } catch(e) { console.error(e); } finally { setLoading(false); }
    };

    useEffect(() => { fetchProducts(); }, []);

    const handleUpdateCost = async (sku, cost) => {
        try {
            await fetch(`${API_URL}/api/internal/cost/${sku}`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-TG-Data': window.Telegram?.WebApp?.initData || "" 
                },
                body: JSON.stringify({ cost_price: Number(cost) })
            });
            setEditingCost(null);
            fetchProducts();
        } catch(e) { alert("Ошибка обновления"); }
    };

    return (
        <div className="p-4 space-y-4 pb-32 animate-in fade-in slide-in-from-bottom-4">
             <div className="flex justify-between items-center px-2">
                <div>
                    <h2 className="text-xl font-bold text-slate-800">Unit-экономика</h2>
                    <p className="text-xs text-slate-400">Внутренняя аналитика (API)</p>
                </div>
                <button onClick={fetchProducts} className="p-2 bg-white rounded-full shadow-sm text-slate-400 active:rotate-180 transition-all"><RefreshCw size={18}/></button>
            </div>

            {editingCost && <CostEditModal item={editingCost} onClose={() => setEditingCost(null)} onSave={handleUpdateCost} />}

            {loading ? (
                <div className="flex justify-center p-10"><Loader2 className="animate-spin text-emerald-600"/></div>
            ) : products.length === 0 ? (
                <div className="text-center p-10 bg-white rounded-3xl border border-dashed border-slate-200">
                    <p className="font-bold text-slate-500 mb-2">Нет данных</p>
                    <p className="text-xs text-slate-400">Убедитесь, что подключен API токен и на остатках есть товары.</p>
                </div>
            ) : (
                products.map((item) => (
                    <div key={item.sku} className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm relative group mb-3">
                        <div className="flex justify-between items-start mb-3">
                            <div className="min-w-0">
                                <div className="font-bold truncate text-sm">SKU {item.sku}</div>
                                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Остаток: {item.quantity} шт</div>
                            </div>
                            <div className="flex flex-col items-end gap-1">
                                <button onClick={() => setEditingCost(item)} className="p-2 bg-slate-50 text-slate-500 rounded-xl hover:bg-slate-100">
                                    <Calculator size={18} />
                                </button>
                                {item.supply && (
                                    <span className={`text-[9px] font-bold px-2 py-1 rounded-lg ${item.supply.status === 'critical' ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-600'}`}>
                                        {item.supply.days_left} дн.
                                    </span>
                                )}
                            </div>
                        </div>
                        
                        <div className="bg-slate-50 rounded-xl p-3 grid grid-cols-3 gap-2 text-sm">
                             <div>
                                <span className="block text-[9px] text-slate-400 uppercase font-bold">Себестоимость</span>
                                <span className="font-bold text-slate-700">{item.cost_price} ₽</span>
                             </div>
                             <div className="text-center">
                                <span className="block text-[9px] text-slate-400 uppercase font-bold">Цена</span>
                                <span className="font-bold text-slate-700">{item.price} ₽</span>
                             </div>
                             <div className="text-right">
                                <span className="block text-[9px] text-slate-400 uppercase font-bold">Прибыль</span>
                                <span className={`font-black ${item.unit_economy.profit > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                    {item.unit_economy.profit} ₽
                                </span>
                             </div>
                        </div>
                        <div className="mt-2 flex gap-2">
                             <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${item.unit_economy.roi > 30 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                                 ROI: {item.unit_economy.roi}%
                             </span>
                             <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-500">
                                 Маржа: {item.unit_economy.margin}%
                             </span>
                        </div>
                    </div>
                ))
            )}
        </div>
    );
}

const MonitorPage = () => {
  const [list, setList] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyData, setHistoryData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const fetchList = async () => {
      try {
        const res = await fetch(`${API_URL}/api/monitor/list`, {
            headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
        });
        if (res.ok) setList(await res.json());
      } catch(e) { console.error(e); } finally { setLoading(false); }
  };

  useEffect(() => { fetchList(); }, []);

  const handleDelete = async (e, sku) => {
    e.stopPropagation();
    if(!confirm("Удалить товар из списка?")) return;
    await fetch(`${API_URL}/api/monitor/delete/${sku}`, { 
        method: 'DELETE',
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
    });
    fetchList();
  };

  const loadHistory = async (sku) => {
    setHistoryData(null);
    try {
        const res = await fetch(`${API_URL}/api/monitor/history/${sku}`, {
            headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
        });
        if(res.ok) setHistoryData(await res.json());
    } catch(e) { console.error(e); }
  };

  const downloadReport = async (sku) => {
      setDownloading(true);
      try {
          const token = window.Telegram?.WebApp?.initData || "";
          const response = await fetch(`${API_URL}/api/report/pdf/${sku}`, {
              headers: { 'X-TG-Data': token }
          });

          if (response.status === 403) {
              alert("Эта функция доступна только в тарифе PRO или Business");
              setDownloading(false);
              return;
          }

          if (!response.ok) throw new Error("Ошибка загрузки");

          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `report_${sku}.pdf`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.URL.revokeObjectURL(url);
      } catch (e) {
          alert("Не удалось скачать отчет");
      } finally {
          setDownloading(false);
      }
  };

  return (
    <div className="p-4 space-y-4 pb-32 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex justify-between items-center px-2">
        <div>
             <h2 className="text-xl font-bold text-slate-800">Конкуренты</h2>
             <p className="text-xs text-slate-400">Мониторинг цен (Внешний)</p>
        </div>
        <div className="flex gap-2">
            <button onClick={() => setHistoryOpen(true)} className="p-2 bg-indigo-50 text-indigo-600 rounded-full shadow-sm active:scale-95"><Clock size={18}/></button>
            <button onClick={fetchList} className="p-2 bg-white rounded-full shadow-sm text-slate-400 active:rotate-180 transition-all"><RefreshCw size={18}/></button>
        </div>
      </div>
      <HistoryModule type="price" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />
      
      {historyData && (
        <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white w-full max-w-lg rounded-[32px] p-6 shadow-2xl relative">
                <button onClick={() => setHistoryData(null)} className="absolute top-4 right-4 p-2 bg-slate-100 rounded-full text-slate-500"><X size={20} /></button>
                <div className="mb-6">
                    <span className="text-[10px] font-black uppercase text-indigo-500 bg-indigo-50 px-2 py-1 rounded-lg">{historyData.sku}</span>
                    <h3 className="font-bold text-xl leading-tight mt-2 line-clamp-2">{historyData.name}</h3>
                </div>
                
                <div className="flex gap-2 mb-4">
                    <button 
                        onClick={() => downloadReport(historyData.sku)} 
                        disabled={downloading}
                        className="flex-1 bg-slate-900 text-white py-3 rounded-xl text-xs font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-70"
                    >
                        {downloading ? <Loader2 size={16} className="animate-spin" /> : <><FileDown size={16} /> Скачать PDF</>}
                    </button>
                </div>

                <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={historyData.history}>
                        <defs>
                        <linearGradient id="colorWallet" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#4f46e5" stopOpacity={0}/>
                        </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                        <XAxis dataKey="date" tick={{fontSize: 10}} tickLine={false} axisLine={false} />
                        <YAxis hide domain={['auto', 'auto']} />
                        <Tooltip 
                            contentStyle={{borderRadius: '16px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)'}} 
                            itemStyle={{color: '#4f46e5', fontWeight: 800}}
                        />
                        <Area type="monotone" dataKey="wallet" stroke="#4f46e5" strokeWidth={3} fill="url(#colorWallet)" />
                    </AreaChart>
                    </ResponsiveContainer>
                </div>
                <p className="text-center text-xs text-slate-400 mt-4">Динамика цены WB Кошелек</p>
            </div>
        </div>
      )}

      <div className="space-y-3">
        {loading ? (
            <div className="flex justify-center p-10"><Loader2 className="animate-spin text-indigo-600"/></div>
        ) : list.length === 0 ? (
          <div className="text-center p-10 text-slate-400 bg-white rounded-3xl border border-dashed border-slate-200">
              Список пуст. Добавьте товары через сканер.
          </div>
        ) : (
          list.map((item) => (
            <div key={item.id} onClick={() => loadHistory(item.sku)} className="bg-white p-4 rounded-2xl flex items-center gap-4 border border-slate-100 shadow-sm relative group active:scale-[0.98] transition-transform cursor-pointer">
              <div className="bg-indigo-50 w-12 h-12 flex items-center justify-center rounded-xl text-indigo-600">
                  <BarChart3 size={20} />
              </div>
              <div className="flex-1 min-w-0">
                  <div className="font-bold truncate text-sm">{item.name || `SKU ${item.sku}`}</div>
                  <div className="text-[10px] text-slate-400 font-black uppercase tracking-wider">{item.brand || 'WB'}</div>
              </div>
              <div className="text-right">
                  <div className="font-black text-indigo-600">{item.prices[0]?.wallet_price} ₽</div>
                  <button onClick={(e) => handleDelete(e, item.sku)} className="text-red-300 hover:text-red-500 p-1"><Trash2 size={16}/></button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

const SeoGeneratorPage = () => {
    const [step, setStep] = useState(1);
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [keywords, setKeywords] = useState([]);
    const [newKeyword, setNewKeyword] = useState('');
    const [tone, setTone] = useState('Продающий');
    const [titleLen, setTitleLen] = useState(100);
    const [descLen, setDescLen] = useState(1000);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [historyOpen, setHistoryOpen] = useState(false);

    const toneOptions = ["Продающий", "Информативный", "Дерзкий", "Формальный"];

    const fetchKeywords = async () => {
        if (!sku) return;
        setLoading(true); setError('');
        try {
            const res = await fetch(`${API_URL}/api/seo/parse/${sku}`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } });
            const data = await res.json();
            if (res.status !== 200) throw new Error(data.detail || data.message);
            setKeywords(data.keywords || []); setStep(2);
        } catch (e) { setError(e.message); } finally { setLoading(false); }
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

    const copyKeywords = () => {
        const text = keywords.join(', ');
        navigator.clipboard.writeText(text);
        alert("Ключевые слова скопированы!");
    };

    const generateContent = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/seo/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }, body: JSON.stringify({ sku: Number(sku), keywords, tone, title_len: titleLen, desc_len: descLen }) });
            const data = await res.json();
            const taskId = data.task_id;
            let attempts = 0;
            while(attempts < 60) {
                await new Promise(r => setTimeout(r, 3000));
                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`);
                const sData = await sRes.json();
                if (sData.status === 'SUCCESS') { setResult(sData.data.generated_content); setStep(3); break; }
                if (sData.status === 'FAILURE') throw new Error(sData.error);
                attempts++;
            }
        } catch (e) { setError(e.message); } finally { setLoading(false); }
    };

    const CopyButton = ({ text }) => (
        <button onClick={() => {navigator.clipboard.writeText(text); alert("Скопировано!");}} className="p-2 text-slate-400 hover:text-indigo-600 transition-colors">
            <Copy size={18} />
        </button>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
                <div className="bg-gradient-to-r from-orange-500 to-pink-500 p-6 rounded-3xl text-white shadow-xl shadow-orange-200 flex-1 mr-4">
                    <h1 className="text-2xl font-black flex items-center gap-2"><Wand2 className="text-yellow-200" /> SEO Gen</h1>
                    <p className="text-sm opacity-90 mt-2">Генератор описаний</p>
                </div>
                <button onClick={() => setHistoryOpen(true)} className="bg-white p-4 rounded-3xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors h-full"><Clock size={24}/></button>
            </div>
            
            <HistoryModule type="seo" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

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

            {step === 2 && (
                <div className="space-y-4 animate-in fade-in">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-4">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="font-bold text-lg">Шаг 2. Настройки</h3>
                            <button onClick={copyKeywords} className="text-xs font-bold text-indigo-600 bg-indigo-50 px-3 py-1 rounded-lg active:scale-95">
                                Копировать всё
                            </button>
                        </div>
                        
                        <div className="flex flex-wrap gap-2 mb-4">
                            {keywords.map((k, i) => (
                                <div key={i} className="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-xl text-sm font-medium flex items-center gap-2">
                                    {k}
                                    <button onClick={() => removeKeyword(k)} className="text-slate-400 hover:text-red-500"><X size={14} /></button>
                                </div>
                            ))}
                        </div>

                        <div className="flex gap-2 mb-6">
                            <input 
                                value={newKeyword}
                                onChange={e => setNewKeyword(e.target.value)}
                                placeholder="Добавить свой ключ..."
                                className="flex-1 bg-slate-50 rounded-xl px-4 py-2 text-sm outline-none"
                            />
                            <button onClick={addKeyword} className="bg-slate-900 text-white px-4 rounded-xl font-bold text-xl">+</button>
                        </div>
                        
                        <div>
                            <label className="text-xs font-bold text-slate-400 uppercase">Длина заголовка: {titleLen}</label>
                            <input type="range" min="40" max="150" value={titleLen} onChange={e=>setTitleLen(Number(e.target.value))} className="w-full accent-indigo-600"/>
                        </div>
                        <div>
                            <label className="text-xs font-bold text-slate-400 uppercase">Длина описания: {descLen}</label>
                            <input type="range" min="500" max="3000" step="100" value={descLen} onChange={e=>setDescLen(Number(e.target.value))} className="w-full accent-indigo-600"/>
                        </div>

                        <h3 className="font-bold text-lg mb-3">Настроение текста</h3>
                        <div className="grid grid-cols-2 gap-2 mb-6">
                            {toneOptions.map(t => (
                                <button 
                                    key={t}
                                    onClick={() => setTone(t)}
                                    className={`p-3 rounded-xl text-sm font-bold border transition-all ${tone === t ? 'border-orange-500 bg-orange-50 text-orange-600' : 'border-slate-100 bg-white text-slate-500'}`}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>

                        {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

                        <div className="flex gap-3">
                            <button onClick={() => setStep(1)} className="flex-1 bg-slate-100 text-slate-600 p-4 rounded-xl font-bold">Назад</button>
                            <button onClick={generateContent} disabled={loading} className="flex-[2] bg-gradient-to-r from-orange-500 to-pink-500 text-white p-4 rounded-xl font-bold shadow-lg shadow-orange-200 active:scale-95 transition-all flex justify-center gap-2">
                                {loading ? <Loader2 className="animate-spin" /> : <><Sparkles size={18} /> Генерировать</>}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {step === 3 && result && (
                <div className="space-y-4 animate-in fade-in">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
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

                    <button onClick={() => setStep(1)} className="w-full bg-slate-900 text-white p-4 rounded-xl font-bold">Новый поиск</button>
                </div>
            )}
        </div>
    );
};

const ScannerPage = ({ onNavigate }) => {
  const [sku, setSku] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');

  const handleScan = async () => {
    if (!sku) return;
    setLoading(true);
    setStatus('Запуск задачи...');

    try {
      const res = await fetch(`${API_URL}/api/monitor/add/${sku}`, { 
        method: 'POST',
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
      });
      
      if (res.status === 403) {
          alert("Лимит тарифа исчерпан! Обновите подписку.");
          setLoading(false);
          return;
      }
      
      const data = await res.json();
      const taskId = data.task_id;

      let attempts = 0;
      while (attempts < 60) {
        await new Promise(r => setTimeout(r, 2000));
        
        const statusRes = await fetch(`${API_URL}/api/monitor/status/${taskId}`);
        const statusData = await statusRes.json();
        
        if (statusData.info && statusData.info !== status) {
            setStatus(statusData.info);
        }

        if (statusData.status === 'SUCCESS') {
           onNavigate('monitor');
           return;
        }
        if (statusData.status === 'FAILURE') throw new Error(statusData.error);
        attempts++;
      }
      throw new Error("Таймаут ожидания");
    } catch (e) {
      alert(`Ошибка: ${e.message}`);
      setLoading(false);
    }
  };

  return (
    <div className="p-4 flex flex-col h-[80vh] justify-center animate-in zoom-in-95 duration-300">
      <div className="bg-white p-8 rounded-[40px] shadow-2xl shadow-indigo-100 border border-slate-100">
        <div className="text-center mb-6">
            <div className="w-16 h-16 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-4">
                <Search size={32} />
            </div>
            <h2 className="text-2xl font-black text-slate-800">Добавить товар</h2>
        </div>

        <div className="relative mb-4">
          <input
            type="number"
            placeholder="Артикул (SKU)"
            className="w-full bg-slate-50 border-none rounded-2xl p-5 pl-4 text-center text-2xl font-black outline-none transition-all placeholder:text-slate-300 text-slate-800"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
          />
        </div>
        <button
          onClick={handleScan}
          disabled={loading}
          className="w-full bg-black text-white p-5 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 active:scale-95 transition-all shadow-xl disabled:opacity-70 min-h-[64px]"
        >
          {loading ? (
             <span className="flex items-center gap-2 animate-in fade-in">
                 <Loader2 className="animate-spin" /> 
                 <span className="min-w-[100px] text-left">{status}</span>
             </span>
          ) : 'Начать отслеживание'}
        </button>
      </div>
    </div>
  );
};

const AIAnalysisPage = () => {
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');
    const [result, setResult] = useState(null);
    const [historyOpen, setHistoryOpen] = useState(false);

    const runAnalysis = async () => {
        if(!sku) return;
        setLoading(true);
        setResult(null);
        try {
            const res = await fetch(`${API_URL}/api/ai/analyze/${sku}`, { 
                method: 'POST',
                headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
            });
            const data = await res.json();
            const taskId = data.task_id;
            
            let attempts = 0;
            while(attempts < 60) {
                setStatus('Анализ отзывов...');
                await new Promise(r => setTimeout(r, 4000));
                const sRes = await fetch(`${API_URL}/api/ai/result/${taskId}`);
                const sData = await sRes.json();
                
                if (sData.status === 'SUCCESS') {
                    setResult(sData.data);
                    break;
                }
                if (sData.status === 'FAILURE') throw new Error(sData.error || "Ошибка ИИ");
                if (sData.info) setStatus(sData.info);
                attempts++;
            }
        } catch(e) {
            alert(e.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
                <div className="bg-gradient-to-br from-violet-600 to-fuchsia-600 p-6 rounded-3xl text-white shadow-xl shadow-fuchsia-200 flex-1 mr-4">
                    <h1 className="text-2xl font-black flex items-center gap-2">
                        <Sparkles className="text-yellow-300" /> AI Стратег
                    </h1>
                </div>
                <button onClick={() => setHistoryOpen(true)} className="bg-white p-4 rounded-3xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors h-full"><Clock size={24}/></button>
            </div>
            
            <HistoryModule type="ai" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

            <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-100">
                <input type="number" value={sku} onChange={e => setSku(e.target.value)} placeholder="Артикул" className="w-full p-4 bg-slate-50 rounded-xl font-bold mb-3 outline-none" />
                <button onClick={runAnalysis} disabled={loading} className="w-full bg-violet-600 text-white p-4 rounded-xl font-bold shadow-lg">{loading ? <Loader2 className="animate-spin mx-auto"/> : 'Анализировать'}</button>
            </div>

            {result && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8">
                    <div className="flex gap-4 items-center bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                        {result.image && <img src={result.image} className="w-16 h-20 object-cover rounded-lg bg-slate-100" alt="product" />}
                        <div>
                            <div className="flex items-center gap-1 text-amber-500 font-black mb-1">
                                <Star size={16} fill="currentColor" /> {result.rating}
                            </div>
                            <p className="text-xs text-slate-400 font-bold uppercase tracking-wider">Проанализировано</p>
                            <p className="font-bold">{result.reviews_count} отзывов</p>
                        </div>
                    </div>

                    <div className="bg-red-50 p-6 rounded-3xl border border-red-100">
                        <h3 className="text-red-600 font-black text-lg flex items-center gap-2 mb-4">
                            <ThumbsDown size={20} /> ТОП Жалоб
                        </h3>
                        <ul className="space-y-3">
                            {result.ai_analysis.flaws?.map((f, i) => (
                                <li key={i} className="bg-white p-3 rounded-xl text-sm font-medium text-slate-700 shadow-sm">
                                    ⛔ {f}
                                </li>
                            ))}
                        </ul>
                    </div>

                    <div className="bg-indigo-50 p-6 rounded-3xl border border-indigo-100">
                        <h3 className="text-indigo-600 font-black text-lg flex items-center gap-2 mb-4">
                            <Crown size={20} /> Стратегия победы
                        </h3>
                        <ul className="space-y-3">
                            {result.ai_analysis.strategy?.map((s, i) => (
                                <li key={i} className="bg-white p-4 rounded-xl text-sm font-medium text-slate-700 shadow-sm border-l-4 border-indigo-500">
                                    {s}
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}
        </div>
    );
};

const ProfilePage = ({ onNavigate }) => {
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);
    const [wbToken, setWbToken] = useState('');
    const [tokenLoading, setTokenLoading] = useState(false);

    useEffect(() => {
        const tgData = window.Telegram?.WebApp?.initData || "";
        fetch(`${API_URL}/api/user/tariffs`, { headers: {'X-TG-Data': tgData} }).then(r=>r.json()).then(setTariffs);
        fetch(`${API_URL}/api/user/me`, { headers: {'X-TG-Data': tgData} }).then(r=>r.json()).then(data => {
            setUser(data);
            if (data.has_wb_token) {
                setWbToken(data.wb_token_preview);
            }
        });
    }, []);

    const payStars = async (plan) => {
        if (!plan.stars) return;
        try {
            const res = await fetch(`${API_URL}/api/payment/stars_link`, { 
                method: 'POST', 
                headers: {'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || ""},
                body: JSON.stringify({plan_id: plan.id, amount: plan.stars})
            });
            const d = await res.json();
            if (d.invoice_link) {
                 window.Telegram?.WebApp?.openInvoice(d.invoice_link, (status) => {
                     if (status === 'paid') {
                         alert("Оплата прошла успешно!");
                         window.location.reload();
                     }
                 });
            } else {
                alert("Ошибка создания ссылки");
            }
        } catch (e) {
            alert(e.message);
        }
    };

    const saveToken = async () => {
        if (!wbToken || wbToken.includes("*****")) return;
        setTokenLoading(true);
        try {
             const res = await fetch(`${API_URL}/api/user/token`, { 
                method: 'POST', 
                headers: {'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || ""},
                body: JSON.stringify({token: wbToken})
            });
            const data = await res.json();
            if (res.status === 200) {
                alert("Токен успешно сохранен!");
                const uRes = await fetch(`${API_URL}/api/user/me`, { headers: {'X-TG-Data': window.Telegram?.WebApp?.initData || ""} });
                setUser(await uRes.json());
            } else {
                throw new Error(data.detail || "Ошибка");
            }
        } catch (e) {
            alert(e.message);
        } finally {
            setTokenLoading(false);
        }
    };

    const deleteToken = async () => {
        if (!confirm("Удалить токен?")) return;
        setTokenLoading(true);
        try {
             await fetch(`${API_URL}/api/user/token`, { 
                method: 'DELETE', 
                headers: {'X-TG-Data': window.Telegram?.WebApp?.initData || ""}
            });
            setWbToken('');
            setUser({...user, has_wb_token: false});
        } finally {
            setTokenLoading(false);
        }
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                    <User size={32} />
                </div>
                <div>
                    <h2 className="text-xl font-bold">{user?.name || 'Гость'}</h2>
                    <p className="text-sm text-slate-400">@{user?.username}</p>
                    <div className="mt-2 inline-flex items-center gap-1 bg-black text-white px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                        {user?.plan || 'Free'} Plan
                    </div>
                </div>
            </div>

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                <div className="flex items-center gap-2 mb-4">
                    <Key className="text-indigo-600" size={20} />
                    <h2 className="font-bold text-lg">API Ключ WB</h2>
                </div>
                <div className="relative">
                    <input 
                        type="text" 
                        value={wbToken}
                        onChange={(e) => setWbToken(e.target.value)}
                        placeholder="Введите токен..."
                        className="w-full bg-slate-50 border border-slate-100 rounded-xl p-3 pr-10 text-sm font-medium outline-none focus:ring-2 ring-indigo-100"
                    />
                    {user?.has_wb_token && (
                        <button onClick={deleteToken} className="absolute right-2 top-2 p-1 text-slate-300 hover:text-red-500"><X size={16}/></button>
                    )}
                </div>
                {!user?.has_wb_token && (
                    <button onClick={saveToken} disabled={tokenLoading} className="w-full mt-3 bg-indigo-600 text-white py-3 rounded-xl font-bold text-sm">
                        {tokenLoading ? <Loader2 className="animate-spin" /> : 'Сохранить токен'}
                    </button>
                )}
            </div>

            <h2 className="font-bold text-lg px-2 mt-4">Тарифы (Stars)</h2>
            <div className="space-y-4">
                {tariffs.map(plan => (
                    <TariffCard key={plan.id} plan={plan} onPay={payStars} />
                ))}
            </div>
            
            {user?.is_admin && (
                 <button onClick={() => onNavigate('admin')} className="w-full bg-slate-900 text-white p-4 rounded-2xl shadow-lg flex items-center justify-between active:scale-95 transition-transform mt-4">
                     <div className="flex items-center gap-3">
                         <Shield size={20} className="text-emerald-400"/>
                         <span className="font-bold text-sm">Админ-панель</span>
                     </div>
                     <ArrowUpRight size={18}/>
                 </button>
            )}
        </div>
    );
};

const AdminPage = ({ onBack }) => {
  const [stats, setStats] = useState(null);
  
  useEffect(() => {
    fetch(`${API_URL}/api/admin/stats`, { 
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } 
    }).then(r => r.json()).then(setStats).catch(console.error);
  }, []);

  return (
    <div className="p-4 space-y-4 pb-24 animate-in fade-in slide-in-from-right-4">
      <div className="flex items-center gap-4 mb-4">
          <button onClick={onBack} className="p-2 bg-white rounded-full shadow-sm active:scale-95"><ChevronLeft size={24}/></button>
          <h2 className="text-xl font-bold">Панель администратора</h2>
      </div>
      
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
          <p className="text-xs text-slate-400 font-bold uppercase">Пользователей</p>
          <p className="text-3xl font-black text-indigo-600 mt-1">{stats?.total_users || '-'}</p>
        </div>
        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
          <p className="text-xs text-slate-400 font-bold uppercase">Товаров в базе</p>
          <p className="text-3xl font-black text-green-600 mt-1">{stats?.total_items_monitored || '-'}</p>
        </div>
        <div className="col-span-2 bg-emerald-50 p-4 rounded-2xl border border-emerald-100 flex items-center justify-between">
           <span className="text-emerald-800 font-bold text-sm">Статус сервера</span>
           <span className="bg-emerald-200 text-emerald-800 text-xs font-bold px-2 py-1 rounded-md">{stats?.server_status || 'Checking...'}</span>
        </div>
      </div>
    </div>
  );
};

// --- ОСНОВНОЙ КОМПОНЕНТ ---

export default function App() {
  const [activeTab, setActiveTab] = useState('home');
  const [user, setUser] = useState(null);

  useEffect(() => {
      const tgData = window.Telegram?.WebApp?.initData || "";
      fetch(`${API_URL}/api/user/me`, { headers: {'X-TG-Data': tgData} })
          .then(r => r.json())
          .then(setUser)
          .catch(console.error);
  }, [activeTab]); 

  const renderContent = () => {
      switch(activeTab) {
          case 'home': return <DashboardPage onNavigate={setActiveTab} user={user} />;
          case 'scanner': return <ScannerPage onNavigate={setActiveTab} />;
          case 'monitor': return <MonitorPage />;
          case 'finance': return <FinancePage onNavigate={setActiveTab} />;
          case 'ai': return <AIAnalysisPage />;
          case 'seo': return <SeoGeneratorPage />;
          case 'seo_tracker': return <SeoTrackerPage />; 
          case 'bidder': return <BidderPage />; 
          case 'supply': return <SupplyPage />; 
          case 'profile': return <ProfilePage onNavigate={setActiveTab} />;
          case 'admin': return <AdminPage onBack={() => setActiveTab('profile')} />;
          default: return <DashboardPage onNavigate={setActiveTab} user={user} />;
      }
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 select-none pb-24">
      {renderContent()}
      <TabNav active={activeTab} setTab={setActiveTab} isAdmin={user?.is_admin} />
    </div>
  );
}