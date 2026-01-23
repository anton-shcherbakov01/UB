import React, { useState, useEffect, useMemo } from 'react';
import { 
    Calendar, Package, Search, Filter, 
    CheckCircle2, Loader2, MapPin, XCircle, 
    ArrowLeft, Truck, Bell, BellRing, Trash2, HelpCircle,
    Zap, Lock, X, Plus
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

// --- COMPONENTS ---

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

const CreateTaskModal = ({ isOpen, onClose, warehouses, userPlan, onSave }) => {
    if (!isOpen) return null;

    // Default values
    const [wh, setWh] = useState(warehouses[0]?.name || '');
    const [boxType, setBoxType] = useState(1); // 1-Box, 2-Pallet
    const [dates, setDates] = useState({ 
        from: new Date().toISOString().split('T')[0], 
        to: new Date(Date.now() + 86400000 * 7).toISOString().split('T')[0] 
    });
    const [coeff, setCoeff] = useState(0);
    const [autoBook, setAutoBook] = useState(false);
    const [preorderId, setPreorderId] = useState('');

    const isPro = userPlan === 'analyst' || userPlan === 'strategist';

    const handleSubmit = () => {
        // Find ID by name
        const selectedWh = warehouses.find(w => w.name === wh);
        if (!selectedWh) {
            alert("Выберите склад из списка");
            return;
        }

        const payload = {
            warehouse_id: selectedWh.id,
            warehouse_name: selectedWh.name,
            box_type_id: Number(boxType),
            date_from: new Date(dates.from).toISOString(),
            date_to: new Date(dates.to).toISOString(),
            target_coefficient: Number(coeff),
            auto_book: autoBook,
            preorder_id: autoBook ? Number(preorderId) : null
        };
        onSave(payload);
    };

    return (
        <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4 animate-in fade-in" onClick={onClose}>
            <div className="bg-white w-full max-w-md rounded-t-[32px] sm:rounded-[32px] p-6 shadow-2xl relative animate-in slide-in-from-bottom" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center mb-6">
                    <h3 className="font-bold text-xl text-slate-800 flex items-center gap-2">
                        <Zap size={24} className="text-amber-500 fill-current"/>
                        Поймать слот
                    </h3>
                    <button onClick={onClose} className="p-2 bg-slate-100 rounded-full hover:bg-slate-200 transition-colors">
                        <X size={20}/>
                    </button>
                </div>

                <div className="space-y-5 mb-6 max-h-[70vh] overflow-y-auto custom-scrollbar pr-1">
                    {/* Склад */}
                    <div>
                        <label className="text-[10px] font-bold text-slate-400 uppercase mb-1.5 block tracking-wide">Склад</label>
                        <div className="relative">
                            <select 
                                value={wh} 
                                onChange={e => setWh(e.target.value)} 
                                className="w-full p-4 bg-slate-50 rounded-xl font-bold text-slate-800 border-none outline-none appearance-none focus:ring-2 ring-indigo-100 transition-all"
                            >
                                {warehouses.map((w, idx) => <option key={`${w.id}-${idx}`} value={w.name}>{w.name}</option>)}
                            </select>
                            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                                <MapPin size={18} />
                            </div>
                        </div>
                    </div>

                    {/* Тип поставки */}
                    <div>
                        <label className="text-[10px] font-bold text-slate-400 uppercase mb-1.5 block tracking-wide">Тип поставки</label>
                        <div className="flex bg-slate-50 p-1.5 rounded-xl">
                            <button 
                                onClick={() => setBoxType(1)} 
                                className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${boxType === 1 ? 'bg-white shadow-md text-indigo-600' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                <Package size={16}/> Короба
                            </button>
                            <button 
                                onClick={() => setBoxType(2)} 
                                className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${boxType === 2 ? 'bg-white shadow-md text-indigo-600' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                <Truck size={16}/> Паллеты
                            </button>
                        </div>
                    </div>

                    {/* Даты */}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="text-[10px] font-bold text-slate-400 uppercase mb-1.5 block tracking-wide">С даты</label>
                            <input 
                                type="date" 
                                value={dates.from} 
                                onChange={e => setDates({...dates, from: e.target.value})} 
                                className="w-full p-3 bg-slate-50 rounded-xl font-bold text-sm outline-none focus:ring-2 ring-indigo-100 transition-all text-center"
                            />
                        </div>
                        <div>
                            <label className="text-[10px] font-bold text-slate-400 uppercase mb-1.5 block tracking-wide">По дату</label>
                            <input 
                                type="date" 
                                value={dates.to} 
                                onChange={e => setDates({...dates, to: e.target.value})} 
                                className="w-full p-3 bg-slate-50 rounded-xl font-bold text-sm outline-none focus:ring-2 ring-indigo-100 transition-all text-center"
                            />
                        </div>
                    </div>

                    {/* Коэффициент */}
                    <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                        <label className="text-[10px] font-bold text-slate-400 uppercase mb-3 flex justify-between tracking-wide">
                            <span>Макс. коэффициент</span>
                            <span className="text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">x{coeff}</span>
                        </label>
                        <input 
                            type="range" 
                            min="0" 
                            max="20" 
                            step="1"
                            value={coeff} 
                            onChange={e => setCoeff(e.target.value)} 
                            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                        />
                        <div className="flex justify-between text-[10px] text-slate-400 mt-2 font-medium">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400"></span> Бесплатно</span>
                            <span className="flex items-center gap-1">Любой <span className="w-2 h-2 rounded-full bg-rose-400"></span></span>
                        </div>
                    </div>

                    {/* Авто-бронь */}
                    <div className={`p-4 rounded-2xl border-2 transition-all ${autoBook ? 'border-emerald-500 bg-emerald-50' : 'border-slate-100 bg-white'}`}>
                        <div className="flex justify-between items-center mb-2">
                            <div className="flex items-center gap-2">
                                <label className="font-bold text-sm text-slate-800">Авто-бронирование</label>
                                {!isPro && <Lock size={14} className="text-amber-500"/>}
                            </div>
                            <div 
                                onClick={() => isPro ? setAutoBook(!autoBook) : alert("Доступно на тарифе PRO")}
                                className={`w-12 h-7 rounded-full relative transition-colors cursor-pointer border-2 border-transparent ${autoBook ? 'bg-emerald-500' : 'bg-slate-200'}`}
                            >
                                <div className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform ${autoBook ? 'translate-x-5' : ''}`}></div>
                            </div>
                        </div>
                        
                        {!isPro ? (
                            <p className="text-[10px] text-amber-600 font-medium leading-snug">
                                Функция доступна на тарифе PRO. Бот сам создаст поставку и займет слот за 1 сек.
                            </p>
                        ) : autoBook ? (
                            <div className="animate-in fade-in slide-in-from-top-2 pt-2 border-t border-emerald-200/50 mt-2">
                                <label className="text-[10px] font-bold text-emerald-700 uppercase mb-1.5 block tracking-wide">ID Плана (Preorder ID)</label>
                                <input 
                                    type="number" 
                                    placeholder="Например: 12345678" 
                                    value={preorderId}
                                    onChange={e => setPreorderId(e.target.value)}
                                    className="w-full p-3 bg-white rounded-xl border border-emerald-200 text-sm font-bold text-emerald-900 outline-none placeholder:text-emerald-300/70"
                                />
                                <p className="text-[9px] text-emerald-600 mt-1.5 flex items-center gap-1">
                                    <HelpCircle size={10}/> ID можно взять из URL на портале WB при создании плана
                                </p>
                            </div>
                        ) : (
                            <p className="text-[10px] text-slate-400 font-medium leading-snug">
                                Если выключено — бот просто пришлет уведомление в Telegram.
                            </p>
                        )}
                    </div>
                </div>

                <button 
                    onClick={handleSubmit} 
                    className="w-full bg-slate-900 text-white py-4 rounded-2xl font-bold shadow-xl active:scale-95 transition-transform flex items-center justify-center gap-2"
                >
                    <Zap size={18} className={autoBook ? "text-emerald-400 fill-current" : "text-amber-400 fill-current"}/>
                    {autoBook ? "Запустить снайпера" : "Создать задачу"}
                </button>
            </div>
        </div>
    );
};

const SlotsPage = ({ user, onNavigate }) => {
    const [data, setData] = useState([]);
    const [monitors, setMonitors] = useState([]); 
    const [loading, setLoading] = useState(false);
    
    // Filters
    const [search, setSearch] = useState('');
    const [onlyFree, setOnlyFree] = useState(false);
    const [boxType, setBoxType] = useState('all');

    // UI
    const [showModal, setShowModal] = useState(false);

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
        try {
            const res = await fetch(`${API_URL}/api/slots/monitors`, { headers: getTgHeaders() });
            if (res.ok) setMonitors(await res.json());
        } catch (e) { console.error(e); }
    };

    const handleDeleteMonitor = async (id) => {
        if(!confirm("Удалить задачу?")) return;
        setMonitors(prev => prev.filter(m => m.id !== id)); // Optimistic
        try {
            await fetch(`${API_URL}/api/slots/monitors/${id}`, { 
                method: 'DELETE', headers: getTgHeaders() 
            });
        } catch(e) { loadMonitors(); }
    };

    const handleCreateTask = async (payload) => {
        try {
            const res = await fetch(`${API_URL}/api/slots/monitors/v2`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                alert("Задача создана! Бот начал мониторинг.");
                setShowModal(false);
                loadMonitors();
            } else {
                const err = await res.json();
                alert(err.detail || "Ошибка создания задачи");
            }
        } catch (e) {
            alert("Ошибка сети");
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
            if (!existing) {
                grouped[wName].slotsMap[dateKey] = item;
            } else {
                const curr = existing.coefficient;
                const next = item.coefficient;
                if ((curr === -1 && next !== -1) || (next !== -1 && next < curr)) {
                    grouped[wName].slotsMap[dateKey] = item;
                }
            }
        });

        const result = Object.values(grouped).map(wh => ({
            ...wh,
            slots: Object.values(wh.slotsMap).sort((a, b) => new Date(a.date) - new Date(b.date))
        }));

        // Sort by "quality" (sum of first 3 days coeffs)
        return result.sort((a, b) => {
            const scoreA = a.slots.slice(0,3).reduce((acc,s) => acc + (s.coefficient === -1 ? 50 : s.coefficient), 0);
            const scoreB = b.slots.slice(0,3).reduce((acc,s) => acc + (s.coefficient === -1 ? 50 : s.coefficient), 0);
            return scoreA - scoreB;
        });

    }, [data, search, onlyFree, boxType]);

    // Unique warehouses list for Modal
    const uniqueWarehouses = useMemo(() => {
        if (!data) return [];
        const map = new Map();
        data.forEach(item => {
            if (item.warehouseName && !map.has(item.warehouseName)) {
                map.set(item.warehouseName, { id: item.warehouseID, name: item.warehouseName });
            }
        });
        return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
    }, [data]);

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

    const headerGradient = 'from-cyan-600 to-blue-600';
    const headerShadow = 'shadow-cyan-200';

    return (
        <div className="p-4 pb-32 space-y-6 animate-in slide-in-from-right-4 fade-in bg-[#F4F4F9] min-h-screen relative">
            
            <CreateTaskModal 
                isOpen={showModal} 
                onClose={() => setShowModal(false)}
                warehouses={uniqueWarehouses}
                userPlan={user.plan}
                onSave={handleCreateTask}
            />

            {/* HEADER */}
            <div className="flex justify-between items-stretch h-24 mb-6">
                 <div className={`bg-gradient-to-br ${headerGradient} p-5 rounded-[28px] text-white shadow-xl ${headerShadow} relative overflow-hidden flex-1 mr-3 flex items-center justify-between transition-colors duration-500`}>
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <Calendar size={24} className="text-white"/>
                            Слоты
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            Мониторинг приемки
                        </p>
                    </div>

                    <div className="relative z-10">
                        <button 
                            onClick={() => setShowModal(true)}
                            className="bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm"
                        >
                            <Plus size={20} strokeWidth={3} />
                        </button>
                    </div>
                    
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button 
                        onClick={() => onNavigate('home')} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95 border border-slate-100"
                      >
                          <ArrowLeft size={24}/>
                      </button>
                      <div className="group relative h-full">
                        <button className="h-full w-full bg-white rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95 border border-slate-100">
                            <HelpCircle size={24}/>
                        </button>
                        <div className="hidden group-hover:block absolute top-0 right-full mr-2 w-64 p-3 bg-slate-900 text-white text-xs rounded-xl shadow-xl z-50">
                            <div className="font-bold mb-2 text-cyan-300">Как это работает?</div>
                            <p className="mb-2">Вы можете создать задачу на автоматический поиск слота:</p>
                            <ul className="space-y-1 list-disc list-inside text-[10px] pl-1 mb-2">
                                <li><strong>Снайпер:</strong> Бот сам забронирует слот, как только он появится (тариф PRO).</li>
                                <li><strong>Монитор:</strong> Бот пришлет уведомление, когда появится слот с нужным коэффициентом.</li>
                            </ul>
                            <div className="absolute top-6 right-0 translate-x-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-l-slate-900"></div>
                        </div>
                      </div>
                 </div>
            </div>

            {/* ACTIVE MONITORS */}
            {monitors.length > 0 && (
                <div className="space-y-3">
                    <h3 className="font-bold text-slate-800 text-sm px-1 flex items-center gap-2">
                        <BellRing size={16} className="text-indigo-600"/> Активные задачи ({monitors.length})
                    </h3>
                    <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 scrollbar-hide">
                        {monitors.map(m => (
                            <div key={m.id} className={`min-w-[200px] p-3 rounded-2xl border flex flex-col justify-between relative group ${m.auto_book ? 'bg-emerald-50 border-emerald-200' : 'bg-white border-slate-200'}`}>
                                <button onClick={() => handleDeleteMonitor(m.id)} className="absolute top-2 right-2 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Trash2 size={14}/>
                                </button>
                                <div>
                                    <div className="flex items-center gap-1.5 mb-1">
                                        {m.auto_book ? <Zap size={14} className="text-emerald-500 fill-current"/> : <Bell size={14} className="text-indigo-500"/>}
                                        <span className={`text-xs font-black uppercase tracking-wide ${m.auto_book ? 'text-emerald-700' : 'text-indigo-700'}`}>
                                            {m.auto_book ? 'Авто-бронь' : 'Слежение'}
                                        </span>
                                    </div>
                                    <div className="font-bold text-sm text-slate-800 truncate pr-4">{m.warehouse_name}</div>
                                    <div className="text-[10px] text-slate-500 mt-0.5">
                                        {m.box_type_id === 2 ? 'Паллеты' : 'Короба'} • x{m.target_coefficient}
                                    </div>
                                </div>
                                <div className="mt-2 pt-2 border-t border-slate-200/50 text-[9px] font-mono text-slate-400">
                                    {new Date(m.date_from).toLocaleDateString()} - {new Date(m.date_to).toLocaleDateString()}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* CONTROLS */}
            <div className="bg-white p-4 rounded-3xl border border-slate-200 shadow-sm space-y-3">
                <div className="relative">
                    <Search className="absolute left-3 top-3.5 text-slate-400" size={18} />
                    <input 
                        type="text" placeholder="Поиск склада..." value={search} onChange={e => setSearch(e.target.value)}
                        className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-2xl font-bold text-sm outline-none focus:ring-2 focus:ring-indigo-100 transition-all border border-slate-100"
                    />
                </div>
                <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
                    <button onClick={() => setOnlyFree(!onlyFree)} className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap border transition-all active:scale-95 ${onlyFree ? 'bg-emerald-600 text-white border-emerald-600 shadow-md shadow-emerald-100' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}>
                        {onlyFree ? <CheckCircle2 size={14}/> : <Filter size={14}/>} Бесплатные
                    </button>
                    <button onClick={() => setBoxType(boxType === 'all' ? 'pallet' : boxType === 'pallet' ? 'box' : 'all')} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 transition-all active:scale-95">
                        <Package size={14}/> {boxType === 'all' ? 'Все типы' : boxType === 'pallet' ? 'Паллеты' : 'Короба'}
                    </button>
                </div>
            </div>

            {/* LIST */}
            {loading && !data.length ? (
                <div className="py-20 text-center text-slate-400 flex flex-col items-center">
                    <Loader2 className="animate-spin mb-2 text-cyan-600" size={32}/>
                    <span className="text-sm font-medium">Обновляем тарифы...</span>
                </div>
            ) : processedData.length === 0 ? (
                <div className="py-20 text-center text-slate-400 font-bold text-sm bg-white rounded-3xl border border-dashed border-slate-200">Нет данных по вашему запросу</div>
            ) : (
                <div className="space-y-3">
                    {processedData.map((wh) => {
                        const isMonitored = monitors.some(m => m.warehouse_name === wh.name);
                        return (
                            <div key={wh.id} className={`bg-white rounded-2xl border shadow-sm overflow-hidden transition-all ${isMonitored ? 'border-indigo-500 ring-1 ring-indigo-500 shadow-indigo-100' : 'border-slate-100'}`}>
                                <div className="p-3 bg-slate-50/50 border-b border-slate-100 flex justify-between items-center">
                                    <div className="flex items-center gap-2">
                                        <MapPin size={16} className={isMonitored ? "text-indigo-600" : "text-slate-400"} />
                                        <div className="font-bold text-slate-800 text-sm flex items-center gap-2">
                                            {wh.name}
                                            {wh.isSortingCenter && <span className="bg-slate-200 text-slate-600 text-[9px] px-1.5 py-0.5 rounded font-black">СЦ</span>}
                                        </div>
                                    </div>
                                    <div className="text-[10px] text-slate-400 font-medium">
                                        {wh.slots[0]?.boxTypeName || 'Короба'}
                                    </div>
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