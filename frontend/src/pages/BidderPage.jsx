import React, { useState } from 'react';
import { Target, ShieldCheck, PlayCircle } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const BidderPage = () => {
    const [isSafeMode, setIsSafeMode] = useState(true);
    const [logs, setLogs] = useState([]);
    const [stats, setStats] = useState(null);

    const startSimulation = async () => {
        const res = await fetch(`${API_URL}/api/bidder/simulation`, { headers: getTgHeaders() });
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

export default BidderPage;