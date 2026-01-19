import React, { useState, useEffect, useRef } from 'react';
import { ArrowLeft, CreditCard, Loader2, Sparkles, ShoppingBag, Star } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_URL, getTgHeaders } from '../config';
import TariffCard from '../components/TariffCard';

const TariffsPage = ({ onBack }) => {
    const navigate = useNavigate();
    const [tariffs, setTariffs] = useState([]);
    const [payLoading, setPayLoading] = useState(false);
    const [paymentMethod, setPaymentMethod] = useState('robokassa'); // 'stars' | 'robokassa'
    const [processingId, setProcessingId] = useState(null); // ID тарифа/аддона, который сейчас оплачивается
    
    // Ссылка на таймер поллинга
    const pollingRef = useRef(null);

    // --- 1. ИНИЦИАЛИЗАЦИЯ И СЛУШАТЕЛИ ---
    useEffect(() => {
        fetchTariffs();

        // Магия для WebApp: когда юзер возвращается из браузера (после оплаты), обновляем данные
        const handleFocus = () => {
            console.log("[App] Focused - refreshing data...");
            fetchTariffs();
        };

        window.addEventListener('focus', handleFocus);
        document.addEventListener('visibilitychange', handleFocus);

        return () => {
            window.removeEventListener('focus', handleFocus);
            document.removeEventListener('visibilitychange', handleFocus);
            stopPolling();
        };
    }, []);

    // Остановка поллинга
    const stopPolling = () => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }
    };

    // --- 2. ЗАГРУЗКА ДАННЫХ ---
    const fetchTariffs = async () => {
        try {
            const res = await fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() });
            const data = await res.json();
            
            if (Array.isArray(data)) {
                const enrichedData = data.map(plan => ({
                    ...plan,
                    stars: convertToStars(plan.price),
                    // Если с бека нет фич, ставим заглушки для красоты
                    features: plan.features || getDefaultFeatures(plan.id) 
                }));
                setTariffs(enrichedData);
                return enrichedData;
            }
        } catch (e) {
            console.error("Ошибка загрузки тарифов:", e);
        }
        return [];
    };

    // --- 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
    const convertToStars = (priceStr) => {
        const price = parseInt(priceStr.replace(/[^0-9]/g, '')) || 0;
        return Math.max(1, Math.round(price));
    };

    const getDefaultFeatures = (id) => {
        if (id === 'start') return ['История 7 дней', '5 AI-запросов', 'Базовая аналитика'];
        if (id === 'analyst') return ['История 60 дней', '100 AI-запросов', 'Форензика', 'SEO'];
        if (id === 'strategist') return ['История 365 дней', '1000 AI-запросов', 'Cash Gap', 'Приоритет'];
        return [];
    };

    // --- 4. ЛОГИКА ОПЛАТЫ (ОБЩАЯ) ---
    
    // Запуск поллинга (проверки статуса)
    const startPolling = (targetId, isAddon = false) => {
        stopPolling();
        setPayLoading(true);
        setProcessingId(targetId);

        // Проверяем каждые 3 секунды
        pollingRef.current = setInterval(async () => {
            const updatedList = await fetchTariffs();
            
            if (isAddon) {
                // Для аддонов сложнее проверить "активность" через список тарифов.
                // Обычно просто ждем возврата юзера или проверяем баланс юзера.
                // Тут оставим просто обновление списка.
            } else {
                const targetPlan = updatedList?.find(t => t.id === targetId);
                // Если тариф стал активным
                if (targetPlan && targetPlan.current) {
                    stopPolling();
                    setPayLoading(false);
                    setProcessingId(null);
                    
                    if (window.Telegram?.WebApp?.showAlert) {
                        window.Telegram.WebApp.showAlert(`Тариф ${targetPlan.name} активирован!`);
                    } else {
                        alert("Успешно! Тариф активирован.");
                    }
                }
            }
        }, 3000);

        // Тайм-аут 5 минут
        setTimeout(() => {
            stopPolling();
            setPayLoading(false);
            setProcessingId(null);
        }, 300000);
    };

    // --- ОПЛАТА ПОДПИСКИ (ROBOKASSA) ---
    const paySubscriptionRobokassa = async (plan) => {
        if (!plan.price || plan.price === "0 ₽") return;
        setPayLoading(true);
        setProcessingId(plan.id);

        try {
            const res = await fetch(`${API_URL}/api/payment/robokassa/subscription`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ plan_id: plan.id })
            });
            const data = await res.json();

            if (res.ok && data.payment_url) {
                // Открываем ссылку во внешнем браузере/popup
                if (window.Telegram?.WebApp?.openLink) {
                    window.Telegram.WebApp.openLink(data.payment_url, { try_instant_view: false });
                } else {
                    window.open(data.payment_url, '_blank');
                }
                // Запускаем ожидание
                startPolling(plan.id, false);
            } else {
                throw new Error(data.detail || "Ошибка получения ссылки");
            }
        } catch (e) {
            alert(e.message);
            setPayLoading(false);
            setProcessingId(null);
        }
    };

    // --- ОПЛАТА ПОДПИСКИ (STARS) ---
    const paySubscriptionStars = async (plan) => {
        setPayLoading(true);
        setProcessingId(plan.id);
        try {
            const starsAmount = convertToStars(plan.price);
            const res = await fetch(`${API_URL}/api/payment/stars_link`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ plan_id: plan.id, amount: starsAmount })
            });
            const data = await res.json();

            if (res.ok && data.invoice_link) {
                if (window.Telegram?.WebApp?.openInvoice) {
                    window.Telegram.WebApp.openInvoice(data.invoice_link, (status) => {
                        if (status === 'paid') {
                            window.Telegram.WebApp.showAlert("Оплата успешна!");
                            fetchTariffs();
                        }
                        setPayLoading(false);
                        setProcessingId(null);
                    });
                } else {
                    window.Telegram.WebApp.openLink(data.invoice_link);
                    setPayLoading(false); // В вебе сбрасываем сразу, т.к. не можем отследить инвойс
                }
            } else {
                throw new Error(data.detail || "Ошибка");
            }
        } catch (e) {
            console.error(e);
            alert("Ошибка оплаты Stars");
            setPayLoading(false);
            setProcessingId(null);
        }
    };

    // --- ОПЛАТА АДДОНОВ (Только Robokassa, как в бэкенде) ---
    const payAddonRobokassa = async (addon) => {
        if (paymentMethod === 'stars') {
            alert("Оплата дополнений через Stars пока недоступна. Пожалуйста, выберите Робокассу.");
            return;
        }

        setPayLoading(true);
        setProcessingId(addon.id);

        try {
            const res = await fetch(`${API_URL}/api/payment/robokassa/addon`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ addon_id: addon.id })
            });
            const data = await res.json();

            if (res.ok && data.payment_url) {
                if (window.Telegram?.WebApp?.openLink) {
                    window.Telegram.WebApp.openLink(data.payment_url, { try_instant_view: false });
                } else {
                    window.open(data.payment_url, '_blank');
                }
                // Для аддонов просто ждем возврата (focus) или таймер
                // startPolling тут менее эффективен, так как список тарифов не меняется
                // Но можно оставить лоадер на 10 сек для визуальной реакции
                setTimeout(() => {
                    setPayLoading(false);
                    setProcessingId(null);
                }, 10000); 
            } else {
                throw new Error(data.detail || "Ошибка");
            }
        } catch (e) {
            alert(e.message);
            setPayLoading(false);
            setProcessingId(null);
        }
    };

    // --- ДАННЫЕ (Статика для UI) ---
    const addons = [
        { id: 'extra_ai_100', name: 'Дополнительные AI-запросы', description: '+100 AI-запросов к текущему лимиту', price: 490 }
    ];

    const startPlan = tariffs.find(t => t.id === 'start');
    const analystPlan = tariffs.find(t => t.id === 'analyst');
    const strategistPlan = tariffs.find(t => t.id === 'strategist');
    const sortedPlans = [startPlan, analystPlan, strategistPlan].filter(Boolean);

    // Данные таблицы
    const featuresList = [
        { key: 'history_days', label: 'История продаж', start: '7 дней', analyst: '60 дней', strategist: '365 дней' },
        { key: 'ai_requests', label: 'AI-запросы', start: '5', analyst: '100', strategist: '1000' },
        { key: 'slots', label: 'Слоты товаров', start: '✓', analyst: '✓', strategist: '✓' },
        { key: 'forensics', label: 'Форензика возвратов', start: '✗', analyst: '✓', strategist: '✓' },
        { key: 'seo_semantics', label: 'SEO Семантика', start: '✗', analyst: '✓', strategist: '✓' },
        { key: 'cashgap', label: 'Cash Gap анализ', start: '✗', analyst: '✗', strategist: '✓' }
    ];

    return (
        <div className="p-4 max-w-6xl mx-auto pb-32">
            {/* Хедер */}
            <div className="flex items-center gap-3 mb-6">
                <button onClick={onBack || (() => navigate('/profile'))} className="text-slate-400 hover:text-slate-600">
                    <ArrowLeft size={24} />
                </button>
                <h1 className="text-2xl font-black text-slate-800">Тарифы и Лимиты</h1>
            </div>

            {/* Выбор метода оплаты */}
            <div className="bg-white rounded-3xl shadow-sm border border-slate-100 p-4 mb-6">
                <div className="flex items-center gap-2 mb-3">
                    <CreditCard size={18} className="text-slate-600" />
                    <span className="text-sm font-bold text-slate-700">Способ оплаты:</span>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => setPaymentMethod('stars')}
                        className={`flex-1 py-3 px-4 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2 ${
                            paymentMethod === 'stars'
                                ? 'bg-blue-600 text-white shadow-md transform scale-[1.02]'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                    >
                        <Star size={16} fill={paymentMethod === 'stars' ? "currentColor" : "none"} />
                        Telegram Stars
                    </button>
                    <button
                        onClick={() => setPaymentMethod('robokassa')}
                        className={`flex-1 py-3 px-4 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2 ${
                            paymentMethod === 'robokassa'
                                ? 'bg-indigo-600 text-white shadow-md transform scale-[1.02]'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                    >
                        <CreditCard size={16} />
                        Робокасса (Карта)
                    </button>
                </div>
            </div>

            {/* СЕТКА ТАРИФОВ */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                {sortedPlans.map((plan) => (
                    <TariffCard 
                        key={plan.id}
                        plan={plan}
                        loading={payLoading} // Глобальное состояние загрузки
                        currentPaymentId={processingId} // Чтобы крутилась только нужная карточка
                        onPayStars={() => paySubscriptionStars(plan)}
                        onPayRubles={() => paySubscriptionRobokassa(plan)}
                    />
                ))}
            </div>

            {/* БЛОК АДДОНОВ (Докупка) */}
            <div className="bg-gradient-to-br from-indigo-50 to-violet-50 rounded-3xl border border-indigo-100 p-6 mb-8">
                <h2 className="text-xl font-black text-indigo-900 mb-4 flex items-center gap-2">
                    <ShoppingBag size={22} className="text-indigo-600" />
                    Докупить лимиты
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {addons.map((addon) => (
                        <div key={addon.id} className="bg-white p-5 rounded-2xl border border-indigo-100 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
                            <div>
                                <h3 className="font-bold text-base text-slate-800 mb-1">{addon.name}</h3>
                                <p className="text-sm text-slate-500 mb-4">{addon.description}</p>
                            </div>
                            <div className="flex items-center justify-between border-t border-slate-100 pt-3">
                                <div className="text-xl font-black text-slate-900">{addon.price} ₽</div>
                                <button 
                                    onClick={() => payAddonRobokassa(addon)}
                                    disabled={payLoading}
                                    className="px-5 py-2.5 bg-indigo-600 text-white text-xs font-bold rounded-xl hover:bg-indigo-700 active:scale-95 transition-all flex items-center gap-2 disabled:opacity-70"
                                >
                                    {payLoading && processingId === addon.id ? (
                                        <Loader2 size={14} className="animate-spin" />
                                    ) : (
                                        <CreditCard size={14} />
                                    )}
                                    Купить
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* СРАВНИТЕЛЬНАЯ ТАБЛИЦА */}
            <div className="bg-white rounded-3xl shadow-sm border border-slate-100 overflow-hidden mb-6">
                <h2 className="p-5 text-lg font-bold text-slate-700 border-b border-slate-100 bg-slate-50/50">
                    Сравнение возможностей
                </h2>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-slate-50 border-b-2 border-slate-200">
                            <tr>
                                <th className="text-left p-4 font-bold text-xs text-slate-500 uppercase tracking-wide">Функция</th>
                                <th className="text-center p-4 font-black text-sm text-slate-900">Start</th>
                                <th className="text-center p-4 font-black text-sm text-indigo-600">Analyst</th>
                                <th className="text-center p-4 font-black text-sm text-slate-900">Strategist</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {featuresList.map((feature) => (
                                <tr key={feature.key} className="hover:bg-slate-50/50">
                                    <td className="p-4 text-sm font-medium text-slate-700">{feature.label}</td>
                                    <td className="p-4 text-center text-sm font-semibold text-slate-600">{feature.start}</td>
                                    <td className="p-4 text-center text-sm font-bold text-indigo-600 bg-indigo-50/30">{feature.analyst}</td>
                                    <td className="p-4 text-center text-sm font-semibold text-slate-600">{feature.strategist}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default TariffsPage;