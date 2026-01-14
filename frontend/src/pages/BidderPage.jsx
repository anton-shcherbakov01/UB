// import React, { useState, useEffect } from 'react';
// import { 
//     Target, ShieldCheck, Zap, Activity, TrendingDown, Loader2, 
//     AlertCircle, RefreshCw, Settings, Save, X, Search, BarChart3
// } from 'lucide-react';
// import { API_URL, getTgHeaders } from '../config';

// const BidderPage = () => {
//     const [campaigns, setCampaigns] = useState([]);
//     const [dashboard, setDashboard] = useState(null);
//     const [logs, setLogs] = useState([]);
//     const [loading, setLoading] = useState(true);
//     const [error, setError] = useState(null);

//     // Состояние для редактирования настроек
//     const [editingCamp, setEditingCamp] = useState(null);
//     const [formData, setFormData] = useState({});
//     const [saving, setSaving] = useState(false);

//     const fetchData = async () => {
//         if (campaigns.length === 0) setLoading(true);
//         setError(null);
//         try {
//             const [campRes, dashRes, logsRes] = await Promise.all([
//                 fetch(`${API_URL}/api/bidder/campaigns`, { headers: getTgHeaders() }),
//                 fetch(`${API_URL}/api/bidder/dashboard`, { headers: getTgHeaders() }),
//                 fetch(`${API_URL}/api/bidder/logs`, { headers: getTgHeaders() })
//             ]);

//             const cData = campRes.ok ? await campRes.json() : [];
//             const dData = dashRes.ok ? await dashRes.json() : {};
//             const lData = logsRes.ok ? await logsRes.json() : [];

//             setCampaigns(cData);
//             setDashboard(dData);
//             setLogs(lData);
//         } catch (e) {
//             console.error(e);
//             setError("Не удалось загрузить данные биддера.");
//         } finally {
//             setLoading(false);
//         }
//     };

//     useEffect(() => {
//         fetchData();
//         const interval = setInterval(fetchData, 10000); 
//         return () => clearInterval(interval);
//     }, []);

//     const openSettings = (camp) => {
//         setFormData({
//             is_active: camp.is_active || false,
//             keyword: camp.keyword || '',
//             target_pos: camp.target_pos || 1,
//             strategy: camp.strategy || 'target_pos',
//             min_bid: camp.min_bid || 125,
//             max_bid: camp.max_bid || 1000,
//             max_cpm: camp.max_cpm || 2000,
//             check_organic: camp.check_organic || false,
//             sku: camp.sku || ''
//         });
//         setEditingCamp(camp);
//     };

//     const saveSettings = async () => {
//         setSaving(true);
//         try {
//             const res = await fetch(`${API_URL}/api/bidder/campaigns/${editingCamp.id}/settings`, {
//                 method: 'POST',
//                 headers: {
//                     ...getTgHeaders(),
//                     'Content-Type': 'application/json'
//                 },
//                 body: JSON.stringify({
//                     campaign_id: editingCamp.id,
//                     ...formData
//                 })
//             });

//             if (res.ok) {
//                 setCampaigns(prev => prev.map(c => 
//                     c.id === editingCamp.id ? { ...c, ...formData } : c
//                 ));
//                 setEditingCamp(null);
//             } else {
//                 alert("Ошибка сохранения настроек");
//             }
//         } catch (e) {
//             console.error(e);
//             alert("Ошибка сети");
//         } finally {
//             setSaving(false);
//         }
//     };

//     // --- Components ---

//     const CampaignCard = ({ camp }) => (
//         <div className="bg-slate-900 text-white p-5 rounded-3xl relative overflow-hidden mb-3 shadow-lg shadow-slate-300">
//             <div className={`absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl -mr-10 -mt-10 transition-colors duration-500 ${camp.is_active ? 'bg-emerald-500/20' : 'bg-slate-600/20'}`}></div>
            
