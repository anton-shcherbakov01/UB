import React, { useState, useEffect } from 'react';
import { Bell, ShoppingCart, DollarSign, BarChart3, Filter, ArrowLeft, Save, Loader2 } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const Toggle = ({ label, description, checked, onChange, icon: Icon, color }) => (
    <div className="bg-white p-4 rounded-2xl border border-slate-100 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl ${checked ? `bg-${color}-100 text-${color}-600` : 'bg-slate-100 text-slate-400'}`}>
                <Icon size={20} />
            </div>
            <div>
                <div className="font-bold text-slate-800 text-sm">{label}</div>
                {description && <div className="text-xs text-slate-400 mt-0.5">{description}</div>}
            </div>
        </div>
        <button 
            onClick={() => onChange(!checked)}
            className={`w-12 h-7 rounded-full transition-colors relative ${checked ? `bg-${color}-500` : 'bg-slate-200'}`}
        >
            <div className={`absolute top-1 left-1 w-5 h-5 bg-white rounded-full transition-transform shadow-sm ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
        </button>
    </div>
);

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
            await fetch(`${API_URL}/api/notifications/settings`, {
                method: 'POST',
                headers: { ...getTgHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            alert("Настройки сохранены");
        } catch (e) {
            alert("Ошибка сохранения");
        } finally {
            setSaving(false);
        }
    };

    const update = (key, val) => setSettings(prev => ({ ...prev, [key]: val }));

    if (loading) return <div className="h-screen flex items-center justify-center"><Loader2 className="animate-spin text-indigo-600"/></div>;

    return (
        <div className="p-4 space-y-6 pb-24 animate-in fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    {onNavigate && <button onClick={() => onNavigate('profile')} className="p-2 bg-white rounded-xl border border-slate-100"><ArrowLeft size={20} className="text-slate-500"/></button>}
                    <div>
                        <h1 className="text-2xl font-black text-slate-900">Уведомления</h1>
                        <p className="text-slate-500 text-xs font-medium">Настройка бота</p>
                    </div>
                </div>
            </div>

            {/* Main Toggles */}
            <div className="space-y-3">
                <h3 className="font-bold text-slate-400 text-xs uppercase tracking-wider px-2">Мгновенные события</h3>
                <Toggle 
                    label="Новые заказы" 
                    description="Присылать уведомление сразу при поступлении заказа"
                    checked={settings.notify_new_orders} 
                    onChange={v => update('notify_new_orders', v)}
                    icon={ShoppingCart} color="indigo"
                />
                <Toggle 
                    label="Выкупы и Продажи" 
                    description="Уведомлять, когда клиент забрал товар"
                    checked={settings.notify_buyouts} 
                    onChange={v => update('notify_buyouts', v)}
                    icon={DollarSign} color="emerald"
                />
            </div>

            {/* Details Config */}
            {(settings.notify_new_orders || settings.notify_buyouts) && (
                <div className="space-y-3 animate-in fade-in slide-in-from-top-2">
                    <h3 className="font-bold text-slate-400 text-xs uppercase tracking-wider px-2">Детализация сообщений</h3>
                    <Toggle 
                        label="Показывать дневную выручку" 
                        description="Добавлять сумму продаж за день в каждое уведомление"
                        checked={settings.show_daily_revenue} 
                        onChange={v => update('show_daily_revenue', v)}
                        icon={Filter} color="blue"
                    />
                </div>
            )}

            {/* Summary */}
            <div className="space-y-3">
                <h3 className="font-bold text-slate-400 text-xs uppercase tracking-wider px-2">Аналитика</h3>
                <Toggle 
                    label="Часовая сводка" 
                    description="Присылать отчет каждый час (Выручка, Заказы)"
                    checked={settings.notify_hourly_stats} 
                    onChange={v => update('notify_hourly_stats', v)}
                    icon={BarChart3} color="violet"
                />
                {settings.notify_hourly_stats && (
                    <Toggle 
                        label="Воронка продаж" 
                        description="Посетители -> Корзина -> Заказ в сводке"
                        checked={settings.show_funnel} 
                        onChange={v => update('show_funnel', v)}
                        icon={Filter} color="violet"
                    />
                )}
            </div>

            {/* Save Button */}
            <button 
                onClick={handleSave}
                disabled={saving}
                className="w-full py-4 bg-slate-900 text-white rounded-2xl font-bold flex items-center justify-center gap-2 shadow-xl active:scale-95 transition-all fixed bottom-24 left-4 right-4 max-w-[calc(100%-2rem)] mx-auto"
            >
                {saving ? <Loader2 className="animate-spin"/> : <Save size={20}/>}
                Сохранить настройки
            </button>
        </div>
    );
};

export default NotificationsPage;