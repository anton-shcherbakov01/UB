import React, { useState, useEffect, useMemo } from 'react';
import { 
    Loader2, Calculator, DollarSign, Info, Truck, Percent 
} from 'lucide-react';
import { 
    BarChart, Bar, Tooltip, ResponsiveContainer, 
    Cell, ReferenceLine 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';
import CostEditModal from '../components/CostEditModal';

const FinancePage = () => {
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingCost, setEditingCost] = useState(null);
    const [viewMode, setViewMode] = useState('unit'); // 'unit' | 'pnl'

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/internal/products`, {
                headers: getTgHeaders()
            });
            if (res.ok) {
                const data = await res.json();
                setProducts(data);
            }
        } catch(e) { 
            console.error(e); 
        } finally { 
            setLoading(false); 
        }
    };

    useEffect(() => { fetchProducts(); }, []);

    // Обновленная функция сохранения.
    // Теперь она ожидает объект formData: { cost_price, logistics, commission_percent }
    const handleUpdateCost = async (sku, formData) => {
        try {
            await fetch(`${API_URL}/api/internal/cost/${sku}`, {
                method: 'POST',
                headers: {
                    ...getTgHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    cost_price: Number(formData.cost_price),
                    logistics: formData.logistics ? Number(formData.logistics) : null,
                    commission_percent: formData.commission_percent ? Number(formData.commission_percent) : null
                })
            });
            setEditingCost(null);
            fetchProducts();
        } catch(e) { 
            alert("Ошибка обновления"); 
        }
    };

    const pnlStats = useMemo(() => {
        let grossSales = 0;
        let cogs = 0;
        let logisticsTotal = 0; 
        let commissionTotal = 0; 
        
        products.forEach(p => {
            const velocity = p.supply?.metrics?.avg_daily_demand || 0;
            const monthlySales = velocity * 30; // Прогноз продаж на месяц
            
            if (monthlySales > 0) {
                // Выручка
                grossSales += p.price * monthlySales;
                
                // Себестоимость товара
                cogs += p.cost_price * monthlySales;
                
                // Логистика (берем реальную из API)
                const itemLogistics = p.logistics || 50; 
                logisticsTotal += itemLogistics * monthlySales;
                
                // Комиссия (берем реальный % из API)
                const commPct = p.commission_percent || 25;
                const itemCommission = p.price * (commPct / 100);
                commissionTotal += itemCommission * monthlySales;
            }
        });

        if (grossSales === 0 && cogs === 0) return [];

        const netSales = grossSales;
        const cm1 = netSales - cogs;
        const cm2 = cm1 - logisticsTotal - commissionTotal;
        const marketing = cm2 * 0.1; // Условные 10% на маркетинг (можно вынести в настройки)
        const ebitda = cm2 - marketing;

        return [
            { name: 'Выручка', value: Math.round(grossSales), type: 'income' },
            { name: 'Себестоимость', value: -Math.round(cogs), type: 'expense' },
            { name: 'Комиссия', value: -Math.round(commissionTotal), type: 'expense' },
            { name: 'Логистика', value: -Math.round(logisticsTotal), type: 'expense' },
            { name: 'Маркетинг', value: -Math.round(marketing), type: 'expense' },
            { name: 'EBITDA', value: Math.round(ebitda), type: 'total' }
        ];
    }, [products]);

    const MetricCard = ({ title, value, subvalue, color }) => (
        <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">{title}</span>
            <div className={`text-xl font-black ${color}`}>{value}</div>
            {subvalue && <div className="text-[10px] text-slate-400 mt-1">{subvalue}</div>}
        </div>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
             <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-black text-slate-800 flex items-center gap-2">
                        <DollarSign className="text-emerald-500" fill="currentColor" /> 
                        Финансы
                    </h2>
                    <p className="text-xs text-slate-400">P&L и Unit-экономика</p>
                </div>
                <div className="flex bg-white rounded-xl p-1 shadow-sm border border-slate-100">
                    <button 
                        onClick={() => setViewMode('unit')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${viewMode === 'unit' ? 'bg-slate-900 text-white' : 'text-slate-400'}`}
                    >
                        Unit
                    </button>
                    <button 
                        onClick={() => setViewMode('pnl')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${viewMode === 'pnl' ? 'bg-slate-900 text-white' : 'text-slate-400'}`}
                    >
                        P&L
                    </button>
                </div>
            </div>

            {editingCost && (
                <CostEditModal 
                    item={editingCost} 
                    onClose={() => setEditingCost(null)} 
                    onSave={handleUpdateCost} 
                />
            )}

            {loading ? (
                <div className="flex justify-center p-20"><Loader2 className="animate-spin text-emerald-600" size={32}/></div>
            ) : viewMode === 'pnl' ? (
                <div className="space-y-4 animate-in slide-in-from-right-8">
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <h3 className="font-bold text-lg mb-4">Проекция (по текущей скорости)</h3>
                        {pnlStats.length > 0 ? (
                            <>
                                <div className="h-64 w-full">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={pnlStats}>
                                            <Tooltip 
                                                cursor={{fill: '#f1f5f9'}}
                                                contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)'}}
                                            />
                                            <ReferenceLine y={0} stroke="#cbd5e1" />
                                            <Bar dataKey="value" radius={[4, 4, 4, 4]}>
                                                {pnlStats.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.value > 0 ? (entry.type === 'total' ? '#10b981' : '#3b82f6') : '#ef4444'} />
                                                ))}
                                            </Bar>
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                                <div className="grid grid-cols-2 gap-2 mt-4">
                                    {pnlStats.map((s, i) => (
                                        <div key={i} className="flex justify-between text-sm border-b border-slate-50 last:border-0 py-2">
                                            <span className="text-slate-500">{s.name}</span>
                                            <span className={`font-bold ${s.value > 0 ? 'text-slate-800' : 'text-red-500'}`}>
                                                {s.value.toLocaleString()} ₽
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </>
                        ) : (
                            <div className="text-center text-slate-400 py-10">
                                Нет данных о продажах для прогноза P&L.
                            </div>
                        )}
                    </div>

                    <div className="bg-blue-50 p-4 rounded-2xl border border-blue-100 flex gap-3 items-start">
                        <Info className="text-blue-600 min-w-[20px]" size={20}/>
                        <p className="text-xs text-blue-800 leading-relaxed">
                            <strong>Отказ от ответственности:</strong> Расчеты строятся на основе текущих остатков и загруженных данных API.
                        </p>
                    </div>
                </div>
            ) : (
                <div className="space-y-4 animate-in slide-in-from-left-8">
                    {/* Unit Economics List */}
                    <div className="grid grid-cols-2 gap-3">
                        <MetricCard title="Товаров в анализе" value={products.length} color="text-slate-800" />
                        <MetricCard 
                            title="Средний ROI" 
                            value={`${Math.round(products.reduce((acc, p) => acc + (p.unit_economy?.roi || 0), 0) / (products.length || 1))}%`} 
                            color="text-emerald-600" 
                        />
                    </div>

                    <div className="space-y-3">
                        {products.map((item) => {
                            // Расчеты для отображения
                            const commPct = item.commission_percent || 25;
                            const commVal = Math.round(item.price * (commPct / 100));
                            const logVal = Math.round(item.logistics || 50);
                            
                            return (
                                <div key={item.sku} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm relative group">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="min-w-0">
                                            <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">SKU {item.sku}</div>
                                            <div className="font-bold text-lg leading-tight">{item.price} ₽</div>
                                        </div>
                                        <button onClick={() => setEditingCost(item)} className="p-3 bg-slate-50 text-slate-500 rounded-2xl hover:bg-indigo-50 hover:text-indigo-600 transition-colors">
                                            <Calculator size={20} />
                                        </button>
                                    </div>
                                    
                                    <div className="space-y-2 mb-4 relative">
                                        <div className="absolute left-[3px] top-2 bottom-2 w-0.5 bg-slate-100 rounded-full"></div>
                                        
                                        {/* Цена */}
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-slate-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-500">Цена продажи</span>
                                            <span className="font-bold">{item.price} ₽</span>
                                        </div>

                                        {/* Комиссия */}
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-purple-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-400 flex items-center gap-1">
                                                Комиссия <span className="text-[10px] bg-purple-50 text-purple-600 px-1 rounded">{commPct}%</span>
                                            </span>
                                            <span className="text-purple-400">-{commVal} ₽</span>
                                        </div>

                                        {/* Логистика */}
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-blue-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-400 flex items-center gap-1">
                                                Логистика <Truck size={10} />
                                            </span>
                                            <span className="text-blue-400">-{logVal} ₽</span>
                                        </div>

                                        {/* Себестоимость */}
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-orange-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-400">Себестоимость</span>
                                            <span className="text-orange-400">-{item.cost_price} ₽</span>
                                        </div>

                                        {/* ИТОГ */}
                                        <div className="flex justify-between items-center text-base pl-4 relative pt-1 border-t border-slate-50 mt-1">
                                            <div className={`w-2 h-2 rounded-full absolute -left-[4px] ${item.unit_economy.profit > 0 ? 'bg-emerald-500' : 'bg-red-500'}`}></div>
                                            <span className="font-bold text-slate-800">Чистая прибыль</span>
                                            <span className={`font-black ${item.unit_economy.profit > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                                {item.unit_economy.profit} ₽
                                            </span>
                                        </div>
                                    </div>

                                    <div className="flex gap-2">
                                        <span className={`flex-1 text-center py-2 rounded-xl text-xs font-bold ${item.unit_economy.roi > 100 ? 'bg-emerald-100 text-emerald-700' : item.unit_economy.roi > 30 ? 'bg-blue-100 text-blue-700' : 'bg-red-50 text-red-600'}`}>
                                            ROI: {item.unit_economy.roi}%
                                        </span>
                                        <span className="flex-1 text-center py-2 rounded-xl text-xs font-bold bg-slate-50 text-slate-600">
                                            Маржа: {item.unit_economy.margin}%
                                        </span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

export default FinancePage;