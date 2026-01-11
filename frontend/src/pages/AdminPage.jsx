import React, { useState, useEffect } from 'react';
import { ChevronLeft } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const AdminPage = ({ onBack }) => {
  const [stats, setStats] = useState(null);
  
  useEffect(() => {
    fetch(`${API_URL}/api/admin/stats`, { 
        headers: getTgHeaders() 
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

export default AdminPage;