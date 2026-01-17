import React, { useState, useEffect } from 'react';
import { ChevronLeft, Loader2, Check, RefreshCw } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const AdminPage = ({ onBack }) => {
  const [stats, setStats] = useState(null);
  const [user, setUser] = useState(null);
  const [planChanging, setPlanChanging] = useState(false);
  
  useEffect(() => {
    fetch(`${API_URL}/api/admin/stats`, { 
        headers: getTgHeaders() 
    }).then(r => r.json()).then(setStats).catch(console.error);
    
    // Загружаем информацию о текущем пользователе
    fetch(`${API_URL}/api/user/me`, {
        headers: getTgHeaders()
    }).then(r => r.json()).then(setUser).catch(console.error);
  }, []);

  const changePlan = async (planId) => {
    setPlanChanging(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/set-plan`, {
        method: 'POST',
        headers: {
          ...getTgHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ plan_id: planId })
      });
      
      if (res.ok) {
        const data = await res.json();
        // Обновляем информацию о пользователе
        const userRes = await fetch(`${API_URL}/api/user/me`, {
          headers: getTgHeaders()
        });
        if (userRes.ok) {
          setUser(await userRes.json());
        }
        alert(`✅ Тариф изменен на: ${data.plan_name}`);
      } else {
        const error = await res.json().catch(() => ({ detail: 'Ошибка изменения тарифа' }));
        alert(`❌ ${error.detail || 'Ошибка изменения тарифа'}`);
      }
    } catch (e) {
      alert(`❌ Ошибка: ${e.message}`);
    } finally {
      setPlanChanging(false);
    }
  };

  const getPlanDisplayName = (planId) => {
    switch(planId) {
      case 'analyst': return 'Аналитик';
      case 'strategist': return 'Стратег';
      case 'start': return 'Старт';
      default: return planId || 'Не определено';
    }
  };

  const plans = [
    { id: 'start', name: 'Старт', color: 'bg-slate-900' },
    { id: 'analyst', name: 'Аналитик', color: 'bg-indigo-600' },
    { id: 'strategist', name: 'Стратег', color: 'bg-slate-700' }
  ];

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

      {/* Переключение тарифов для тестирования */}
      <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-100">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-800">Тестирование тарифов</h3>
            <p className="text-xs text-slate-500 mt-1">Текущий тариф: <strong className="text-slate-800">{getPlanDisplayName(user?.plan)}</strong></p>
          </div>
          <button 
            onClick={() => {
              fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
                .then(r => r.json())
                .then(setUser)
                .catch(console.error);
            }}
            className="p-2 bg-slate-100 rounded-lg hover:bg-slate-200 active:scale-95 transition-transform"
            title="Обновить информацию"
          >
            <RefreshCw size={18} className="text-slate-600" />
          </button>
        </div>
        
        <div className="grid grid-cols-3 gap-3">
          {plans.map((plan) => (
            <button
              key={plan.id}
              onClick={() => changePlan(plan.id)}
              disabled={planChanging || user?.plan === plan.id}
              className={`
                p-4 rounded-2xl font-bold text-sm text-white shadow-lg active:scale-95 transition-all
                ${planChanging ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-xl'}
                ${user?.plan === plan.id ? `${plan.color} ring-4 ring-offset-2 ring-offset-white ring-indigo-300` : plan.color}
                ${user?.plan === plan.id ? '' : 'hover:opacity-90'}
              `}
            >
              {planChanging && user?.plan === plan.id ? (
                <Loader2 className="animate-spin mx-auto" size={20} />
              ) : user?.plan === plan.id ? (
                <div className="flex flex-col items-center gap-2">
                  <Check size={20} className="text-white" />
                  <span>{plan.name}</span>
                  <span className="text-[10px] opacity-80">Активен</span>
                </div>
              ) : (
                <span>{plan.name}</span>
              )}
            </button>
          ))}
        </div>
        
        <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-xl">
          <p className="text-xs text-amber-800 leading-relaxed">
            <strong>⚠️ Для тестирования:</strong> Выберите тариф для немедленного применения. Квоты будут сброшены, срок подписки установлен на 30 дней для платных тарифов.
          </p>
        </div>
      </div>
    </div>
  );
};

export default AdminPage;