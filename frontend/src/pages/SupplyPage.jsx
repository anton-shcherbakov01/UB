import React, { useState, useEffect } from 'react';
import { Truck, Scale, Loader2 } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const SupplyPage = () => {
    const [coeffs, setCoeffs] = useState([]);
    const [volume, setVolume] = useState(1000);
    const [calculation, setCalculation] = useState(null);
    const [loading, setLoading] = useState(false);
    
    useEffect(() => {
        fetch(`${API_URL}/api/internal/coefficients`, {
             headers: getTgHeaders()
        }).then(r => r.json()).then(setCoeffs).catch(console.error);
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

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-orange-400 to-amber-500 p-6 rounded-3xl text-white shadow-xl shadow-orange-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <Truck className="text-white" /> Supply Chain
                </h1>
                <p className="text-sm opacity-90 mt-2">Управление поставками и коэффициенты складов.</p>
            </div>
            
            <h3 className="font-bold text-lg px-2">Приемка складов (Live)</h3>
            <div className="grid grid-cols-2 gap-3">
                {coeffs.map((c, i) => (
                    <div key={i} className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                        <div className="flex justify-between items-start mb-2">
                             <span className="font-bold text-sm truncate">{c.warehouse}</span>
                             <span className={`text-xs font-black px-2 py-0.5 rounded ${c.coefficient === 0 ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
                                x{c.coefficient}
                             </span>
                        </div>
                        <p className="text-[10px] text-slate-400">Транзит: {c.transit_time}</p>
                    </div>
                ))}
            </div>

            <div className="bg-blue-50 p-6 rounded-3xl border border-blue-100">
                 <h3 className="font-bold text-blue-800 mb-2 flex items-center gap-2"><Scale size={18}/> Калькулятор транзита</h3>
                 <p className="text-sm text-blue-600 mb-4">Сравнение: Прямая поставка vs Транзит через Казань.</p>
                 
                 <div className="mb-4 bg-white p-3 rounded-xl border border-blue-100">
                    <label className="text-[10px] font-bold text-slate-400 uppercase">Объем поставки (литры)</label>
                    <input 
                        type="number"
                        value={volume}
                        onChange={e => setVolume(e.target.value)}
                        className="w-full font-black text-lg outline-none text-slate-800"
                    />
                 </div>

                 <button 
                    onClick={handleCalculate} 
                    disabled={loading}
                    className="w-full bg-blue-600 text-white py-3 rounded-xl font-bold active:scale-95 transition-transform"
                 >
                    {loading ? <Loader2 className="animate-spin mx-auto"/> : 'Рассчитать выгоду'}
                 </button>

                 {calculation && (
                     <div className="mt-4 bg-white p-4 rounded-xl animate-in slide-in-from-top-2 border border-slate-100">
                         <div className="flex justify-between text-sm mb-1">
                             <span className="text-slate-500">Прямая (Коледино):</span>
                             <span className="font-bold">{calculation.direct_cost} ₽</span>
                         </div>
                         <div className="flex justify-between text-sm mb-3">
                             <span className="text-slate-500">Транзит (Казань):</span>
                             <span className="font-bold text-emerald-600">{calculation.transit_cost} ₽</span>
                         </div>
                         <div className={`text-xs font-bold p-3 rounded-lg text-center ${calculation.is_profitable ? 'bg-emerald-100 text-emerald-700' : 'bg-orange-100 text-orange-700'}`}>
                             {calculation.recommendation}
                             {calculation.is_profitable && <div className="mt-1">Выгода: {calculation.benefit} ₽</div>}
                         </div>
                     </div>
                 )}
            </div>
        </div>
    )
}

export default SupplyPage;