//             <div className="flex justify-between items-start mb-4 relative z-10">
//                 <div className="flex-1 pr-4">
//                     <div className="flex items-center gap-2 mb-1">
//                         <span className={`w-2 h-2 rounded-full shrink-0 ${camp.is_active ? 'bg-emerald-400 shadow-[0_0_10px_#34d399]' : 'bg-slate-500'}`}></span>
//                         <h4 className="font-bold text-sm text-slate-200 line-clamp-1">{camp.name || `Кампания ${camp.id}`}</h4>
//                     </div>
//                     {camp.keyword ? (
//                         <div className="flex items-center gap-1 text-[10px] text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded w-fit mt-1">
//                             <Search size={10} /> {camp.keyword}
//                         </div>
//                     ) : (
//                         <div className="text-[10px] text-amber-500/80 mt-1 flex items-center gap-1">
//                             <AlertCircle size={10}/> Не настроено
//                         </div>
//                     )}
//                 </div>
                
//                 <button 
//                     onClick={() => openSettings(camp)}
//                     className="bg-white/10 active:bg-white/20 p-2 rounded-xl backdrop-blur-md transition-colors"
//                 >
//                     <Settings size={18} className="text-slate-200" />
//                 </button>
//             </div>

//             <div className="grid grid-cols-3 gap-2 relative z-10 bg-slate-800/50 p-3 rounded-2xl border border-white/5">
//                 <div className="text-center border-r border-white/5">
//                     <div className="text-[9px] text-slate-400 uppercase mb-0.5">Цель</div>
//                     <div className="font-black text-sm">{camp.target_pos || '-'} <span className="text-[9px] font-normal text-slate-500">место</span></div>
//                 </div>
//                 <div className="text-center border-r border-white/5">
//                     <div className="text-[9px] text-slate-400 uppercase mb-0.5">Лимит</div>
//                     <div className="font-black text-sm">{camp.max_bid || '-'} <span className="text-[9px] font-normal text-slate-500">₽</span></div>
//                 </div>
//                 <div className="text-center">
//                     <div className="text-[9px] text-slate-400 uppercase mb-0.5">Статус</div>
//                     <div className={`font-bold text-xs py-0.5 px-2 rounded-lg inline-block ${camp.status === 9 ? 'text-emerald-400 bg-emerald-400/10' : 'text-amber-400 bg-amber-400/10'}`}>
//                         {camp.status === 9 ? 'Run' : 'Pause'}
//                     </div>
//                 </div>
//             </div>
//         </div>
//     );

//     const SettingsModal = () => {
//         if (!editingCamp) return null;

//         return (
//             <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
//                 <div className="bg-white w-full max-w-md rounded-t-[32px] sm:rounded-[32px] p-6 pb-10 shadow-2xl animate-in slide-in-from-bottom duration-300">
                    
//                     <div className="flex justify-between items-center mb-6">
//                         <h3 className="text-xl font-black text-slate-800">Настройки Биддера</h3>
//                         <button onClick={() => setEditingCamp(null)} className="p-2 bg-slate-100 rounded-full text-slate-500">
//                             <X size={20} />
//                         </button>
//                     </div>

//                     <div className="space-y-5 max-h-[70vh] overflow-y-auto pr-1 custom-scrollbar">
                        
//                         <div className="flex items-center justify-between bg-slate-50 p-4 rounded-2xl border border-slate-100">
//                             <span className="font-bold text-slate-700">Биддер включен</span>
//                             <label className="relative inline-flex items-center cursor-pointer">
//                                 <input 
//                                     type="checkbox" 
//                                     className="sr-only peer"
//                                     checked={formData.is_active}
//                                     onChange={e => setFormData({...formData, is_active: e.target.checked})}
//                                 />
//                                 <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
//                             </label>
//                         </div>

