import React, { useState, useEffect } from 'react';
import { RefreshCw, Loader2, Calculator } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import CostEditModal from '../components/CostEditModal';

const FinancePage = ({ onNavigate }) => {
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingCost, setEditingCost] = useState(null);

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/internal/products`, {
                headers: getTgHeaders()
            });
            if (res.ok) setProducts(await res.json());
        } catch(e) { console.error(e); } finally { setLoading(false); }
    };

    useEffect(() => { fetchProducts(); }, []);

    const handleUpdateCost = async (sku, cost) => {
        try {
            await fetch(`${API_URL}/api/internal/cost/${sku}`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ cost_price: Number(cost) })
            });
            setEditingCost(null);
            fetchProducts();
        } catch(e) { alert("Ошибка обновления"); }
    };

    return (
        <div className="p-4 space-y-4 pb-32 animate-in fade-in slide-in-from-bottom-4">
             <div className="flex justify-between items-center px-2">
                <div>
                    <h2 className="text-xl font-bold text-slate-800">Unit-экономика</h2>
                    <p className="text-xs text-slate-400">Внутренняя аналитика (API)</p>
                </div>
                <button onClick={fetchProducts} className="p-2 bg-white rounded-full shadow-sm text-slate-400 active:rotate-180 transition-all"><RefreshCw size={18}/></button>
            </div>

            {editingCost && <CostEditModal item={editingCost} onClose={() => setEditingCost(null)} onSave={handleUpdateCost} />}

            {loading ? (
                <div className="flex justify-center p-10"><Loader2 className="animate-spin text-emerald-600"/></div>
            ) : products.length === 0 ? (
                <div className="text-center p-10 bg-white rounded-3xl border border-dashed border-slate-200">
                    <p className="font-bold text-slate-500 mb-2">Нет данных</p>
                    <p className="text-xs text-slate-400">Убедитесь, что подключен API токен и на остатках есть товары.</p>
                </div>
            ) : (
                products.map((item) => (
                    <div key={item.sku} className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm relative group mb-3">
                        <div className="flex justify-between items-start mb-3">
                            <div className="min-w-0">
                                <div className="font-bold truncate text-sm">SKU {item.sku}</div>
                                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Остаток: {item.quantity} шт</div>
                            </div>
                            <div className="flex flex-col items-end gap-1">
                                <button onClick={() => setEditingCost(item)} className="p-2 bg-slate-50 text-slate-500 rounded-xl hover:bg-slate-100">
                                    <Calculator size={18} />
                                </button>
                                {item.supply && (
                                    <span className={`text-[9px] font-bold px-2 py-1 rounded-lg ${item.supply.status === 'critical' ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-600'}`}>
                                        {item.supply.days_left} дн.
                                    </span>
                                )}
                            </div>
                        </div>
                        
                        <div className="bg-slate-50 rounded-xl p-3 grid grid-cols-3 gap-2 text-sm">
                             <div>
                                <span className="block text-[9px] text-slate-400 uppercase font-bold">Себестоимость</span>
                                <span className="font-bold text-slate-700">{item.cost_price} ₽</span>
                             </div>
                             <div className="text-center">
                                <span className="block text-[9px] text-slate-400 uppercase font-bold">Цена</span>
                                <span className="font-bold text-slate-700">{item.price} ₽</span>
                             </div>
                             <div className="text-right">
                                <span className="block text-[9px] text-slate-400 uppercase font-bold">Прибыль</span>
                                <span className={`font-black ${item.unit_economy.profit > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                    {item.unit_economy.profit} ₽
                                </span>
                             </div>
                        </div>
                        <div className="mt-2 flex gap-2">
                             <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${item.unit_economy.roi > 30 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                                 ROI: {item.unit_economy.roi}%
                             </span>
                             <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-500">
                                 Маржа: {item.unit_economy.margin}%
                             </span>
                        </div>
                    </div>
                ))
            )}
        </div>
    );
}

export default FinancePage;