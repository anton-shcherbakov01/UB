import React, { useState, useEffect } from 'react';
import { Search, Wallet, CreditCard, Loader2, Sparkles, TrendingUp, Plus, BarChart3, ArrowUpRight } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

const API_URL = "https://api.ulike-bot.ru"; // ЗАМЕНИТЕ НА СВОЙ ДОМЕН

export default function App() {
  const [activeTab, setActiveTab] = useState('scanner'); // scanner | monitor
  const [sku, setSku] = useState('');
  const [loading, setLoading] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  
  const [monitorList, setMonitorList] = useState([]);
  const [historyData, setHistoryData] = useState(null);

  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
    }
    fetchMonitorList();
  }, []);

  const fetchMonitorList = async () => {
    try {
      const res = await fetch(`${API_URL}/api/monitor/list`);
      if (res.ok) setMonitorList(await res.json());
    } catch (e) console.error(e);
  };

  const handleScan = async () => {
    if (!sku) return;
    setLoading(true);
    setScanResult(null);
    // Для сканера используем тот же метод добавления, чтобы сразу сохранить историю
    try {
      // Сначала добавляем задачу
      const res = await fetch(`${API_URL}/api/monitor/add/${sku}`, { method: 'POST' });
      // В реальном приложении тут нужен поллинг статуса, для демо просто ждем немного и обновляем список
      setTimeout(() => {
        fetchMonitorList();
        loadHistory(sku); 
        setLoading(false);
        setActiveTab('monitor');
      }, 5000); 
    } catch (e) {
      setLoading(false);
    }
  };

  const loadHistory = async (sku) => {
    const res = await fetch(`${API_URL}/api/monitor/history/${sku}`);
    if (res.ok) setHistoryData(await res.json());
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 pb-20">
      
      {/* Header */}
      <div className="bg-white px-6 pt-6 pb-4 shadow-sm rounded-b-3xl mb-6">
        <h1 className="text-2xl font-black text-indigo-600 flex items-center gap-2">
          <Sparkles className="text-amber-400 fill-amber-400" size={24} /> WB Analytics
        </h1>
        <p className="text-xs text-slate-400 font-bold tracking-widest mt-1">PRO MONITORING TOOL</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 px-4 mb-6">
        <button 
          onClick={() => setActiveTab('scanner')}
          className={`flex-1 py-3 rounded-xl font-bold text-sm transition-all ${activeTab === 'scanner' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200' : 'bg-white text-slate-400'}`}
        >
          Сканер
        </button>
        <button 
          onClick={() => setActiveTab('monitor')}
          className={`flex-1 py-3 rounded-xl font-bold text-sm transition-all ${activeTab === 'monitor' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200' : 'bg-white text-slate-400'}`}
        >
          Мониторинг
        </button>
      </div>

      {activeTab === 'scanner' && (
        <div className="px-4 animate-in fade-in slide-in-from-bottom-4">
          <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
            <label className="text-sm font-bold text-slate-400 ml-1 mb-2 block">ДОБАВИТЬ ТОВАР</label>
            <div className="relative mb-4">
              <input
                type="number"
                placeholder="Артикул WB"
                className="w-full bg-slate-50 border-none rounded-2xl p-4 pl-12 text-lg font-semibold focus:ring-2 focus:ring-indigo-500 outline-none transition-all"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
              />
              <Search className="absolute left-4 top-4.5 text-slate-400" />
            </div>
            <button
              onClick={handleScan}
              disabled={loading}
              className="w-full bg-black text-white p-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 active:scale-95 transition-all shadow-xl disabled:opacity-70"
            >
              {loading ? <Loader2 className="animate-spin" /> : <><Plus size={20} /> Отследить</>}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'monitor' && (
        <div className="px-4 space-y-4 animate-in fade-in slide-in-from-bottom-4">
          
          {historyData && (
            <div className="bg-white p-5 rounded-3xl shadow-lg border border-indigo-100 relative overflow-hidden">
               <div className="absolute top-0 right-0 bg-indigo-600 text-white px-3 py-1 rounded-bl-xl text-[10px] font-bold">LIVE</div>
               <h3 className="font-bold text-lg leading-tight mb-1 pr-10">{historyData.name}</h3>
               <p className="text-xs text-slate-400 font-bold mb-6">SKU: {historyData.sku}</p>
               
               <div className="h-48 -mx-2">
                 <ResponsiveContainer width="100%" height="100%">
                   <AreaChart data={historyData.history}>
                     <defs>
                       <linearGradient id="colorPv" x1="0" y1="0" x2="0" y2="1">
                         <stop offset="5%" stopColor="#8884d8" stopOpacity={0.3}/>
                         <stop offset="95%" stopColor="#8884d8" stopOpacity={0}/>
                       </linearGradient>
                     </defs>
                     <Tooltip 
                        contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)'}}
                        itemStyle={{color: '#4f46e5', fontWeight: 'bold'}}
                     />
                     <Area type="monotone" dataKey="wallet" stroke="#4f46e5" strokeWidth={3} fillOpacity={1} fill="url(#colorPv)" />
                   </AreaChart>
                 </ResponsiveContainer>
               </div>
            </div>
          )}

          <div className="space-y-3">
            {monitorList.map((item) => (
              <div key={item.id} onClick={() => loadHistory(item.sku)} className="bg-white p-4 rounded-2xl flex items-center gap-4 active:scale-95 transition-transform border border-slate-100">
                <div className="bg-slate-100 p-3 rounded-xl">
                  <BarChart3 className="text-slate-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold truncate">{item.name || `Товар ${item.sku}`}</div>
                  <div className="text-xs text-slate-400 font-medium">{item.brand || 'WB'}</div>
                </div>
                <ArrowUpRight className="text-slate-300" />
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}