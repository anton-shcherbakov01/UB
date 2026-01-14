import React, { useState, useEffect } from 'react';
import { 
    Truck, Scale, Loader2, MapPin, ArrowRight, 
    PackageCheck, AlertTriangle, Box, RefreshCw,
    Activity, Settings, X, Save
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const SupplyPage = () => {
    const [coeffs, setCoeffs] = useState([]);
    const [volume, setVolume] = useState(1000);
    const [calculation, setCalculation] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [products, setProducts] = useState([]);
    const [error, setError] = useState(null);
    
    // Settings State
    const [showSettings, setShowSettings] = useState(false);
    const [settings, setSettings] = useState({
        lead_time: 7,
        min_stock_days: 14,
        abc_a_share: 80
    });
    const [savingSettings, setSavingSettings] = useState(false);

    useEffect(() => {
        fetchData();
        fetchSettings();
    }, []);

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
            
            // Handle analysis errors gracefully
            if (analysisRes.ok) {
                const aData = await analysisRes.json();
                setProducts(Array.isArray(aData) ? aData : []);
            } else if (analysisRes.status === 400) {
                 setError("Необходимо добавить API токен Wildberries в настройках.");
            } else {
                 // Non-blocking error for supply data if user just wants calculator
                 console.error("Analysis fetch failed");
            }
            
            setCoeffs(Array.isArray(cData) ? cData : []);

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
            await fetch(`${API_URL}/api/supply/refresh`, { 
                method: 'POST',
                headers: getTgHeaders() 
            });
            await fetchData();
        } catch (e) {
            console.error(e);
        } finally {
            setRefreshing(false);
        }
    };

    const handleSaveSettings = async () => {
        setSavingSettings(true);
        try {
            const res = await fetch(`${API_URL}/api/supply/settings`, {
                method: 'POST',
                headers: {
                    ...getTgHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });
            
            if (res.ok) {
                setShowSettings(false);
                // Reload analysis with new settings
                await fetchData(); 
            }
        } catch (e) {
            console.error("Save failed", e);
        } finally {
            setSavingSettings(false);
        }
    };

    const handleCalculate = async () => {
        if (!volume) return;
        try {
            const res = await fetch(`${API_URL}/api/internal/transit_calc`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ volume: Number(volume), destination: "Koledino" })
            });
            if (res.ok) {
                setCalculation(await res.json());
            }
        } catch(e) {
            console.error("Calculator error", e);
        }
    };

    // --- Subcomponents ---

    const SettingsModal = () => {
        if (!showSettings) return null;
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in">
                <div className="bg-white rounded-3xl w-full max-w-sm shadow-2xl p-6 space-y-4">
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                            <Settings size={20} className="text-slate-500"/> Настройки логистики
                        </h3>
                        <button onClick={() => setShowSettings(false)} className="p-2 bg-slate-100 rounded-full hover:bg-slate-200">
                            <X size={16}/>
                        </button>
                    </div>

                    <div className="space-y-4">
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-xs font-bold text-slate-500 uppercase block mb-1">Срок поставки (Lead Time)</label>
                            <div className="flex items-center gap-2">
                                <input 
                                    type="number" 
                                    value={settings.lead_time}
                                    onChange={(e) => setSettings({...settings, lead_time: Number(e.target.value)})}
                                    className="w-full bg-white p-2 rounded-lg font-bold text-slate-800 border border-slate-200 focus:outline-indigo-500"
                                />
                                <span className="text-xs font-bold text-slate-400">дней</span>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-1">Сколько дней едет товар от поставщика до WB.</p>
                        </div>

                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-xs font-bold text-slate-500 uppercase block mb-1">Страховой запас</label>
                            <div className="flex items-center gap-2">
                                <input 
                                    type="number" 
                                    value={settings.min_stock_days}
                                    onChange={(e) => setSettings({...settings, min_stock_days: Number(e.target.value)})}
                                    className="w-full bg-white p-2 rounded-lg font-bold text-slate-800 border border-slate-200 focus:outline-indigo-500"
                                />
                                <span className="text-xs font-bold text-slate-400">дней</span>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-1">На сколько дней продаж хранить "подушку безопасности".</p>
                        </div>

                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <label className="text-xs font-bold text-slate-500 uppercase block mb-1">Группа А (ABC-анализ)</label>
                            <div className="flex items-center gap-2">
                                <input 
                                    type="number" 
                                    value={settings.abc_a_share}
                                    onChange={(e) => setSettings({...settings, abc_a_share: Number(e.target.value)})}
                                    className="w-full bg-white p-2 rounded-lg font-bold text-slate-800 border border-slate-200 focus:outline-indigo-500"
                                />
                                <span className="text-xs font-bold text-slate-400">%</span>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-1">Процент выручки, определяющий топовые товары.</p>
                        </div>
                    </div>

                    <button 
                        onClick={handleSaveSettings}
                        disabled={savingSettings}
                        className="w-full bg-slate-900 text-white py-3 rounded-xl font-bold flex justify-center items-center gap-2 active:scale-95 transition-transform"
                    >
                        {savingSettings ? <Loader2 className="animate-spin"/> : <Save size={18}/>}
                        Сохранить и пересчитать
                    </button>
                </div>
            </div>
        );
    };

    const StockHealthCard = ({ item }) => {
        const { 
            sku, name, size, stock, velocity, 
            days_to_stock, rop, abc, status, 
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

        const maxScale = rop > 0 ? rop * 2 : (stock > 0 ? stock * 1.5 : 10);
        const fillPercent = Math.min(100, (stock / maxScale) * 100);
        const ropPercent = rop > 0 ? Math.min(100, (rop / maxScale) * 100) : 0;

        return (
            <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 mb-3 animate-in fade-in">
                <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                            <span className={`text-[10px] font-black px-1.5 py-0.5 rounded ${abcColor}`}>{abc}</span>
                            <span className="font-bold text-sm text-slate-800 truncate max-w-[180px]">{name}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 flex gap-2">
                             <span>SKU: {sku}</span>
                             {size && <span>Размер: {size}</span>}
                        </div>
                    </div>
                    <div className={`px-2 py-1 rounded-lg flex items-center gap-1 text-xs font-bold ${colorClass} ${textClass}`}>
                        {icon} 
                        {days_to_stock > 365 ? '>1 года' : `${days_to_stock} дн.`}
                    </div>
                </div>
                
                <div className="grid grid-cols-3 gap-2 mb-3">
                    <div className="bg-slate-50 p-2 rounded-xl">
                        <div className="text-[10px] text-slate-400">Остаток</div>
                        <div className="font-bold text-slate-800">{stock} шт</div>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-xl">
                        <div className="text-[10px] text-slate-400">Скорость</div>
                        <div className="font-bold text-slate-800 flex items-center gap-1">
                            {velocity} <span className="text-[8px] opacity-60">шт/д</span>
                        </div>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-xl">
                        <div className="text-[10px] text-slate-400">ROP (Заказ)</div>
                        <div className="font-bold text-slate-800">{rop} шт</div>
                    </div>
                </div>

                <div className="relative h-3 w-full bg-slate-100 rounded-full overflow-hidden mb-3">
                    <div 
                        className={`h-full rounded-full transition-all duration-500 ${progressColor}`} 
                        style={{ width: `${fillPercent}%` }}
                    ></div>
                    {ropPercent > 0 && ropPercent < 100 && (
                        <div 
                            className="absolute top-0 bottom-0 w-0.5 bg-black/20 border-l border-white/50 z-10"
                            style={{ left: `${ropPercent}%` }}
                        ></div>
                    )}
                </div>
                
                <div className="flex justify-between items-center gap-2">
                    <div className="flex-1 text-[10px] text-slate-500 font-medium bg-slate-50 p-2 rounded-lg flex items-center gap-2">
                        {status === 'ok' ? <PackageCheck size={12}/> : <AlertTriangle size={12}/>}
                        {recommendation}
                    </div>
                    {to_order > 0 && (
                        <div className="bg-slate-900 text-white px-3 py-2 rounded-lg text-xs font-bold whitespace-nowrap flex items-center gap-1">
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
                <button onClick={fetchData} className="bg-slate-900 text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 mx-auto">
                    <RefreshCw size={14} /> Повторить
                </button>
            </div>
        )
    }

    if (loading && products.length === 0) {
        return <div className="flex justify-center items-center h-[80vh]"><Loader2 className="animate-spin text-indigo-600" /></div>;
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in relative">
             <SettingsModal />

             <div className="bg-gradient-to-r from-orange-500 to-amber-500 p-6 rounded-[32px] text-white shadow-xl shadow-orange-200 relative overflow-hidden">
                <div className="relative z-10 flex justify-between items-center">
                    <div>
                        <h1 className="text-2xl font-black flex items-center gap-2">
                            <Truck className="text-white" /> Supply Chain
                        </h1>
                        <p className="text-sm opacity-90 mt-2 font-medium">Умное управление запасами</p>
                    </div>
                    
                    <button 
                        onClick={() => setShowSettings(true)}
                        className="bg-white/20 backdrop-blur-md p-3 rounded-full hover:bg-white/30 transition-colors"
                    >
                        <Settings className="text-white" size={20} />
                    </button>
                </div>
                <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
            </div>

            {/* Calculator Section */}
            <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                 <h3 className="font-bold text-slate-800 mb-4 flex items-center gap-2">
                     <Scale size={20} className="text-indigo-600"/> 
                     Калькулятор маршрута
                 </h3>
                 
                 <div className="bg-slate-50 p-4 rounded-2xl mb-4 border border-slate-100">
                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2">Объем поставки (литры)</label>
                    <div className="flex items-center gap-2">
                        <input 
                            type="number"
                            value={volume}
                            onChange={e => setVolume(e.target.value)}
                            className="flex-1 bg-white p-3 rounded-xl font-black text-xl outline-none text-slate-800 shadow-sm transition-all focus:ring-2 focus:ring-indigo-500/20"
                        />
                        <button 
                            onClick={handleCalculate} 
                            disabled={loading}
                            className="bg-indigo-600 text-white p-3 rounded-xl active:scale-95 transition-transform shadow-lg shadow-indigo-200 disabled:opacity-50"
                        >
                            {loading && calculation === null ? <Loader2 className="animate-spin"/> : <ArrowRight />}
                        </button>
                    </div>
                 </div>

                 {calculation && (
                     <div className="space-y-3 animate-in slide-in-from-top-4">
                         <div className={`p-4 rounded-2xl border-2 transition-all ${!calculation.is_profitable ? 'border-emerald-500 bg-emerald-50' : 'border-slate-100 opacity-60'}`}>
                             <div className="flex justify-between items-center mb-1">
                                 <span className="font-bold text-sm flex items-center gap-1"><MapPin size={14}/> Коледино (Прямая)</span>
                                 <span className="font-black text-lg">{calculation.direct_cost.toLocaleString()} ₽</span>
                             </div>
                         </div>
                         <div className={`p-4 rounded-2xl border-2 transition-all ${calculation.is_profitable ? 'border-emerald-500 bg-emerald-50' : 'border-slate-100 opacity-60'}`}>
                             <div className="flex justify-between items-center mb-1">
                                 <span className="font-bold text-sm flex items-center gap-1"><Truck size={14}/> Казань (Транзит)</span>
                                 <span className="font-black text-lg">{calculation.transit_cost.toLocaleString()} ₽</span>
                             </div>
                             {calculation.is_profitable && (
                                 <div className="mt-2 bg-emerald-200 text-emerald-800 text-xs font-bold px-2 py-1 rounded-lg inline-block">
                                      Выгода: {calculation.benefit.toLocaleString()} ₽
                                 </div>
                             )}
                         </div>
                     </div>
                 )}
            </div>

            {/* Stock Health Section */}
            <div className="px-2">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="font-bold text-lg text-slate-800 flex items-center gap-2">
                        <Activity size={20} className="text-emerald-500"/>
                        Анализ запасов
                    </h3>
                    <div className="flex items-center gap-2">
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

                {products.length > 0 ? (
                    <div className="space-y-1">
                        {products.map(item => <StockHealthCard key={item.sku} item={item} />)}
                    </div>
                ) : (
                    <div className="text-center p-8 text-slate-400 bg-white rounded-3xl border border-dashed border-slate-200">
                        Нет данных о товарах. <br/>
                        <span className="text-xs">Убедитесь, что API ключ WB добавлен и корректен.</span>
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