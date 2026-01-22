import React, { useState, useEffect } from 'react';
import { 
    ArrowLeft, ShieldAlert, AlertOctagon, RefreshCw, Search, 
    Loader2, DollarSign, PenLine, Save, X, HelpCircle, TrendingDown 
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const PriceControlPage = ({ onBack }) => {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [editingSku, setEditingSku] = useState(null); 
    const [tempPrice, setTempPrice] = useState('');     
    const [refreshing, setRefreshing] = useState(null);
    
    // НОВОЕ: Состояние для модалки помощи
    const [showHelp, setShowHelp] = useState(false);

    useEffect(() => { fetchItems(); }, []);

    const fetchItems = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/control/list`, { headers: getTgHeaders() });
            if (res.ok) setItems(await res.json());
        } catch (e) { console.error(e); } 
        finally { setLoading(false); }
    };

    const startEditing = (item) => {
        setEditingSku(item.sku);
        setTempPrice(item.min_price > 0 ? item.min_price : '');
    };

    const savePrice = async (sku) => {
        const priceVal = Number(tempPrice);
        setItems(prev => prev.map(i => i.sku === sku ? { 
            ...i, 
            min_price: priceVal,
            status: priceVal > 0 && i.current_price < priceVal ? 'danger' : 'ok'
        } : i));
        
        setEditingSku(null);

        try {
            await fetch(`${API_URL}/api/control/update`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ sku, min_price: priceVal, is_active: true })
            });
        } catch (e) { console.error(e); fetchItems(); }
    };

    const handleForceRefresh = async (sku) => {
        setRefreshing(sku);
        try {
            const res = await fetch(`${API_URL}/api/control/refresh/${sku}`, {
                method: 'POST',
                headers: getTgHeaders()
            });
            if (res.ok) {
                const data = await res.json();
                setItems(prev => prev.map(i => i.sku === sku ? { ...i, current_price: data.current_price } : i));
            }
        } catch (e) { alert("Ошибка обновления"); }
        finally { setRefreshing(null); }
    };

    const filteredItems = items.filter(i => 
        String(i.sku).includes(search)
    );

    const dangerCount = items.filter(i => i.status === 'danger').length;
    const activeCount = items.filter(i => i.min_price > 0).length;

    // --- Модалка помощи ---
    const HelpModal = () => {
        if (!showHelp) return null;
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in" onClick={() => setShowHelp(false)}>
                <div className="bg-white rounded-[32px] w-full max-w-sm p-6 shadow-2xl relative" onClick={e => e.stopPropagation()}>
                    <button onClick={() => setShowHelp(false)} className="absolute top-4 right-4 p-2 bg-slate-50 rounded-full text-slate-400 hover:bg-slate-100 transition-colors">
                        <X size={20} />
                    </button>
                    
                    <div className="text-center mb-6">
                        <div className="w-16 h-16 bg-rose-50 rounded-full flex items-center justify-center mx-auto mb-4 text-rose-500">
                            <ShieldAlert size={32} />
                        </div>
                        <h3 className="text-xl font-black text-slate-800">Как это работает?</h3>
                    </div>
                    
                    <div className="space-y-4 text-sm text-slate-600 leading-relaxed">
                        <p>
                            Система защищает вас от <b>автоматических акций Wildberries</b>, когда цена товара падает ниже вашей рентабельности.
                        </p>
                        
                        <div className="bg-slate-50 p-3 rounded-2xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1 flex items-center gap-2"><DollarSign size={14} className="text-indigo-600"/> Stop-Loss</div>
                            Это минимальная цена, которую вы готовы принять. Если WB опустит цену ниже этого порога — мы пришлем уведомление.
                        </div>

                        <div className="bg-slate-50 p-3 rounded-2xl border border-slate-100">
                            <div className="font-bold text-slate-800 mb-1 flex items-center gap-2"><RefreshCw size={14} className="text-emerald-600"/> Мониторинг</div>
                            Бот проверяет ваши цены <b>каждые 15 минут</b> через официальный API.
                        </div>
                        
                        <p className="text-xs text-slate-400 text-center pt-2">
                            Уведомления приходят в Telegram бот. Убедитесь, что они включены в настройках.
                        </p>
                    </div>
                    
                    <button onClick={() => setShowHelp(false)} className="w-full bg-slate-900 text-white py-3.5 rounded-2xl font-bold mt-6 active:scale-95 transition-transform">
                        Все понятно
                    </button>
                </div>
            </div>
        );
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in bg-[#F4F4F9] min-h-screen">
            <HelpModal />
            
            {/* Header */}
            <div className="flex justify-between items-stretch h-24 mb-6">
                 <div className={`bg-gradient-to-br ${dangerCount > 0 ? 'from-rose-500 to-red-600' : 'from-emerald-500 to-teal-600'} p-5 rounded-[28px] text-white shadow-xl ${dangerCount > 0 ? 'shadow-rose-200' : 'shadow-emerald-200'} relative overflow-hidden flex-1 mr-3 flex items-center justify-between transition-all duration-500`}>
                    <div className="relative z-10">
                        <h1 className="text-xl font-black flex items-center gap-2 mb-1">
                            {dangerCount > 0 ? <AlertOctagon size={24} className="text-white animate-pulse"/> : <ShieldAlert size={24} className="text-white"/>}
                            {dangerCount > 0 ? 'Тревога!' : 'Цены под защитой'}
                        </h1>
                        <p className="text-xs font-medium text-white/90">
                            {dangerCount > 0 
                                ? `${dangerCount} товаров продаются в минус!` 
                                : `На контроле: ${activeCount} шт.`}
                        </p>
                    </div>
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button onClick={onBack} className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95 border border-slate-100">
                         <ArrowLeft size={24}/>
                     </button>
                     <button onClick={() => setShowHelp(true)} className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95 border border-slate-100">
                         <HelpCircle size={24}/>
                     </button>
                 </div>
            </div>

            {/* Search */}
            <div className="bg-white p-3 rounded-2xl shadow-sm border border-slate-100 flex items-center">
                <Search className="text-slate-400 ml-2" size={20}/>
                <input 
                    className="w-full p-2 outline-none text-sm font-bold bg-transparent placeholder:font-normal"
                    placeholder="Поиск по названию или SKU..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                />
            </div>

            {/* List */}
            {loading ? (
                <div className="flex justify-center py-20"><Loader2 className="animate-spin text-indigo-500" size={32}/></div>
            ) : filteredItems.length === 0 ? (
                <div className="text-center py-20 text-slate-400 font-medium">Список пуст</div>
            ) : (
                <div className="space-y-4">
                    {filteredItems.map(item => {
                        const isDanger = item.status === 'danger';
                        const isEditing = editingSku === item.sku;
                        
                        return (
                            <div key={item.sku} className={`bg-white p-5 rounded-3xl border-2 shadow-sm transition-all relative overflow-hidden ${isDanger ? 'border-rose-500 ring-4 ring-rose-100' : 'border-slate-100'}`}>
                                {isDanger && <div className="absolute top-0 right-0 bg-rose-500 text-white text-[9px] font-bold px-3 py-1 rounded-bl-xl">PRICE DROP</div>}
                                
                                <div className="flex gap-4 mb-4">
                                    <div className="relative w-20 h-24 shrink-0 rounded-xl overflow-hidden bg-slate-100 border border-slate-200">
                                        <img src={item.photo} className="w-full h-full object-cover" alt=""/>
                                    </div>
                                    <div className="flex-1 min-w-0 py-1">
                                        <div className="text-[10px] font-black text-slate-400 uppercase tracking-wider mb-1">SKU {item.sku}</div>
                                        
                                        <div className="flex items-baseline gap-2 mb-2">
                                            <span className={`text-2xl font-black ${isDanger ? 'text-rose-600' : 'text-slate-800'}`}>
                                                {item.current_price} ₽
                                            </span>
                                            <span className="text-xs text-slate-400 line-through font-bold">{item.base_price}</span>
                                            <span className="text-[10px] font-bold bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded">
                                                -{item.discount}%
                                            </span>
                                        </div>

                                        {item.cost_price > 0 && (
                                            <div className="text-xs font-medium text-slate-500 flex items-center gap-1">
                                                Себест: {item.cost_price} ₽
                                                {item.current_price < item.cost_price && (
                                                    <span className="text-rose-500 font-bold flex items-center gap-0.5"><TrendingDown size={12}/> Убыток</span>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Controls */}
                                <div className={`p-3 rounded-2xl flex items-center justify-between gap-3 transition-colors ${isEditing ? 'bg-indigo-50 ring-2 ring-indigo-200' : 'bg-slate-50'}`}>
                                    <div className="flex items-center gap-2 flex-1">
                                        <ShieldAlert size={18} className={item.min_price > 0 ? "text-indigo-600" : "text-slate-300"} />
                                        
                                        {isEditing ? (
                                            <input 
                                                type="number"
                                                autoFocus
                                                className="w-full bg-transparent font-black text-lg text-indigo-900 outline-none placeholder:text-indigo-300"
                                                placeholder="Мин. цена"
                                                value={tempPrice}
                                                onChange={e => setTempPrice(e.target.value)}
                                            />
                                        ) : (
                                            <div onClick={() => startEditing(item)} className="cursor-pointer">
                                                <div className="text-[10px] font-bold text-slate-400 uppercase leading-none mb-0.5">Stop-Loss</div>
                                                <div className={`text-sm font-black ${item.min_price > 0 ? 'text-slate-800' : 'text-slate-300'}`}>
                                                    {item.min_price > 0 ? `${item.min_price} ₽` : 'Не задан'}
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {isEditing ? (
                                        <div className="flex gap-2">
                                            <button onClick={() => setEditingSku(null)} className="p-2 bg-white text-slate-400 rounded-xl shadow-sm"><X size={18}/></button>
                                            <button onClick={() => savePrice(item.sku)} className="p-2 bg-indigo-600 text-white rounded-xl shadow-lg shadow-indigo-200"><Save size={18}/></button>
                                        </div>
                                    ) : (
                                        <button onClick={() => startEditing(item)} className="p-2 bg-white text-slate-400 hover:text-indigo-600 rounded-xl shadow-sm border border-slate-200 transition-colors">
                                            <PenLine size={16}/>
                                        </button>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default PriceControlPage;