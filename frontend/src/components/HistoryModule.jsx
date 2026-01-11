import React, { useState, useEffect } from 'react';
import { API_URL, getTgHeaders } from '../config';
import { Brain, Wand2, BarChart3, Search, Star, ThumbsDown, Crown, X, Loader2, ChevronLeft, Copy } from 'lucide-react';

const CopyableBlock = ({ label, text }) => (
  <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100 mb-3 group relative">
    <div className="flex justify-between items-center mb-2">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{label}</span>
        <button 
            onClick={() => { navigator.clipboard.writeText(text); alert('Скопировано'); }} 
            className="p-2 text-slate-300 hover:text-indigo-600 transition-colors bg-white rounded-lg shadow-sm"
        >
            <Copy size={14}/>
        </button>
    </div>
    <div className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{text}</div>
  </div>
);

const HistoryModule = ({ type, isOpen, onClose }) => {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedItem, setSelectedItem] = useState(null);

    useEffect(() => {
        if (isOpen) {
            setLoading(true);
            fetch(`${API_URL}/api/user/history?request_type=${type}`, { 
                headers: getTgHeaders()
            })
            .then(r => r.json())
            .then(data => { setHistory(data); setLoading(false); })
            .catch(() => setLoading(false));
        }
    }, [isOpen, type]);

    if (!isOpen) return null;

    const getTypeIcon = (t) => {
        switch(t) {
            case 'ai': return <Brain size={18}/>;
            case 'seo': return <Wand2 size={18}/>;
            case 'price': return <BarChart3 size={18}/>;
            default: return <Search size={18}/>;
        }
    };

    const renderDetails = (item) => {
        const data = item.data;
        
        // --- SEO History ---
        if (item.type === 'seo' && data.generated_content) {
            return (
                <div className="space-y-2 animate-in fade-in">
                    <div className="flex flex-wrap gap-1 mb-4">
                        {data.keywords?.map((k, i) => (
                            <span key={i} className="bg-indigo-50 text-indigo-700 px-2 py-1 rounded-lg text-[10px] font-bold">{k}</span>
                        ))}
                    </div>
                    <CopyableBlock label="Заголовок" text={data.generated_content.title} />
                    <CopyableBlock label="Описание" text={data.generated_content.description} />
                </div>
            )
        }

        // --- AI Analysis History ---
        if (item.type === 'ai' && data.ai_analysis) {
            return (
                <div className="space-y-4 animate-in fade-in">
                    <div className="flex gap-4 items-center bg-white border border-slate-100 p-3 rounded-2xl">
                         {data.image && <img src={data.image} className="w-12 h-16 object-cover rounded-lg" alt="product"/>}
                         <div>
                             <div className="font-bold text-lg flex items-center gap-1 text-amber-500"><Star size={16} fill="currentColor"/> {data.rating}</div>
                             <div className="text-xs text-slate-500">{data.reviews_count} отзывов</div>
                         </div>
                    </div>
                    <div className="bg-red-50 p-4 rounded-2xl border border-red-100">
                         <h4 className="font-bold text-red-600 text-sm mb-2 flex items-center gap-2"><ThumbsDown size={14}/> Жалобы</h4>
                         <ul className="text-sm space-y-2 text-slate-700">
                             {data.ai_analysis.flaws?.map((f,i) => <li key={i} className="bg-white p-2 rounded-lg shadow-sm text-xs">⛔ {f}</li>)}
                         </ul>
                    </div>
                    <div className="bg-indigo-50 p-4 rounded-2xl border border-indigo-100">
                         <h4 className="font-bold text-indigo-600 text-sm mb-2 flex items-center gap-2"><Crown size={14}/> Стратегия</h4>
                         <ul className="text-sm space-y-2 text-slate-700">
                             {data.ai_analysis.strategy?.map((s,i) => <li key={i} className="bg-white p-2 rounded-lg shadow-sm text-xs">{s}</li>)}
                         </ul>
                    </div>
                </div>
            )
        }

        // --- Price/Monitor History (Beautiful Card) ---
        if (item.type === 'price' && data.prices) {
            return (
                <div className="space-y-4 animate-in fade-in">
                    {/* Header */}
                    <div className="flex gap-4 items-start">
                        {data.image && <img src={data.image} className="w-16 h-20 object-cover rounded-lg bg-slate-100" alt="product" />}
                        <div>
                            <div className="text-[10px] font-bold text-slate-400 uppercase">{data.brand}</div>
                            <div className="font-bold text-sm leading-tight">{data.name}</div>
                            <div className="mt-1 text-xs bg-slate-100 inline-block px-2 py-1 rounded text-slate-500">Остаток: {data.stock_qty} шт</div>
                        </div>
                    </div>

                    {/* Prices Card */}
                    <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                        <div className="flex justify-between items-center mb-2">
                            <span className="text-sm font-medium text-slate-500">WB Кошелек</span>
                            <span className="text-xl font-black text-purple-600">{data.prices.wallet_purple} ₽</span>
                        </div>
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-xs text-slate-400">Обычная цена</span>
                            <span className="text-sm font-bold text-slate-700">{data.prices.standard_black} ₽</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-xs text-slate-400">До скидок</span>
                            <span className="text-xs text-slate-400 line-through">{data.prices.base_crossed} ₽</span>
                        </div>
                    </div>

                    {/* Metrics */}
                    {data.metrics && (
                        <div className="grid grid-cols-2 gap-3">
                            <div className="bg-emerald-50 p-3 rounded-xl border border-emerald-100">
                                <div className="text-[10px] text-emerald-600 font-bold uppercase">Скидка</div>
                                <div className="text-lg font-black text-emerald-700">{data.metrics.total_discount_percent}%</div>
                            </div>
                            <div className="bg-indigo-50 p-3 rounded-xl border border-indigo-100">
                                <div className="text-[10px] text-indigo-600 font-bold uppercase">Выгода</div>
                                <div className="text-lg font-black text-indigo-700">{data.metrics.wallet_benefit} ₽</div>
                            </div>
                        </div>
                    )}
                </div>
            )
        }

        // --- Fallback (JSON) ---
        return (
            <pre className="text-xs bg-slate-50 p-3 rounded-xl overflow-auto max-h-[60vh] text-slate-600 font-mono">
                {JSON.stringify(data, null, 2)}
            </pre>
        );
    };

    return (
        <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center animate-in fade-in duration-200">
            <div className="bg-white w-full max-w-lg sm:rounded-[32px] rounded-t-[32px] p-6 shadow-2xl relative max-h-[85vh] flex flex-col">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="font-bold text-lg">История</h3>
                    <button onClick={onClose} className="p-2 bg-slate-100 rounded-full text-slate-500 hover:bg-slate-200"><X size={20} /></button>
                </div>

                {!selectedItem ? (
                    <div className="flex-1 overflow-y-auto space-y-3 pb-4">
                        {loading ? (
                            <div className="flex justify-center p-10"><Loader2 className="animate-spin text-slate-400"/></div>
                        ) : history.length === 0 ? (
                            <div className="text-center p-10 text-slate-400 border border-dashed border-slate-200 rounded-2xl">Пусто</div>
                        ) : (
                            history.map(h => (
                                <div key={h.id} onClick={() => setSelectedItem(h)} className="bg-slate-50 p-3 rounded-xl flex items-center gap-3 cursor-pointer active:scale-[0.99] transition-transform hover:bg-slate-100">
                                    <div className="bg-white p-2 rounded-lg text-indigo-600 shadow-sm">{getTypeIcon(h.type)}</div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-bold text-sm truncate">{h.title || `SKU ${h.sku}`}</div>
                                        <div className="text-[10px] text-slate-400">{new Date(h.created_at).toLocaleString('ru-RU')}</div>
                                    </div>
                                    <ChevronLeft className="rotate-180 text-slate-300" size={16}/>
                                </div>
                            ))
                        )}
                    </div>
                ) : (
                    <div className="flex-1 overflow-y-auto pb-4">
                        <button onClick={() => setSelectedItem(null)} className="flex items-center gap-1 text-xs font-bold text-slate-400 mb-4 hover:text-indigo-600 transition-colors">
                            <ChevronLeft size={14}/> Назад к списку
                        </button>
                        <h3 className="font-bold text-xl mb-4 leading-tight">{selectedItem.title}</h3>
                        {renderDetails(selectedItem)}
                    </div>
                )}
            </div>
        </div>
    );
};

export default HistoryModule;