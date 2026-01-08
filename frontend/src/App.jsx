import React, { useState, useEffect } from 'react';
import { Search, Wallet, CreditCard, AlertCircle, Loader2, Sparkles, BarChart3, ArrowUpRight, Plus, RefreshCw } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

const API_URL = "https://api.ulike-bot.ru"; 

export default function App() {
  const [activeTab, setActiveTab] = useState('scanner'); 
  const [sku, setSku] = useState('');
  const [loading, setLoading] = useState(false);
  const [monitorList, setMonitorList] = useState([]);
  const [historyData, setHistoryData] = useState(null);
  const [statusMsg, setStatusMsg] = useState('Начать');

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
    } catch (e) {
      console.error("Ошибка загрузки списка:", e);
    }
  };

  const handleScan = async () => {
    if (!sku) return;
    setLoading(true);
    setHistoryData(null);
    setStatusMsg('В очереди...');

    try {
      // 1. Ставим задачу
      const res = await fetch(`${API_URL}/api/monitor/add/${sku}`, { 
        method: 'POST',
        headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }
      });
      const data = await res.json();
      const taskId = data.task_id;

      // 2. Ждем выполнения (Polling)
      let attempts = 0;
      const maxAttempts = 100; // Ждем до 5 минут (100 * 3 сек)
      
      while (attempts < maxAttempts) {
        await new Promise(r => setTimeout(r, 3000));
        
        const statusRes = await fetch(`${API_URL}/api/monitor/status/${taskId}`);
        const statusData = await statusRes.json();
        
        // Обновляем текст на кнопке (Прозрачность процесса!)
        if (statusData.info && typeof statusData.info === 'string') {
             setStatusMsg(statusData.info);
        } else if (statusData.status === 'PENDING') {
             setStatusMsg('В очереди...');
        }

        if (statusData.status === 'SUCCESS') {
           setStatusMsg('Готово!');
           await fetchMonitorList();
           await loadHistory(sku);
           setLoading(false);
           setActiveTab('monitor');
           return;
        }
        
        if (statusData.status === 'FAILURE') {
           throw new Error(statusData.error || "Ошибка парсинга");
        }
        
        attempts++;
      }
      throw new Error("Сервер долго не отвечает. Проверьте вкладку Мониторинг позже.");

    } catch (e) {
      console.error("Ошибка:", e);
      alert(`⚠️ ${e.message}`);
      setLoading(false);
      setStatusMsg('Найти');
    }
  };

  const loadHistory = async (sku) => {
    try {
      const res = await fetch(`${API_URL}/api/monitor/history/${sku}`);
      if (res.ok) setHistoryData(await res.json());
    } catch (e) {
      console.error("Ошибка истории:", e);
    }
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 pb-20">
      
      {/* Header */}
      <div className="bg-white px-6 pt-6 pb-4 shadow-sm rounded-b-3xl mb-6">
        <h1 className="text-2xl font-black text-indigo-600 flex items-center gap-2">
          <Sparkles className="text-amber-400 fill-amber-400" size={24} /> WB Analytics
        </h1>
        <div className="flex justify-between items-center mt-1">
            <p className="text-[10px] text-slate-400 font-bold tracking-widest">PRO MONITORING TOOL</p>
            <button onClick={fetchMonitorList} className="p-1 bg-slate-50 rounded-full text-slate-400 active:rotate-180 transition-all">
                <RefreshCw size={14}/>
            </button>
        </div>
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
            <label className="text-sm font-bold text-slate-400 ml-1 mb-2 block uppercase">Добавить товар</label>
            <div className="relative mb-4">
              <input
                type="number"
                placeholder="Артикул (например 171877467)"
                className="w-full bg-slate-50 border-none rounded-2xl p-4 pl-12 text-lg font-semibold focus:ring-2 focus:ring-indigo-500 outline-none transition-all"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
              />
              <Search className="absolute left-4 top-4 text-slate-400" />
            </div>
            <button
              onClick={handleScan}
              disabled={loading}
              className="w-full bg-black text-white p-4 rounded-2xl font-bold text-lg flex items-center justify-center gap-3 active:scale-95 transition-all shadow-xl disabled:opacity-70"
            >
              {loading ? (
                <><Loader2 className="animate-spin" /> {statusMsg}</>
              ) : (
                <><Plus size={20} /> Отследить</>
              )}
            </button>
          </div>
          
          <div className="mt-8 px-4 text-center">
             <p className="text-xs text-slate-400">Бот работает в фоновом режиме.<br/>История цен обновляется каждые 4 часа.</p>
          </div>
        </div>
      )}

      {activeTab === 'monitor' && (
        <div className="px-4 space-y-4 animate-in fade-in slide-in-from-bottom-4">
          
          {historyData && (
            <div className="bg-white p-5 rounded-3xl shadow-lg border border-indigo-100 relative overflow-hidden">
               <div className="absolute top-0 right-0 bg-indigo-600 text-white px-3 py-1 rounded-bl-xl text-[10px] font-bold tracking-tighter">LIVE DATA</div>
               <h3 className="font-bold text-lg leading-tight mb-1 pr-10 truncate">{historyData.name}</h3>
               <p className="text-[10px] text-slate-400 font-black mb-6 uppercase">История цен SKU: {historyData.sku}</p>
               
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
                        contentStyle={{borderRadius: '16px', border: 'none', boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)'}}
                        itemStyle={{color: '#4f46e5', fontWeight: '900'}}
                     />
                     <Area type="monotone" dataKey="wallet" stroke="#4f46e5" strokeWidth={4} fillOpacity={1} fill="url(#colorPv)" />
                   </AreaChart>
                 </ResponsiveContainer>
               </div>
            </div>
          )}

          <div className="space-y-3 pb-10">
            {monitorList.length === 0 ? (
              <div className="text-center p-12 bg-white rounded-3xl border border-dashed border-slate-200">
                <p className="text-slate-400 font-bold text-sm">Список пуст</p>
              </div>
            ) : (
              monitorList.map((item) => (
                <div 
                  key={item.id} 
                  onClick={() => {
                    loadHistory(item.sku);
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }} 
                  className="bg-white p-4 rounded-2xl flex items-center gap-4 active:scale-[0.98] transition-all border border-slate-100 cursor-pointer shadow-sm"
                >
                  <div className="bg-indigo-50 p-3 rounded-xl">
                    <BarChart3 className="text-indigo-500" size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold truncate text-sm">{item.name || `Товар ${item.sku}`}</div>
                    <div className="text-[10px] text-slate-400 font-black uppercase tracking-tighter">{item.brand || 'Wildberries'}</div>
                  </div>
                  <ArrowUpRight className="text-slate-300" size={18} />
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}