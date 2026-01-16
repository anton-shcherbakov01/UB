import React, { useState, useEffect, useMemo } from 'react';
import { 
    Calendar, Package, Search, Filter, 
    AlertTriangle, CheckCircle2, Loader2, 
    MapPin, XCircle, ArrowLeft, Truck
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

// --- Компоненты UI ---

const CoefficientBadge = ({ value }) => {
    // Обработка статуса "Закрыто" (-1)
    if (value === -1) {
        return (
            <div className="px-2 py-1 rounded-lg border border-slate-200 bg-slate-100 text-slate-400 text-[10px] font-bold flex items-center gap-1">
                <XCircle size={10}/> Закрыто
            </div>
        );
    }

    let style = "bg-slate-100 text-slate-500 border-slate-200"; 
    
    if (value === 0) style = "bg-emerald-100 text-emerald-700 border-emerald-200 shadow-sm shadow-emerald-100";
    else if (value === 1) style = "bg-blue-50 text-blue-700 border-blue-100";
    else if (value > 1 && value <= 5) style = "bg-amber-50 text-amber-700 border-amber-100";
    else if (value > 5) style = "bg-rose-50 text-rose-700 border-rose-100 font-black animate-pulse";

    return (
        <div className={`px-2 py-1 rounded-lg border text-xs font-black flex items-center justify-center gap-1 min-w-[40px] ${style}`}>
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
    const [boxType, setBoxType] = useState('all'); // 'all', 'box', 'pallet'

    const loadSlots = async (force = false) => {
        setLoading(true);
        setError(null);
        try {
            const url = new URL(`${API_URL}/api/slots/coefficients`);
            if (force) url.searchParams.append('refresh', 'true');
            
            const res = await fetch(url, { headers: getTgHeaders() });
            
            if (!res.ok) throw new Error("Не удалось загрузить данные");
            
            const json = await res.json();
            setData(Array.isArray(json) ? json : []);
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

    // Обработка данных
    const processedData = useMemo(() => {
        if (!data) return [];

        // 1. Фильтрация
        let filtered = data.filter(item => {
            const matchSearch = item.warehouseName?.toLowerCase().includes(search.toLowerCase());
            
            // Логика "Бесплатно": только если коэффициент 0. 
            // Если -1 (закрыто), то скрываем при включенном фильтре.
            const matchFree = onlyFree ? item.coefficient === 0 : true;
            
            // Определение типа по ID или имени
            const typeName = item.boxTypeName?.toLowerCase() || "короба";
            const isPallet = item.boxTypeID === 2 || typeName.includes('моно') || typeName.includes('паллет');
            
            let matchType = true;
            if (boxType === 'pallet') matchType = isPallet;
            if (boxType === 'box') matchType = !isPallet;

            return matchSearch && matchFree && matchType;
        });

        // 2. Группировка по складам
        const grouped = {};
        
        filtered.forEach(item => {
            const wName = item.warehouseName || "Неизвестный склад";
            
            if (!grouped[wName]) {
                grouped[wName] = {
                    name: wName,
                    id: item.warehouseID,
                    isSortingCenter: item.isSortingCenter, // Берем флаг из API
                    slotsMap: {} // Используем Map для дедупликации дат
                };
            }

            // 3. Дедупликация дат
            // API может вернуть несколько записей на одну дату (разные ворота или типы коробов).
            // Если выбран фильтр "Все", мы можем получить две записи на 16 января.
            // Логика: берем ЛУЧШИЙ коэффициент для этой даты.
            const dateKey = item.date;
            const existing = grouped[wName].slotsMap[dateKey];

            if (!existing) {
                grouped[wName].slotsMap[dateKey] = item;
            } else {
                // Если запись уже есть, сравниваем коэффициенты
                // Если текущий -1 (закрыто), а новый нормальный -> берем новый
                // Если оба нормальные -> берем меньший
                const currCoeff = existing.coefficient;
                const newCoeff = item.coefficient;

                if (currCoeff === -1 && newCoeff !== -1) {
                    grouped[wName].slotsMap[dateKey] = item;
                } else if (newCoeff !== -1 && newCoeff < currCoeff) {
                    grouped[wName].slotsMap[dateKey] = item;
                }
            }
        });

        // Превращаем Map обратно в массив для рендера
        const result = Object.values(grouped).map(wh => ({
            ...wh,
            slots: Object.values(wh.slotsMap).sort((a, b) => new Date(a.date) - new Date(b.date))
        }));

        // Сортируем склады: сначала бесплатные слоты в ближайшие дни
        return result.sort((a, b) => {
            // Простая эвристика: сумма первых 3 коэффициентов (где -1 считается как 100)
            const getScore = (slots) => slots.slice(0, 3).reduce((acc, s) => acc + (s.coefficient === -1 ? 50 : s.coefficient), 0);
            return getScore(a.slots) - getScore(b.slots);
        });

    }, [data, search, onlyFree, boxType]);

    if (!user?.has_wb_token) {
        return (
            <div className="flex flex-col items-center justify-center h-[60vh] p-6 text-center animate-in fade-in">
                <div className="bg-slate-100 p-4 rounded-full mb-4"><Package size={32} className="text-slate-400"/></div>
                <h3 className="font-bold text-lg mb-2">Подключите API</h3>
                <p className="text-slate-500 text-sm mb-6 max-w-xs">Данные по слотам доступны только после ввода токена в профиле.</p>
                <button onClick={() => onNavigate('profile')} className="bg-indigo-600 text-white px-6 py-3 rounded-xl font-bold text-sm shadow-lg shadow-indigo-200 active:scale-95 transition-all">
                    В профиль
                </button>
            </div>
        );
    }

    return (
        <div className="p-4 pb-32 space-y-6 animate-in slide-in-from-right-4 fade-in duration-300">
            
            {/* Header */}
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
                    <p className="text-slate-500 text-xs font-medium">Лимиты приемки WB</p>
                </div>
            </div>

            {/* Controls */}
            <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm space-y-4">
                <div className="relative">
                    <Search className="absolute left-3 top-3.5 text-slate-400" size={18} />
                    <input 
                        type="text" 
                        placeholder="Поиск склада (Коледино, Тула...)" 
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-xl font-bold text-sm outline-none focus:ring-2 focus:ring-cyan-500 transition-all"
                    />
                </div>

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
                        Бесплатные (x0)
                    </button>

                    <button 
                        onClick={() => setBoxType(boxType === 'all' ? 'pallet' : boxType === 'pallet' ? 'box' : 'all')}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap bg-white text-slate-600 border border-slate-200 active:scale-95"
                    >
                        <Package size={14}/>
                        {boxType === 'all' ? 'Короба + Паллеты' : boxType === 'pallet' ? 'Только Паллеты' : 'Только Короба'}
                    </button>
                </div>
            </div>

            {/* Легенда (упрощенная) */}
            <div className="flex gap-2 text-[10px] text-slate-400 px-2">
                <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-emerald-500"></div>Бесплатно</span>
                <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-blue-500"></div>База</span>
                <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-slate-300"></div>Закрыто</span>
            </div>

            {/* Список складов */}
            {loading && !data.length ? (
                <div className="py-20 flex flex-col items-center text-slate-400">
                    <Loader2 className="animate-spin mb-3 text-cyan-500" size={32}/>
                    <span className="text-xs font-bold">Обновляем тарифы...</span>
                </div>
            ) : processedData.length === 0 ? (
                <div className="py-20 text-center text-slate-400">
                    <div className="bg-slate-50 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Search size={24} className="opacity-50"/>
                    </div>
                    <p className="font-bold text-sm">Нет доступных складов</p>
                </div>
            ) : (
                <div className="space-y-4">
                    {processedData.map((wh) => (
                        <div key={wh.id} className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                            {/* Warehouse Header */}
                            <div className="p-4 bg-slate-50/50 border-b border-slate-100 flex justify-between items-center">
                                <div className="flex items-center gap-2">
                                    <MapPin size={18} className="text-cyan-600" />
                                    <div>
                                        <div className="font-bold text-slate-800 text-sm flex items-center gap-2">
                                            {wh.name}
                                            {/* Бейдж Транзитного склада (СЦ) */}
                                            {wh.isSortingCenter && (
                                                <span className="bg-indigo-100 text-indigo-700 text-[9px] px-1.5 py-0.5 rounded font-black flex items-center gap-1">
                                                    <Truck size={10}/> СЦ
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Dates Grid */}
                            <div className="p-3">
                                <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
                                    {wh.slots.slice(0, 12).map((slot, idx) => {
                                        const d = new Date(slot.date);
                                        const isToday = d.toDateString() === new Date().toDateString();
                                        
                                        return (
                                            <div key={idx} className={`flex flex-col items-center justify-center p-2 rounded-xl border min-h-[50px] ${isToday ? 'bg-cyan-50 border-cyan-200' : 'bg-slate-50 border-slate-100'}`}>
                                                <div className={`text-[10px] font-bold mb-1.5 ${isToday ? 'text-cyan-700' : 'text-slate-400'}`}>
                                                    {d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                                                </div>
                                                <CoefficientBadge value={slot.coefficient} />
                                            </div>
                                        );
                                    })}
                                </div>
                                {wh.slots.length === 0 && (
                                    <div className="text-center text-xs text-slate-400 py-2">Нет данных на ближайшие дни</div>
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