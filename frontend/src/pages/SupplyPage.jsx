import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
    Truck, Scale, Loader2, MapPin, ArrowRight, 
    PackageCheck, AlertTriangle, Box, RefreshCw,
    Activity, Settings, X, Save, HelpCircle, Info,
    ArrowDown, FilterX, FileDown, ArrowLeft, Lock
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import AbcXyzMatrix from '../components/AbcXyzMatrix'; 

const SupplyPage = () => {
    const navigate = useNavigate();
    const [user, setUser] = useState(null);
    const [coeffs, setCoeffs] = useState([]);
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState(null);
    
    // --- STATE: МАТРИЦА ---
    const [filterGroup, setFilterGroup] = useState(null);

    // Calculator State
    const [volume, setVolume] = useState(1000);
    const [origin, setOrigin] = useState("Казань");
    const [destination, setDestination] = useState("Коледино");
    const [transitRate, setTransitRate] = useState(4.5); 
    const [calcResult, setCalcResult] = useState(null);
    const [calcLoading, setCalcLoading] = useState(false);

    // Settings State
    const [showSettings, setShowSettings] = useState(false);
    const [showHelp, setShowHelp] = useState(false);
    const [showCalcHelp, setShowCalcHelp] = useState(false);
    const [showUpgrade, setShowUpgrade] = useState(false); // Для алерта
    const [settings, setSettings] = useState({
        lead_time: 7,
        min_stock_days: 14,
        abc_a_share: 80
    });
    const [savingSettings, setSavingSettings] = useState(false);

    const defaultWarehouses = [
        "Коледино", "Казань", "Электросталь", "Тула", "Краснодар", 
        "Санкт-Петербург (Уткина Заводь)", "Екатеринбург", "Новосибирск",
        "Невинномысск", "Астана", "Минск"
    ];

    useEffect(() => {
        fetchUser();
        fetchData();
        fetchSettings();
    }, []);

    const fetchUser = async () => {
        try {
            const res = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
            if (res.ok) setUser(await res.json());
        } catch (e) { console.error(e); }
    };

    const fetchSettings = async () => {
        try {
            const res = await fetch(`${API_URL}/api/supply/settings`, { headers: getTgHeaders() });
            if (res.ok) {
                const data = await res.json();
                setSettings(data);
            }
        } catch (e) {
            console.error("Failed to load settings", e);
        }
    };

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
            const [coeffRes, analysisRes] = await Promise.all([
                 fetch(`${API_URL}/api/internal/coefficients`, { headers: getTgHeaders() }),
                 fetch(`${API_URL}/api/supply/analysis`, { headers: getTgHeaders() })
            ]);

            const cData = coeffRes.ok ? await coeffRes.json() : [];
            setCoeffs(Array.isArray(cData) ? cData : []);
            
            if (analysisRes.ok) {
                const aData = await analysisRes.json();
                setProducts(Array.isArray(aData) ? aData : []);
            } else if (analysisRes.status === 400) {
                 setError("Необходимо добавить API токен Wildberries в настройках.");
            }
        } catch (e) {
            console.error(e);
            setError("Не удалось загрузить данные.");
        } finally {
            setLoading(false);
        }
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            await fetch(`${API_URL}/api/supply/refresh`, { method: 'POST', headers: getTgHeaders() });
            await fetchData();
        } catch (e) { console.error(e); } 
        finally { setRefreshing(false); }
    };

    const handleSaveSettings = async () => {
        setSavingSettings(true);
        try {
            const res = await fetch(`${API_URL}/api/supply/settings`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            if (res.ok) {
                setShowSettings(false);
                await fetchData(); 
            }
        } catch (e) { console.error(e); } 
        finally { setSavingSettings(false); }
    };

    const handleCalculate = async () => {
        if (!volume) return;
        setCalcLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/supply/transit_calc`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ 
                    volume: Number(volume), 
                    origin: origin, 
                    destination: destination,
                    transit_rate: Number(transitRate)
                })
            });
            if (res.ok) {
                const data = await res.json();
                setCalcResult(data);
            }
        } catch(e) {
            console.error("Calculator error", e);
        } finally {
            setCalcLoading(false);
        }
    };

    const handleDownloadReport = async () => {
        if (user?.plan === 'start') {
            setShowUpgrade(true);
            return;
        }
        try {
            const token = window.Telegram?.WebApp?.initData || '';
            const url = `${API_URL}/api/supply/report/supply-pdf?x_tg_data=${encodeURIComponent(token)}`;
            window.open(url, '_blank');
        } catch (e) {
            alert('Не удалось скачать PDF: ' + (e.message || ''));
        }
    };

    const getWarehouseOptions = () => {
        if (coeffs.length > 0) {
            return coeffs.map(c => c.warehouseName).sort();
        }
        return defaultWarehouses.sort();
    };

    // --- LOGIC: MATRIX & FILTERING ---
    const matrixData = useMemo(() => {
        if (!products.length) return null;
        const summary = {};
        products.forEach(p => {
            const group = `${p.abc || 'C'}${p.xyz || 'Z'}`; 
            summary[group] = (summary[group] || 0) + 1;
        });
        return { summary };
    }, [products]);

    const filteredProducts = useMemo(() => {
        if (!filterGroup) return products;
        return products.filter(p => {
            const group = `${p.abc || 'C'}${p.xyz || 'Z'}`;
            return group === filterGroup;
        });
    }, [products, filterGroup]);


    // --- Components ---

    const UpgradeModal = () => {
        if (!showUpgrade) return null;
        return (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setShowUpgrade(false)}>
                <div className="bg-white rounded-3xl w-full max-w-xs p-6 shadow-2xl animate-in zoom-in-95 relative overflow-hidden" onClick={e => e.stopPropagation()}>
                     <div className="absolute top-0 right-0 w-32 h-32 bg-amber-100 rounded-full -mr-16 -mt-16 blur-2xl"></div>
                     
                     <div className="relative z-10 text-center">
                        <div className="w-16 h-16 bg-amber-50 rounded-full flex items-center justify-center mx-auto mb-4 text-amber-500 border border-amber-100 shadow-sm">
                            <Lock size={32} />
                        </div>
                        <h3 className="text-xl font-black text-slate-800 mb-2">Доступ закрыт</h3>
                        <p className="text-sm text-slate-500 mb-6 leading-relaxed font-medium">
                            Скачивание PDF-отчетов по поставкам доступно на тарифе <span className="font-bold text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">PRO</span> и выше.
                        </p>
                        
                        <div className="space-y-3">
                             <button onClick={() => window.Telegram?.WebApp?.openLink('https://t.me/WbAnalyticsBot')} className="w-full bg-slate-900 text-white py-3.5 rounded-2xl font-bold shadow-lg shadow-slate-200 active:scale-95 transition-all">
                                Обновить тариф
                             </button>
                             <button onClick={() => setShowUpgrade(false)} className="w-full bg-white text-slate-500 py-3.5 rounded-2xl font-bold border border-slate-200 active:scale-95 transition-all hover:bg-slate-50">
                                Понятно
                             </button>
                        </div>
                     </div>
                </div>
            </div>
        )
    };

    const InfoTooltip = ({ text }) => (
        <div className="group relative inline-flex ml-1 align-middle">
            <Info size={14} className="text-slate-400 cursor-help" />
            <div className="hidden group-hover:block absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-slate-800 text-white text-[10px] rounded-lg shadow-xl whitespace-nowrap z-[100]">
                {text}
                <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800"></div>
            </div>
        </div>
    );

    const HelpModal = () => {
        if (!showHelp) return null;
        return (
            <div className="fixed top-0 left-0 right-0 bottom-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setShowHelp(false)}>
                <div className="bg-white rounded-3xl w-full max-w-sm shadow-2xl p-6 space-y-4 max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                            <HelpCircle size={20} className="text-indigo-600"/> Справочник
                        </h3>
                        <button onClick={() => setShowHelp(false)} className="p-2 bg-slate-100 rounded-full hover:bg-slate-200 transition-colors">
                            <X size={16}/>
                        </button>
                    </div>
                    
                    <div className="space-y-3 text-sm text-slate-600">
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1">Velocity (Скорость)</div>
                            Среднее количество продаж в день за последние 30 дней.
                        </div>
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1">Lead Time (Срок поставки)</div>
                            Время (в днях) от заказа товара у поставщика до его появления на складе WB.
                        </div>
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1">ROP (Точка заказа)</div>
                            <div className="text-xs mb-1 italic text-slate-400">Reorder Point</div>
                            Критический остаток. Если товара меньше этого числа — вы рискуете уйти в Out-of-Stock пока едет новая партия.
                        </div>
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1">ABC/XYZ Анализ</div>
                            <ul className="list-disc list-inside space-y-1 mt-1 text-xs">
                                <li><b>A-C</b> - Доля в выручке (A-много, C-мало).</li>
                                <li><b>X-Z</b> - Стабильность спроса (X-стабильно, Z-скачки).</li>
                            </ul>
                        </div>
                    </div>
                    
                    <button onClick={() => setShowHelp(false)} className="w-full bg-slate-900 text-white py-3 rounded-xl font-bold active:scale-95 transition-transform">
                        Понятно
                    </button>
                </div>
            </div>
        );
    }
    
    const CalcHelpModal = () => {
        if (!showCalcHelp) return null;
        return (
            <div className="fixed top-0 left-0 right-0 bottom-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setShowCalcHelp(false)}>
                <div className="bg-white rounded-3xl w-full max-w-sm shadow-2xl p-6 space-y-4 max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                            <Scale size={20} className="text-indigo-600"/> Транзит vs Прямая
                        </h3>
                        <button onClick={() => setShowCalcHelp(false)} className="p-2 bg-slate-100 rounded-full hover:bg-slate-200 transition-colors">
                            <X size={16}/>
                        </button>
                    </div>
                    
                    <div className="space-y-3 text-sm text-slate-600">
                         <p>
                             Калькулятор помогает понять, как дешевле отправить товар на склад WB.
                         </p>
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1 flex items-center gap-2"><MapPin size={14}/> Прямая (Direct)</div>
                            Вы нанимаете машину и везете товар сразу в Москву (Коледино). Это быстро, но дорого для малых партий.
                        </div>
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1 flex items-center gap-2"><Truck size={14}/> Транзит (Cross-Docking)</div>
                            Вы сдаете товар на ближайший склад (например, в Казани), а WB сам везет его в Москву. Это дольше, но часто дешевле.
                        </div>
                        <div className="bg-amber-50 p-3 rounded-xl border border-amber-100 text-amber-800 text-xs font-medium">
                            💡 <b>Совет:</b> Если партия меньше 3-5 паллет, транзит почти всегда выгоднее.
                        </div>
                    </div>
                    
                    <button onClick={() => setShowCalcHelp(false)} className="w-full bg-slate-900 text-white py-3 rounded-xl font-bold active:scale-95 transition-transform">
                        Ясно
                    </button>
                </div>
            </div>
        );
    }

    const SettingsModal = () => {
        if (!showSettings) return null;
        return (
            <div className="fixed top-0 left-0 right-0 bottom-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
                <div className="bg-white rounded-3xl w-full max-w-sm shadow-2xl p-6 space-y-4 max-h-[85vh] overflow-y-auto">
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                            <Settings size={20} className="text-slate-500"/> Настройки логистики
                        </h3>
                        <button onClick={() => setShowSettings(false)} className="p-2 bg-slate-100 rounded-full hover:bg-slate-200 transition-colors">
                            <X size={16}/>
                        </button>
                    </div>

                    <div className="space-y-4">
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="flex justify-between mb-1">
                                <label className="text-xs font-bold text-slate-500 uppercase flex items-center">
                                    Срок поставки
                                </label>
                                <span className="text-[10px] font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">Lead Time</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <input 
                                    type="number" 
                                    value={settings.lead_time}
                                    onChange={(e) => setSettings({...settings, lead_time: Number(e.target.value)})}
                                    className="w-full bg-white p-2 rounded-lg font-bold text-slate-800 border border-slate-200 focus:outline-indigo-500 focus:ring-2 ring-indigo-100 transition-all"
                                />
                                <span className="text-xs font-bold text-slate-400">дней</span>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                                <Info size={10}/> Время доставки от поставщика до склада WB.
                            </p>
                        </div>

                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-xs font-bold text-slate-500 uppercase block mb-1">Страховой запас</label>
                            <div className="flex items-center gap-2">
                                <input 
                                    type="number" 
                                    value={settings.min_stock_days}
                                    onChange={(e) => setSettings({...settings, min_stock_days: Number(e.target.value)})}
                                    className="w-full bg-white p-2 rounded-lg font-bold text-slate-800 border border-slate-200 focus:outline-indigo-500 focus:ring-2 ring-indigo-100 transition-all"
                                />
                                <span className="text-xs font-bold text-slate-400">дней</span>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                                <Info size={10}/> Доп. запас на случай задержек.
                            </p>
                        </div>

                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-xs font-bold text-slate-500 uppercase block mb-1">Группа А (ABC)</label>
                            <div className="flex items-center gap-2">
                                <input 
                                    type="number" 
                                    value={settings.abc_a_share}
                                    onChange={(e) => setSettings({...settings, abc_a_share: Number(e.target.value)})}
                                    className="w-full bg-white p-2 rounded-lg font-bold text-slate-800 border border-slate-200 focus:outline-indigo-500 focus:ring-2 ring-indigo-100 transition-all"
                                />
                                <span className="text-xs font-bold text-slate-400">%</span>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                                <Info size={10}/> Доля выручки для товаров группы А.
                            </p>
                        </div>
                    </div>

                    <button 
                        onClick={handleSaveSettings}
                        disabled={savingSettings}
                        className="w-full bg-slate-900 text-white py-3 rounded-xl font-bold flex justify-center items-center gap-2 active:scale-95 transition-transform"
                    >
                        {savingSettings ? <Loader2 className="animate-spin"/> : <Save size={18}/>}
                        Сохранить
                    </button>
                </div>
            </div>
        );
    };

    const StockHealthCard = ({ item }) => {
        const { 
            sku, name, size, stock, velocity, 
            days_to_stock, rop, abc, xyz, status, // <-- xyz добавлен
            recommendation, to_order 
        } = item;
        
        let colorClass = 'bg-slate-50 border-slate-100';
        let textClass = 'text-slate-600';
        let icon = <Box size={16}/>;
        let progressColor = 'bg-slate-300';

        if (status === 'out_of_stock' || status === 'critical') {
            colorClass = 'bg-red-50 border-red-100';
            textClass = 'text-red-700';
            progressColor = 'bg-red-500';
            icon = <AlertTriangle size={16} className="text-red-500"/>;
        } else if (status === 'warning') {
            colorClass = 'bg-orange-50 border-orange-100';
            textClass = 'text-orange-700';
            progressColor = 'bg-orange-500';
            icon = <Truck size={16} className="text-orange-500"/>;
        } else if (status === 'overstock') {
            colorClass = 'bg-blue-50 border-blue-100';
            textClass = 'text-blue-700';
            progressColor = 'bg-blue-500';
            icon = <Box size={16} className="text-blue-500"/>;
        } else {
            colorClass = 'bg-emerald-50 border-emerald-100';
            textClass = 'text-emerald-700';
            progressColor = 'bg-emerald-500';
            icon = <PackageCheck size={16} className="text-emerald-500"/>;
        }

        const abcColor = abc === 'A' ? 'bg-emerald-100 text-emerald-800' : 
                         abc === 'B' ? 'bg-amber-100 text-amber-800' : 
                         'bg-slate-100 text-slate-500';

        // Progress calculation
        const safeRop = rop || 0;
        const maxScale = safeRop > 0 ? safeRop * 2 : (stock > 0 ? stock * 1.5 : 10);
        const fillPercent = Math.min(100, (stock / maxScale) * 100);
        const ropPercent = safeRop > 0 ? Math.min(100, (safeRop / maxScale) * 100) : 0;

        return (
            <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 mb-3 animate-in fade-in transition-all hover:shadow-md">
                <div className="flex justify-between items-start mb-3">
                    <div className="flex-1 min-w-0 pr-2">
                        <div className="flex items-center gap-2 mb-1">
                            {/* Показываем группу ABCXYZ */}
                            <span className={`text-[10px] font-black px-1.5 py-0.5 rounded ${abcColor} flex-shrink-0 uppercase`}>
                                {abc}{xyz}
                            </span>
                            <span className="font-bold text-sm text-slate-800 truncate block">{name}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 flex gap-2 items-center">
                             <span className="bg-slate-50 px-1 rounded">SKU: {sku}</span>
                             {size && <span className="bg-slate-50 px-1 rounded">Размер: {size}</span>}
                        </div>
                    </div>
                    <div className={`px-2 py-1 rounded-lg flex items-center gap-1 text-xs font-bold ${colorClass} ${textClass} whitespace-nowrap`}>
                        {icon} 
                        {days_to_stock > 365 ? '>1 года' : `${days_to_stock} дн.`}
                    </div>
                </div>
                
                <div className="grid grid-cols-3 gap-2 mb-3">
                    <div className="bg-slate-50 p-2 rounded-xl border border-slate-100">
                        <div className="text-[9px] text-slate-400 uppercase font-bold flex items-center gap-1 mb-0.5">
                            Остаток 
                        </div>
                        <div className="font-bold text-slate-800 text-sm">{stock} шт</div>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-xl border border-slate-100">
                        <div className="text-[9px] text-slate-400 uppercase font-bold flex items-center gap-1 mb-0.5">
                            Velocity 
                        </div>
                        <div className="font-bold text-slate-800 text-sm flex items-center gap-1">
                            {velocity} <span className="text-[8px] opacity-60 font-normal">шт/д</span>
                        </div>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-xl border border-slate-100">
                        <div className="text-[9px] text-slate-400 uppercase font-bold flex items-center gap-1 mb-0.5">
                            ROP 
                        </div>
                        <div className="font-bold text-slate-800 text-sm">{safeRop} шт</div>
                    </div>
                </div>

                <div className="relative h-2.5 w-full bg-slate-100 rounded-full overflow-hidden mb-3">
                    <div 
                        className={`h-full rounded-full transition-all duration-500 ${progressColor}`} 
                        style={{ width: `${fillPercent}%` }}
                    ></div>
                    {ropPercent > 0 && ropPercent < 100 && (
                        <div 
                            className="absolute top-0 bottom-0 w-0.5 bg-black/20 border-l border-white/50 z-10"
                            style={{ left: `${ropPercent}%` }}
                            title={`Точка заказа: ${rop} шт`}
                        ></div>
                    )}
                </div>
                
                <div className="flex justify-between items-center gap-2">
                    <div className="flex-1 text-[10px] text-slate-500 font-medium bg-slate-50 p-2 rounded-lg flex items-center gap-2 min-w-0">
                        {status === 'ok' ? <PackageCheck size={12} className="flex-shrink-0 text-emerald-500"/> : <AlertTriangle size={12} className="flex-shrink-0 text-amber-500"/>}
                        <span className="truncate">{recommendation}</span>
                    </div>
                    {to_order > 0 && (
                        <div className="bg-slate-900 text-white px-3 py-2 rounded-lg text-xs font-bold whitespace-nowrap flex items-center gap-1 shadow-lg shadow-slate-200">
                            +{to_order} шт
                        </div>
                    )}
                </div>
            </div>
        );
    };

    if (error) {
         return (
            <div className="p-6 text-center animate-in fade-in h-[80vh] flex flex-col items-center justify-center">
                <AlertTriangle className="mx-auto text-amber-500 mb-2" size={32}/>
                <h3 className="font-bold text-slate-800">Нет доступа к данным</h3>
                <p className="text-sm text-slate-500 mt-2 mb-4">{error}</p>
                <button onClick={fetchData} className="bg-slate-900 text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 mx-auto active:scale-95 transition-transform">
                    <RefreshCw size={14} /> Повторить
                </button>
            </div>
        )
    }

    if (loading && products.length === 0) {
        return <div className="flex justify-center items-center h-[80vh]"><Loader2 className="animate-spin text-indigo-600" /></div>;
    }

    const warehouses = getWarehouseOptions();

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in relative">
             <SettingsModal />
             <HelpModal />
             <CalcHelpModal />
             <UpgradeModal />

             {/* Header */}
             <div className="bg-gradient-to-r from-orange-500 to-amber-500 p-6 rounded-[32px] text-white shadow-xl shadow-orange-200 relative overflow-hidden">
                <div className="relative z-10 flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        <button onClick={() => navigate(-1)} className="bg-white/20 p-2 rounded-xl backdrop-blur-md hover:bg-white/30 transition-colors active:scale-95">
                            <ArrowLeft size={20} className="text-white"/>
                        </button>
                        <div>
                            <h1 className="text-2xl font-black flex items-center gap-2">
                                <Truck className="text-white" /> Supply Chain
                            </h1>
                            <p className="text-sm opacity-90 mt-1 font-medium">Умное управление запасами</p>
                        </div>
                    </div>
                    
                    <div className="flex gap-2">
                        <button 
                            onClick={handleDownloadReport}
                            className="bg-white/20 backdrop-blur-md p-3 rounded-full hover:bg-white/30 transition-colors"
                            title="Скачать PDF отчёт"
                        >
                            <FileDown className="text-white" size={20} />
                        </button>
                        <button 
                            onClick={() => setShowSettings(true)}
                            className="bg-white/20 backdrop-blur-md p-3 rounded-full hover:bg-white/30 transition-colors"
                        >
                            <Settings className="text-white" size={20} />
                        </button>
                    </div>
                </div>
                <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
            </div>

            {/* Calculator Section */}
            <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm relative">
                 <button 
                    onClick={() => setShowCalcHelp(true)}
                    className="absolute top-6 right-6 text-slate-300 hover:text-indigo-600 transition-colors"
                 >
                     <HelpCircle size={18} />
                 </button>
                 
                 <h3 className="font-bold text-slate-800 mb-4 flex items-center gap-2">
                     <Scale size={20} className="text-indigo-600"/> 
                     Калькулятор транзита
                 </h3>
                 
                 <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Откуда</label>
                            <select 
                                value={origin} 
                                onChange={e => setOrigin(e.target.value)} 
                                className="w-full bg-transparent font-bold text-sm text-slate-800 outline-none appearance-none"
                            >
                                {warehouses.map(w => <option key={w} value={w}>{w}</option>)}
                            </select>
                        </div>
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Куда</label>
                            <select 
                                value={destination} 
                                onChange={e => setDestination(e.target.value)} 
                                className="w-full bg-transparent font-bold text-sm text-slate-800 outline-none appearance-none"
                            >
                                {warehouses.map(w => <option key={w} value={w}>{w}</option>)}
                            </select>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-[9px] font-bold text-slate-400 uppercase flex items-center gap-1 mb-1">
                                Объем <InfoTooltip text="Суммарный объем коробов или паллет в литрах" />
                            </label>
                            <div className="flex items-center">
                                <input 
                                    type="number" 
                                    value={volume} 
                                    onChange={e => setVolume(e.target.value)} 
                                    className="w-full bg-transparent font-black text-lg outline-none text-slate-800"
                                />
                                <span className="text-xs font-bold text-slate-400">л</span>
                            </div>
                        </div>
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-[9px] font-bold text-slate-400 uppercase flex items-center gap-1 mb-1">
                                Тариф транзита <InfoTooltip text="Ваша цена за 1 литр транзита (среднее 4.5₽)" />
                            </label>
                            <div className="flex items-center">
                                <input 
                                    type="number" 
                                    step="0.1" 
                                    value={transitRate} 
                                    onChange={e => setTransitRate(e.target.value)} 
                                    className="w-full bg-transparent font-black text-lg outline-none text-slate-800"
                                />
                                <span className="text-xs font-bold text-slate-400 ml-1">₽/л</span>
                            </div>
                        </div>
                    </div>

                    <button 
                        onClick={handleCalculate} 
                        disabled={calcLoading} 
                        className="w-full bg-indigo-600 text-white p-3 rounded-xl shadow-lg shadow-indigo-200 active:scale-95 transition-transform disabled:opacity-50 flex justify-center items-center"
                    >
                        {calcLoading ? <Loader2 className="animate-spin"/> : <span className="flex items-center gap-2">Рассчитать <ArrowDown size={16}/></span>}
                    </button>
                 </div>

                 {calcResult && (
                     <div className="mt-4 space-y-3 animate-in slide-in-from-top-4">
                         {/* Safe Access Checks Added */}
                         <div className={`p-4 rounded-2xl border-2 transition-all ${!calcResult.is_profitable ? 'border-emerald-500 bg-emerald-50' : 'border-slate-100 opacity-60'}`}>
                             <div className="flex justify-between items-center mb-1">
                                 <span className="font-bold text-sm flex items-center gap-1"><MapPin size={14}/> Прямая (Direct)</span>
                                 <span className="font-black text-lg">{calcResult.direct?.total?.toLocaleString() || 0} ₽</span>
                             </div>
                             <div className="text-[10px] text-slate-500">База: {calcResult.direct?.base}₽ + {calcResult.direct?.rate}₽/л</div>
                         </div>
                         <div className={`p-4 rounded-2xl border-2 transition-all ${calcResult.is_profitable ? 'border-emerald-500 bg-emerald-50' : 'border-slate-100 opacity-60'}`}>
                             <div className="flex justify-between items-center mb-1">
                                 <span className="font-bold text-sm flex items-center gap-1"><Truck size={14}/> Транзит WB</span>
                                 <span className="font-black text-lg">{calcResult.transit?.total?.toLocaleString() || 0} ₽</span>
                             </div>
                             <div className="text-[10px] text-slate-500">Тариф: {calcResult.transit?.rate}₽/л</div>
                             {calcResult.is_profitable && (
                                 <div className="mt-2 bg-emerald-200 text-emerald-800 text-xs font-bold px-2 py-1 rounded-lg inline-block">
                                      Выгода: {calcResult.benefit?.toLocaleString()} ₽
                                 </div>
                             )}
                         </div>
                     </div>
                 )}
            </div>

            {/* --- ABC/XYZ MATRIX INTEGRATION --- */}
            {matrixData && (
                <div className="animate-in fade-in slide-in-from-bottom-2">
                    <AbcXyzMatrix 
                        data={{ items: {}, summary: matrixData.summary }}
                        loading={loading}
                        onCellClick={(group) => setFilterGroup(group === filterGroup ? null : group)}
                        selectedGroup={filterGroup}
                    />
                </div>
            )}

            {/* Stock Health Section */}
            <div className="px-2">
                <div className="flex justify-between items-center mb-4">
                    <div className="flex items-center gap-2">
                         <h3 className="font-bold text-lg text-slate-800 flex items-center gap-2">
                            <Activity size={20} className="text-emerald-500"/>
                            Анализ запасов
                        </h3>
                        {/* Кнопка сброса фильтра */}
                        {filterGroup && (
                            <button 
                                onClick={() => setFilterGroup(null)} 
                                className="flex items-center gap-1 bg-indigo-100 text-indigo-700 px-2 py-1 rounded-lg text-xs font-bold animate-in fade-in active:scale-95"
                            >
                                <FilterX size={12}/> {filterGroup} <X size={12}/>
                            </button>
                        )}
                    </div>

                    <div className="flex items-center gap-2">
                        <button 
                            onClick={() => setShowHelp(true)}
                            className="bg-slate-100 text-slate-500 p-2 rounded-full hover:bg-slate-200 transition-colors"
                        >
                             <HelpCircle size={18} />
                        </button>
                        
                        {settings.lead_time !== 7 && (
                            <span className="text-[10px] bg-slate-100 px-2 py-1 rounded text-slate-500">
                                Lead: {settings.lead_time}д
                            </span>
                        )}
                        <button 
                            onClick={handleRefresh}
                            disabled={refreshing}
                            className="text-slate-400 hover:text-indigo-600 transition-colors disabled:animate-spin"
                        >
                            <RefreshCw size={18} />
                        </button>
                    </div>
                </div>

                {filteredProducts.length > 0 ? (
                    <div className="space-y-1">
                        {filteredProducts.map(item => <StockHealthCard key={item.sku} item={item} />)}
                    </div>
                ) : (
                    <div className="text-center p-8 text-slate-400 bg-white rounded-3xl border border-dashed border-slate-200">
                        {products.length > 0 ? 'Нет товаров в выбранной группе' : 'Нет данных о товарах.'} <br/>
                        <span className="text-xs">
                            {products.length === 0 && 'Убедитесь, что API ключ WB добавлен и корректен.'}
                        </span>
                    </div>
                )}
            </div>
            
            {/* Warehouse Coefficients */}
            {coeffs.length > 0 && (
                 <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm mt-6 opacity-80 hover:opacity-100 transition-opacity">
                    <h3 className="font-bold text-slate-800 mb-2 text-sm">Коэффициенты складов (Справочно)</h3>
                    <div className="overflow-x-auto pb-2">
                        <table className="w-full text-left text-xs">
                            <thead>
                                <tr className="text-slate-400 border-b border-slate-50">
                                    <th className="py-2 pl-2">Склад</th>
                                    <th className="py-2 text-center">Короба</th>
                                    <th className="py-2 text-center">Паллеты</th>
                                </tr>
                            </thead>
                            <tbody>
                                {coeffs.slice(0, 5).map((c, i) => (
                                    <tr key={i} className="border-b border-slate-50 last:border-0 hover:bg-slate-50 transition-colors">
                                        <td className="py-3 pl-2 font-bold text-slate-700">{c.warehouseName}</td>
                                        <td className="py-3 text-center">{c.boxDeliveryBase}</td>
                                        <td className="py-3 text-center">{c.palletDeliveryBase}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                 </div>
            )}
        </div>
    )
}

export default SupplyPage;