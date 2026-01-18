import React, { useState, useEffect } from 'react';
import { ArrowLeft, Check, X, CreditCard, Loader2, Sparkles, ShoppingBag, Star } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_URL, getTgHeaders } from '../config';

const TariffsPage = ({ onBack }) => {
    const navigate = useNavigate();
    const [tariffs, setTariffs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [payLoading, setPayLoading] = useState(false);
    const [paymentMethod, setPaymentMethod] = useState('robokassa'); // 'stars' or 'robokassa'

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

    // Конвертация цены в Telegram Stars (примерно 1₽ = 0.1 звезды, но нужно уточнить курс)
    const convertToStars = (priceStr) => {
        const price = parseInt(priceStr.replace(/[^0-9]/g, '')) || 0;
        // Примерный курс: 100 рублей = 10 звезд (1 звезда = 10 рублей)
        return Math.round(price / 10);
    };

    const payWithStars = async (plan) => {
        if (!plan.price || plan.price === "0 ₽") return;
        setPayLoading(true);
        try {
            const starsAmount = convertToStars(plan.price);
            const res = await fetch(`${API_URL}/api/payment/stars_link`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ 
                    plan_id: plan.id,
                    amount: starsAmount
                })
            });
            const data = await res.json();
            if (res.ok && data.invoice_link) {
                if (window.Telegram?.WebApp?.openInvoice) {
                    // Используем встроенный метод Telegram для оплаты
                    window.Telegram.WebApp.openInvoice(data.invoice_link);
                } else if (window.Telegram?.WebApp?.openLink) {
                    window.Telegram.WebApp.openLink(data.invoice_link);
                } else {
                    window.open(data.invoice_link, '_blank');
                }
            } else {
                throw new Error(data.detail || "Ошибка создания ссылки оплаты");
            }
        } catch (e) {
            alert(e.message || "Ошибка при создании платежа через Telegram Stars");
        } finally {
            setPayLoading(false);
        }
    };

    const payWithRobokassa = async (plan) => {
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
                if (window.Telegram?.WebApp?.openLink) {
                    window.Telegram.WebApp.openLink(data.payment_url);
                } else {
                    window.open(data.payment_url, '_blank');
                }
            } else {
                throw new Error(data.detail || "Ошибка инициализации платежа");
            }
        } catch (e) {
            alert(e.message || "Ошибка при создании платежа через Робокассу");
        } finally {
            setPayLoading(false);
        }
    };

    const handlePay = (plan) => {
        if (paymentMethod === 'stars') {
            payWithStars(plan);
        } else {
            payWithRobokassa(plan);
        }
    };

    // Определение функций для сравнения (Согласно config/plans.py)
    const features = [
        { key: 'history_days', label: 'История продаж', start: '7 дней', analyst: '60 дней', strategist: '365 дней' },
        { key: 'ai_requests', label: 'AI-запросы в месяц', start: '5', analyst: '100', strategist: '1000' },
        { key: 'review_analysis_limit', label: 'Лимит отзывов (1 анализ)', start: '30 шт', analyst: '100 шт', strategist: '200 шт' },
        { key: 'cluster_requests', label: 'Запросы кластеров', start: '0', analyst: '50', strategist: '200' },
        { key: 'slots', label: 'Слоты товаров', start: '✓', analyst: '✓', strategist: '✓' },
        { key: 'notifications', label: 'Уведомления', start: 'Раз в сутки', analyst: 'Раз в 3 часа', strategist: 'Раз в час' },
        { key: 'pnl', label: 'P&L (Прибыль/Убыток)', start: 'Демо', analyst: 'Полный', strategist: 'Полный + Экспорт' },
        { key: 'forensics', label: 'Форензика возвратов', start: '✗', analyst: '✓', strategist: '✓' },
        { key: 'cashgap', label: 'Cash Gap анализ', start: '✗', analyst: '✗', strategist: '✓' },
        { key: 'seo_semantics', label: 'SEO Семантика', start: '✗', analyst: '✓', strategist: '✓' },
        { key: 'priority_poll', label: 'Приоритетный опрос AI', start: '✗', analyst: '✗', strategist: '✓' }
    ];

    const addons = [
        { id: 'extra_ai_100', name: 'Дополнительные AI-запросы', description: '+100 AI-запросов', price: 490 }
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

            {/* Выбор метода оплаты */}
            <div className="bg-white rounded-3xl shadow-sm border border-slate-100 p-4 mb-4">
                <div className="flex items-center gap-2 mb-3">
                    <CreditCard size={18} className="text-slate-600" />
                    <span className="text-sm font-bold text-slate-700">Метод оплаты:</span>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => setPaymentMethod('stars')}
                        className={`flex-1 py-2.5 px-4 rounded-xl font-bold text-sm transition-all ${
                            paymentMethod === 'stars'
                                ? 'bg-blue-600 text-white shadow-md'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                    >
                        <Star size={16} className="inline mr-2" />
                        Telegram Stars
                    </button>
                    <button
                        onClick={() => setPaymentMethod('robokassa')}
                        className={`flex-1 py-2.5 px-4 rounded-xl font-bold text-sm transition-all ${
                            paymentMethod === 'robokassa'
                                ? 'bg-indigo-600 text-white shadow-md'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                    >
                        <CreditCard size={16} className="inline mr-2" />
                        Робокасса
                    </button>
                </div>
            </div>

            {/* Сравнительная таблица */}
            <div className="bg-white rounded-3xl shadow-sm border border-slate-100 overflow-hidden mb-6">
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-slate-50 border-b-2 border-slate-200">
                            <tr>
                                <th className="text-left p-4 font-bold text-sm text-slate-700 uppercase tracking-wide">Функции</th>
                                <th className="text-center p-4 font-black text-lg text-slate-900 min-w-[150px]">
                                    {startPlan?.name || 'Start'}
                                    {startPlan?.current && <span className="ml-2 text-xs text-emerald-600 font-bold block">(Активен)</span>}
                                </th>
                                <th className="text-center p-4 font-black text-lg text-indigo-600 min-w-[150px] relative">
                                    {analystPlan?.name || 'Analyst'}
                                    {analystPlan?.current && <span className="ml-2 text-xs text-emerald-600 font-bold block">(Активен)</span>}
                                    {!analystPlan?.current && (
                                        <div className="absolute -top-2 left-1/2 -translate-x-1/2 bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full shadow-lg">
                                            <Sparkles size={8} className="inline mr-1" /> PRO
                                        </div>
                                    )}
                                </th>
                                <th className="text-center p-4 font-black text-lg text-slate-900 min-w-[150px]">
                                    {strategistPlan?.name || 'Strategist'}
                                    {strategistPlan?.current && <span className="ml-2 text-xs text-emerald-600 font-bold block">(Активен)</span>}
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
                                    <div className="text-xl font-black text-slate-900">{startPlan?.price || '0 ₽'}</div>
                                    {startPlan?.price !== "0 ₽" && <div className="text-xs text-slate-500 mt-1">/мес</div>}
                                </td>
                                <td className="p-4 text-center">
                                    <div className="text-xl font-black text-indigo-600">{analystPlan?.price || '1490 ₽'}</div>
                                    <div className="text-xs text-slate-500 mt-1">/мес</div>
                                </td>
                                <td className="p-4 text-center">
                                    <div className="text-xl font-black text-slate-900">{strategistPlan?.price || '4990 ₽'}</div>
                                    <div className="text-xs text-slate-500 mt-1">/мес</div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                {/* Кнопки покупки */}
                <div className="grid grid-cols-3 gap-2 md:gap-4 p-4 bg-slate-50 border-t border-slate-200">
                    {startPlan && (
                        <div>
                            {startPlan.current ? (
                                <div className="w-full py-3 rounded-xl font-bold text-xs bg-emerald-50 text-emerald-600 flex justify-center items-center gap-2 border border-emerald-100">
                                    <Check size={16} /> <span className="hidden md:inline">Выбран</span>
                                </div>
                            ) : (
                                <button disabled className="w-full py-3 rounded-xl font-bold text-xs border-2 border-slate-200 text-slate-400 bg-white cursor-not-allowed">
                                    Free
                                </button>
                            )}
                        </div>
                    )}
                    {analystPlan && (
                        <div>
                            {analystPlan.current ? (
                                <div className="w-full py-3 rounded-xl font-bold text-xs bg-emerald-50 text-emerald-600 flex justify-center items-center gap-2 border border-emerald-100">
                                    <Check size={16} /> <span className="hidden md:inline">Выбран</span>
                                </div>
                            ) : (
                                <button
                                    onClick={() => handlePay(analystPlan)}
                                    disabled={payLoading}
                                    className="w-full py-3 rounded-xl font-bold text-xs bg-indigo-600 text-white shadow-lg shadow-indigo-200 active:scale-95 transition-transform flex justify-center items-center gap-2 hover:bg-indigo-700"
                                >
                                    {payLoading ? <Loader2 size={16} className="animate-spin" /> : <>{paymentMethod === 'stars' ? <Star size={16} /> : <CreditCard size={16} />} Купить</>}
                                </button>
                            )}
                        </div>
                    )}
                    {strategistPlan && (
                        <div>
                            {strategistPlan.current ? (
                                <div className="w-full py-3 rounded-xl font-bold text-xs bg-emerald-50 text-emerald-600 flex justify-center items-center gap-2 border border-emerald-100">
                                    <Check size={16} /> <span className="hidden md:inline">Выбран</span>
                                </div>
                            ) : (
                                <button
                                    onClick={() => handlePay(strategistPlan)}
                                    disabled={payLoading}
                                    className="w-full py-3 rounded-xl font-bold text-xs bg-slate-900 text-white shadow-lg shadow-slate-200 active:scale-95 transition-transform flex justify-center items-center gap-2 hover:bg-slate-800"
                                >
                                    {payLoading ? <Loader2 size={16} className="animate-spin" /> : <>{paymentMethod === 'stars' ? <Star size={16} /> : <CreditCard size={16} />} Купить</>}
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
                        <div key={addon.id} className="p-4 rounded-2xl border-2 border-slate-100 hover:border-indigo-200 transition-all flex flex-col justify-between">
                            <div>
                                <h3 className="font-bold text-sm text-slate-800 mb-1">{addon.name}</h3>
                                <p className="text-xs text-slate-600 mb-3">{addon.description}</p>
                            </div>
                            <div className="flex items-center justify-between mt-2">
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