//                         <div>
//                             <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5 ml-1">
//                                 Ключевая фраза (обязательно)
//                             </label>
//                             <div className="relative">
//                                 <Search className="absolute left-3 top-3 text-slate-400" size={18}/>
//                                 <input 
//                                     type="text" 
//                                     value={formData.keyword}
//                                     onChange={e => setFormData({...formData, keyword: e.target.value})}
//                                     placeholder="напр. платье женское вечернее"
//                                     className="w-full bg-slate-50 border border-slate-200 text-slate-800 font-bold rounded-xl py-3 pl-10 pr-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
//                                 />
//                             </div>
//                             <p className="text-[10px] text-slate-400 mt-1 ml-1">По этой фразе мы будем проверять реальный аукцион.</p>
//                         </div>

//                         <div>
//                             <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5 ml-1">Стратегия</label>
//                             <div className="grid grid-cols-3 gap-2">
//                                 {[
//                                     { id: 'target_pos', label: 'Позиция', icon: Target },
//                                     { id: 'pid', label: 'PID Smart', icon: Activity },
//                                     { id: 'shadowing', label: 'Тень', icon: TrendingDown }
//                                 ].map(s => (
//                                     <button
//                                         key={s.id}
//                                         onClick={() => setFormData({...formData, strategy: s.id})}
//                                         className={`flex flex-col items-center gap-1 p-3 rounded-xl border-2 transition-all ${
//                                             formData.strategy === s.id 
//                                             ? 'border-indigo-500 bg-indigo-50 text-indigo-700' 
//                                             : 'border-slate-100 bg-white text-slate-400'
//                                         }`}
//                                     >
//                                         <s.icon size={20} />
//                                         <span className="text-[10px] font-bold">{s.label}</span>
//                                     </button>
//                                 ))}
//                             </div>
//                         </div>

//                         <div className="grid grid-cols-2 gap-4">
//                             <div>
//                                 <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1 ml-1">Целевое место</label>
//                                 <input 
//                                     type="number" 
//                                     value={formData.target_pos}
//                                     onChange={e => setFormData({...formData, target_pos: parseInt(e.target.value)})}
//                                     className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-center"
//                                 />
//                             </div>
//                             <div>
//                                 <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1 ml-1">Макс. ставка (₽)</label>
//                                 <input 
//                                     type="number" 
//                                     value={formData.max_bid}
//                                     onChange={e => setFormData({...formData, max_bid: parseInt(e.target.value)})}
//                                     className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-center"
//                                 />
//                             </div>
//                         </div>

//                         <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100 space-y-4">
//                             <h4 className="flex items-center gap-2 font-bold text-slate-700 text-sm">
//                                 <ShieldCheck size={16} className="text-emerald-500"/> Защита бюджета
//                             </h4>
                            
//                             <div className="flex items-center justify-between">
//                                 <span className="text-xs text-slate-600 font-medium">Проверять органику</span>
//                                 <input 
//                                     type="checkbox"
//                                     checked={formData.check_organic}
//                                     onChange={e => setFormData({...formData, check_organic: e.target.checked})}
//                                     className="w-5 h-5 accent-emerald-500 rounded cursor-pointer"
//                                 />
//                             </div>
//                             <p className="text-[10px] text-slate-400 leading-tight">Если товар уже в топе поиска бесплатно, биддер не будет тратить бюджет.</p>

//                             <div className="pt-2 border-t border-slate-200">
//                                 <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Хард-лимит CPM (Аварийный)</label>
//                                 <input 
//                                     type="number" 
//                                     value={formData.max_cpm}
//                                     onChange={e => setFormData({...formData, max_cpm: parseInt(e.target.value)})}
//                                     className="w-full bg-white border border-slate-200 rounded-lg p-2 text-sm"
//                                 />
//                             </div>
//                         </div>

//                     </div>

