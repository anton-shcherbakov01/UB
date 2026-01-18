import React, { useState, useEffect } from 'react';
import { 
    Search, MapPin, Rocket, Info, CheckCircle, 
    AlertTriangle, Loader2, RotateCcw, HelpCircle, 
    Target, Globe, Zap, ArrowLeft, FileDown
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const SEOTrackerPage = ({ onNavigate }) => {
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
            .then(data => {
                if (Array.isArray(data)) setRegions(data);
            })
            .catch(() => {});
    }, []);

    const handleReset = () => {
        setSku('');
        setQuery('');
        setResult(null);
        setLoading(false);
    };

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
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4 bg-[#F4F4F9] min-h-screen">
            
            {/* Unified Header */}
            <div className="flex justify-between items-stretch h-24 mb-6">
                 {/* Main Header Card */}
                 <div className="bg-gradient-to-br from-indigo-600 to-blue-600 p-5 rounded-[28px] text-white shadow-xl shadow-indigo-200 relative overflow-hidden flex-1 mr-3 flex items-center justify-between transition-colors duration-500">
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <Rocket size={24} className="text-cyan-300"/>
                            SEO Радар
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            Real-time Rank Tracking
                        </p>
                    </div>

                    <div className="relative z-10">
                        {/* Можно добавить доп. иконку или статус здесь */}
                        <Globe size={24} className="text-white/20" />
                    </div>
                    
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 {/* Right Sidebar Buttons */}
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button 
                        onClick={() => onNavigate('home')} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95 border border-slate-100"
                        title="Назад"
                      >
                          <ArrowLeft size={24}/>
                      </button>
                      
                      <div className="group relative h-full">
                        <button 
                            onClick={() => setShowGeoInfo(!showGeoInfo)}
                            className={`h-full w-full rounded-2xl shadow-sm transition-colors flex items-center justify-center active:scale-95 border ${showGeoInfo ? 'bg-indigo-50 border-indigo-200 text-indigo-600' : 'bg-white border-slate-100 text-slate-400 hover:text-indigo-600'}`}
                        >
                            <HelpCircle size={24}/>
                        </button>
                      </div>
                 </div>
            </div>

            {/* ГЕО-ПОДСКАЗКА (Выпадающая) */}
            {showGeoInfo && (
                <div className="bg-slate-800 text-slate-200 p-4 rounded-3xl shadow-xl animate-in zoom-in-95 duration-200 text-xs leading-relaxed border-b-4 border-indigo-500">
                    <div className="flex items-center gap-2 mb-2 text-indigo-300 font-bold uppercase tracking-widest">
                        <Globe size={14}/> Как работает ГЕО?
                    </div>
                    Мы эмулируем запрос через конкретные дата-центры. Wildberries выдает разные результаты для Москвы, Казани или Хабаровска из-за **скорости доставки** (priority) и наличия товара на локальных складах. Используйте это, чтобы проверить видимость товара в ключевых регионах.
                </div>
            )}

            {/* ФОРМА ПОИСКА */}
            <div className="bg-white p-5 rounded-[32px] shadow-sm border border-slate-200 space-y-4">
                <div>
                    <label className="text-[10px] font-black text-slate-400 uppercase ml-1 mb-1 block tracking-widest">Артикул товара</label>
                    <div className="relative">
                        <Target className="absolute left-3 top-3.5 text-slate-300" size={18} />
                        <input 
                            type="number" 
                            value={sku} 
                            onChange={e => setSku(e.target.value)}
                            placeholder="Например: 12345678" 
                            className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-2xl font-mono text-lg outline-none focus:ring-2 ring-indigo-100 border border-slate-100 transition-all"
                        />
                    </div>
                </div>

                <div>
                    <label className="text-[10px] font-black text-slate-400 uppercase ml-1 mb-1 block tracking-widest">Ключевой запрос</label>
                    <div className="relative">
                        <Search className="absolute left-3 top-3.5 text-slate-300" size={18} />
                        <input 
                            type="text" 
                            value={query} 
                            onChange={e => setQuery(e.target.value)}
                            placeholder="Например: платье летнее" 
                            className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-2xl font-bold outline-none focus:ring-2 ring-indigo-100 border border-slate-100 transition-all"
                        />
                    </div>
                </div>

                <div>
                    <label className="text-[10px] font-black text-slate-400 uppercase ml-1 mb-1 block tracking-widest">Регион сканирования</label>
                    <div className="relative">
                        <MapPin className="absolute left-3 top-3.5 text-slate-300" size={18} />
                        <select 
                            value={geo} 
                            onChange={e => setGeo(e.target.value)}
                            className="w-full pl-10 pr-10 py-3 bg-slate-50 rounded-2xl font-bold outline-none border border-slate-100 appearance-none focus:ring-2 ring-indigo-100"
                        >
                            {regions.length > 0 ? regions.map(r => (
                                <option key={r.key} value={r.key}>{r.label}</option>
                            )) : <option value="moscow">Москва</option>}
                        </select>
                        <div className="absolute right-3 top-4 pointer-events-none text-slate-400">
                            <Info size={16}/>
                        </div>
                    </div>
                </div>

                <button 
                    onClick={handleCheck} 
                    disabled={loading || !sku || !query}
                    className={`w-full py-4 rounded-2xl font-black text-lg transition-all flex justify-center items-center gap-3 shadow-lg ${
                        loading || !sku || !query 
                        ? 'bg-slate-100 text-slate-300' 
                        : 'bg-slate-900 text-white shadow-indigo-100 active:scale-95'
                    }`}
                >
                    {loading ? <Loader2 className="animate-spin" /> : <Zap size={20} className="text-yellow-400 fill-current" />}
                    {loading ? "Ищем в выдаче..." : "Запустить Радар"}
                </button>
            </div>

            {/* РЕЗУЛЬТАТЫ */}
            {result && (
                <div className="mt-2 animate-in slide-in-from-bottom-8 duration-500">
                    {result.status === 'success' ? (
                        <div className="space-y-4">
                            <div className="bg-white border-2 border-emerald-100 p-6 rounded-[32px] relative overflow-hidden shadow-xl shadow-emerald-50">
                                <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-50 rounded-full blur-3xl -mr-16 -mt-16 opacity-60"></div>
                                
                                <div className="flex items-center gap-2 text-emerald-600 font-black text-xs uppercase tracking-widest mb-4 relative z-10">
                                    <CheckCircle size={16}/> Позиция найдена
                                </div>

                                <div className="flex items-end gap-3 relative z-10">
                                    <div className="text-7xl font-black text-slate-900 tracking-tighter">
                                        #{result.data.absolute_pos}
                                    </div>
                                    <div className="mb-2">
                                        <div className="text-xs font-bold text-slate-400 uppercase tracking-widest">Место</div>
                                        <div className="text-emerald-500 font-black text-sm">В ТОП-500</div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-3 mt-6 relative z-10">
                                    <div className="bg-slate-50 border border-slate-100 p-3 rounded-2xl text-center">
                                        <div className="text-[10px] font-bold text-slate-400 uppercase mb-1">Страница</div>
                                        <div className="text-xl font-black text-slate-800">{result.data.page}</div>
                                    </div>
                                    <div className="bg-slate-50 border border-slate-100 p-3 rounded-2xl text-center">
                                        <div className="text-[10px] font-bold text-slate-400 uppercase mb-1">На странице</div>
                                        <div className="text-xl font-black text-slate-800">{result.data.position}</div>
                                    </div>
                                </div>

                                {result.data.is_advertising && (
                                    <div className="mt-4 p-3 bg-indigo-600 rounded-2xl text-white flex items-center justify-between shadow-lg shadow-indigo-100">
                                        <div className="flex items-center gap-2">
                                            <Zap size={16} className="text-yellow-300 fill-current" />
                                            <span className="text-xs font-black uppercase tracking-wider">Рекламное буст-место</span>
                                        </div>
                                        <div className="text-[10px] font-bold bg-white/20 px-2 py-1 rounded-lg">
                                            CPM: {result.data.cpm || 'Auto'}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Полезная карточка после нахождения */}
                            <div className="bg-indigo-50 p-5 rounded-3xl border border-indigo-100 flex gap-4">
                                <div className="bg-white p-2 h-10 w-10 rounded-xl shadow-sm flex items-center justify-center shrink-0">
                                    <Info className="text-indigo-600" size={20}/>
                                </div>
                                <div className="text-xs text-indigo-900 leading-snug font-medium">
                                    <b>Совет:</b> Если вы видите рекламную пометку, значит текущая позиция удерживается за счет ставок. Чтобы расти органически, работайте над CTR карточки и скоростью доставки в выбранном ГЕО.
                                </div>
                            </div>
                            
                            {/* Кнопка PDF */}
                            <button 
                                onClick={async () => {
                                    try {
                                        const params = new URLSearchParams();
                                        if (sku) params.append('sku', sku);
                                        if (query) params.append('keyword', query);
                                        const x_tg_data = new URLSearchParams(window.location.search).get('tgWebAppData') || '';
                                        if (x_tg_data) params.append('x_tg_data', x_tg_data);
                                        const url = `${API_URL}/api/seo/report/tracker-pdf?${params.toString()}`;
                                        window.open(url, '_blank');
                                    } catch (e) {
                                        alert('Не удалось скачать PDF: ' + (e.message || ''));
                                    }
                                }}
                                className="w-full py-4 bg-white text-indigo-600 border-2 border-indigo-100 rounded-2xl font-bold flex justify-center items-center gap-2 shadow-sm active:scale-95 transition-all hover:bg-indigo-50"
                            >
                                <FileDown size={20}/> Скачать PDF отчет
                            </button>

                            {/* Блок изменения региона */}
                            <div className="bg-white p-5 rounded-3xl border border-slate-200 shadow-sm">
                                <div className="flex items-center gap-2 mb-3">
                                    <MapPin className="text-indigo-600" size={18}/>
                                    <span className="text-sm font-bold text-slate-800">Проверить в другом регионе</span>
                                </div>
                                <div className="flex gap-3">
                                    <div className="flex-1 relative">
                                        <select 
                                            value={geo} 
                                            onChange={e => setGeo(e.target.value)}
                                            className="w-full pl-10 pr-4 py-3 bg-slate-50 rounded-2xl font-bold text-sm outline-none border border-slate-100 appearance-none focus:ring-2 ring-indigo-100"
                                        >
                                            {regions.length > 0 ? regions.map(r => (
                                                <option key={r.key} value={r.key}>{r.label}</option>
                                            )) : <option value="moscow">Москва</option>}
                                        </select>
                                        <MapPin className="absolute left-3 top-3.5 text-slate-300" size={18} />
                                    </div>
                                    <button 
                                        onClick={handleCheck}
                                        disabled={loading}
                                        className="px-6 py-3 bg-indigo-600 text-white rounded-2xl font-bold text-sm hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                    >
                                        {loading ? <Loader2 className="animate-spin" size={16}/> : <Search size={16}/>}
                                        Проверить
                                    </button>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="bg-white p-8 rounded-[32px] border border-slate-200 text-center shadow-lg">
                            <div className="w-20 h-20 bg-rose-50 rounded-full flex items-center justify-center mx-auto mb-4 border border-rose-100">
                                <AlertTriangle className="text-rose-500" size={40}/>
                            </div>
                            <div className="font-black text-slate-800 text-xl uppercase tracking-tight">Вне зоны радара</div>
                            <div className="text-sm text-slate-500 mt-3 font-medium leading-relaxed">
                                Товар не обнаружен в первых 500 результатах. <br/>
                                Это может быть связано с нулевыми остатками на складах региона <b>{geo}</b> или отсутствием индексации по запросу <b>"{query}"</b>.
                            </div>
                            <div className="space-y-3 mt-6">
                                <button 
                                    onClick={handleReset}
                                    className="text-indigo-600 font-bold text-sm border-b-2 border-indigo-100 pb-1"
                                >
                                    Попробовать другой запрос
                                </button>
                                
                                {/* Блок изменения региона для случая "не найдено" */}
                                <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200 text-left mt-4">
                                    <div className="flex items-center gap-2 mb-3">
                                        <MapPin className="text-indigo-600" size={16}/>
                                        <span className="text-xs font-bold text-slate-700">Попробовать другой регион</span>
                                    </div>
                                    <div className="flex gap-2">
                                        <div className="flex-1 relative">
                                            <select 
                                                value={geo} 
                                                onChange={e => setGeo(e.target.value)}
                                                className="w-full pl-8 pr-4 py-2 bg-white rounded-xl font-bold text-xs outline-none border border-slate-200 appearance-none focus:ring-2 ring-indigo-100"
                                            >
                                                {regions.length > 0 ? regions.map(r => (
                                                    <option key={r.key} value={r.key}>{r.label}</option>
                                                )) : <option value="moscow">Москва</option>}
                                            </select>
                                            <MapPin className="absolute left-2 top-2.5 text-slate-300" size={14} />
                                        </div>
                                        <button 
                                            onClick={handleCheck}
                                            disabled={loading}
                                            className="px-4 py-2 bg-indigo-600 text-white rounded-xl font-bold text-xs hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                                        >
                                            {loading ? <Loader2 className="animate-spin" size={12}/> : <Search size={12}/>}
                                            Проверить
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ИНСТРУКЦИЯ (Если ничего еще не искали) */}
            {!result && !loading && (
                <div className="bg-slate-50 border border-dashed border-slate-300 p-6 rounded-[32px]">
                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4 text-center">Как пользоваться</h3>
                    <div className="space-y-4">
                        <div className="flex gap-3">
                            <div className="text-indigo-500 font-black">01.</div>
                            <div className="text-xs text-slate-500 font-medium">Введите артикул (SKU) вашего товара или товара конкурента.</div>
                        </div>
                        <div className="flex gap-3">
                            <div className="text-indigo-500 font-black">02.</div>
                            <div className="text-xs text-slate-500 font-medium">Укажите ключевую фразу. Радар проверит позиции именно по ней.</div>
                        </div>
                        <div className="flex gap-3">
                            <div className="text-indigo-500 font-black">03.</div>
                            <div className="text-xs text-slate-500 font-medium">Выберите регион. Это критично для понимания вашей "видимости" в разных частях страны.</div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default SEOTrackerPage;