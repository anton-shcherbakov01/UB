import React, { useState, useEffect, useMemo } from 'react';
import { 
    Loader2, Calculator, DollarSign, Info, Truck, Percent, HelpCircle, ArrowLeft, Download
} from 'lucide-react';
import { 
    BarChart, Bar, Tooltip, ResponsiveContainer, 
    Cell, ReferenceLine 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';
import CostEditModal from '../components/CostEditModal';

const FinancePage = ({ user, onNavigate }) => {
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingCost, setEditingCost] = useState(null);
    const [viewMode, setViewMode] = useState('unit'); // 'unit' | 'pnl'
    const [pnlData, setPnlData] = useState(null);
    const [pnlLoading, setPnlLoading] = useState(false);
    const [pnlError, setPnlError] = useState(null);
    const [pdfLoading, setPdfLoading] = useState(false);

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
    
    const fetchPnlData = async () => {
        setPnlLoading(true);
        setPnlError(null);
        try {
            const res = await fetch(`${API_URL}/api/finance/pnl`, {
                headers: getTgHeaders()
            });
            if (res.ok) {
                const data = await res.json();
                setPnlData(data);
            } else {
                const errorData = await res.json().catch(() => ({ detail: 'Неизвестная ошибка' }));
                if (res.status === 403) {
                    setPnlError(errorData.detail || 'P&L недоступен на вашем тарифе. Обновите тариф для полного доступа.');
                } else {
                    setPnlError(errorData.detail || 'Ошибка загрузки данных P&L');
                }
                setPnlData(null);
            }
        } catch(e) { 
            console.error(e);
            setPnlError('Ошибка соединения с сервером');
            setPnlData(null);
        } finally {
            setPnlLoading(false);
        }
    };
    
    useEffect(() => {
        if (viewMode === 'pnl') {
            fetchPnlData();
        }
    }, [viewMode]);

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
            const monthlySales = velocity * 30;
            
            if (monthlySales > 0) {
                // Используем selling price (с учетом скидки)
                const price = p.price_structure?.selling || 0;
                grossSales += price * monthlySales;
                
                cogs += p.cost_price * monthlySales;
                
                const itemLogistics = p.logistics || 50; 
                logisticsTotal += itemLogistics * monthlySales;
                
                const commPct = p.commission_percent || 25;
                const itemCommission = price * (commPct / 100);
                commissionTotal += itemCommission * monthlySales;
            }
        });

        if (grossSales === 0 && cogs === 0) return [];

        const netSales = grossSales;
        const cm1 = netSales - cogs;
        const cm2 = cm1 - logisticsTotal - commissionTotal;
        const marketing = cm2 * 0.1; 
        const ebitda = cm2 - marketing;

        return [
            { name: 'Выручка (Seller)', value: Math.round(grossSales), type: 'income' },
            { name: 'Себестоимость', value: -Math.round(cogs), type: 'expense' },
            { name: 'Комиссия WB', value: -Math.round(commissionTotal), type: 'expense' },
            { name: 'Логистика', value: -Math.round(logisticsTotal), type: 'expense' },
            { name: 'Маркетинг (10%)', value: -Math.round(marketing), type: 'expense' },
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
                <div className="flex items-center gap-3 flex-1">
                    {onNavigate && (
                        <button 
                            onClick={() => onNavigate('home')} 
                            className="p-2 bg-white rounded-xl border border-slate-100 shadow-sm text-slate-400 hover:text-indigo-600 transition-colors"
                        >
                            <ArrowLeft size={20} />
                        </button>
                    )}
                    <div className="flex-1">
                        <h2 className="text-2xl font-black text-slate-800 flex items-center gap-2">
                            <DollarSign className="text-emerald-500" fill="currentColor" /> 
                            Финансы
                        </h2>
                        <p className="text-xs text-slate-400">P&L и Unit-экономика</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className="group relative">
                        <button className="p-2 bg-white rounded-xl shadow-sm border border-slate-100 text-slate-400 hover:text-indigo-600 transition-colors">
                            <HelpCircle size={20} />
                        </button>
                        <div className="hidden group-hover:block absolute bottom-full right-0 sm:right-0 sm:left-auto left-1/2 sm:left-auto sm:translate-x-0 -translate-x-1/2 mb-2 w-64 max-w-[calc(100vw-2rem)] p-3 bg-slate-900 text-white text-xs rounded-xl shadow-xl z-50 max-h-[80vh] overflow-y-auto">
                            <div className="font-bold mb-2">P&L (Прибыль и Убытки)</div>
                            <p className="mb-2">Отчет о финансовых результатах: выручка, себестоимость, комиссии, логистика и итоговая прибыль.</p>
                            <div className="font-bold mb-2 mt-3">Unit Экономика</div>
                            <p>Анализ прибыльности каждого товара: ROI, маржа, себестоимость и рекомендации по оптимизации.</p>
                            <div className="absolute bottom-0 right-4 sm:right-4 sm:left-auto left-1/2 sm:left-auto sm:translate-x-0 -translate-x-1/2 transform translate-y-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-slate-900"></div>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
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
                    <button
                        onClick={async () => {
                            setPdfLoading(true);
                            try {
                                const token = window.Telegram?.WebApp?.initData || '';
                                if (!token) {
                                    alert('Ошибка авторизации. Перезагрузите страницу.');
                                    return;
                                }
                                const endpoint = viewMode === 'unit' 
                                    ? '/api/finance/report/unit-economy-pdf'
                                    : '/api/finance/report/pnl-pdf';
                                const url = `${API_URL}${endpoint}?x_tg_data=${encodeURIComponent(token)}`;
                                window.open(url, '_blank');
                            } catch (e) {
                                alert('Не удалось скачать PDF: ' + (e.message || ''));
                            } finally {
                                setPdfLoading(false);
                            }
                        }}
                        disabled={pdfLoading}
                        className="p-2 bg-white rounded-xl border border-slate-100 shadow-sm text-slate-400 hover:text-indigo-600 transition-colors disabled:opacity-50"
                        title={viewMode === 'unit' ? 'Скачать PDF Unit экономики' : 'Скачать PDF P&L'}
                    >
                        {pdfLoading ? <Loader2 size={20} className="animate-spin" /> : <Download size={20} />}
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
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="font-bold text-lg">
                                {pnlData ? 'P&L (реальные данные)' : 'Проекция (по текущей скорости)'}
                            </h3>
                            {user?.plan === 'start' && (
                                <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded-lg font-bold">
                                    Демо: только вчера
                                </span>
                            )}
                        </div>
                        {pnlLoading ? (
                            <div className="flex justify-center p-10"><Loader2 className="animate-spin text-emerald-600" size={24}/></div>
                        ) : pnlError ? (
                            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm">
                                <div className="font-bold text-amber-900 mb-2">⚠️ {pnlError}</div>
                                {user?.plan === 'start' && (
                                    <div className="text-amber-700 mt-2">
                                        <p className="mb-2">На тарифе <strong>Старт</strong> доступен демо-режим P&L (только данные за вчера).</p>
                                        <p>Для полного доступа к P&L обновите тариф на <strong>Аналитик</strong> или <strong>Стратег</strong>.</p>
                                    </div>
                                )}
                            </div>
                        ) : (pnlData?.data && pnlData.data.length > 0) ? (
                            <>
                                <div className="h-64 w-full">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={pnlData.data}>
                                            <Tooltip 
                                                cursor={{fill: '#f1f5f9'}}
                                                contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)'}}
                                            />
                                            <ReferenceLine y={0} stroke="#cbd5e1" />
                                            <Bar dataKey="cm3" radius={[4, 4, 4, 4]}>
                                                {pnlData.data.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.cm3 > 0 ? '#10b981' : '#ef4444'} />
                                                ))}
                                            </Bar>
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                                <div className="grid grid-cols-2 gap-2 mt-4">
                                    {pnlData.data.slice(-1)[0] && (() => {
                                        const last = pnlData.data.slice(-1)[0];
                                        return [
                                            { name: 'Выручка', value: last.net_sales },
                                            { name: 'COGS', value: -last.cogs },
                                            { name: 'Комиссия', value: -last.commission },
                                            { name: 'Логистика', value: -last.logistics },
                                            { name: 'Штрафы', value: -last.penalties },
                                            { name: 'CM3', value: last.cm3 }
                                        ].map((s, i) => (
                                            <div key={i} className="flex justify-between text-sm border-b border-slate-50 last:border-0 py-2">
                                                <span className="text-slate-500">{s.name}</span>
                                                <span className={`font-bold ${s.value > 0 ? 'text-slate-800' : 'text-red-500'}`}>
                                                    {Math.round(s.value).toLocaleString()} ₽
                                                </span>
                                            </div>
                                        ));
                                    })()}
                                </div>
                            </>
                        ) : pnlStats.length > 0 ? (
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
                            <strong>Обратите внимание:</strong> Выручка рассчитывается от Вашей цены реализации (до СПП). Скидка Постоянного Покупателя (СПП) предоставляется за счет Wildberries и не уменьшает вашу базу для выплат (обычно).
                        </p>
                    </div>
                </div>
            ) : (
                <div className="space-y-4 animate-in slide-in-from-left-8">
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
                            const price = item.price_structure?.selling || 0;
                            const basicPrice = item.price_structure?.basic || 0;
                            const discount = item.price_structure?.discount || 0;

                            const commPct = item.commission_percent || 25;
                            const commVal = Math.round(price * (commPct / 100));
                            const logVal = Math.round(item.logistics || 50);
                            
                            return (
                                <div key={item.sku} className="bg-white p-5 rounded-3xl border border-slate-100 shadow-sm relative group">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="min-w-0">
                                            <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">SKU {item.sku}</div>
                                            
                                            {/* Блок Цены - ВОДОПАД */}
                                            <div className="flex flex-col relative">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm text-slate-400 line-through decoration-slate-300">{basicPrice} ₽</span>
                                                    <span className="text-[10px] font-bold bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded-md">-{discount}%</span>
                                                </div>
                                                <div className="flex items-baseline gap-2">
                                                    <div className="font-bold text-xl leading-tight text-slate-800">{price} ₽</div>
                                                    <div className="group/tooltip relative">
                                                        <HelpCircle size={12} className="text-slate-300 cursor-help" />
                                                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-slate-800 text-white text-[10px] rounded-lg opacity-0 group-hover/tooltip:opacity-100 pointer-events-none transition-opacity z-10">
                                                            Это ваша цена (до СПП). Комиссия считается от неё. На сайте цена может быть ниже (напр. {Math.round(price * 0.7)}₽) за счет скидки WB.
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="text-[9px] text-emerald-600 font-medium mt-0.5">База для выплат</div>
                                            </div>
                                        </div>
                                        <button onClick={() => setEditingCost(item)} className="p-3 bg-slate-50 text-slate-500 rounded-2xl hover:bg-indigo-50 hover:text-indigo-600 transition-colors">
                                            <Calculator size={20} />
                                        </button>
                                    </div>
                                    
                                    <div className="space-y-2 mb-4 relative">
                                        <div className="absolute left-[3px] top-2 bottom-2 w-0.5 bg-slate-100 rounded-full"></div>
                                        
                                        {/* Комиссия */}
                                        <div className="flex justify-between items-center text-sm pl-4 relative">
                                            <div className="w-2 h-2 bg-purple-300 rounded-full absolute -left-[4px]"></div>
                                            <span className="text-slate-400 flex items-center gap-1">
                                                Комиссия WB <span className="text-[10px] bg-purple-50 text-purple-600 px-1 rounded">{commPct}%</span>
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