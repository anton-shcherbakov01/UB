import React, { useState, useEffect } from 'react';
import { Search, Package, Tag, Wallet, CreditCard, AlertCircle, Loader2, Sparkles } from 'lucide-react';

export default function App() {
  const [sku, setSku] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
    }
  }, []);

  const handleAnalyze = async () => {
    if (!sku) return;
    setLoading(true);
    setError(null);
    setData(null);

    try {
      // Передаем данные инициализации Telegram в заголовке для безопасности
      const tgData = window.Telegram?.WebApp?.initData || "";
      const response = await fetch(`https://api.ulike-bot.ru/api/analyze/${sku}`, {
        headers: { 'X-TG-Data': tgData }
      });
      const result = await response.json();
      
      if (response.ok) {
        setData(result);
      } else {
        setError(result.detail || 'Ошибка анализа');
      }
    } catch (err) {
      setError('Сервер не отвечает');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-4 font-sans text-slate-900">
      <div className="mb-6 text-center">
        <h1 className="text-2xl font-bold text-indigo-600 flex items-center justify-center gap-2">
          <Sparkles className="text-amber-400" /> WB Monitor
        </h1>
        <p className="text-xs text-slate-400 uppercase tracking-widest mt-1 font-semibold">Microservice Edition</p>
      </div>

      <div className="mb-6 space-y-3">
        <div className="relative">
          <input
            type="number"
            placeholder="Введите артикул"
            className="w-full rounded-2xl border border-slate-200 bg-white p-4 pl-12 text-lg shadow-sm focus:ring-2 focus:ring-indigo-500 transition-all outline-none"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
          />
          <Search className="absolute left-4 top-4.5 text-slate-400" size={24} />
        </div>
        <button
          onClick={handleAnalyze}
          disabled={loading || !sku}
          className="w-full rounded-2xl bg-indigo-600 p-4 font-bold text-white shadow-lg active:scale-95 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
        >
          {loading ? <><Loader2 className="animate-spin" /> Анализ...</> : 'Получить цены'}
        </button>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-2xl bg-red-50 p-4 text-red-600 border border-red-100 animate-pulse">
          <AlertCircle size={20} />
          <p className="text-sm font-medium">{error}</p>
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="rounded-3xl bg-white p-6 shadow-sm border border-slate-100 relative overflow-hidden">
            {data.metrics.is_favorable && (
              <div className="absolute top-0 right-0 bg-amber-400 text-white px-4 py-1 rounded-bl-xl text-[10px] font-black uppercase">
                Выгодно
              </div>
            )}
            
            <div className="mb-5">
              <span className="text-[10px] font-black uppercase text-indigo-500 bg-indigo-50 px-2 py-0.5 rounded-md">{data.brand}</span>
              <h2 className="text-xl font-bold mt-1 text-slate-800 leading-tight">{data.name}</h2>
            </div>

            <div className="space-y-3">
              {/* Wallet */}
              <div className="flex items-center justify-between rounded-2xl bg-purple-600 p-4 text-white shadow-md">
                <div className="flex items-center gap-3">
                  <Wallet size={20} />
                  <span className="font-bold text-sm">Кошелек</span>
                </div>
                <div className="text-right">
                   <div className="text-2xl font-black">{data.prices.wallet_purple} ₽</div>
                   <div className="text-[10px] opacity-80">выгода {data.metrics.wallet_benefit} ₽</div>
                </div>
              </div>

              {/* Standard */}
              <div className="flex items-center justify-between rounded-2xl bg-slate-100 p-4 border border-slate-200">
                <div className="flex items-center gap-3">
                  <CreditCard size={20} className="text-slate-600" />
                  <span className="font-bold text-slate-600 text-sm">Обычная</span>
                </div>
                <span className="text-xl font-bold text-slate-900">{data.prices.standard_black} ₽</span>
              </div>

              {/* Base */}
              <div className="flex items-center justify-between px-4 pt-2">
                <span className="text-xs text-slate-400">Без скидок:</span>
                <span className="text-sm text-slate-400 line-through font-medium">{data.prices.base_crossed} ₽</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}