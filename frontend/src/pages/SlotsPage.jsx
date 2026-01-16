import React, { useState, useEffect, useMemo } from 'react';
import { 
    Calendar, Package, Search, Info, Filter, 
    ArrowDown, TrendingUp, AlertTriangle, CheckCircle2,
    Loader2, MapPin
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

// --- Components for User Education ---
const InfoCard = ({ icon: Icon, title, text, color }) => (
    <div className={`p-3 rounded-xl border flex gap-3 items-start ${color}`}>
        <Icon size={18} className="mt-0.5 shrink-0" />
        <div>
            <div className="font-bold text-xs mb-1 uppercase tracking-wide opacity-80">{title}</div>
            <div className="text-xs leading-relaxed font-medium">{text}</div>
        </div>
    </div>
);

const CoefficientBadge = ({ value }) => {
    let style = "bg-slate-100 text-slate-500 border-slate-200"; // default
    
    if (value === 0) style = "bg-emerald-100 text-emerald-700 border-emerald-200 shadow-sm shadow-emerald-100";
    else if (value === 1) style = "bg-blue-50 text-blue-700 border-blue-100";
    else if (value > 1 && value <= 5) style = "bg-amber-50 text-amber-700 border-amber-100";
    else if (value > 5) style = "bg-rose-50 text-rose-700 border-rose-100 animate-pulse";

    return (
        <div className={`px-2.5 py-1 rounded-lg border text-xs font-black flex items-center gap-1 ${style}`}>
            {value === 0 ? <CheckCircle2 size={12}/> : null}
            x{value}
        </div>
    );
};

const SlotsPage = ({ user, onNavigate }) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Filters
    const [search, setSearch] = useState('');
    const [onlyFree, setOnlyFree] = useState(false);
    const [boxType, setBoxType] = useState('all'); // all, Koroba, Monopallet

    // Load Data
    const loadSlots = async (force = false) => {
        setLoading(true);
        setError(null);
        try {
            const url = new URL(`${API_URL}/api/slots/coefficients`);
            if (force) url.searchParams.append('refresh', 'true');
            
            const res = await fetch(url, { headers: getTgHeaders() });
            if (res.status === 401 || res.status === 403) {
                // If token invalid, we might handle it
            }
            if (!res.ok) throw new Error("Не удалось загрузить данные");
            
            const json = await res.json();
            setData(json);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (user?.has_wb_token) {
            loadSlots();
        }
    }, [user]);

    // Data Processing
    const processedData = useMemo(() => {
        if (!data) return [];

        let filtered = data.filter(item => {
            const matchSearch = item.warehouseName.toLowerCase().includes(search.toLowerCase());
            const matchFree = onlyFree ? item.coefficient === 0 : true;
            const matchType = boxType === 'all' ? true : 
                              boxType === 'pallet' ? item.boxTypeName.toLowerCase().includes('моно') :
                              !item.boxTypeName.toLowerCase().includes('моно');
            return matchSearch && matchFree && matchType;
        });

        // Group by Warehouse to show timeline? 
        // Or simple list? Simple list is often better for "Find me a slot NOW".
        // Let's grouping by Warehouse makes sense to see upcoming days.
        
        const grouped = {};
        filtered.forEach(item => {
            if (!grouped[item.warehouseName]) {
                grouped[item.warehouseName] = {
                    name: item.warehouseName,
                    id: item.warehouseID,
                    slots: []
                };
            }
            grouped[item.warehouseName].slots.push(item);
        });

        // Convert back to array and sort by "Best Coefficient Available"
        return Object.values(grouped).sort((a, b) => {
            const minA = Math.min(...a.slots.map(s => s.coefficient));
            const minB = Math.min(...b.slots.map(s => s.coefficient));
            return minA - minB;
        });
    }, [data, search, onlyFree, boxType]);

    if (!user?.has_wb_token) {
        return (
            <div className="flex flex-col items-center justify-center h-[60vh] p-6 text-center animate-in fade-in">
                <div className="bg-slate-100 p-4 rounded-full mb-4"><Package size={32} className="text-slate-400"/></div>
                <h3 className="font-bold text-lg mb-2">Подключите API</h3>
                <p className="text-slate-500 text-sm mb-6 max-w-xs">Чтобы видеть свободные слоты и коэффициенты приемки, нужно добавить API токен.</p>
                <button onClick={() => onNavigate('profile')} className="bg-indigo-600 text-white px-6 py-3 rounded-xl font-bold text-sm shadow-lg shadow-indigo-200 active:scale-95 transition-all">
                    Перейти в профиль
                </button>
            </div>
        );
    }

    return (
        <div className="p-4 pb-32 space-y-6 animate-in slide-in-from-right-4 fade-in duration-300">
            
            {/* Header Area */}
            <div>
                <h1 className="text-2xl font-black text-slate-900">Слоты</h1>
                <p className="text-slate-500 text-xs font-medium mt-1">
                    Планирование поставок по выгодным тарифам
                </p>
            </div>

            {/* Educational / Hint Area */}
            <div className="grid grid-cols-1 gap-3">
                <InfoCard 
                    icon={TrendingUp}
                    title="Экономия"
                    text="Выбирая слоты с коэффициентом x0 (бесплатно), вы экономите до 15-20₽ на каждой единице товара."
                    color="bg-emerald-50 border-emerald-100 text-emerald-800"
                />
                <InfoCard 
                    icon={AlertTriangle}
                    title="Перегрузка"
                    text="Коэффициенты x5-x20 означают перегрузку склада. Приемка будет стоить очень дорого."
                    color="bg-amber-50 border-amber-100 text-amber-800"
                />
            </div>

            {/* Controls */}
            <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm space-y-4">
                {/* Search */}
                <div className="relative">
                    <Search className="absolute left-3 top-3.5 text-slate-400" size={18} />
                    <input 
                        type="text" 
                        placeholder="Название склада (например: Тула)" 
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-xl font-bold text-sm outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
                    />
                </div>

                {/* Toggles */}
                <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar">
                    <button 
                        onClick={() => setOnlyFree(!onlyFree)}
                        className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all border ${
                            onlyFree 
                            ? 'bg-emerald-600 text-white border-emerald-600 shadow-md shadow-emerald-200' 
                            : 'bg-white text-slate-600 border-slate-200'
                        }`}
                    >
                        {onlyFree ? <CheckCircle2 size={14}/> : <Filter size={14}/>}
                        Только бесплатные (x0)
                    </button>

                    <button 
                        onClick={() => setBoxType(boxType === 'all' ? 'pallet' : boxType === 'pallet' ? 'box' : 'all')}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap bg-white text-slate-600 border border-slate-200"
                    >
                        <Package size={14}/>
                        {boxType === 'all' ? 'Все типы' : boxType === 'pallet' ? 'Монопаллеты' : 'Короба'}
                    </button>
                </div>
            </div>

            {/* Results List */}
            {loading && !data.length ? (
                <div className="py-20 flex flex-col items-center text-slate-400">
                    <Loader2 className="animate-spin mb-3" size={32}/>
                    <span className="text-xs font-bold">Получаем данные от Wildberries...</span>
                </div>
            ) : error ? (
                <div className="bg-rose-50 text-rose-600 p-4 rounded-xl text-sm font-bold text-center">
                    {error}
                    <button onClick={() => loadSlots(true)} className="block mx-auto mt-2 text-rose-700 underline">Повторить</button>
                </div>
            ) : processedData.length === 0 ? (
                <div className="py-20 text-center text-slate-400">
                    <div className="bg-slate-50 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Search size={24} className="opacity-50"/>
                    </div>
                    <p className="font-bold text-sm">Нет подходящих слотов</p>
                    <p className="text-xs mt-1">Попробуйте изменить фильтры</p>
                </div>
            ) : (
                <div className="space-y-4">
                    {processedData.map((wh) => (
                        <div key={wh.id} className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                            {/* Warehouse Header */}
                            <div className="p-4 bg-slate-50/50 border-b border-slate-100 flex justify-between items-center">
                                <div className="flex items-center gap-2">
                                    <MapPin size={16} className="text-indigo-500" />
                                    <span className="font-bold text-slate-800">{wh.name}</span>
                                </div>
                                <div className="text-[10px] font-bold text-slate-400 uppercase bg-slate-100 px-2 py-1 rounded">
                                    {wh.slots[0].boxTypeName}
                                </div>
                            </div>

                            {/* Dates Grid */}
                            <div className="p-3">
                                <div className="grid grid-cols-4 gap-2">
                                    {wh.slots.slice(0, 8).map((slot, idx) => {
                                        const d = new Date(slot.date);
                                        const isToday = d.toDateString() === new Date().toDateString();
                                        
                                        return (
                                            <div key={idx} className="flex flex-col items-center p-2 rounded-xl bg-slate-50 border border-slate-100">
                                                <div className={`text-[10px] font-bold mb-1 ${isToday ? 'text-indigo-600' : 'text-slate-400'}`}>
                                                    {d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                                                </div>
                                                <CoefficientBadge value={slot.coefficient} />
                                            </div>
                                        );
                                    })}
                                </div>
                                {wh.slots.length > 8 && (
                                    <div className="mt-2 text-center">
                                        <button className="text-xs font-bold text-indigo-600">Показать еще даты...</button>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default SlotsPage;