import React, { useState, useEffect } from 'react';
import { 
    Wallet, RefreshCw, Loader2, ArrowUpRight, ArrowDownRight,
    PieChart, Truck, Target, TrendingUp, Plus, Wand2 
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import StoriesBar from '../components/StoriesBar';

const DashboardPage = ({ onNavigate, user }) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    const loadData = async () => {
        setLoading(true);
        try {
            // Используем кэшируемый эндпоинт
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

    // 1. Стейт загрузки
    if (loading && !data) {
        return <div className="h-screen flex items-center justify-center"><Loader2 className="animate-spin text-indigo-600" size={32}/></div>;
    }

    // 2. Нет токена
    if (data?.status === 'no_token') {
        return (
            <div className="p-6 flex flex-col h-[80vh] justify-center text-center">
                <div className="bg-indigo-50 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6">
                    <Wallet size={32} className="text-indigo-600" />
                </div>
                <h2 className="text-2xl font-black mb-2">Подключите WB</h2>
                <button onClick={() => onNavigate('profile')} className="bg-slate-900 text-white py-4 rounded-2xl font-bold mt-4 shadow-xl">
                    В профиль
                </button>
            </div>
        );
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            
            {/* --- БЛОК 1: STORIES --- */}
            <StoriesBar stories={data?.stories} />

            {/* --- БЛОК 2: ГЛАВНЫЙ БАЛАНС (КРАСИВЫЙ) --- */}
            <div className="bg-slate-900 text-white p-6 rounded-[32px] shadow-xl shadow-slate-200 relative overflow-hidden">
                <div className="absolute top-[-50%] right-[-10%] w-64 h-64 bg-indigo-600/30 rounded-full blur-3xl"></div>
                <div className="absolute bottom-[-20%] left-[-10%] w-40 h-40 bg-emerald-500/20 rounded-full blur-3xl"></div>
                
                <div className="relative z-10">
                    <div className="flex justify-between items-start mb-2">
                        <span className="text-slate-400 text-xs font-bold uppercase tracking-wider">Выручка сегодня</span>
                        {data?.header && (
                            <div className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold ${data.header.growth ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
                                {data.header.growth ? <ArrowUpRight size={12}/> : <ArrowDownRight size={12}/>}
                                {data.header.growth ? 'Растем' : 'Падаем'}
                            </div>
                        )}
                    </div>
                    <div className="text-4xl font-black tracking-tight mb-4">
                        {data?.header?.balance.toLocaleString('ru-RU')} <span className="text-2xl text-slate-500">₽</span>
                    </div>
                    
                    <div className="flex items-center gap-6 pt-4 border-t border-white/10">
                        <div>
                            <div className="text-slate-400 text-[10px] mb-1">Заказов</div>
                            <div className="font-bold text-lg">{data?.header?.orders_count}</div>
                        </div>
                        <div>
                            <div className="text-slate-400 text-[10px] mb-1">Обновлено</div>
                            <div className="font-bold text-lg flex items-center gap-2">
                                {data?.last_updated}
                                <RefreshCw size={14} className="opacity-50" onClick={loadData}/>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* --- БЛОК 3: СЕРВИСЫ (ВОССТАНОВЛЕННЫЕ) --- */}
            <div>
                <h3 className="font-bold text-lg mb-3 px-2 text-slate-800">Инструменты</h3>
                <div className="grid grid-cols-2 gap-4">
                    {/* Unit Economy */}
                    <div onClick={() => onNavigate('finance')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer col-span-2">
                        <div className="bg-emerald-100 w-12 h-12 rounded-2xl flex items-center justify-center text-emerald-600">
                            <PieChart size={24} />
                        </div>
                        <div>
                            <span className="font-bold text-slate-800 block">Unit-экономика</span>
                            <span className="text-xs text-slate-400">P&L, Маржа, ROI</span>
                        </div>
                    </div>

                    {/* Supply */}
                    <div onClick={() => onNavigate('supply')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                        <div className="bg-orange-100 w-12 h-12 rounded-2xl flex items-center justify-center text-orange-600">
                            <Truck size={24} />
                        </div>
                        <div>
                            <span className="font-bold text-slate-800 block">Поставки</span>
                            <span className="text-xs text-slate-400">Склад</span>
                        </div>
                    </div>

                    {/* Bidder */}
                    <div onClick={() => onNavigate('bidder')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                        <div className="bg-purple-100 w-12 h-12 rounded-2xl flex items-center justify-center text-purple-600">
                            <Target size={24} />
                        </div>
                        <div>
                            <span className="font-bold text-slate-800 block">Биддер</span>
                            <span className="text-xs text-slate-400">Реклама</span>
                        </div>
                    </div>

                    {/* SEO Tracker */}
                    <div onClick={() => onNavigate('seo_tracker')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                        <div className="bg-blue-100 w-12 h-12 rounded-2xl flex items-center justify-center text-blue-600">
                            <TrendingUp size={24} />
                        </div>
                        <div>
                            <span className="font-bold text-slate-800 block">Позиции</span>
                            <span className="text-xs text-slate-400">Трекер</span>
                        </div>
                    </div>

                    {/* Scanner */}
                    <div onClick={() => onNavigate('scanner')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                        <div className="bg-slate-100 w-12 h-12 rounded-2xl flex items-center justify-center text-slate-600">
                            <Plus size={24} />
                        </div>
                        <div>
                            <span className="font-bold text-slate-800 block">Сканер</span>
                            <span className="text-xs text-slate-400">Добавить</span>
                        </div>
                    </div>

                    {/* SEO Gen */}
                    <div onClick={() => onNavigate('seo')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                        <div className="bg-yellow-100 w-12 h-12 rounded-2xl flex items-center justify-center text-yellow-600">
                            <Wand2 size={24} />
                        </div>
                        <div>
                            <span className="font-bold text-slate-800 block">SEO Gen</span>
                            <span className="text-xs text-slate-400">Тексты</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DashboardPage;