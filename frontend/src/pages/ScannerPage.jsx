import React, { useState } from 'react';
import { Search, Loader2, ArrowRight, Wallet, History } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import { useNavigate } from 'react-router-dom';

const ScannerPage = () => {
    const [sku, setSku] = useState('');
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleScan = async () => {
        if (!sku) return;
        setLoading(true);
        setData(null);
        try {
            // Используем новый эндпоинт в мониторинге
            const res = await fetch(`${API_URL}/api/monitoring/scan/${sku}`, { headers: getTgHeaders() });
            if (res.ok) {
                const json = await res.json();
                setData(json);
            } else {
                alert("Товар не найден");
            }
        } catch (e) {
            console.error(e);
            alert("Ошибка сети");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-4 max-w-lg mx-auto pb-32 animate-in fade-in">
            <h2 className="text-2xl font-black text-slate-800 mb-6">Сканер цен</h2>

            <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-100">
                <div className="flex gap-2">
                    <input type="number" value={sku} onChange={e => setSku(e.target.value)}
                        placeholder="Артикул (например: 146972800)" 
                        className="flex-1 p-4 bg-slate-50 rounded-xl font-mono text-lg outline-none focus:ring-2 ring-indigo-100"/>
                    <button onClick={handleScan} disabled={loading}
                        className="bg-indigo-600 text-white p-4 rounded-xl active:scale-95 transition-transform">
                        {loading ? <Loader2 className="animate-spin"/> : <Search/>}
                    </button>
                </div>
            </div>

            {data && (
                <div className="mt-6 bg-white p-5 rounded-3xl border border-slate-100 shadow-sm animate-in slide-in-from-bottom-4">
                    <div className="text-xs text-slate-400 font-bold mb-1 uppercase tracking-wider">{data.brand}</div>
                    <div className="font-bold text-lg leading-tight mb-6 text-slate-800">{data.name}</div>
                    
                    <div className="bg-gradient-to-r from-indigo-50 to-violet-50 p-4 rounded-2xl border border-indigo-100 flex items-center justify-between mb-4">
                        <div>
                            <div className="text-xs text-indigo-400 font-bold mb-1 flex items-center gap-1">
                                <Wallet size={12}/> Цена с СПП
                            </div>
                            <div className="text-3xl font-black text-indigo-700">{data.price} ₽</div>
                        </div>
                        <div className="text-right">
                             <div className="text-xs text-slate-400 font-bold mb-1">Рейтинг</div>
                             <div className="text-xl font-bold text-slate-700">★ {data.rating}</div>
                             <div className="text-[10px] text-slate-400">({data.review_count} отз.)</div>
                        </div>
                    </div>

                    <button onClick={() => navigate('/monitoring')} 
                        className="w-full py-3 bg-slate-900 text-white rounded-xl font-bold text-sm flex items-center justify-center gap-2 active:scale-95 transition-transform">
                        <History size={16}/>
                        Добавить в отслеживание
                    </button>
                </div>
            )}

            {/* Кнопка тарифов */}
            <div className="mt-8">
                <button onClick={() => navigate('/tariffs')} 
                    className="w-full py-4 bg-gradient-to-r from-violet-600 to-indigo-600 text-white rounded-2xl font-bold flex items-center justify-between px-6 shadow-lg shadow-indigo-200 active:scale-95 transition-transform">
                    <span>Лимиты и Тарифы</span>
                    <ArrowRight/>
                </button>
            </div>
        </div>
    );
};
export default ScannerPage;