import React, { useState, useEffect } from 'react';
import { 
  Search, Wallet, CreditCard, AlertCircle, Loader2, Sparkles, BarChart3, 
  ArrowUpRight, Plus, User, Shield, Brain, Star, ThumbsDown, CheckCircle2, 
  Crown, LayoutGrid, Trash2, RefreshCw, X, History as HistoryIcon, ChevronLeft 
} from 'lucide-react';
import { 
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area, CartesianGrid 
} from 'recharts';

const API_URL = "https://api.ulike-bot.ru"; 

// --- КОМПОНЕНТЫ ---

const TabNav = ({ active, setTab, isAdmin }) => (
  <div className="fixed bottom-0 left-0 right-0 bg-white/95 backdrop-blur-md border-t border-slate-100 px-2 py-3 flex justify-between items-end z-50 pb-8 safe-area-pb shadow-[0_-5px_20px_rgba(0,0,0,0.03)]">
    <button onClick={() => setTab('home')} className={`flex flex-col items-center gap-1 w-1/5 transition-colors ${active === 'home' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <LayoutGrid size={24} strokeWidth={active === 'home' ? 2.5 : 2} />
      <span className="text-[10px] font-bold">Главная</span>
    </button>
    <button onClick={() => setTab('monitor')} className={`flex flex-col items-center gap-1 w-1/5 transition-colors ${active === 'monitor' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <BarChart3 size={24} strokeWidth={active === 'monitor' ? 2.5 : 2} />
      <span className="text-[10px] font-bold">Цены</span>
    </button>
    
    <div className="relative -top-6 w-1/5 flex justify-center">
        <button 
            onClick={() => setTab('scanner')} 
            className="bg-indigo-600 text-white w-14 h-14 rounded-full shadow-xl shadow-indigo-300 active:scale-95 transition-transform border-4 border-white flex items-center justify-center"
        >
            <Plus size={28} strokeWidth={3} />
        </button>
    </div>

    {/* КНОПКА ИСТОРИИ */}
    <button onClick={() => setTab('history')} className={`flex flex-col items-center gap-1 w-1/5 transition-colors ${active === 'history' ? 'text-indigo-600' : 'text-slate-400'}`}>
       <HistoryIcon size={24} strokeWidth={active === 'history' ? 2.5 : 2} />
       <span className="text-[10px] font-bold">История</span>
    </button>
    
    <button onClick={() => setTab('profile')} className={`flex flex-col items-center gap-1 w-1/5 transition-colors ${active === 'profile' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <User size={24} strokeWidth={active === 'profile' ? 2.5 : 2} />
      <span className="text-[10px] font-bold">Профиль</span>
    </button>
  </div>
);

const TariffCard = ({ plan }) => (
  <div className={`p-6 rounded-3xl border-2 relative overflow-hidden transition-all ${plan.is_best ? 'border-indigo-600 bg-indigo-50/50 scale-[1.02] shadow-lg' : 'border-slate-100 bg-white'}`}>
    {plan.is_best && (
      <div className="absolute top-0 right-0 bg-indigo-600 text-white px-3 py-1 rounded-bl-xl text-[10px] font-black uppercase">
        ХИТ
      </div>
    )}
    <h3 className={`text-xl font-black uppercase ${plan.is_best ? 'text-indigo-700' : 'text-slate-800'}`}>{plan.name}</h3>
    <div className="text-3xl font-black mt-2 mb-4 text-slate-900">{plan.price}</div>
    
    <ul className="space-y-3 mb-6">
      {plan.features.map((f, i) => (
        <li key={i} className="flex items-start gap-3 text-sm font-medium text-slate-600">
          <CheckCircle2 size={16} className={`mt-0.5 ${plan.is_best ? 'text-indigo-600' : 'text-slate-400'}`} />
          <span>{f}</span>
        </li>
      ))}
    </ul>
    
    <button className={`w-full py-4 rounded-xl font-bold text-sm shadow-lg active:scale-95 transition-all ${plan.current ? 'bg-slate-200 text-slate-500 cursor-not-allowed' : plan.is_best ? 'bg-indigo-600 text-white shadow-indigo-200' : 'bg-slate-900 text-white'}`}>
      {plan.current ? 'Ваш текущий план' : 'Перейти'}
    </button>
  </div>
);

// --- СТРАНИЦЫ ---

const HomePage = ({ onNavigate }) => (
  <div className="p-4 space-y-6 pb-32 animate-in fade-in duration-500">
    <div className="bg-gradient-to-br from-indigo-600 to-violet-700 rounded-[32px] p-8 text-white shadow-xl shadow-indigo-200 relative overflow-hidden">
      <div className="relative z-10">
        <div className="flex items-center gap-2 mb-2 opacity-80">
            <Sparkles size={16} className="text-amber-300" />
            <span className="text-xs font-bold uppercase tracking-widest">WB Analytics Pro</span>
        </div>
        <h1 className="text-3xl font-black mb-4 leading-tight">Управляйте продажами умно</h1>
        <p className="opacity-90 text-sm mb-6 font-medium max-w-[80%]">Мониторинг цен, анализ конкурентов и стратегии от ИИ в одном приложении.</p>
        <button onClick={() => onNavigate('scanner')} className="bg-white text-indigo-600 px-6 py-3.5 rounded-2xl font-bold text-sm shadow-lg active:scale-95 transition-transform flex items-center gap-2">
          <Plus size={18} />
          Добавить товар
        </button>
      </div>
      <div className="absolute -right-10 -top-10 w-40 h-40 bg-white opacity-10 rounded-full blur-3xl"></div>
      <div className="absolute -left-10 -bottom-10 w-40 h-40 bg-purple-500 opacity-20 rounded-full blur-3xl"></div>
    </div>

    <h2 className="text-lg font-bold px-2 text-slate-800">Инструменты</h2>
    <div className="grid grid-cols-2 gap-4">
      <div onClick={() => onNavigate('monitor')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
        <div className="bg-emerald-100 w-12 h-12 rounded-2xl flex items-center justify-center text-emerald-600">
          <BarChart3 size={24} />
        </div>
        <div>
            <span className="font-bold text-slate-800 block">Мониторинг</span>
            <span className="text-xs text-slate-400">История цен</span>
        </div>
      </div>
      <div onClick={() => onNavigate('ai')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
        <div className="bg-violet-100 w-12 h-12 rounded-2xl flex items-center justify-center text-violet-600">
          <Brain size={24} />
        </div>
        <div>
            <span className="font-bold text-slate-800 block">AI Аналитик</span>
            <span className="text-xs text-slate-400">Анализ отзывов</span>
        </div>
      </div>
    </div>
  </div>
);

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
        await new Promise(r => setTimeout(r, 3000));
        setStatus('Парсинг WB...');
        
        const statusRes = await fetch(`${API_URL}/api/monitor/status/${taskId}`);
        const statusData = await statusRes.json();
        
        if (statusData.info) setStatus(statusData.info);

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
          className="w-full bg-black text-white p-5 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 active:scale-95 transition-all shadow-xl disabled:opacity-70"
        >
          {loading ? <><Loader2 className="animate-spin" /> {status}</> : 'Начать отслеживание'}
        </button>
      </div>
    </div>
  );
};

const MonitorPage = () => {
  const [list, setList] = useState([]);
  const [historyData, setHistoryData] = useState(null);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="p-4 space-y-4 pb-32 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex justify-between items-center px-2">
        <h2 className="text-xl font-bold text-slate-800">Мой список</h2>
        <button onClick={fetchList} className="p-2 bg-white rounded-full shadow-sm text-slate-400 active:rotate-180 transition-all">
            <RefreshCw size={18}/>
        </button>
      </div>
      
      {historyData && (
        <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-white w-full max-w-lg rounded-[32px] p-6 shadow-2xl relative">
                <button onClick={() => setHistoryData(null)} className="absolute top-4 right-4 p-2 bg-slate-100 rounded-full text-slate-500">
                    <X size={20} />
                </button>
                <div className="mb-6">
                    <span className="text-[10px] font-black uppercase text-indigo-500 bg-indigo-50 px-2 py-1 rounded-lg">{historyData.sku}</span>
                    <h3 className="font-bold text-xl leading-tight mt-2 line-clamp-2">{historyData.name}</h3>
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
              Список пуст. Добавьте товары.
          </div>
        ) : (
          list.map((item) => (
            <div key={item.id} className="bg-white p-4 rounded-2xl flex items-center gap-4 border border-slate-100 shadow-sm relative group active:scale-[0.98] transition-transform">
              <div onClick={() => loadHistory(item.sku)} className="flex-1 flex items-center gap-4 cursor-pointer">
                <div className="bg-indigo-50 w-12 h-12 flex items-center justify-center rounded-xl text-indigo-600">
                  <BarChart3 size={20} />
                </div>
                <div className="min-w-0">
                  <div className="font-bold truncate text-sm">{item.name || `SKU ${item.sku}`}</div>
                  <div className="text-[10px] text-slate-400 font-black uppercase tracking-wider">{item.brand || 'WB'}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                  <button onClick={() => loadHistory(item.sku)} className="p-2 bg-slate-50 text-indigo-600 rounded-xl">
                    <ArrowUpRight size={18} />
                  </button>
                  <button onClick={(e) => handleDelete(e, item.sku)} className="p-2 bg-red-50 text-red-500 rounded-xl">
                    <Trash2 size={18} />
                  </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

const AIAnalysisPage = () => {
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');
    const [result, setResult] = useState(null);

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
            <div className="bg-gradient-to-br from-violet-600 to-fuchsia-600 p-6 rounded-3xl text-white shadow-xl shadow-fuchsia-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <Sparkles className="text-yellow-300" /> AI Стратег
                </h1>
                
                <div className="mt-6 relative">
                    <input 
                        type="number" 
                        value={sku}
                        onChange={e => setSku(e.target.value)}
                        placeholder="Артикул конкурента" 
                        className="w-full p-4 pl-12 rounded-xl text-slate-900 font-bold placeholder:font-medium placeholder:text-slate-400 focus:ring-4 ring-white/30 outline-none transition-all"
                    />
                    <Search className="absolute left-4 top-4.5 text-slate-400" />
                </div>
                
                <button 
                    onClick={runAnalysis} 
                    disabled={loading}
                    className="w-full bg-white text-violet-700 mt-3 py-4 rounded-xl font-black shadow-lg active:scale-95 transition-all disabled:opacity-70 flex justify-center gap-2"
                >
                    {loading ? <><Loader2 className="animate-spin"/> {status}</> : 'Запустить анализ'}
                </button>
            </div>

            {result && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8">
                    <div className="flex gap-4 items-center bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                        {result.image && <img src={result.image} className="w-16 h-20 object-cover rounded-lg bg-slate-100" />}
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

const HistoryPage = () => {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);

    const loadHistory = () => {
        fetch(`${API_URL}/api/user/history`, { headers: {'X-TG-Data': window.Telegram?.WebApp?.initData || ""} })
            .then(r => r.json())
            .then(data => { setHistory(data); setLoading(false); })
            .catch(e => { console.error(e); setLoading(false); });
    };

    const clearHistory = async () => {
        if(!confirm("Очистить историю?")) return;
        await fetch(`${API_URL}/api/user/history`, { 
            method: 'DELETE', 
            headers: {'X-TG-Data': window.Telegram?.WebApp?.initData || ""} 
        });
        loadHistory();
    };

    useEffect(() => { loadHistory(); }, []);

    return (
        <div className="p-4 space-y-4 pb-24 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center px-2">
                <h2 className="text-xl font-bold text-slate-800">История запросов</h2>
                {history.length > 0 && (
                    <button onClick={clearHistory} className="text-red-500 text-xs font-bold uppercase active:scale-95 transition-transform">Очистить</button>
                )}
            </div>
            
            <div className="space-y-3">
                {loading ? <div className="text-center p-10"><Loader2 className="animate-spin text-slate-400 mx-auto"/></div> : 
                 history.length === 0 ? (
                    <div className="text-center p-12 bg-white rounded-3xl border border-dashed border-slate-200">
                        <p className="text-slate-400 font-bold text-sm">История пуста</p>
                    </div>
                ) : (
                    history.map((h) => (
                        <div key={h.id} className="bg-white p-4 rounded-2xl flex items-center gap-4 shadow-sm border border-slate-100">
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${h.request_type === 'ai' ? 'bg-violet-100 text-violet-600' : 'bg-emerald-100 text-emerald-600'}`}>
                                {h.request_type === 'ai' ? <Brain size={18}/> : <Search size={18}/>}
                            </div>
                            <div>
                                <div className="font-bold text-sm">SKU {h.sku}</div>
                                <div className="text-xs text-slate-500 truncate max-w-[200px]">{h.title}</div>
                                <div className="text-[10px] text-slate-300 mt-1">{new Date(h.created_at).toLocaleString('ru-RU')}</div>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};

const ProfilePage = ({ onNavigate }) => {
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);

    useEffect(() => {
        const tgData = window.Telegram?.WebApp?.initData || "";
        fetch(`${API_URL}/api/user/tariffs`, { headers: {'X-TG-Data': tgData} }).then(r=>r.json()).then(setTariffs);
        fetch(`${API_URL}/api/user/me`, { headers: {'X-TG-Data': tgData} }).then(r=>r.json()).then(setUser);
    }, []);

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
            
            <div className="grid grid-cols-2 gap-3">
                 <button onClick={() => onNavigate('history')} className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm flex flex-col items-center gap-2 active:scale-95 transition-transform">
                     <div className="bg-indigo-50 p-2 rounded-xl text-indigo-600"><HistoryIcon size={20}/></div>
                     <span className="text-xs font-bold text-slate-700">История</span>
                 </button>
                 {/* Кнопка Админка РЕАГИРУЕТ на нажатие */}
                 {user?.is_admin && (
                     <button onClick={() => onNavigate('admin')} className="bg-slate-900 p-4 rounded-2xl shadow-lg flex flex-col items-center gap-2 active:scale-95 transition-transform">
                         <div className="bg-white/20 p-2 rounded-xl text-white"><Shield size={20}/></div>
                         <span className="text-xs font-bold text-white">Админка</span>
                     </button>
                 )}
            </div>

            <h2 className="font-bold text-lg px-2 mt-4">Ваш тариф</h2>
            <div className="space-y-4">
                {tariffs.map(plan => (
                    <TariffCard key={plan.id} plan={plan} />
                ))}
            </div>
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
      </div>
    </div>
  );
};

export default function App() {
  const [activeTab, setActiveTab] = useState('home');
  const [user, setUser] = useState(null);

  useEffect(() => {
      if (window.Telegram?.WebApp) {
        const tgData = window.Telegram.WebApp.initData;
        fetch(`${API_URL}/api/user/me`, { headers: {'X-TG-Data': tgData} })
          .then(r => r.json())
          .then(setUser)
          .catch(console.error);
      }
  }, []);

  const renderContent = () => {
      if (activeTab === 'home') return <HomePage onNavigate={setActiveTab} />;
      if (activeTab === 'scanner') return <ScannerPage onNavigate={setActiveTab} />;
      if (activeTab === 'monitor') return <MonitorPage />;
      if (activeTab === 'ai') return <AIAnalysisPage />;
      if (activeTab === 'profile') return <ProfilePage onNavigate={setActiveTab} />;
      if (activeTab === 'history') return <HistoryPage />;
      if (activeTab === 'admin') return <AdminPage onBack={() => setActiveTab('profile')} />;
      return null;
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 select-none">
      {renderContent()}
      <TabNav active={activeTab} setTab={setActiveTab} isAdmin={user?.is_admin} />
    </div>
  );
}