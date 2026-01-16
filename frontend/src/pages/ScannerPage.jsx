import React, { useState } from 'react';
import { Search, Loader2, ArrowRight, Wallet, Plus, Check } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import { useNavigate } from 'react-router-dom';

const ScannerPage = () => {
    const [sku, setSku] = useState('');
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false); // Загрузка сканирования
    const [adding, setAdding] = useState(false);   // Загрузка добавления в базу
    const navigate = useNavigate();

    // 1. Просто сканируем (получаем данные, но не сохраняем)
    const handleScan = async () => {
        if (!sku) return;
        setLoading(true);
        setData(null);
        try {
            const res = await fetch(`${API_URL}/api/monitoring/scan/${sku}`, { headers: getTgHeaders() });
            if (res.ok) {
                const json = await res.json();
                setData(json);
            } else {
                alert("Товар не найден на WB");
            }
        } catch (e) {
            console.error(e);
            alert("Ошибка сети");
        } finally {
            setLoading(false);
        }
    };

    // 2. Пользователь решил добавить товар в мониторинг
    const handleAddToMonitoring = async () => {
        if (!sku) return;
        setAdding(true);
        try {
            const res = await fetch(`${API_URL}/api/monitor/add/${sku}`, {
                method: 'POST',
                headers: getTgHeaders()
            });
            
            const result = await res.json();

            if (res.ok || result.status === 'exists') {
                // Если успешно или уже был - идем в список
                navigate('/monitor'); 
            } else if (res.status === 403) {
                alert(result.detail || "Лимит товаров исчерпан. Обновите тариф.");
            } else {
                alert("Ошибка при добавлении");
            }
        } catch (e) {
            console.error(e);
            alert("Ошибка сети");
        } finally {
            setAdding(false);
        }
    };

    return (
        <div className="p-4 max-w-lg mx-auto pb-32 animate-in fade-in">
            <h2 className="text-2xl font-black text-slate-800 mb-6">Сканер цен</h2>

            {/* Блок ввода и поиска */}
            <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-100">
                <div className="flex gap-2">
                    <input 
                        type="number" 
                        value={sku} 
                        onChange={e => setSku(e.target.value)}
                        placeholder="Артикул (например: 146972800)" 
                        className="flex-1 p-4 bg-slate-50 rounded-xl font-mono text-lg outline-none focus:ring-2 focus:ring-indigo-100 transition-all"
                    />
                    <button 
                        onClick={handleScan} 
                        disabled={loading || !sku}
                        className="bg-indigo-600 text-white p-4 rounded-xl active:scale-95 transition-transform disabled:opacity-70 disabled:active:scale-100"
                    >
                        {loading ? <Loader2 className="animate-spin"/> : <Search/>}
                    </button>
                </div>
                <p className="text-[10px] text-slate-400 mt-2 ml-1">
                    Введите артикул, чтобы проверить текущую цену и СПП перед добавлением.
                </p>
            </div>

            {/* Результат сканирования */}
            {data && (
                <div className="mt-6 bg-white p-5 rounded-3xl border border-slate-100 shadow-lg shadow-indigo-100/50 animate-in slide-in-from-bottom-4">
                    <div className="text-xs text-slate-400 font-bold mb-1 uppercase tracking-wider">
                        {data.brand}
                    </div>
                    <div className="font-bold text-lg leading-tight mb-6 text-slate-800">
                        {data.name}
                    </div>
                    
                    <div className="bg-gradient-to-r from-indigo-50 to-violet-50 p-4 rounded-2xl border border-indigo-100 flex items-center justify-between mb-6">
                        <div>
                            <div className="text-xs text-indigo-400 font-bold mb-1 flex items-center gap-1">
                                <Wallet size={12}/> Цена с СПП
                            </div>
                            <div className="text-3xl font-black text-indigo-700">
                                {data.price} ₽
                            </div>
                        </div>
                        <div className="text-right">
                             <div className="text-xs text-slate-400 font-bold mb-1">Рейтинг</div>
                             <div className="text-xl font-bold text-slate-700">★ {data.rating}</div>
                             <div className="text-[10px] text-slate-400">({data.review_count} отз.)</div>
                        </div>
                    </div>

                    {/* Кнопка добавления - появляется только после скана */}
                    <button 
                        onClick={handleAddToMonitoring} 
                        disabled={adding}
                        className="w-full py-4 bg-slate-900 text-white rounded-2xl font-bold text-sm flex items-center justify-center gap-2 active:scale-95 transition-transform shadow-lg shadow-slate-200"
                    >
                        {adding ? (
                            <><Loader2 size={18} className="animate-spin"/> Сохранение...</>
                        ) : (
                            <><Plus size={18}/> Добавить в Мониторинг</>
                        )}
                    </button>
                </div>
            )}

            {/* Кнопка тарифов (внизу, чтобы не мешала) */}
            <div className="mt-10 pt-6 border-t border-slate-100">
                <button 
                    onClick={() => navigate('/tariffs')} 
                    className="w-full py-4 bg-white border border-slate-200 text-slate-600 rounded-2xl font-bold flex items-center justify-between px-6 active:scale-95 transition-transform hover:bg-slate-50"
                >
                    <span>Лимиты и Тарифы</span>
                    <ArrowRight size={18} className="text-slate-400"/>
                </button>
            </div>
        </div>
    );
};

export default ScannerPage;