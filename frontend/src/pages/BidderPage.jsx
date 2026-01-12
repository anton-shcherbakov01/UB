import React, { useState, useEffect } from 'react';
import { 
    Target, ShieldCheck, Zap, Activity, TrendingDown, Loader2, AlertCircle, RefreshCw
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const BidderPage = () => {
    const [campaigns, setCampaigns] = useState([]);
    const [dashboard, setDashboard] = useState(null);
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
            const [campRes, dashRes, logsRes] = await Promise.all([
                fetch(`${API_URL}/api/bidder/campaigns`, { headers: getTgHeaders() }),
                fetch(`${API_URL}/api/bidder/dashboard`, { headers: getTgHeaders() }),
                fetch(`${API_URL}/api/bidder/logs`, { headers: getTgHeaders() })
            ]);

            if (!campRes.ok || !dashRes.ok) throw new Error("Ошибка API");

            setCampaigns(await campRes.json());
            setDashboard(await dashRes.json());
            setLogs(await logsRes.json());
        } catch (e) {
            console.error(e);
            setError("Не удалось загрузить данные. Проверьте WB API токен или подключение.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, []);

    const CampaignCard = ({ camp }) => (
        <div className="bg-slate-900 text-white p-5 rounded-3xl relative overflow-hidden mb-3 shadow-lg shadow-slate-300">
            <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-600/20 rounded-full blur-3xl -mr-10 -mt-10"></div>
            
            <div className="flex justify-between items-start mb-4 relative z-10">
                <div>
                    <div className="flex items-center gap-2 mb-1">
                        <span className={`w-2 h-2 rounded-full ${camp.status === 9 ? 'bg-emerald-400 shadow-[0_0_10px_#34d399]' : 'bg-amber-400'}`}></span>
                        <h4 className="font-bold text-sm text-slate-200 uppercase tracking-wider">{camp.name}</h4>
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">ID: {camp.id}</div>
                </div>
                <div className="bg-white/10 px-2 py-1 rounded-lg backdrop-blur-md">
                    <span className="text-xs font-bold text-indigo-300">{camp.status === 9 ? 'Active' : 'Paused'}</span>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4 relative z-10">
                <div>
                    <div className="text-[10px] text-slate-400 uppercase">Тип</div>
                    <div className="text-sm font-black">{camp.type === 6 ? 'Поиск' : camp.type === 8 ? 'Авто' : 'Другое'}</div>
                </div>
                <div className="text-right">
                    <div className="text-[10px] text-slate-400 uppercase">Изменено</div>
                    <div className="text-sm font-bold text-slate-300">{new Date(camp.changeTime).toLocaleDateString()}</div>
                </div>
            </div>
        </div>
    );

    if (loading && campaigns.length === 0) {
        return <div className="flex justify-center items-center h-[80vh]"><Loader2 className="animate-spin text-indigo-600" /></div>;
    }

    if (error) {
        return (
            <div className="p-6 text-center animate-in fade-in">
                <AlertCircle className="mx-auto text-red-500 mb-2" size={32}/>
                <h3 className="font-bold text-slate-800">Ошибка соединения</h3>
                <p className="text-sm text-slate-500 mt-2">{error}</p>
                <button onClick={fetchData} className="mt-4 bg-slate-900 text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 mx-auto">
                    <RefreshCw size={14} /> Повторить
                </button>
            </div>
        )
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-violet-600 to-indigo-600 p-6 rounded-[32px] text-white shadow-xl shadow-indigo-200 relative overflow-hidden">
                <div className="relative z-10">
                    <h1 className="text-2xl font-black flex items-center gap-2">
                        <Zap className="text-yellow-300" fill="currentColor" /> Биддер
                    </h1>
                    <p className="text-sm opacity-90 mt-2 font-medium">Управление ставками</p>
                    
                    <div className="mt-6 flex items-center gap-4">
                        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-3 flex-1">
                            <div className="text-[10px] opacity-70 uppercase font-bold">Экономия 24ч</div>
                            <div className="text-xl font-black flex items-center gap-1">
                                {dashboard?.total_budget_saved || 0} ₽ 
                                <TrendingDown size={14} className="text-emerald-300"/>
                            </div>
                        </div>
                        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-3 flex-1">
                            <div className="text-[10px] opacity-70 uppercase font-bold">Активных</div>
                            <div className="text-xl font-black">{dashboard?.campaigns_active || 0}</div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="flex items-center justify-between px-2">
                <h3 className="font-bold text-lg text-slate-800">Мои кампании</h3>
                <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded-lg">{campaigns.length} шт</span>
            </div>

            <div className="space-y-3">
                {campaigns.length === 0 ? (
                    <div className="text-center p-8 text-slate-400 bg-white rounded-3xl border border-dashed border-slate-200">
                        Нет активных кампаний
                    </div>
                ) : (
                    campaigns.map(camp => <CampaignCard key={camp.id} camp={camp} />)
                )}
            </div>

            {logs.length > 0 && (
                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                    <h3 className="font-bold text-sm text-slate-400 uppercase tracking-wider mb-4">Лог активности</h3>
                    <div className="space-y-4 relative before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[2px] before:bg-slate-100">
                        {logs.map((l, i) => (
                            <div key={i} className="flex gap-4 relative">
                                <div className="w-6 h-6 rounded-full bg-slate-50 border-2 border-white shadow-sm z-10 flex items-center justify-center text-[8px] font-black text-slate-400 shrink-0">
                                    {l.time}
                                </div>
                                <div>
                                    <div className="text-[10px] font-bold text-slate-400 mb-0.5">{l.full_date}</div>
                                    <div className="text-xs font-medium text-slate-700 leading-relaxed bg-slate-50 p-2 rounded-lg border border-slate-100">
                                        {l.msg}
                                        {l.saved > 0 && <span className="block text-emerald-600 font-bold mt-1">Сэкономлено: {l.saved} ₽</span>}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

export default BidderPage;