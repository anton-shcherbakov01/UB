import React, { useState, useEffect } from 'react';
import { 
    Target, ShieldCheck, PlayCircle, Zap, PauseCircle, 
    Activity, ChevronRight, TrendingDown 
} from 'lucide-react';
import { 
    AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';

const BidderPage = () => {
    const [isSafeMode, setIsSafeMode] = useState(true);
    const [logs, setLogs] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);
    
    // Данные для микро-графика позиций (имитация истории PID)
    const [pidHistory] = useState([
        { time: '10:00', pos: 5, bid: 200 },
        { time: '10:15', pos: 4, bid: 210 },
        { time: '10:30', pos: 2, bid: 250 },
        { time: '10:45', pos: 2, bid: 245 }, // Удержание
        { time: '11:00', pos: 2, bid: 240 }, // Оптимизация
        { time: '11:15', pos: 2, bid: 235 }, // PID работает
        { time: '11:30', pos: 1, bid: 300 }, // Скачок
        { time: '11:45', pos: 2, bid: 240 }, // Возврат
    ]);

    const startSimulation = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/bidder/simulation`, { headers: getTgHeaders() });
            const data = await res.json();
            setStats(data);
            setLogs(data.logs);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        startSimulation();
    }, []);

    const CampaignCard = ({ id, name, status, pos, bid, target }) => (
        <div className="bg-slate-900 text-white p-5 rounded-3xl relative overflow-hidden mb-3 shadow-lg shadow-slate-300">
            {/* Background Decor */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-600/20 rounded-full blur-3xl -mr-10 -mt-10"></div>
            
            <div className="flex justify-between items-start mb-4 relative z-10">
                <div>
                    <div className="flex items-center gap-2 mb-1">
                        <span className={`w-2 h-2 rounded-full ${status === 'active' ? 'bg-emerald-400 shadow-[0_0_10px_#34d399]' : 'bg-red-400'}`}></span>
                        <h4 className="font-bold text-sm text-slate-200 uppercase tracking-wider">{name}</h4>
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">ID: {id}</div>
                </div>
                <div className="bg-white/10 px-2 py-1 rounded-lg backdrop-blur-md">
                    <span className="text-xs font-bold text-indigo-300">Target: #{target}</span>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4 relative z-10">
                <div>
                    <div className="text-[10px] text-slate-400 uppercase">Текущая поз.</div>
                    <div className="text-2xl font-black">{pos > 20 ? '20+' : `#${pos}`}</div>
                </div>
                <div className="text-right">
                    <div className="text-[10px] text-slate-400 uppercase">Ставка (CPM)</div>
                    <div className="text-2xl font-black text-indigo-400">{bid} ₽</div>
                </div>
            </div>

            {/* Micro PID Chart */}
            <div className="h-16 w-full -mx-2 opacity-50 relative z-0">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={pidHistory}>
                        <defs>
                            <linearGradient id="colorBid" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#818cf8" stopOpacity={0.8}/>
                                <stop offset="95%" stopColor="#818cf8" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <Area type="monotone" dataKey="bid" stroke="#818cf8" strokeWidth={2} fill="url(#colorBid)" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-violet-600 to-indigo-600 p-6 rounded-[32px] text-white shadow-xl shadow-indigo-200 relative overflow-hidden">
                <div className="relative z-10">
                    <h1 className="text-2xl font-black flex items-center gap-2">
                        <Zap className="text-yellow-300" fill="currentColor" /> Биддер
                    </h1>
                    <p className="text-sm opacity-90 mt-2 font-medium">Алгоритмическое управление рекламой</p>
                    
                    <div className="mt-6 flex items-center gap-4">
                        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-3 flex-1">
                            <div className="text-[10px] opacity-70 uppercase font-bold">Экономия 24ч</div>
                            <div className="text-xl font-black flex items-center gap-1">
                                {stats?.total_budget_saved || 0} ₽ 
                                <TrendingDown size={14} className="text-emerald-300"/>
                            </div>
                        </div>
                        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-3 flex-1">
                            <div className="text-[10px] opacity-70 uppercase font-bold">Кампаний</div>
                            <div className="text-xl font-black">{stats?.campaigns_active || 0}</div>
                        </div>
                    </div>
                </div>
                
                {/* Background Pattern */}
                <div className="absolute -right-10 -bottom-20 w-64 h-64 bg-violet-500 rounded-full blur-3xl opacity-50"></div>
            </div>

            {/* Control Panel */}
            <div className="bg-white p-2 rounded-[24px] shadow-sm border border-slate-100 flex p-1">
                <button 
                    onClick={() => setIsSafeMode(true)} 
                    className={`flex-1 py-4 rounded-[20px] font-bold text-sm transition-all flex flex-col items-center gap-1 ${isSafeMode ? 'bg-emerald-50 text-emerald-700 shadow-inner' : 'text-slate-400 hover:bg-slate-50'}`}
                >
                    <ShieldCheck size={20}/>
                    Safe Mode
                </button>
                <button 
                    onClick={() => setIsSafeMode(false)} 
                    className={`flex-1 py-4 rounded-[20px] font-bold text-sm transition-all flex flex-col items-center gap-1 ${!isSafeMode ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200' : 'text-slate-400 hover:bg-slate-50'}`}
                >
                    <Activity size={20}/>
                    Active Bidding
                </button>
            </div>

            <div className="flex items-center justify-between px-2">
                <h3 className="font-bold text-lg text-slate-800">Кампании</h3>
                <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded-lg">PID Control</span>
            </div>

            <div className="space-y-3">
                {/* Mock Campaigns - в реале брать из API */}
                <CampaignCard id={123456} name="Платья Лето" status="active" pos={2} bid={155} target={2} />
                <CampaignCard id={123457} name="Блузки Офис" status="active" pos={5} bid={320} target={3} />
            </div>

            {logs.length > 0 && (
                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                    <h3 className="font-bold text-sm text-slate-400 uppercase tracking-wider mb-4">Лог PID-регулятора</h3>
                    <div className="space-y-4 relative before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[2px] before:bg-slate-100">
                        {logs.map((l, i) => (
                            <div key={i} className="flex gap-4 relative">
                                <div className="w-6 h-6 rounded-full bg-slate-50 border-2 border-white shadow-sm z-10 flex items-center justify-center text-[8px] font-black text-slate-400 shrink-0">
                                    {l.time.split(':')[1]}
                                </div>
                                <div>
                                    <div className="text-[10px] font-bold text-slate-400 mb-0.5">{l.time}</div>
                                    <div className="text-xs font-medium text-slate-700 leading-relaxed bg-slate-50 p-2 rounded-lg border border-slate-100">
                                        {l.msg}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                    <button 
                        onClick={startSimulation} 
                        className="w-full mt-4 py-3 text-xs font-bold text-indigo-600 bg-indigo-50 rounded-xl hover:bg-indigo-100 transition-colors"
                    >
                        Обновить данные
                    </button>
                </div>
            )}
        </div>
    )
}

export default BidderPage;