import React, { useState, useEffect } from 'react';
import { Sparkles, Loader2, PieChart, Truck, Target, TrendingUp, Plus, Wand2 } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import StoriesBar from '../components/StoriesBar';

const DashboardPage = ({ onNavigate, user }) => {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (user?.has_wb_token) {
            setLoading(true);
            fetch(`${API_URL}/api/internal/stats`, {
                headers: getTgHeaders()
            })
            .then(r => r.json())
            .then(data => {
                setStats(data);
                setLoading(false);
            })
            .catch(() => setLoading(false));
        }
    }, [user]);

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in duration-500">
            <StoriesBar />

            <div className="bg-gradient-to-br from-indigo-600 to-violet-700 rounded-[32px] p-6 text-white shadow-xl shadow-indigo-200 relative overflow-hidden">
                <div className="relative z-10">
                    <div className="flex justify-between items-start mb-4">
                        <div className="flex items-center gap-2 opacity-80">
                            <Sparkles size={16} className="text-amber-300" />
                            <span className="text-xs font-bold uppercase tracking-widest">Мои Продажи</span>
                        </div>
                        {!user?.has_wb_token && (
                            <button onClick={() => onNavigate('profile')} className="bg-white/20 hover:bg-white/30 px-3 py-1 rounded-full text-xs font-bold transition-colors">
                                Подключить
                            </button>
                        )}
                    </div>

                    {!user?.has_wb_token ? (
                        <div className="text-center py-4">
                            <p className="font-bold text-lg mb-2">Подключите API</p>
                            <p className="text-xs opacity-70">Чтобы видеть реальные продажи</p>
                        </div>
                    ) : loading ? (
                        <div className="flex justify-center py-6"><Loader2 className="animate-spin" /></div>
                    ) : (
                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-white/10 p-3 rounded-2xl backdrop-blur-sm">
                                <p className="text-xs opacity-70 mb-1">Заказы сегодня</p>
                                <p className="text-2xl font-black">{stats?.orders_today?.sum?.toLocaleString() || 0} ₽</p>
                                <p className="text-xs opacity-70">{stats?.orders_today?.count || 0} шт</p>
                            </div>
                            <div className="bg-white/10 p-3 rounded-2xl backdrop-blur-sm">
                                <p className="text-xs opacity-70 mb-1">Остатки</p>
                                <p className="text-2xl font-black">{stats?.stocks?.total_quantity?.toLocaleString() || 0} шт</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                 <div onClick={() => onNavigate('finance')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer col-span-2">
                    <div className="bg-emerald-100 w-12 h-12 rounded-2xl flex items-center justify-center text-emerald-600">
                        <PieChart size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Unit-экономика</span>
                        <span className="text-xs text-slate-400">P&L, Маржа, ROI</span>
                    </div>
                </div>
                <div onClick={() => onNavigate('supply')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-orange-100 w-12 h-12 rounded-2xl flex items-center justify-center text-orange-600">
                        <Truck size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Поставки</span>
                        <span className="text-xs text-slate-400">Прогноз склада</span>
                    </div>
                </div>
                <div onClick={() => onNavigate('bidder')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-purple-100 w-12 h-12 rounded-2xl flex items-center justify-center text-purple-600">
                        <Target size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Биддер</span>
                        <span className="text-xs text-slate-400">Управление рекламой</span>
                    </div>
                </div>
                 <div onClick={() => onNavigate('seo_tracker')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-blue-100 w-12 h-12 rounded-2xl flex items-center justify-center text-blue-600">
                        <TrendingUp size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">SEO Трекер</span>
                        <span className="text-xs text-slate-400">Позиции (SERP)</span>
                    </div>
                </div>
                 <div onClick={() => onNavigate('scanner')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-slate-100 w-12 h-12 rounded-2xl flex items-center justify-center text-slate-600">
                        <Plus size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">Сканер</span>
                        <span className="text-xs text-slate-400">Добавить</span>
                    </div>
                </div>
                 <div onClick={() => onNavigate('seo')} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm flex flex-col gap-3 active:scale-[0.98] transition-all cursor-pointer">
                    <div className="bg-yellow-100 w-12 h-12 rounded-2xl flex items-center justify-center text-yellow-600">
                        <Wand2 size={24} />
                    </div>
                    <div>
                        <span className="font-bold text-slate-800 block">SEO Gen</span>
                        <span className="text-xs text-slate-400">Генератор</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DashboardPage;