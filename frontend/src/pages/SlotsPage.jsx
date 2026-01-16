import React, { useState, useEffect, useMemo } from 'react';
import { 
    Calendar, Package, Search, Info, Filter, 
    ArrowDown, TrendingUp, AlertTriangle, CheckCircle2,
    Loader2, MapPin, DollarSign, X, ArrowLeft
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
    const [boxType, setBoxType] = useState('all'); // all, box, pallet

    // Load Data
    const loadSlots = async (force = false) => {
        setLoading(true);
        setError(null);
        try {
            const url = new URL(`${API_URL}/api/slots/coefficients`);
            if (force) url.searchParams.append('refresh', 'true');
            
            const res = await fetch(url, { headers: getTgHeaders() });
            
            if (res.status === 401 || res.status === 403) {
                // Token error handling if needed
            }
            if (!res.ok) throw new Error("Не удалось загрузить данные");
            
            const json = await res.json();
            setData(Array.isArray(json) ? json : []);
        } catch (e) {
            setError(e.message);
            // Fallback mock data for demo if API fails
            // setData([]); 
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
            // Безопасная проверка имени склада
            const matchSearch = item.warehouseName?.toLowerCase().includes(search.toLowerCase()) || false;
            const matchFree = onlyFree ? item.coefficient === 0 : true;
            
            // Безопасная проверка типа короба (с дефолтом)
            const typeName = item.boxTypeName?.toLowerCase() || "короба";
            
            let matchType = true;
            if (boxType === 'pallet') matchType = typeName.includes('моно');
            if (boxType === 'box') matchType = !typeName.includes('моно');

            return matchSearch && matchFree && matchType;
        });

        // Group by Warehouse
        const grouped = {};
        filtered.forEach(item => {
            // Группируем, если есть имя склада
            const wName = item.warehouseName || "Неизвестный склад";
            
            if (!grouped[wName]) {
                grouped[wName] = {
                    name: wName,
                    id: item.warehouseID,
                    slots: []
                };
            }
            grouped[wName].slots.push(item);
        });

        // Convert to array and sort by best coefficient
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
            <div className="flex items-center gap-3">
                 {onNavigate && (
                    <button onClick={() => onNavigate('home')} className="p-2 bg-white rounded-xl border border-slate-100 shadow-sm active:scale-95">
                        <ArrowLeft size={20} className="text-slate-500"/>
                    </button>
                 )}
                <div>
                    <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2">
                        <Calendar className="text-cyan-500"/> Слоты
                    </h1>
                    <p className="text-slate-500 text-xs font-medium">
                        Лимиты и коэффициенты приемки
                    </p>
                </div>
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
                        className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-xl font-bold text-sm outline-none focus:ring-2 focus:ring-cyan-500 transition-all"
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
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap bg-white text-slate-600 border border-slate-200 active:scale-95"
                    >
                        <Package size={14}/>
                        {boxType === 'all' ? 'Все типы' : boxType === 'pallet' ? 'Монопаллеты' : 'Короба'}
                    </button>
                </div>
            </div>

            {/* Results List */}
            {loading && !data.length ? (
                <div className="py-20 flex flex-col items-center text-slate-400">
                    <Loader2 className="animate-spin mb-3 text-cyan-500" size={32}/>
                    <span className="text-xs font-bold">Получаем данные от Wildberries...</span>
                </div>
            ) : error ? (
                <div className="bg-rose-50 text-rose-600 p-4 rounded-xl text-sm font-bold text-center border border-rose-100">
                    <p className="mb-2">{error}</p>
                    <p className="text-xs opacity-75">Проверьте API токен в профиле.</p>
                    <button onClick={() => loadSlots(true)} className="mt-3 px-4 py-2 bg-white rounded-lg shadow-sm text-xs font-bold border border-rose-200 text-rose-700">Повторить</button>
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
                                    <MapPin size={16} className="text-cyan-500" />
                                    <span className="font-bold text-slate-800">{wh.name}</span>
                                </div>
                                <div className="text-[10px] font-bold text-slate-400 uppercase bg-slate-100 px-2 py-1 rounded">
                                    {wh.slots[0]?.boxTypeName || "Слот"}
                                </div>
                            </div>

                            {/* Dates Grid */}
                            <div className="p-3">
                                <div className="grid grid-cols-4 gap-2">
                                    {wh.slots.slice(0, 12).map((slot, idx) => {
                                        const d = new Date(slot.date);
                                        const isToday = d.toDateString() === new Date().toDateString();
                                        
                                        return (
                                            <div key={idx} className={`flex flex-col items-center p-2 rounded-xl border ${isToday ? 'bg-cyan-50 border-cyan-100' : 'bg-slate-50 border-slate-100'}`}>
                                                <div className={`text-[10px] font-bold mb-1 ${isToday ? 'text-cyan-600' : 'text-slate-400'}`}>
                                                    {d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                                                </div>
                                                <CoefficientBadge value={slot.coefficient} />
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default SlotsPage;