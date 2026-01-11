import React, { useState, useEffect } from 'react';
import { TrendingUp, Loader2 } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const SeoTrackerPage = () => {
    const [positions, setPositions] = useState([]);
    const [sku, setSku] = useState('');
    const [keyword, setKeyword] = useState('');
    const [loading, setLoading] = useState(false);

    const loadPositions = () => {
        fetch(`${API_URL}/api/seo/positions`, {
             headers: getTgHeaders()
        }).then(r => r.json()).then(setPositions).catch(console.error);
    }

    useEffect(() => { loadPositions(); }, []);

    const handleTrack = async () => {
        if(!sku || !keyword) return;
        setLoading(true);
        try {
             await fetch(`${API_URL}/api/seo/track`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({sku: Number(sku), keyword})
             });
             alert("Задача добавлена! Обновите список через пару минут.");
             setSku(''); setKeyword('');
             loadPositions();
        } catch(e) { console.error(e); } finally { setLoading(false); }
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in">
             <div className="bg-gradient-to-r from-blue-500 to-cyan-500 p-6 rounded-3xl text-white shadow-xl shadow-blue-200">
                <h1 className="text-2xl font-black flex items-center gap-2">
                    <TrendingUp className="text-white" /> SEO Tracker
                </h1>
                <p className="text-sm opacity-90 mt-2">Отслеживайте позиции товаров в поисковой выдаче WB.</p>
            </div>

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                 <div className="flex gap-2 mb-3">
                     <input value={sku} onChange={e => setSku(e.target.value)} placeholder="SKU" className="w-1/3 bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none"/>
                     <input value={keyword} onChange={e => setKeyword(e.target.value)} placeholder="Ключевой запрос" className="flex-1 bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none"/>
                 </div>
                 <button onClick={handleTrack} disabled={loading} className="w-full bg-slate-900 text-white py-3 rounded-xl font-bold text-sm">
                     {loading ? <Loader2 className="animate-spin mx-auto"/> : 'Отследить позицию'}
                 </button>
            </div>

            <div className="space-y-3">
                {positions.map(p => (
                    <div key={p.id} className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex items-center justify-between">
                         <div>
                             <div className="font-bold text-sm">{p.keyword}</div>
                             <div className="text-[10px] text-slate-400">SKU: {p.sku}</div>
                         </div>
                         <div className="text-right">
                             <div className={`font-black text-lg ${p.position > 0 && p.position <= 10 ? 'text-emerald-500' : 'text-slate-700'}`}>
                                 {p.position > 0 ? `#${p.position}` : '>100'}
                             </div>
                             <div className="text-[9px] text-slate-300">{new Date(p.last_check).toLocaleDateString()}</div>
                         </div>
                    </div>
                ))}
            </div>
        </div>
    )
}

export default SeoTrackerPage;