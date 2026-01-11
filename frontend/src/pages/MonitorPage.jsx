import React, { useState, useEffect } from 'react';
import { Clock, RefreshCw, X, FileDown, Loader2, BarChart3, Trash2 } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { API_URL, getTgHeaders } from '../config';
import HistoryModule from '../components/HistoryModule';

const MonitorPage = () => {
  const [list, setList] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyData, setHistoryData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const fetchList = async () => {
      try {
        const res = await fetch(`${API_URL}/api/monitor/list`, {
            headers: getTgHeaders()
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
        headers: getTgHeaders()
    });
    fetchList();
  };

  const loadHistory = async (sku) => {
    setHistoryData(null);
    try {
        const res = await fetch(`${API_URL}/api/monitor/history/${sku}`, {
            headers: getTgHeaders()
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

export default MonitorPage;