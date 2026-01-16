import React, { useState, useEffect } from 'react';
import { Search, MapPin, Rocket, Info, CheckCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const SEOTrackerPage = () => {
    const [sku, setSku] = useState('');
    const [query, setQuery] = useState('');
    const [geo, setGeo] = useState('moscow');
    const [regions, setRegions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [showGeoInfo, setShowGeoInfo] = useState(false);

    useEffect(() => {
        fetch(`${API_URL}/api/seo/regions`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setRegions)
            .catch(() => {});
    }, []);

    const handleCheck = async () => {
        if (!sku || !query) return;
        setLoading(true);
        setResult(null);
        try {
            const res = await fetch(
                `${API_URL}/api/seo/position?query=${encodeURIComponent(query)}&sku=${sku}&geo=${geo}`,
                { headers: getTgHeaders() }
            );
            const data = await res.json();
            setResult(data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-4 max-w-lg mx-auto pb-32 animate-in fade-in">
            <h2 className="text-2xl font-black text-slate-800 mb-6 flex items-center gap-2">
                <Rocket className="text-indigo-600" />
                SEO Радар
            </h2>

            <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-100 space-y-4 relative">
                <div>
                    <label className="text-xs font-bold text-slate-400 ml-1">Артикул (SKU)</label>
                    <input type="number" value={sku} onChange={e => setSku(e.target.value)}
                        placeholder="12345678" className="w-full mt-1 p-3 bg-slate-50 rounded-xl font-mono text-lg outline-none focus:ring-2 ring-indigo-100"/>
                </div>
                <div>
                    <label className="text-xs font-bold text-slate-400 ml-1">Поисковой запрос</label>
                    <input type="text" value={query} onChange={e => setQuery(e.target.value)}
                        placeholder="платье женское" className="w-full mt-1 p-3 bg-slate-50 rounded-xl outline-none focus:ring-2 ring-indigo-100"/>
                </div>
                <div className="relative">
                    <label className="text-xs font-bold text-slate-400 ml-1 flex items-center gap-1">
                        <MapPin size={12}/> Гео-локация 
                        <button onClick={() => setShowGeoInfo(!showGeoInfo)} className="text-indigo-400"><Info size={12}/></button>
                    </label>
                    <select value={geo} onChange={e => setGeo(e.target.value)}
                        className="w-full mt-1 p-3 bg-slate-50 rounded-xl outline-none appearance-none bg-white border border-slate-100">
                        {regions.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
                    </select>
                    
                    {showGeoInfo && (
                        <div className="absolute z-10 top-full mt-2 p-3 bg-slate-800 text-white text-xs rounded-xl shadow-xl w-full">
                            <p className="font-bold mb-1">Как это работает?</p>
                            Мы подменяем системные Cookie (x-geo-id) в браузере парсера. 
                            Это заставляет Wildberries думать, что запрос идет из выбранного города.
                            Влияет на наличие товара, сроки доставки и ранжирование.
                        </div>
                    )}
                </div>

                <button onClick={handleCheck} disabled={loading}
                    className="w-full py-4 bg-indigo-600 text-white rounded-xl font-bold text-lg active:scale-95 transition-all flex justify-center items-center gap-2 shadow-lg shadow-indigo-200">
                    {loading ? <Loader2 className="animate-spin" /> : <Search size={20} />}
                    {loading ? "Сканирование..." : "Найти позицию"}
                </button>
            </div>

            {result && (
                <div className="mt-6 animate-in slide-in-from-bottom-4">
                    {result.status === 'success' ? (
                        <div className="bg-emerald-50 border border-emerald-100 p-5 rounded-3xl relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-100 rounded-full blur-2xl -mr-10 -mt-10"></div>
                            <div className="flex items-center gap-2 text-emerald-700 font-bold mb-2 relative z-10">
                                <CheckCircle size={20}/> Найдено!
                            </div>
                            <div className="flex items-baseline gap-2 relative z-10">
                                <span className="text-6xl font-black text-emerald-800">#{result.data.absolute_pos}</span>
                                <span className="text-sm text-emerald-600 font-bold">место</span>
                            </div>
                            <div className="mt-4 flex gap-3 relative z-10">
                                <div className="bg-white/80 px-4 py-2 rounded-xl text-xs font-bold text-emerald-800 border border-emerald-100">
                                    Страница {result.data.page}
                                </div>
                                <div className="bg-white/80 px-4 py-2 rounded-xl text-xs font-bold text-emerald-800 border border-emerald-100">
                                    Позиция {result.data.position}
                                </div>
                            </div>
                            {result.data.is_advertising && (
                                <div className="mt-3 relative z-10 bg-indigo-100 text-indigo-700 px-3 py-2 rounded-xl text-xs font-bold border border-indigo-200 inline-block">
                                    ⚡ Рекламное место (CPM: {result.data.cpm || 'Auto'})
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="bg-white p-6 rounded-3xl border border-slate-200 text-center shadow-sm">
                            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                <AlertTriangle className="text-slate-400" size={32}/>
                            </div>
                            <div className="font-bold text-slate-800 text-lg">Не найдено</div>
                            <div className="text-sm text-slate-500 mt-2">
                                Товар находится за пределами Топ-500 или не ранжируется по запросу "{query}" в регионе {geo}.
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
export default SEOTrackerPage;