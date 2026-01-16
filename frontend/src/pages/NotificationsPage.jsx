import React, { useState, useEffect } from 'react';
import { Bell, ShoppingCart, DollarSign, BarChart3, Filter, ArrowLeft, Save, Loader2, Clock } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

// Карта цветов для Tailwind, чтобы избежать динамических строк, которые Tailwind не компилирует
const COLOR_MAPS = {
    indigo: { bg: 'bg-indigo-500', light: 'bg-indigo-100', text: 'text-indigo-600' },
    emerald: { bg: 'bg-emerald-500', light: 'bg-emerald-100', text: 'text-emerald-600' },
    blue: { bg: 'bg-blue-500', light: 'bg-blue-100', text: 'text-blue-600' },
    violet: { bg: 'bg-violet-500', light: 'bg-violet-100', text: 'text-violet-600' },
};

const Toggle = ({ label, description, checked, onChange, icon: Icon, color }) => {
    const colors = COLOR_MAPS[color] || COLOR_MAPS.indigo;
    return (
        <div className="bg-white p-4 rounded-2xl border border-slate-200 flex items-center justify-between shadow-sm">
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
            <div className="flex items-center gap-3">
                <button onClick={() => onNavigate('profile')} className="p-2 bg-white rounded-xl border border-slate-200 shadow-sm"><ArrowLeft size={20} className="text-slate-500"/></button>
                <div>
                    <h1 className="text-2xl font-black text-slate-900 leading-none">Уведомления</h1>
                    <p className="text-[10px] text-slate-400 font-bold uppercase mt-1 tracking-wider">Настройка Telegram бота</p>
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
                className="w-full py-4 bg-slate-900 text-white rounded-2xl font-bold flex items-center justify-center gap-3 shadow-xl active:scale-95 transition-all sticky bottom-4"
            >
                {saving ? <Loader2 className="animate-spin" size={20}/> : <Save size={20}/>}
                Сохранить настройки
            </button>
        </div>
    );
};

export default NotificationsPage;