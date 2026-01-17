import React, { useState, useEffect, useMemo } from 'react';
import { 
    Calendar, Package, Search, Filter, 
    CheckCircle2, Loader2, MapPin, XCircle, 
    ArrowLeft, Truck, Bell, BellRing, Trash2, HelpCircle
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

// --- Components ---

const CoefficientBadge = ({ value }) => {
    if (value === -1) {
        return (
            <div className="px-2 py-1 rounded-lg border border-slate-200 bg-slate-50 text-slate-400 text-[10px] font-bold flex items-center justify-center gap-1 min-w-[40px]">
                <XCircle size={10}/>
            </div>
        );
    }
    
    let style = "bg-slate-100 text-slate-500 border-slate-200"; 
    if (value === 0) style = "bg-emerald-100 text-emerald-700 border-emerald-200 shadow-sm";
    else if (value === 1) style = "bg-blue-50 text-blue-700 border-blue-100";
    else if (value > 1 && value <= 5) style = "bg-amber-50 text-amber-700 border-amber-100";
    else if (value > 5) style = "bg-rose-50 text-rose-700 border-rose-100 font-black";

    return (
        <div className={`px-2 py-1 rounded-lg border text-xs font-black flex items-center justify-center gap-1 min-w-[40px] ${style}`}>
            {value === 0 ? <CheckCircle2 size={12}/> : null}
            x{value}
        </div>
    );
};

const SlotsPage = ({ user, onNavigate }) => {
    const [data, setData] = useState([]);
    const [monitors, setMonitors] = useState([]); // Список подписок
    const [loading, setLoading] = useState(false);
    const [monitorsLoading, setMonitorsLoading] = useState(false);

    // Filters
    const [search, setSearch] = useState('');
    const [onlyFree, setOnlyFree] = useState(false);
    const [boxType, setBoxType] = useState('all');

    // Init
    useEffect(() => {
        if (user?.has_wb_token) {
            loadSlots();
            loadMonitors();
        }
    }, [user]);

    const loadSlots = async (force = false) => {
        setLoading(true);
        try {
            const url = new URL(`${API_URL}/api/slots/coefficients`);
            if (force) url.searchParams.append('refresh', 'true');
            const res = await fetch(url, { headers: getTgHeaders() });
            if (res.ok) setData(await res.json());
        } catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const loadMonitors = async () => {
        setMonitorsLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/slots/monitors`, { headers: getTgHeaders() });
            if (res.ok) setMonitors(await res.json());
        } catch (e) { console.error(e); } finally { setMonitorsLoading(false); }
    };

    const toggleMonitor = async (wh) => {
        const isMonitored = monitors.some(m => m.warehouse_id === wh.id);
        
        // Optimistic update
        if (isMonitored) {
            setMonitors(prev => prev.filter(m => m.warehouse_id !== wh.id));
            await fetch(`${API_URL}/api/slots/monitors/${wh.id}`, { 
                method: 'DELETE', headers: getTgHeaders() 
            });
        } else {
            const newMonitor = { warehouse_id: wh.id, warehouse_name: wh.name, target_coefficient: 0 };
            setMonitors(prev => [...prev, newMonitor]);
            await fetch(`${API_URL}/api/slots/monitors`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(newMonitor)
            });
            alert(`Бот будет следить за бесплатными слотами на складе "${wh.name}"`);
        }
    };

    // Data Processing
    const processedData = useMemo(() => {
        if (!data) return [];

        let filtered = data.filter(item => {
            const matchSearch = item.warehouseName?.toLowerCase().includes(search.toLowerCase());
            const matchFree = onlyFree ? item.coefficient === 0 : true;
            
            const typeName = item.boxTypeName?.toLowerCase() || "короба";
            const isPallet = item.boxTypeID === 2 || typeName.includes('моно');
            
            let matchType = true;
            if (boxType === 'pallet') matchType = isPallet;
            if (boxType === 'box') matchType = !isPallet;

            return matchSearch && matchFree && matchType;
        });

        // Grouping & Deduplication
        const grouped = {};
        
        filtered.forEach(item => {
            const wName = item.warehouseName || "Неизвестный";
            
            if (!grouped[wName]) {
                grouped[wName] = {
                    name: wName,
                    id: item.warehouseID,
                    isSortingCenter: item.isSortingCenter,
                    slotsMap: {}
                };
            }

            const dateKey = item.date;
            const existing = grouped[wName].slotsMap[dateKey];

            // Logic: Pick the BEST coefficient for this date
            if (!existing) {
                grouped[wName].slotsMap[dateKey] = item;
            } else {
                const curr = existing.coefficient;
                const next = item.coefficient;
                // If current is Closed (-1) and new is Open -> Replace
                // If both Open -> Pick smaller
                if ((curr === -1 && next !== -1) || (next !== -1 && next < curr)) {
                    grouped[wName].slotsMap[dateKey] = item;
                }
            }
        });

        const result = Object.values(grouped).map(wh => ({
            ...wh,
            slots: Object.values(wh.slotsMap).sort((a, b) => new Date(a.date) - new Date(b.date))
        }));

        // Sort: Tracked first -> Free slots -> Others
        return result.sort((a, b) => {
            const isAMonitored = monitors.some(m => m.warehouse_id === a.id);
            const isBMonitored = monitors.some(m => m.warehouse_id === b.id);
            if (isAMonitored && !isBMonitored) return -1;
            if (!isAMonitored && isBMonitored) return 1;

            const scoreA = a.slots.slice(0,3).reduce((acc,s) => acc + (s.coefficient === -1 ? 50 : s.coefficient), 0);
            const scoreB = b.slots.slice(0,3).reduce((acc,s) => acc + (s.coefficient === -1 ? 50 : s.coefficient), 0);
            return scoreA - scoreB;
        });

    }, [data, search, onlyFree, boxType, monitors]);

    if (!user?.has_wb_token) {
        return (
            <div className="flex flex-col items-center justify-center h-[60vh] p-6 text-center animate-in fade-in">
                <div className="bg-slate-100 p-4 rounded-full mb-4"><Package size={32} className="text-slate-400"/></div>
                <h3 className="font-bold text-lg mb-2">Подключите API</h3>
                <p className="text-slate-500 text-sm mb-6 max-w-xs">Требуется токен "Статистика" и "Поставки".</p>
                <button onClick={() => onNavigate('profile')} className="bg-indigo-600 text-white px-6 py-3 rounded-xl font-bold text-sm shadow-lg">В профиль</button>
            </div>
        );
    }

    return (
        <div className="p-4 pb-32 space-y-4 animate-in slide-in-from-right-4 fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 flex-1">
                    {onNavigate && <button onClick={() => onNavigate('home')} className="p-2 bg-white rounded-xl border border-slate-100"><ArrowLeft size={20} className="text-slate-500"/></button>}
                    <div>
                        <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2">Слоты</h1>
                        <p className="text-slate-500 text-xs font-medium">Мониторинг приемки</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className="group relative">
                        <button className="p-2 bg-white rounded-xl border border-slate-100 text-slate-400 hover:text-indigo-600 transition-colors">
                            <HelpCircle size={20}/>
                        </button>
                        <div className="hidden group-hover:block absolute bottom-full right-0 mb-2 w-64 p-3 bg-slate-900 text-white text-xs rounded-xl shadow-xl z-50">
                            <div className="font-bold mb-2">Коэффициенты приемки</div>
                            <p className="mb-2">Коэффициент показывает доступность слотов на складе:</p>
                            <ul className="space-y-1 list-disc list-inside text-[10px]">
                                <li><strong>x0</strong> - Бесплатные слоты (зеленый)</li>
                                <li><strong>x1</strong> - Низкая загрузка (синий)</li>
                                <li><strong>x2-5</strong> - Средняя загрузка (желтый)</li>
                                <li><strong>x6+</strong> - Высокая загрузка (красный)</li>
                                <li><strong>—</strong> - Склад закрыт</li>
                            </ul>
                            <p className="mt-2 text-[10px]">Подпишитесь на уведомления, чтобы получать информацию о появлении свободных слотов.</p>
                            <div className="absolute bottom-0 right-4 transform translate-y-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-slate-900"></div>
                        </div>
                    </div>
                    {/* Active Monitors Counter */}
                    {monitors.length > 0 && (
                        <div className="bg-indigo-600 text-white px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg shadow-indigo-200">
                            <BellRing size={14} className="animate-pulse"/>
                            {monitors.length} на слежении
                        </div>
                    )}
                </div>
            </div>

            {/* Controls */}
            <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm space-y-3">
                <div className="relative">
                    <Search className="absolute left-3 top-3.5 text-slate-400" size={18} />
                    <input 
                        type="text" placeholder="Поиск склада..." value={search} onChange={e => setSearch(e.target.value)}
                        className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-xl font-bold text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                </div>
                <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar">
                    <button onClick={() => setOnlyFree(!onlyFree)} className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap border transition-all ${onlyFree ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-200'}`}>
                        {onlyFree ? <CheckCircle2 size={14}/> : <Filter size={14}/>} Бесплатные
                    </button>
                    <button onClick={() => setBoxType(boxType === 'all' ? 'pallet' : boxType === 'pallet' ? 'box' : 'all')} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap bg-white text-slate-600 border border-slate-200">
                        <Package size={14}/> {boxType === 'all' ? 'Все типы' : boxType === 'pallet' ? 'Паллеты' : 'Короба'}
                    </button>
                </div>
            </div>

            {/* List */}
            {loading && !data.length ? (
                <div className="py-20 text-center text-slate-400"><Loader2 className="animate-spin mx-auto mb-2 text-indigo-500"/>Обновляем тарифы...</div>
            ) : processedData.length === 0 ? (
                <div className="py-20 text-center text-slate-400 font-bold text-sm">Нет данных</div>
            ) : (
                <div className="space-y-3">
                    {processedData.map((wh) => {
                        const isMonitored = monitors.some(m => m.warehouse_id === wh.id);
                        return (
                            <div key={wh.id} className={`bg-white rounded-2xl border shadow-sm overflow-hidden transition-all ${isMonitored ? 'border-indigo-500 ring-1 ring-indigo-500 shadow-indigo-100' : 'border-slate-100'}`}>
                                <div className="p-3 bg-slate-50/50 border-b border-slate-100 flex justify-between items-center">
                                    <div className="flex items-center gap-2">
                                        <MapPin size={16} className={isMonitored ? "text-indigo-600" : "text-slate-400"} />
                                        <div className="font-bold text-slate-800 text-sm flex items-center gap-2">
                                            {wh.name}
                                            {wh.isSortingCenter && <span className="bg-slate-200 text-slate-600 text-[9px] px-1.5 rounded font-black">СЦ</span>}
                                        </div>
                                    </div>
                                    <button 
                                        onClick={() => toggleMonitor(wh)}
                                        className={`p-2 rounded-xl transition-all active:scale-95 ${isMonitored ? 'bg-indigo-100 text-indigo-600' : 'bg-white border border-slate-200 text-slate-400 hover:text-indigo-500'}`}
                                    >
                                        {isMonitored ? <BellRing size={16} className="fill-current"/> : <Bell size={16}/>}
                                    </button>
                                </div>
                                <div className="p-3">
                                    <div className="grid grid-cols-5 gap-2">
                                        {wh.slots.slice(0, 10).map((slot, idx) => {
                                            const d = new Date(slot.date);
                                            const isToday = d.toDateString() === new Date().toDateString();
                                            return (
                                                <div key={idx} className={`flex flex-col items-center justify-center p-1.5 rounded-lg border min-h-[46px] ${isToday ? 'bg-indigo-50 border-indigo-100' : 'bg-slate-50 border-slate-100'}`}>
                                                    <div className={`text-[9px] font-bold mb-1 ${isToday ? 'text-indigo-700' : 'text-slate-400'}`}>
                                                        {d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                                                    </div>
                                                    <CoefficientBadge value={slot.coefficient} />
                                                </div>
                                            );
                                        })}
                                    </div>
                                    {isMonitored && <div className="mt-2 text-[10px] text-indigo-600 bg-indigo-50 p-2 rounded text-center font-bold">Бот следит за этим складом (x0)</div>}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default SlotsPage;