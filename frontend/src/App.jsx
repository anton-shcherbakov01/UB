import React, { useState, useEffect } from 'react';
import { 
  Search, Wallet, BarChart3, ArrowUpRight, Plus, User, 
  Settings, Shield, Zap, TrendingUp, LayoutGrid, Trash2, Loader2 
} from 'lucide-react';
import { LineChart, Line, XAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

const API_URL = "https://api.ulike-bot.ru"; 

// --- КОМПОНЕНТЫ СТРАНИЦ ---

const TabNav = ({ active, setTab, isAdmin }) => (
  <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-100 px-6 py-3 flex justify-between items-center z-50 safe-area-pb">
    <button onClick={() => setTab('home')} className={`flex flex-col items-center gap-1 ${active === 'home' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <LayoutGrid size={24} />
      <span className="text-[10px] font-bold">Главная</span>
    </button>
    <button onClick={() => setTab('monitor')} className={`flex flex-col items-center gap-1 ${active === 'monitor' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <BarChart3 size={24} />
      <span className="text-[10px] font-bold">Мониторинг</span>
    </button>
    {isAdmin && (
      <button onClick={() => setTab('admin')} className={`flex flex-col items-center gap-1 ${active === 'admin' ? 'text-indigo-600' : 'text-slate-400'}`}>
        <Shield size={24} />
        <span className="text-[10px] font-bold">Админ</span>
      </button>
    )}
    <button onClick={() => setTab('profile')} className={`flex flex-col items-center gap-1 ${active === 'profile' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <User size={24} />
      <span className="text-[10px] font-bold">Профиль</span>
    </button>
  </div>
);

const HomePage = ({ onScan }) => (
  <div className="p-4 space-y-6 pb-24">
    <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-3xl p-6 text-white shadow-xl shadow-indigo-200">
      <h1 className="text-2xl font-black mb-2">WB Analytics Pro</h1>
      <p className="opacity-90 text-sm mb-4">Управляйте ценами и следите за конкурентами в реальном времени.</p>
      <button onClick={() => onScan()} className="bg-white text-indigo-600 px-6 py-3 rounded-xl font-bold text-sm shadow-md active:scale-95 transition-transform">
        Начать сканирование
      </button>
    </div>

    <div className="grid grid-cols-2 gap-3">
      <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm flex flex-col gap-2">
        <div className="bg-green-100 w-10 h-10 rounded-full flex items-center justify-center text-green-600">
          <Zap size={20} />
        </div>
        <span className="font-bold text-slate-800">Быстрый чек</span>
        <span className="text-xs text-slate-400">Мгновенная проверка цены</span>
      </div>
      <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm flex flex-col gap-2">
        <div className="bg-blue-100 w-10 h-10 rounded-full flex items-center justify-center text-blue-600">
          <TrendingUp size={20} />
        </div>
        <span className="font-bold text-slate-800">Тренды</span>
        <span className="text-xs text-slate-400">История изменений</span>
      </div>
    </div>
  </div>
);

const ScannerPage = ({ onAdd }) => {
  const [sku, setSku] = useState('');
  const [loading, setLoading] = useState(false);

  const handleScan = async () => {
    if (!sku) return;
    setLoading(true);
    await onAdd(sku);
    setLoading(false);
    setSku('');
  };

  return (
    <div className="p-4 flex flex-col h-[80vh] justify-center">
      <div className="bg-white p-6 rounded-3xl shadow-lg border border-slate-100">
        <label className="text-xs font-black text-slate-400 ml-1 mb-3 block uppercase tracking-widest">Новый товар</label>
        <div className="relative mb-4">
          <input
            type="number"
            placeholder="Введите артикул"
            className="w-full bg-slate-50 border-none rounded-2xl p-5 pl-12 text-xl font-bold focus:ring-2 focus:ring-indigo-500 outline-none transition-all"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
          />
          <Search className="absolute left-4 top-5 text-slate-400" />
        </div>
        <button
          onClick={handleScan}
          disabled={loading}
          className="w-full bg-black text-white p-5 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 active:scale-95 transition-all shadow-xl disabled:opacity-70"
        >
          {loading ? <Loader2 className="animate-spin" /> : <><Plus size={20} /> Добавить в базу</>}
        </button>
      </div>
    </div>
  );
};

const MonitorPage = ({ list, onDelete, onLoadHistory, historyData }) => (
  <div className="p-4 space-y-4 pb-24">
    <h2 className="text-xl font-bold text-slate-800 px-2">Мой список</h2>
    
    {historyData && (
      <div className="bg-white p-5 rounded-3xl shadow-lg border border-indigo-100 relative overflow-hidden animate-in fade-in slide-in-from-top-4">
          <div className="absolute top-0 right-0 bg-indigo-600 text-white px-3 py-1 rounded-bl-xl text-[10px] font-bold">LIVE</div>
          <h3 className="font-bold text-lg leading-tight mb-1 pr-10">{historyData.name}</h3>
          <div className="h-32 -mx-2 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={historyData.history}>
                <defs>
                  <linearGradient id="colorPv" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#4f46e5" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <Tooltip contentStyle={{borderRadius: '12px', border: 'none'}} />
                <Area type="monotone" dataKey="wallet" stroke="#4f46e5" strokeWidth={3} fill="url(#colorPv)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
      </div>
    )}

    <div className="space-y-3">
      {list.length === 0 ? (
        <div className="text-center p-10 text-slate-400">Список пуст</div>
      ) : (
        list.map((item) => (
          <div key={item.id} className="bg-white p-4 rounded-2xl flex items-center gap-4 border border-slate-100 shadow-sm relative group">
            <div onClick={() => onLoadHistory(item.sku)} className="flex-1 flex items-center gap-4 cursor-pointer">
              <div className="bg-indigo-50 p-3 rounded-xl text-indigo-600">
                <BarChart3 size={20} />
              </div>
              <div className="min-w-0">
                <div className="font-bold truncate text-sm">{item.name || `SKU ${item.sku}`}</div>
                <div className="text-[10px] text-slate-400 font-black uppercase">{item.brand || 'WB'}</div>
              </div>
            </div>
            <button onClick={() => onDelete(item.sku)} className="p-2 text-slate-300 hover:text-red-500 transition-colors">
              <Trash2 size={18} />
            </button>
          </div>
        ))
      )}
    </div>
  </div>
);

const ProfilePage = ({ user }) => (
  <div className="p-4 space-y-6 pb-24">
    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center gap-4">
      <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
        <User size={32} />
      </div>
      <div>
        <h2 className="text-xl font-bold">{user?.name || 'Пользователь'}</h2>
        <p className="text-sm text-slate-400">@{user?.username}</p>
      </div>
    </div>

    <div className="bg-black text-white p-6 rounded-3xl shadow-xl relative overflow-hidden">
      <div className="relative z-10">
        <div className="flex justify-between items-start mb-4">
          <div>
            <p className="text-xs font-bold opacity-70 uppercase tracking-widest">Ваш план</p>
            <h3 className="text-2xl font-black uppercase">{user?.plan || 'Free'}</h3>
          </div>
          {user?.plan === 'free' && <span className="bg-white/20 px-2 py-1 rounded-md text-[10px] font-bold">LITE</span>}
        </div>
        <p className="text-sm opacity-80 mb-6">Доступно {user?.plan === 'free' ? '3' : '50'} товаров для мониторинга</p>
        <button className="w-full bg-white text-black py-3 rounded-xl font-bold text-sm active:scale-95 transition-transform">
          Улучшить до PRO
        </button>
      </div>
      <div className="absolute -bottom-10 -right-10 w-32 h-32 bg-indigo-500 rounded-full blur-3xl opacity-50"></div>
    </div>
  </div>
);

const AdminPage = () => {
  const [stats, setStats] = useState(null);
  
  useEffect(() => {
    fetch(`${API_URL}/api/admin/stats`, { 
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } 
    }).then(r => r.json()).then(setStats).catch(console.error);
  }, []);

  return (
    <div className="p-4 space-y-4 pb-24">
      <h2 className="text-xl font-bold px-2">Панель администратора</h2>
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
          <p className="text-xs text-slate-400 font-bold uppercase">Пользователей</p>
          <p className="text-2xl font-black text-indigo-600">{stats?.total_users || '-'}</p>
        </div>
        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
          <p className="text-xs text-slate-400 font-bold uppercase">Товаров</p>
          <p className="text-2xl font-black text-green-600">{stats?.total_items_monitored || '-'}</p>
        </div>
      </div>
    </div>
  );
};

// --- ОСНОВНОЙ КОМПОНЕНТ ---

export default function App() {
  const [activeTab, setActiveTab] = useState('home');
  const [user, setUser] = useState(null);
  const [monitorList, setMonitorList] = useState([]);
  const [historyData, setHistoryData] = useState(null);

  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
      // Получаем профиль пользователя
      fetch(`${API_URL}/api/user/me`, {
        headers: { 'X-TG-Data': window.Telegram.WebApp.initData }
      })
      .then(r => r.json())
      .then(setUser)
      .catch(e => console.error("Auth error:", e));
    }
  }, []);

  const fetchList = () => {
    fetch(`${API_URL}/api/monitor/list`, {
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
    }).then(r => r.json()).then(setMonitorList);
  };

  useEffect(() => {
    if (activeTab === 'monitor') fetchList();
  }, [activeTab]);

  const handleAdd = async (sku) => {
    try {
      const res = await fetch(`${API_URL}/api/monitor/add/${sku}`, { 
        method: 'POST',
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
      });
      const data = await res.json();
      if (res.status === 403) {
          alert("Лимит тарифа исчерпан! Перейдите в профиль.");
          return;
      }
      // Переходим в мониторинг и ждем
      setActiveTab('monitor');
      // В реале тут нужен поллинг, как в прошлом коде
      setTimeout(fetchList, 5000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleDelete = async (sku) => {
    if(!confirm("Удалить товар?")) return;
    await fetch(`${API_URL}/api/monitor/delete/${sku}`, { 
        method: 'DELETE',
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
    });
    fetchList();
  };

  const handleLoadHistory = async (sku) => {
    const res = await fetch(`${API_URL}/api/monitor/history/${sku}`, {
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
    });
    if (res.ok) setHistoryData(await res.json());
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900">
      {activeTab === 'home' && <HomePage onScan={() => setActiveTab('scanner')} />}
      {activeTab === 'scanner' && <ScannerPage onAdd={handleAdd} />}
      {activeTab === 'monitor' && <MonitorPage list={monitorList} onDelete={handleDelete} onLoadHistory={handleLoadHistory} historyData={historyData} />}
      {activeTab === 'profile' && <ProfilePage user={user} />}
      {activeTab === 'admin' && <AdminPage />}

      <TabNav active={activeTab} setTab={setActiveTab} isAdmin={user?.is_admin} />
    </div>
  );
}