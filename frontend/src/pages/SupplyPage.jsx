import React, { useState, useEffect } from 'react';
import { 
    Truck, Scale, Loader2, MapPin, ArrowRight, 
    PackageCheck, AlertTriangle, Box 
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const SupplyPage = () => {
    const [coeffs, setCoeffs] = useState([]);
    const [volume, setVolume] = useState(1000);
    const [calculation, setCalculation] = useState(null);
    const [loading, setLoading] = useState(false);
    const [products, setProducts] = useState([]);

    useEffect(() => {
        // Загружаем коэффициенты
        fetch(`${API_URL}/api/internal/coefficients`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setCoeffs)
            .catch(console.error);

        // Загружаем товары для отображения метрик ROP/Safety Stock
        fetch(`${API_URL}/api/internal/products`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setProducts)
            .catch(console.error);
    }, []);

    const handleCalculate = async () => {
        if (!volume) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/internal/transit_calc`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ volume: Number(volume), destination: "Koledino" })
            });
            setCalculation(await res.json());
        } catch(e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const StockHealthCard = ({ item }) => {
        if (!item.supply) return null;
        const { status, days_left, metrics, recommendation } = item.supply;
        
        let colorClass = 'bg-slate-50 border-slate-100';
        let textClass = 'text-slate-600';
        let icon = <Box size={16}/>;

        if (status === 'critical' || status === 'out_of_stock') {
            colorClass = 'bg-red-50 border-red-100';
            textClass = 'text-red-700';
            icon = <AlertTriangle size={16} className="text-red-500"/>;
        } else if (status === 'warning') {
            colorClass = 'bg-orange-50 border-orange-100';
            textClass = 'text-orange-700';
            icon = <Truck size={16} className="text-orange-500"/>;
        } else {
            colorClass = 'bg-emerald-50 border-emerald-100';
            textClass = 'text-emerald-700';
            icon = <PackageCheck size={16} className="text-emerald-500"/>;
        }

        const fillPercent = Math.min(100, (metrics.current_stock / (metrics.rop * 1.5)) * 100);

        return (
            <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 mb-3">
                <div className="flex justify-between items-start mb-2">
                    <div>
                        <div className="font-bold text-sm">SKU {item.sku}</div>
                        <div className="text-[10px] text-slate-400">ROP: {metrics.rop} шт | Safety: {metrics.safety_stock} шт</div>
                    </div>
                    <div className={`px-2 py-1 rounded-lg flex items-center gap-1 text-xs font-bold ${colorClass} ${textClass}`}>
                        {icon} {days_left} дн.
                    </div>
                </div>
                
                {/* Visual Bar */}
                <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden mb-2">
                    <div 
                        className={`h-full rounded-full transition-all duration-500 ${status === 'ok' ? 'bg-emerald-500' : status === 'warning' ? 'bg-orange-500' : 'bg-red-500'}`} 
                        style={{ width: `${fillPercent}%` }}
                    ></div>
                </div>
                
                <div className="text-[10px] text-slate-500 font-medium bg-slate-50 p-2 rounded-lg">
                    💡 {recommendation}
                </div>
            </div>
        );
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-orange-500 to-amber-500 p-6 rounded-[32px] text-white shadow-xl shadow-orange-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <Truck className="text-white" /> Supply Chain
                </h1>
                <p className="text-sm opacity-90 mt-2 font-medium">Умная логистика и пополнение</p>
            </div>

            {/* Transit Calculator */}
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
                            className="flex-1 bg-white p-3 rounded-xl font-black text-xl outline-none text-slate-800 shadow-sm"
                        />
                        <button 
                            onClick={handleCalculate} 
                            disabled={loading}
                            className="bg-indigo-600 text-white p-3 rounded-xl active:scale-95 transition-transform shadow-lg shadow-indigo-200"
                        >
                            {loading ? <Loader2 className="animate-spin"/> : <ArrowRight />}
                        </button>
                    </div>
                 </div>

                 {calculation && (
                     <div className="space-y-3 animate-in slide-in-from-top-4">
                         {/* Direct Route Card */}
                         <div className={`p-4 rounded-2xl border-2 transition-all ${!calculation.is_profitable ? 'border-emerald-500 bg-emerald-50' : 'border-slate-100 opacity-60'}`}>
                             <div className="flex justify-between items-center mb-1">
                                 <span className="font-bold text-sm flex items-center gap-1"><MapPin size={14}/> Коледино (Прямая)</span>
                                 <span className="font-black text-lg">{calculation.direct_cost.toLocaleString()} ₽</span>
                             </div>
                             <div className="text-[10px] text-slate-500">1500₽ база + {volume}л × 30₽</div>
                         </div>

                         {/* Transit Route Card */}
                         <div className={`p-4 rounded-2xl border-2 transition-all ${calculation.is_profitable ? 'border-emerald-500 bg-emerald-50' : 'border-slate-100 opacity-60'}`}>
                             <div className="flex justify-between items-center mb-1">
                                 <span className="font-bold text-sm flex items-center gap-1"><Truck size={14}/> Казань (Транзит)</span>
                                 <span className="font-black text-lg">{calculation.transit_cost.toLocaleString()} ₽</span>
                             </div>
                             <div className="text-[10px] text-slate-500">500₽ база + 1000₽ лог. + {volume}л × 10₽</div>
                             {calculation.is_profitable && (
                                 <div className="mt-2 bg-emerald-200 text-emerald-800 text-xs font-bold px-2 py-1 rounded-lg inline-block">
                                     Выгода: {calculation.benefit.toLocaleString()} ₽
                                 </div>
                             )}
                         </div>
                     </div>
                 )}
            </div>
            
            <h3 className="font-bold text-lg px-2 text-slate-800">Здоровье склада (ROP)</h3>
            <div>
                {products
                    .filter(p => p.supply) // Показываем только товары с расчетами supply
                    .map(item => <StockHealthCard key={item.sku} item={item} />)
                }
                {products.length === 0 && !loading && (
                    <div className="text-center p-8 text-slate-400">Нет данных для прогноза</div>
                )}
            </div>
        </div>
    )
}

export default SupplyPage;