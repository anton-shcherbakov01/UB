import React, { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

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
        headers: getTgHeaders()
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

export default ScannerPage;