//                     <button 
//                         onClick={saveSettings}
//                         disabled={saving || !formData.keyword}
//                         className="w-full mt-6 bg-slate-900 text-white font-bold py-4 rounded-2xl flex items-center justify-center gap-2 disabled:opacity-50 active:scale-95 transition-transform"
//                     >
//                         {saving ? <Loader2 className="animate-spin" /> : <Save size={20} />}
//                         {saving ? 'Сохранение...' : 'Сохранить настройки'}
//                     </button>
//                 </div>
//             </div>
//         );
//     }

//     if (loading && campaigns.length === 0) {
//         return <div className="flex justify-center items-center h-[80vh]"><Loader2 className="animate-spin text-indigo-600" size={40} /></div>;
//     }

//     if (error && campaigns.length === 0) {
//         return (
//             <div className="p-6 text-center animate-in fade-in h-[80vh] flex flex-col justify-center items-center">
//                 <AlertCircle className="mx-auto text-red-500 mb-2" size={32}/>
//                 <h3 className="font-bold text-slate-800">Ошибка соединения</h3>
//                 <p className="text-sm text-slate-500 mt-2 mb-4">{error}</p>
//                 <button onClick={fetchData} className="bg-slate-900 text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2">
//                     <RefreshCw size={14} /> Повторить
//                 </button>
//             </div>
//         )
//     }

//     return (
//         <div className="p-4 space-y-6 pb-32 animate-in fade-in max-w-lg mx-auto">
//              <div className="bg-gradient-to-r from-violet-600 to-indigo-600 p-6 rounded-[32px] text-white shadow-xl shadow-indigo-200 relative overflow-hidden">
//                 <div className="relative z-10">
//                     <h1 className="text-2xl font-black flex items-center gap-2">
//                         <Zap className="text-yellow-300" fill="currentColor" /> Биддер
//                     </h1>
//                     <p className="text-sm opacity-90 mt-2 font-medium">Управление ставками</p>
                    
//                     <div className="mt-6 flex items-center gap-4">
//                         <div className="bg-white/10 backdrop-blur-md rounded-2xl p-3 flex-1">
//                             <div className="text-[10px] opacity-70 uppercase font-bold">Экономия 24ч</div>
//                             <div className="text-xl font-black flex items-center gap-1">
//                                 {dashboard?.total_budget_saved || 0} ₽ 
//                                 <TrendingDown size={14} className="text-emerald-300"/>
//                             </div>
//                         </div>
//                         <div className="bg-white/10 backdrop-blur-md rounded-2xl p-3 flex-1">
//                             <div className="text-[10px] opacity-70 uppercase font-bold">Активных</div>
//                             <div className="text-xl font-black">{dashboard?.campaigns_active || 0}</div>
//                         </div>
//                     </div>
//                 </div>
//             </div>

//             <div className="flex items-center justify-between px-2">
//                 <h3 className="font-bold text-lg text-slate-800">Кампании</h3>
//                 <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded-lg">{campaigns.length} шт</span>
//             </div>

//             <div className="space-y-3">
//                 {campaigns.length === 0 ? (
//                     <div className="text-center p-8 text-slate-400 bg-white rounded-3xl border border-dashed border-slate-200">
//                         Нет доступных рекламных кампаний
//                     </div>
//                 ) : (
//                     campaigns.map(camp => <CampaignCard key={camp.id} camp={camp} />)
//                 )}
//             </div>

