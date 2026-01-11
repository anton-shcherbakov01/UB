import React, { useState, useEffect } from 'react';
import { 
    TrendingUp, Loader2, MapPin, Zap, Search, 
    CheckCircle2, AlertCircle, ArrowRight 
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const REGIONS = [
    { id: 'moscow', name: 'Москва' },
    { id: 'spb', name: 'СПб' },
    { id: 'kazan', name: 'Казань' },
    { id: 'krasnodar', name: 'Краснодар' },
    { id: 'novosibirsk', name: 'Новосибирск' },
];

const SeoTrackerPage = () => {
    const [positions, setPositions] = useState([]);
    const [sku, setSku] = useState('');
    const [keyword, setKeyword] = useState('');
    const [selectedRegions, setSelectedRegions] = useState(['moscow']);
    const [loading, setLoading] = useState(false);
    const [liveResult, setLiveResult] = useState(null);
    const [statusText, setStatusText] = useState('');

    const loadPositions = () => {
        fetch(`${API_URL}/api/seo/positions`, {
             headers: getTgHeaders()
        }).then(r => r.json()).then(setPositions).catch(console.error);
    }

    useEffect(() => { loadPositions(); }, []);

    const toggleRegion = (regId) => {
        if (selectedRegions.includes(regId)) {
            // Не даем убрать последний регион
            if (selectedRegions.length > 1) {
                setSelectedRegions(selectedRegions.filter(r => r !== regId));
            }
        } else {
            setSelectedRegions([...selectedRegions, regId]);
        }
    };

    const handleTrack = async () => {
        if(!sku || !keyword) return;
        setLoading(true);
        setLiveResult(null);
        setStatusText('Запуск проверки...');

        try {
             // 1. Запускаем задачу
             const res = await fetch(`${API_URL}/api/seo/track`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({
                    sku: Number(sku), 
                    keyword,
                    regions: selectedRegions
                })
             });
             
             if (!res.ok) throw new Error("Ошибка запуска");
             const data = await res.json();
             const taskId = data.task_id;

             // 2. Поллинг результата (Geo Tracking может занять время)
             let attempts = 0;
             while (attempts < 30) {
                 await new Promise(r => setTimeout(r, 2000));
                 
                 const statusRes = await fetch(`${API_URL}/api/monitor/status/${taskId}`);
                 const statusData = await statusRes.json();
                 
                 if (statusData.info) setStatusText(statusData.info);

                 if (statusData.status === 'SUCCESS') {
                     setLiveResult(statusData.data);
                     loadPositions(); // Обновляем историю
                     break;
                 }
                 
                 if (statusData.status === 'FAILURE') {
                     throw new Error(statusData.error || "Ошибка парсинга");
                 }
                 
                 attempts++;
             }

        } catch(e) { 
            console.error(e);
            alert("Ошибка: " + e.message); 
        } finally { 
            setLoading(false); 
        }
    }

    // Компонент карточки регионального результата
    const RegionResultCard = ({ regionId, data }) => {
        const regionName = REGIONS.find(r => r.id === regionId)?.name || regionId;
        const isBoosted = data?.is_boosted;
        const organicPos = data?.organic_pos;
        const adPos = data?.ad_pos;

        return (
            <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 flex justify-between items-center mb-2 animate-in fade-in slide-in-from-top-2">
                <div className="flex items-center gap-2">
                    <div className="bg-white p-1.5 rounded-lg shadow-sm text-slate-400">
                        <MapPin size={16}/>
                    </div>
                    <span className="text-sm font-bold text-slate-700">{regionName}</span>
                </div>
                
                <div className="flex items-center gap-3 text-right">
                    {/* Organic Status */}
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] uppercase font-bold text-slate-400">Органика</span>
                        <div className={`text-lg font-black flex items-center gap-1 ${organicPos > 0 ? 'text-emerald-600' : 'text-slate-300'}`}>
                            {organicPos > 0 ? `#${organicPos}` : '—'}
                            {organicPos > 0 && <CheckCircle2 size={14} />}
                        </div>
                    </div>

                    {/* Ad Status (Only if exists) */}
                    {(adPos > 0 || isBoosted) && (
                        <div className="flex flex-col items-end pl-3 border-l border-slate-200">
                            <span className="text-[10px] uppercase font-bold text-purple-400">Реклама</span>
                            <div className="text-lg font-black text-purple-600 flex items-center gap-1">
                                {adPos > 0 ? `#${adPos}` : 'Авто'}
                                <Zap size={14} fill="currentColor"/>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-blue-600 to-cyan-500 p-6 rounded-[32px] text-white shadow-xl shadow-cyan-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <TrendingUp className="text-white" /> SEO Tracker
                </h1>
                <p className="text-sm opacity-90 mt-2">Мульти-региональный мониторинг позиций (Geo & Ads).</p>
            </div>

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                 <div className="space-y-3 mb-4">
                     <input 
                        value={sku} 
                        onChange={e => setSku(e.target.value)} 
                        placeholder="Артикул (SKU)" 
                        type="number"
                        className="w-full bg-slate-50 rounded-xl p-4 text-sm font-bold outline-none focus:ring-2 ring-cyan-100 transition-all"
                     />
                     <input 
                        value={keyword} 
                        onChange={e => setKeyword(e.target.value)} 
                        placeholder="Ключевой запрос" 
                        className="w-full bg-slate-50 rounded-xl p-4 text-sm font-bold outline-none focus:ring-2 ring-cyan-100 transition-all"
                     />
                 </div>

                 {/* Region Selector */}
                 <div className="mb-4">
                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2 block">Регионы проверки</label>
                    <div className="flex flex-wrap gap-2">
                        {REGIONS.map(r => (
                            <button
                                key={r.id}
                                onClick={() => toggleRegion(r.id)}
                                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                                    selectedRegions.includes(r.id) 
                                    ? 'bg-cyan-50 border-cyan-200 text-cyan-700' 
                                    : 'bg-white border-slate-100 text-slate-400 hover:border-cyan-100'
                                }`}
                            >
                                {r.name}
                            </button>
                        ))}
                    </div>
                 </div>

                 <button 
                    onClick={handleTrack} 
                    disabled={loading || !sku || !keyword} 
                    className="w-full bg-slate-900 text-white py-4 rounded-xl font-bold text-sm shadow-lg active:scale-95 transition-transform disabled:opacity-70 flex justify-center items-center gap-2"
                 >
                     {loading ? (
                         <><Loader2 className="animate-spin" size={18}/> {statusText}</>
                     ) : (
                         <><Search size={18}/> Проверить позиции</>
                     )}
                 </button>
            </div>

            {/* LIVE RESULT BLOCK */}
            {liveResult && (
                <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-100 animate-in zoom-in-95">
                    <div className="flex items-center gap-2 mb-4 pb-4 border-b border-slate-50">
                        <div className="bg-emerald-100 text-emerald-600 p-2 rounded-xl">
                            <CheckCircle2 size={24}/>
                        </div>
                        <div>
                            <h3 className="font-bold text-slate-800">Результат проверки</h3>
                            <p className="text-xs text-slate-400">{liveResult.keyword} • SKU {liveResult.sku}</p>
                        </div>
                    </div>

                    <div className="space-y-1">
                        {liveResult.geo_details && Object.entries(liveResult.geo_details).map(([regId, data]) => (
                            <RegionResultCard key={regId} regionId={regId} data={data} />
                        ))}
                    </div>
                </div>
            )}

            {/* HISTORY LIST */}
            <div className="space-y-3">
                <h3 className="font-bold text-slate-400 text-xs uppercase px-2">История проверок</h3>
                {positions.length === 0 ? (
                    <div className="text-center p-8 text-slate-300 border border-dashed border-slate-200 rounded-2xl">
                        История пуста
                    </div>
                ) : (
                    positions.map(p => (
                        <div key={p.id} className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex items-center justify-between">
                            <div className="min-w-0 pr-4">
                                <div className="font-bold text-sm truncate">{p.keyword}</div>
                                <div className="text-[10px] text-slate-400">SKU: {p.sku}</div>
                            </div>
                            <div className="text-right whitespace-nowrap">
                                <div className={`font-black text-lg ${p.position > 0 && p.position <= 10 ? 'text-emerald-500' : 'text-slate-700'}`}>
                                    {p.position > 0 ? `#${p.position}` : '>100'}
                                </div>
                                <div className="text-[9px] text-slate-300">{new Date(p.last_check).toLocaleDateString()}</div>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}

export default SeoTrackerPage;