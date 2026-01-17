import React, { useState, useEffect } from 'react';
import { ArrowLeft, Check, X, CreditCard, Loader2, Sparkles, ShoppingBag } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_URL, getTgHeaders } from '../config';

const TariffsPage = ({ onBack }) => {
    const navigate = useNavigate();
    const [tariffs, setTariffs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [payLoading, setPayLoading] = useState(false);

    useEffect(() => {
        fetchTariffs();
    }, []);

    const fetchTariffs = async () => {
        try {
            const res = await fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() });
            const data = await res.json();
            if (Array.isArray(data)) setTariffs(data);
        } catch (e) {
            console.error(e);
        }
    };

    const payRubles = async (plan) => {
        if (!plan.price || plan.price === "0 ₽") return;
        setPayLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/payment/robokassa/subscription`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ plan_id: plan.id })
            });
            const data = await res.json();
            if (res.ok && data.payment_url) {
                if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(data.payment_url);
                else window.open(data.payment_url, '_blank');
            } else {
                throw new Error(data.detail || "Ошибка инициализации платежа");
            }
        } catch (e) {
            alert(e.message);
        } finally {
            setPayLoading(false);
        }
    };

    // Определение функций для сравнения - все сервисы приложения
    const features = [
        { key: 'history_days', label: 'История продаж', start: '7 дней', analyst: '60 дней', strategist: '365 дней' },
        { key: 'ai_requests', label: 'AI-запросы в месяц', start: '5', analyst: '100', strategist: '1000' },
        { key: 'slots', label: 'Слоты товаров', start: '✓', analyst: '✓', strategist: '✓' },
        { key: 'notifications', label: 'Уведомления', start: '✓', analyst: '✓', strategist: '✓' },
        { key: 'pnl', label: 'P&L (Прибыль/Убыток)', start: 'Демо (вчера)', analyst: 'Полный доступ', strategist: 'Полный + Экспорт PDF' },
        { key: 'supply', label: 'Анализ поставок', start: '✓', analyst: '✓', strategist: '✓ + PDF' },
        { key: 'seo_gen', label: 'SEO генератор текстов', start: '✓', analyst: '✓', strategist: '✓ + PDF' },
        { key: 'seo_tracker', label: 'SEO трекер позиций', start: '✓', analyst: '✓', strategist: '✓ + PDF' },
        { key: 'ai_analysis', label: 'AI анализ отзывов', start: '✓ (5/мес)', analyst: '✓ (100/мес)', strategist: '✓ (1000/мес) + PDF' },
        { key: 'forensics', label: 'Форензика возвратов', start: '✗', analyst: '✓', strategist: '✓ + PDF' },
        { key: 'cashgap', label: 'Cash Gap анализ', start: '✗', analyst: '✗', strategist: '✓ + PDF' },
        { key: 'monitoring', label: 'Мониторинг цен', start: '✓', analyst: '✓ + PDF', strategist: '✓ + PDF' },
        { key: 'priority_poll', label: 'Приоритетный опрос', start: '✗', analyst: '✗', strategist: '✓' }
    ];

    const addons = [
        { id: 'extra_ai_100', name: 'Дополнительные AI-запросы', description: '+100 AI-запросов', price: 490 },
        { id: 'history_audit', name: 'Глубокий аудит PDF', description: 'Детальный PDF отчет', price: 990 }
    ];

    const startPlan = tariffs.find(t => t.id === 'start');
    const analystPlan = tariffs.find(t => t.id === 'analyst');
    const strategistPlan = tariffs.find(t => t.id === 'strategist');

    return (
        <div className="p-4 max-w-6xl mx-auto pb-32">
            <div className="flex items-center gap-3 mb-6">
                <button onClick={onBack || (() => navigate('/profile'))} className="text-slate-400 hover:text-slate-600">
                    <ArrowLeft size={24} />
                </button>
                <h1 className="text-2xl font-black text-slate-800">Тарифные планы</h1>
            </div>

            {/* Сравнительная таблица */}
            <div className="bg-white rounded-3xl shadow-sm border border-slate-100 overflow-hidden mb-6">
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-slate-50 border-b-2 border-slate-200">
                            <tr>
                                <th className="text-left p-4 font-bold text-sm text-slate-700 uppercase tracking-wide">Функции</th>
                                <th className="text-center p-4 font-black text-lg text-slate-900 min-w-[180px]">
                                    {startPlan?.name || 'Старт'}
                                    {startPlan?.current && <span className="ml-2 text-xs text-emerald-600 font-bold">(Активен)</span>}
                                </th>
                                <th className="text-center p-4 font-black text-lg text-indigo-600 min-w-[180px] relative">
                                    {analystPlan?.name || 'Аналитик'}
                                    {analystPlan?.current && <span className="ml-2 text-xs text-emerald-600 font-bold">(Активен)</span>}
                                    {analystPlan?.is_best && (
                                        <div className="absolute -top-2 left-1/2 -translate-x-1/2 bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-[10px] font-black uppercase tracking-widest px-3 py-1 rounded-full shadow-lg">
                                            <Sparkles size={10} className="inline mr-1" /> ХИТ
                                        </div>
                                    )}
                                </th>
                                <th className="text-center p-4 font-black text-lg text-slate-900 min-w-[180px]">
                                    {strategistPlan?.name || 'Стратег'}
                                    {strategistPlan?.current && <span className="ml-2 text-xs text-emerald-600 font-bold">(Активен)</span>}
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {features.map((feature, idx) => (
                                <tr key={feature.key} className={idx % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                                    <td className="p-4 text-sm font-medium text-slate-700">{feature.label}</td>
                                    <td className="p-4 text-center text-sm font-bold text-slate-600">{feature.start}</td>
                                    <td className="p-4 text-center text-sm font-bold text-indigo-600">{feature.analyst}</td>
                                    <td className="p-4 text-center text-sm font-bold text-slate-600">{feature.strategist}</td>
                                </tr>
                            ))}
                            <tr className="bg-slate-100 border-t-2 border-slate-200">
                                <td className="p-4 text-sm font-bold text-slate-900">Цена</td>
                                <td className="p-4 text-center">
                                    <div className="text-2xl font-black text-slate-900">{startPlan?.price || '0 ₽'}</div>
                                    {startPlan?.price !== "0 ₽" && <div className="text-xs text-slate-500 mt-1">/мес</div>}
                                </td>
                                <td className="p-4 text-center">
                                    <div className="text-2xl font-black text-indigo-600">{analystPlan?.price || '1490 ₽'}</div>
                                    <div className="text-xs text-slate-500 mt-1">/мес</div>
                                </td>
                                <td className="p-4 text-center">
                                    <div className="text-2xl font-black text-slate-900">{strategistPlan?.price || '4990 ₽'}</div>
                                    <div className="text-xs text-slate-500 mt-1">/мес</div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                {/* Кнопки покупки */}
                <div className="grid grid-cols-3 gap-4 p-4 bg-slate-50 border-t border-slate-200">
                    {startPlan && (
                        <div>
                            {startPlan.current ? (
                                <div className="w-full py-3 rounded-xl font-bold text-sm bg-emerald-50 text-emerald-600 flex justify-center items-center gap-2 border border-emerald-100">
                                    <Check size={16} /> Активен
                                </div>
                            ) : (
                                <button disabled className="w-full py-3 rounded-xl font-bold text-sm border-2 border-slate-200 text-slate-400 bg-white cursor-not-allowed">
                                    Бесплатно
                                </button>
                            )}
                        </div>
                    )}
                    {analystPlan && (
                        <div>
                            {analystPlan.current ? (
                                <div className="w-full py-3 rounded-xl font-bold text-sm bg-emerald-50 text-emerald-600 flex justify-center items-center gap-2 border border-emerald-100">
                                    <Check size={16} /> Активен
                                </div>
                            ) : (
                                <button
                                    onClick={() => payRubles(analystPlan)}
                                    disabled={payLoading}
                                    className="w-full py-3 rounded-xl font-bold text-sm bg-indigo-600 text-white shadow-lg shadow-indigo-200 active:scale-95 transition-transform flex justify-center items-center gap-2 hover:bg-indigo-700"
                                >
                                    {payLoading ? <Loader2 size={16} className="animate-spin" /> : <><CreditCard size={16} /> Купить</>}
                                </button>
                            )}
                        </div>
                    )}
                    {strategistPlan && (
                        <div>
                            {strategistPlan.current ? (
                                <div className="w-full py-3 rounded-xl font-bold text-sm bg-emerald-50 text-emerald-600 flex justify-center items-center gap-2 border border-emerald-100">
                                    <Check size={16} /> Активен
                                </div>
                            ) : (
                                <button
                                    onClick={() => payRubles(strategistPlan)}
                                    disabled={payLoading}
                                    className="w-full py-3 rounded-xl font-bold text-sm bg-slate-900 text-white shadow-lg shadow-slate-200 active:scale-95 transition-transform flex justify-center items-center gap-2 hover:bg-slate-800"
                                >
                                    {payLoading ? <Loader2 size={16} className="animate-spin" /> : <><CreditCard size={16} /> Купить</>}
                                </button>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Аддоны */}
            <div className="bg-white rounded-3xl shadow-sm border border-slate-100 p-6">
                <h2 className="text-xl font-black text-slate-800 mb-4 flex items-center gap-2">
                    <ShoppingBag size={20} className="text-violet-600" />
                    Дополнительные опции
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {addons.map((addon) => (
                        <div key={addon.id} className="p-4 rounded-2xl border-2 border-slate-100 hover:border-indigo-200 transition-all">
                            <h3 className="font-bold text-sm text-slate-800 mb-1">{addon.name}</h3>
                            <p className="text-xs text-slate-600 mb-3">{addon.description}</p>
                            <div className="flex items-center justify-between">
                                <div className="text-xl font-black text-slate-900">{addon.price} ₽</div>
                                <button className="px-4 py-2 bg-indigo-600 text-white text-xs font-bold rounded-lg hover:bg-indigo-700 active:scale-95 transition-transform">
                                    Купить
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default TariffsPage;