//             {logs.length > 0 && (
//                 <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
//                     <div className="flex items-center gap-2 mb-4">
//                         <Activity size={16} className="text-slate-400" />
//                         <h3 className="font-bold text-sm text-slate-400 uppercase tracking-wider">Лог действий</h3>
//                     </div>
//                     <div className="space-y-4 relative before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[2px] before:bg-slate-100">
//                         {logs.map((l, i) => (
//                             <div key={i} className="flex gap-4 relative">
//                                 <div className="w-6 h-6 rounded-full bg-slate-50 border-2 border-white shadow-sm z-10 flex items-center justify-center text-[8px] font-black text-slate-400 shrink-0">
//                                     {l.time}
//                                 </div>
//                                 <div>
//                                     <div className="text-[10px] font-bold text-slate-400 mb-0.5">{l.full_date}</div>
//                                     <div className="text-xs font-medium text-slate-700 leading-relaxed bg-slate-50 p-2 rounded-lg border border-slate-100">
//                                         <div className="mb-1 font-bold text-indigo-900">ID: {l.campaign_id}</div>
//                                         {l.msg || l.reason}
//                                         {l.calculated_bid && (
//                                             <div className="mt-1 flex gap-2 text-[10px]">
//                                                 <span className="text-slate-500">
//                                                     Ставка: {l.previous_bid} &rarr; <span className="text-indigo-600 font-bold">{l.calculated_bid}₽</span>
//                                                 </span>
//                                                 <span className="text-slate-500">
//                                                     Поз: {l.current_pos} &rarr; {l.target_pos}
//                                                 </span>
//                                             </div>
//                                         )}
//                                     </div>
//                                 </div>
//                             </div>
//                         ))}
//                     </div>
//                 </div>
//             )}
            
//             <SettingsModal />
//         </div>
//     );
// }

// export default BidderPage;


import React from 'react';
import { Construction, Zap, ShieldCheck } from 'lucide-react';

const BidderPage = () => {
    // Мы убрали все useEffect и fetch запросы, 
    // чтобы компонент не нагружал бэкенд и не вызывал ошибок API.

    return (
        <div className="p-4 h-[85vh] flex flex-col relative overflow-hidden animate-in fade-in">
            {/* Декоративный фон */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl -mr-20 -mt-20"></div>
            <div className="absolute bottom-0 left-0 w-64 h-64 bg-violet-500/10 rounded-full blur-3xl -ml-20 -mb-20"></div>

            <div className="flex-1 flex flex-col items-center justify-center text-center relative z-10 pb-20">
                
                {/* Карточка статуса */}
                <div className="bg-white p-8 rounded-[40px] shadow-2xl shadow-indigo-100/50 mb-8 relative max-w-sm w-full mx-auto border border-white">
                     <div className="absolute inset-0 bg-gradient-to-b from-indigo-50/50 to-white/0 rounded-[40px] -z-10"></div>
                    
                    <div className="bg-indigo-100 w-24 h-24 rounded-3xl flex items-center justify-center mx-auto mb-6 shadow-inner">
                        <Construction className="text-indigo-600" size={48} />
                    </div>
                    
                    <h2 className="text-2xl font-black text-slate-800 mb-3">
                        Биддер на обновлении
                    </h2>
                    
                    <p className="text-sm text-slate-500 font-medium leading-relaxed mb-6">
                        Мы обновляем модули интеграции под новые требования API Wildberries (v6), чтобы управление ставками было безопасным и точным.
                    </p>

                    {/* Прогресс-бар для красоты */}
                    <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                        <div className="flex justify-between items-end mb-2">
                            <div className="flex items-center gap-2">
                                <Zap size={14} className="text-amber-500 fill-amber-500"/>
                                <span className="text-xs font-bold text-slate-700 uppercase tracking-wide">Статус работ</span>
                            </div>
                            <span className="text-xs font-black text-indigo-600">85%</span>
                        </div>
                        <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 w-[85%] rounded-full animate-pulse shadow-[0_0_10px_rgba(99,102,241,0.5)]"></div>
                        </div>
                        <div className="mt-3 flex gap-2 justify-center">
                            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-bold flex items-center gap-1">
                                <ShieldCheck size={10} /> Safe Mode
                            </span>
                            <span className="text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded font-bold">
                                API v6
                            </span>
                        </div>
                    </div>
                </div>

                <div className="text-xs font-medium text-slate-400">
                    Скоро раздел снова станет доступен
                </div>
            </div>
        </div>
    );
};

export default BidderPage;