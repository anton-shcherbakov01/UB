import React, { useState, useEffect } from 'react';
import { Bell, ShoppingCart, DollarSign, BarChart3, Filter, ArrowLeft, Save, Loader2, Clock, HelpCircle } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

// Карта цветов для Tailwind
const COLOR_MAPS = {
    indigo: { bg: 'bg-indigo-500', light: 'bg-indigo-100', text: 'text-indigo-600' },
    emerald: { bg: 'bg-emerald-500', light: 'bg-emerald-100', text: 'text-emerald-600' },
    blue: { bg: 'bg-blue-500', light: 'bg-blue-100', text: 'text-blue-600' },
    violet: { bg: 'bg-violet-500', light: 'bg-violet-100', text: 'text-violet-600' },
};

const Toggle = ({ label, description, checked, onChange, icon: Icon, color }) => {
    const colors = COLOR_MAPS[color] || COLOR_MAPS.indigo;
    return (
        <div className="bg-white p-4 rounded-2xl border border-slate-200 flex items-center justify-between shadow-sm transition-all hover:shadow-md">
            <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-xl ${checked ? colors.light + ' ' + colors.text : 'bg-slate-100 text-slate-400'}`}>
                    <Icon size={20} />
                </div>
                <div>
                    <div className="font-bold text-slate-800 text-sm">{label}</div>
                    {description && <div className="text-[10px] text-slate-400 mt-0.5 leading-tight">{description}</div>}
                </div>
            </div>
            <button 
                onClick={() => onChange(!checked)}
                className={`w-12 h-7 rounded-full transition-colors relative border border-transparent ${checked ? colors.bg : 'bg-slate-300'}`}
            >
                <div className={`absolute top-0.5 left-0.5 w-5.5 h-5.5 bg-white rounded-full transition-transform shadow-md ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
            </button>
        </div>
    );
};

const NotificationsPage = ({ onNavigate }) => {
    const [settings, setSettings] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        fetch(`${API_URL}/api/notifications/settings`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setSettings)
            .finally(() => setLoading(false));
    }, []);

    const handleSave = async () => {
        setSaving(true);
        try {
            const res = await fetch(`${API_URL}/api/notifications/settings`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            if (res.ok) alert("Настройки успешно сохранены!");
        } catch (e) { alert("Ошибка при сохранении"); }
        finally { setSaving(false); }
    };

    const update = (key, val) => setSettings(prev => ({ ...prev, [key]: val }));

    if (loading) return <div className="h-screen flex items-center justify-center bg-[#F4F4F9]"><Loader2 className="animate-spin text-indigo-600" size={32}/></div>;

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in bg-[#F4F4F9] min-h-screen">
            
            {/* Unified Header */}
            <div className="flex justify-between items-stretch h-24 mb-6">
                 {/* Main Header Card */}
                 <div className="bg-gradient-to-r from-violet-600 to-indigo-600 p-5 rounded-[28px] text-white shadow-xl shadow-indigo-200 relative overflow-hidden flex-1 mr-3 flex items-center justify-between transition-colors duration-500">
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <Bell size={24} className="text-white"/>
                            Уведомления
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            Настройка Telegram бота
                        </p>
                    </div>
                    
                    <div className="relative z-10 hidden sm:block text-right">
                        <p className="text-[10px] opacity-75 font-medium text-white/80 flex items-center gap-1 justify-end">
                            <Clock size={12} /> МСК (UTC+3)
                        </p>
                    </div>

                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                 </div>
                 
                 {/* Right Sidebar Buttons */}
                 <div className="flex flex-col gap-2 w-14 shrink-0">
                     <button 
                        onClick={() => onNavigate('profile')} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                      >
                          <ArrowLeft size={24}/>
                      </button>
                      
                      <div className="group relative h-full">
                        <button className="bg-white h-full w-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95">
                            <HelpCircle size={24}/>
                        </button>
                        {/* Tooltip */}
                        <div className="hidden group-hover:block absolute top-0 right-full mr-2 w-64 p-4 bg-slate-900 text-white text-xs rounded-xl shadow-xl z-50">
                            <div className="font-bold mb-2 text-indigo-300">Настройки уведомлений</div>
                            <p className="mb-2">Включите уведомления о важных событиях:</p>
                            <ul className="space-y-1 text-[10px] list-disc pl-3">
                                <li><strong>Новые заказы</strong> - мгновенно при поступлении</li>
                                <li><strong>Выкупы</strong> - фиксация прибыли</li>
                                <li><strong>Сводка</strong> - отчеты по расписанию</li>
                            </ul>
                            <div className="absolute top-6 right-0 translate-x-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-l-slate-900"></div>
                        </div>
                      </div>
                 </div>
            </div>

            <div className="space-y-4">
                <section className="space-y-3">
                    <h3 className="font-bold text-slate-400 text-[10px] uppercase tracking-widest px-2">События</h3>
                    <Toggle 
                        label="Новые заказы" description="Мгновенно при поступлении заказа"
                        checked={settings.notify_new_orders} onChange={v => update('notify_new_orders', v)}
                        icon={ShoppingCart} color="indigo"
                    />
                    <Toggle 
                        label="Выкупы" description="Когда клиент оплатил и забрал товар"
                        checked={settings.notify_buyouts} onChange={v => update('notify_buyouts', v)}
                        icon={DollarSign} color="emerald"
                    />
                </section>

                <section className="space-y-3">
                    <h3 className="font-bold text-slate-400 text-[10px] uppercase tracking-widest px-2">Аналитика и Расписание</h3>
                    <Toggle 
                        label="Периодическая сводка" description="Отчет по выручке и воронке за день"
                        checked={settings.notify_hourly_stats} onChange={v => update('notify_hourly_stats', v)}
                        icon={BarChart3} color="violet"
                    />
                    
                    {settings.notify_hourly_stats && (
                        <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-4 animate-in slide-in-from-top-2">
                            <div>
                                <label className="text-[10px] font-black text-slate-400 uppercase flex items-center gap-2 mb-2">
                                    <Clock size={12}/> Частота отправки сводки
                                </label>
                                <div className="grid grid-cols-3 gap-2">
                                    {[1, 3, 6, 12, 24].map(h => (
                                        <button 
                                            key={h}
                                            onClick={() => update('summary_interval', h)}
                                            className={`py-2 rounded-xl text-xs font-bold border transition-all ${
                                                settings.summary_interval === h 
                                                ? 'bg-violet-600 border-violet-600 text-white shadow-lg shadow-violet-100' 
                                                : 'bg-slate-50 border-slate-100 text-slate-500'
                                            }`}
                                        >
                                            {h === 1 ? 'Раз в час' : h === 24 ? 'Раз в день' : `Каждые ${h}ч`}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <Toggle 
                                label="Воронка продаж" description="Добавить данные о просмотрах и корзинах"
                                checked={settings.show_funnel} onChange={v => update('show_funnel', v)}
                                icon={Filter} color="blue"
                            />
                        </div>
                    )}
                </section>
            </div>

            <button 
                onClick={handleSave} disabled={saving}
                className="w-full py-4 bg-slate-900 text-white rounded-2xl font-bold flex items-center justify-center gap-3 shadow-xl active:scale-95 transition-all sticky bottom-4 hover:bg-slate-800"
            >
                {saving ? <Loader2 className="animate-spin" size={20}/> : <Save size={20}/>}
                Сохранить настройки
            </button>
        </div>
    );
};

export default NotificationsPage;