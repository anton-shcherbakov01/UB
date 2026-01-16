import React, { useState, useEffect, useMemo } from 'react';
import { 
    Clock, RefreshCw, X, FileDown, Loader2, BarChart3, Trash2, 
    Search, TrendingUp, AlertCircle, ArrowRight, Wallet 
} from 'lucide-react';
import { 
    AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';
import { useNavigate } from 'react-router-dom';
import HistoryModule from '../components/HistoryModule';

const MonitorPage = () => {
    const [list, setList] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    
    // States for Modals
    const [historyOpen, setHistoryOpen] = useState(false); // Global history module
    const [itemHistory, setItemHistory] = useState(null); // Specific item detail
    const [downloading, setDownloading] = useState(false);
    
    const navigate = useNavigate();

    const fetchList = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/monitor/list`, {
                headers: getTgHeaders()
            });
            if (res.ok) setList(await res.json());
        } catch(e) { 
            console.error(e); 
        } finally { 
            setLoading(false); 
        }
    };

    useEffect(() => { fetchList(); }, []);

    const handleDelete = async (e, sku) => {
        e.stopPropagation();
        if(!window.confirm("Удалить этот товар из отслеживания?")) return;
        
        // Optimistic update for speed
        setList(prev => prev.filter(item => item.sku !== sku));
        
        try {
            await fetch(`${API_URL}/api/monitor/delete/${sku}`, { 
                method: 'DELETE',
                headers: getTgHeaders()
            });
        } catch(e) {
            console.error(e);
            fetchList(); // Revert on error
        }
    };

    const loadHistory = async (sku) => {
        // Show modal immediately with loading state implied (data null)
        try {
            const res = await fetch(`${API_URL}/api/monitor/history/${sku}`, {
                headers: getTgHeaders()
            });
            if(res.ok) setItemHistory(await res.json());
        } catch(e) { console.error(e); }
    };

    const downloadReport = async (sku) => {
        setDownloading(true);
        try {
            const token = window.Telegram?.WebApp?.initData || "";
            const response = await fetch(`${API_URL}/api/report/pdf/${sku}`, {
                headers: { 'X-TG-Data': token }
            });

            if (response.status === 403) {
                alert("Функция доступна в тарифе PRO");
                return;
            }

            if (!response.ok) throw new Error("Ошибка загрузки");

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `report_${sku}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (e) {
            alert("Не удалось скачать отчет");
        } finally {
            setDownloading(false);
        }
    };

    // Filter list based on search
    const filteredList = useMemo(() => {
        if (!searchQuery) return list;
        const lower = searchQuery.toLowerCase();
        return list.filter(item => 
            String(item.sku).includes(lower) || 
            item.name.toLowerCase().includes(lower) || 
            (item.brand && item.brand.toLowerCase().includes(lower))
        );
    }, [list, searchQuery]);

    // --- Sub-components ---

    const SkeletonLoader = () => (
        <div className="animate-pulse space-y-3">
            {[1, 2, 3].map(i => (
                <div key={i} className="h-20 bg-slate-200 rounded-2xl w-full"></div>
            ))}
        </div>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in max-w-lg mx-auto min-h-screen bg-slate-50/50">
            
            {/* Header */}
            <div className="flex justify-between items-end px-1">
                <div>
                    <h2 className="text-2xl font-black text-slate-800 tracking-tight">Конкуренты</h2>
                    <p className="text-xs font-medium text-slate-400">Мониторинг цен 24/7</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => setHistoryOpen(true)} className="p-2.5 bg-white border border-slate-100 text-indigo-600 rounded-xl shadow-sm active:scale-95 transition-transform">
                        <Clock size={20}/>
                    </button>
                    <button onClick={fetchList} className="p-2.5 bg-slate-900 text-white rounded-xl shadow-lg shadow-slate-300 active:rotate-180 transition-all">
                        <RefreshCw size={20}/>
                    </button>
                </div>
            </div>

            {/* Global History Component (Popup) */}
            <HistoryModule type="price" isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />

            {/* Search Bar */}
            <div className="relative">
                <Search className="absolute left-3 top-3.5 text-slate-400" size={18} />
                <input 
                    type="text" 
                    placeholder="Поиск по SKU или названию..." 
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-3 bg-white border border-slate-100 rounded-2xl shadow-sm outline-none focus:ring-2 focus:ring-indigo-100 transition-all text-sm font-medium placeholder:text-slate-400"
                />
            </div>

            {/* Content List */}
            <div className="space-y-3">
                {loading ? (
                    <SkeletonLoader />
                ) : list.length === 0 ? (
                    <div className="flex flex-col items-center justify-center p-10 bg-white rounded-3xl border border-dashed border-slate-200 text-center animate-in zoom-in-95 duration-300">
                        <div className="w-16 h-16 bg-indigo-50 rounded-full flex items-center justify-center mb-4">
                            <TrendingUp className="text-indigo-500" size={32} />
                        </div>
                        <h3 className="font-bold text-slate-800 mb-2">Список пуст</h3>
                        <p className="text-xs text-slate-400 mb-6 max-w-[200px]">Добавьте товары конкурентов через сканер, чтобы следить за ценами.</p>
                        <button onClick={() => navigate('/scanner')} className="flex items-center gap-2 bg-indigo-600 text-white px-5 py-2.5 rounded-xl font-bold text-sm shadow-lg shadow-indigo-200 active:scale-95 transition-transform">
                            В сканер <ArrowRight size={16}/>
                        </button>
                    </div>
                ) : filteredList.length === 0 ? (
                    <div className="text-center py-10 text-slate-400 text-sm">Ничего не найдено</div>
                ) : (
                    filteredList.map((item) => (
                        <div 
                            key={item.id} 
                            onClick={() => loadHistory(item.sku)} 
                            className="bg-white p-4 rounded-2xl flex items-center gap-4 border border-slate-100 shadow-sm relative group active:scale-[0.98] transition-all cursor-pointer hover:shadow-md hover:border-indigo-100"
                        >
                            <div className="bg-gradient-to-br from-indigo-50 to-white w-12 h-12 flex items-center justify-center rounded-xl border border-indigo-50 text-indigo-600 shrink-0">
                                <BarChart3 size={20} />
                            </div>
                            
                            <div className="flex-1 min-w-0">
                                <div className="text-[9px] font-black uppercase tracking-wider text-indigo-400 mb-0.5">
                                    {item.brand || 'NO BRAND'}
                                </div>
                                <div className="font-bold truncate text-sm text-slate-700 leading-tight">
                                    {item.name || `SKU ${item.sku}`}
                                </div>
                                <div className="text-[10px] text-slate-400 mt-1">SKU: {item.sku}</div>
                            </div>
                            
                            <div className="text-right shrink-0">
                                <div className="font-black text-lg text-slate-800">
                                    {item.prices[0]?.wallet_price ? `${item.prices[0].wallet_price.toLocaleString()} ₽` : '...'}
                                </div>
                                <div className="text-[10px] text-slate-400 font-medium">WB Кошелек</div>
                            </div>

                            <button 
                                onClick={(e) => handleDelete(e, item.sku)} 
                                className="absolute -right-2 -top-2 bg-white border border-slate-100 text-slate-300 p-1.5 rounded-full shadow-sm opacity-0 group-hover:opacity-100 transition-opacity hover:text-red-500 hover:border-red-100"
                            >
                                <Trash2 size={14}/>
                            </button>
                        </div>
                    ))
                )}
            </div>

            {/* --- Detail Modal (Bottom Sheet style) --- */}
            {itemHistory && (
                <div className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm flex items-end sm:items-center justify-center animate-in fade-in duration-200">
                    {/* Клик по фону закрывает */}
                    <div className="absolute inset-0" onClick={() => setItemHistory(null)}></div>
                    
                    <div className="bg-white w-full max-w-lg rounded-t-[32px] sm:rounded-[32px] p-6 pb-8 shadow-2xl relative animate-in slide-in-from-bottom duration-300">
                        {/* Close bar for mobile */}
                        <div className="w-12 h-1.5 bg-slate-200 rounded-full mx-auto mb-6 sm:hidden"></div>
                        
                        <button onClick={() => setItemHistory(null)} className="absolute top-4 right-4 p-2 bg-slate-50 hover:bg-slate-100 rounded-full text-slate-400 transition-colors hidden sm:block">
                            <X size={20} />
                        </button>

                        <div className="mb-6 pr-8">
                            <div className="flex items-center gap-2 mb-2">
                                <span className="text-[10px] font-black uppercase text-white bg-indigo-500 px-2 py-0.5 rounded-md">
                                    {itemHistory.sku}
                                </span>
                                <span className="text-[10px] font-bold text-slate-400 uppercase">История цен</span>
                            </div>
                            <h3 className="font-bold text-xl leading-snug text-slate-800 line-clamp-2">
                                {itemHistory.name}
                            </h3>
                        </div>
                        
                        {/* Actions */}
                        <div className="grid grid-cols-2 gap-3 mb-6">
                            <div className="bg-indigo-50 p-3 rounded-2xl flex items-center justify-between">
                                <span className="text-xs text-indigo-400 font-bold flex items-center gap-1">
                                    <Wallet size={12}/> Текущая
                                </span>
                                <span className="text-lg font-black text-indigo-700">
                                    {itemHistory.history[itemHistory.history.length-1]?.wallet} ₽
                                </span>
                            </div>
                            <button 
                                onClick={() => downloadReport(itemHistory.sku)} 
                                disabled={downloading}
                                className="bg-slate-900 text-white rounded-2xl text-xs font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-70"
                            >
                                {downloading ? <Loader2 size={16} className="animate-spin" /> : <><FileDown size={16} /> Отчет PDF</>}
                            </button>
                        </div>

                        {/* Chart */}
                        <div className="h-64 w-full bg-slate-50/50 rounded-3xl p-2 border border-slate-100">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={itemHistory.history}>
                                    <defs>
                                        <linearGradient id="colorWallet" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                    <XAxis 
                                        dataKey="date" 
                                        tick={{fontSize: 10, fill: '#94a3b8'}} 
                                        tickLine={false} 
                                        axisLine={false} 
                                        minTickGap={30}
                                    />
                                    <YAxis 
                                        hide 
                                        domain={['dataMin - 50', 'dataMax + 50']} 
                                    />
                                    <Tooltip 
                                        contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)'}} 
                                        itemStyle={{color: '#4f46e5', fontWeight: 800, fontSize: '12px'}}
                                        labelStyle={{color: '#64748b', fontSize: '10px', marginBottom: '2px'}}
                                    />
                                    <Area 
                                        type="monotone" 
                                        dataKey="wallet" 
                                        name="Цена WB Кошелек"
                                        stroke="#6366f1" 
                                        strokeWidth={3} 
                                        fill="url(#colorWallet)" 
                                        animationDuration={1000}
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MonitorPage;