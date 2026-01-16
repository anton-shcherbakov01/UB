import React, { useState, useEffect } from 'react';
import { Search, MapPin, Rocket, AlertTriangle, CheckCircle } from 'lucide-react';
import { getTgHeaders, API_URL } from '../config';

const SEOTrackerPage = () => {
    const [sku, setSku] = useState('');
    const [query, setQuery] = useState('');
    const [geo, setGeo] = useState('moscow');
    const [regions, setRegions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);

    useEffect(() => {
        // Загружаем список регионов
        fetch(`${API_URL}/api/seo/regions`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setRegions)
            .catch(e => console.error("Err regions", e));
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
            alert("Ошибка запроса");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-4 max-w-lg mx-auto pb-24">
            <h2 className="text-2xl font-black text-slate-800 mb-6 flex items-center gap-2">
                <Rocket className="text-indigo-600" />
                SEO Радар 2.0
            </h2>

            <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-100 space-y-4">
                {/* Inputs */}
                <div>
                    <label className="text-xs font-bold text-slate-400 ml-1">Артикул (SKU)</label>
                    <input 
                        type="number" 
                        value={sku} 
                        onChange={e => setSku(e.target.value)}
                        placeholder="Например: 12345678"
                        className="w-full mt-1 p-3 bg-slate-50 rounded-xl font-mono text-lg outline-none focus:ring-2 ring-indigo-100"
                    />
                </div>
                
                <div>
                    <label className="text-xs font-bold text-slate-400 ml-1">Поисковой запрос</label>
                    <input 
                        type="text" 
                        value={query} 
                        onChange={e => setQuery(e.target.value)}
                        placeholder="Например: платье женское"
                        className="w-full mt-1 p-3 bg-slate-50 rounded-xl outline-none focus:ring-2 ring-indigo-100"
                    />
                </div>

                <div>
                    <label className="text-xs font-bold text-slate-400 ml-1 flex items-center gap-1">
                        <MapPin size={12}/> Регион выдачи (Geo)
                    </label>
                    <select 
                        value={geo} 
                        onChange={e => setGeo(e.target.value)}
                        className="w-full mt-1 p-3 bg-slate-50 rounded-xl outline-none appearance-none"
                    >
                        {regions.map(r => (
                            <option key={r.key} value={r.key}>{r.label}</option>
                        ))}
                    </select>
                </div>

                <button 
                    onClick={handleCheck}
                    disabled={loading}
                    className="w-full py-4 bg-indigo-600 text-white rounded-xl font-bold text-lg active:scale-95 transition-all flex justify-center items-center gap-2"
                >
                    {loading ? <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent"/> : <Search size={20}/>}
                    {loading ? "Сканирую..." : "Найти позицию"}
                </button>
            </div>

            {/* Results */}
            {result && (
                <div className="mt-6 animate-in fade-in slide-in-from-bottom-4">
                    {result.status === 'success' ? (
                        <div className="bg-emerald-50 border border-emerald-100 p-5 rounded-3xl relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-100 rounded-full blur-2xl -mr-10 -mt-10"></div>
                            
                            <div className="relative z-10">
                                <div className="flex items-center gap-2 text-emerald-700 font-bold mb-2">
                                    <CheckCircle size={20}/> Найдено!
                                </div>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-4xl font-black text-emerald-800">
                                        #{result.data.absolute_pos}
                                    </span>
                                    <span className="text-sm text-emerald-600">
                                        место в общем поиске
                                    </span>
                                </div>

                                <div className="mt-4 grid grid-cols-2 gap-3">
                                    <div className="bg-white/60 p-3 rounded-xl">
                                        <div className="text-xs text-emerald-600">Страница</div>
                                        <div className="font-bold text-emerald-900">{result.data.page}</div>
                                    </div>
                                    <div className="bg-white/60 p-3 rounded-xl">
                                        <div className="text-xs text-emerald-600">Позиция на стр.</div>
                                        <div className="font-bold text-emerald-900">{result.data.position}</div>
                                    </div>
                                </div>

                                {result.data.is_advertising && (
                                    <div className="mt-3 bg-indigo-100 text-indigo-700 p-3 rounded-xl text-xs font-bold flex items-center justify-between border border-indigo-200">
                                        <span>⚡ Рекламная ставка (Аукцион)</span>
                                        <span>{result.data.cpm} ₽</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="bg-slate-100 p-5 rounded-3xl border border-slate-200 text-center">
                            <AlertTriangle className="mx-auto text-slate-400 mb-2" size={32}/>
                            <div className="font-bold text-slate-700">Не найдено</div>
                            <div className="text-sm text-slate-500 mt-1">
                                Товар находится дальше 5-й страницы или не ранжируется по этому запросу в регионе {geo.toUpperCase()}.
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default SEOTrackerPage;