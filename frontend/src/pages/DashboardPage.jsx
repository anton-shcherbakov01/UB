import React, { useState, useEffect } from 'react';
import { Wallet, TrendingUp, Package, RefreshCw, ArrowUpRight, ArrowDownRight, Loader2, Info } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import StoriesBar from '../components/StoriesBar';

const DashboardPage = ({ onNavigate, user }) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    const loadData = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/dashboard/summary`, { headers: getTgHeaders() });
            if (res.ok) {
                setData(await res.json());
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadData(); }, []);

    if (loading && !data) {
        return <div className="h-screen flex items-center justify-center"><Loader2 className="animate-spin text-indigo-600" size={32}/></div>;
    }

    // Если нет токена WB
    if (data?.status === 'no_token') {
        return (
            <div className="p-6 flex flex-col h-[80vh] justify-center text-center">
                <div className="bg-indigo-50 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6">
                    <Wallet size={32} className="text-indigo-600" />
                </div>
                <h2 className="text-2xl font-black mb-2">Подключите WB</h2>
                <p className="text-slate-400 mb-8">Чтобы видеть аналитику, добавьте API токен в профиле.</p>
                <button onClick={() => onNavigate('profile')} className="bg-slate-900 text-white py-4 rounded-2xl font-bold shadow-xl active:scale-95 transition-transform">
                    Перейти в профиль
                </button>
            </div>
        );
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            
            {/* 1. STORIES BLOCK */}
            <StoriesBar stories={data?.stories} />

            {/* 2. MAIN BALANCE CARD */}
            <div className="bg-slate-900 text-white p-6 rounded-[32px] shadow-xl shadow-slate-200 relative overflow-hidden">
                {/* Декор фона */}
                <div className="absolute top-[-50%] right-[-10%] w-64 h-64 bg-indigo-600/30 rounded-full blur-3xl"></div>
                <div className="absolute bottom-[-20%] left-[-10%] w-40 h-40 bg-emerald-500/20 rounded-full blur-3xl"></div>
                
                <div className="relative z-10">
                    <div className="flex justify-between items-start mb-2">
                        <span className="text-slate-400 text-xs font-bold uppercase tracking-wider">Выручка сегодня</span>
                        <div className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold ${data?.header.growth ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
                            {data?.header.growth ? <ArrowUpRight size={12}/> : <ArrowDownRight size={12}/>}
                            {data?.header.growth ? 'Растем' : 'Падаем'}
                        </div>
                    </div>
                    <div className="text-4xl font-black tracking-tight mb-4">
                        {data?.header.balance.toLocaleString('ru-RU')} <span className="text-2xl text-slate-500">₽</span>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/10">
                        <div>
                            <div className="text-slate-400 text-[10px] mb-1">Заказов</div>
                            <div className="font-bold text-lg flex items-center gap-2">
                                <Package size={16} className="text-indigo-400"/>
                                {data?.header.orders_count}
                            </div>
                        </div>
                        <div>
                            <div className="text-slate-400 text-[10px] mb-1">Обновлено</div>
                            <div className="font-bold text-lg flex items-center gap-2">
                                <RefreshCw size={16} className="text-emerald-400"/>
                                {data?.last_updated}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* 3. METRICS GRID */}
            <div>
                <h3 className="font-bold text-lg mb-3 px-2 flex items-center gap-2">
                    <TrendingUp size={20} className="text-indigo-600"/> Показатели
                </h3>
                <div className="grid grid-cols-2 gap-3">
                    {data?.cards.map((card, idx) => (
                        <div key={idx} className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm active:scale-[0.98] transition-transform">
                            <p className="text-[10px] font-bold text-slate-400 uppercase mb-2">{card.label}</p>
                            <div className="flex items-baseline gap-1">
                                <span className={`text-2xl font-black text-${card.color}-600`}>
                                    {card.value}
                                </span>
                                <span className="text-xs font-bold text-slate-400">{card.sub}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* 4. QUICK ACTIONS */}
            <div className="bg-indigo-50 p-5 rounded-3xl border border-indigo-100 flex items-center justify-between">
                <div>
                    <h4 className="font-bold text-indigo-900">Сканер позиций</h4>
                    <p className="text-xs text-indigo-600/80 mt-1">Проверьте позиции товара в поиске</p>
                </div>
                <button 
                    onClick={() => onNavigate('scanner')}
                    className="bg-white text-indigo-600 px-4 py-2 rounded-xl font-bold text-xs shadow-sm active:scale-95 transition-transform"
                >
                    Открыть
                </button>
            </div>

            <div className="text-center">
                <p className="text-[10px] text-slate-300">Данные обновляются в реальном времени через API Wildberries</p>
            </div>
        </div>
    );
};

export default DashboardPage;