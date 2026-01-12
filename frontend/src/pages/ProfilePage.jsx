import React, { useState, useEffect } from 'react';
import { User, Key, X, Loader2, Shield, ArrowUpRight, CreditCard, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const ProfilePage = ({ onNavigate }) => {
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);
    const [wbToken, setWbToken] = useState('');
    const [tokenLoading, setTokenLoading] = useState(false);
    const [payLoading, setPayLoading] = useState(false);
    const [error, setError] = useState(null);
    const [scopes, setScopes] = useState(null);
    const [scopesLoading, setScopesLoading] = useState(false);

    useEffect(() => {
        // Загрузка тарифов
        fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(data => {
                if (Array.isArray(data)) setTariffs(data);
            })
            .catch(e => console.error("Tariffs error:", e));

        // Загрузка профиля
        fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
            .then(async r => {
                if (!r.ok) {
                    const text = await r.text();
                    try {
                        const json = JSON.parse(text);
                        throw new Error(json.detail || `Статус ${r.status}`);
                    } catch {
                        throw new Error(`Ошибка сервера: ${r.status}`);
                    }
                }
                return r.json();
            })
            .then(data => {
                setUser(data);
                if (data && data.has_wb_token) {
                    setWbToken(data.wb_token_preview || '');
                    fetchScopes();
                }
            })
            .catch(e => {
                console.error("Profile fetch failed:", e);
                setError(`${e.message}`);
            });
    }, []);

    const fetchScopes = () => {
        setScopesLoading(true);
        fetch(`${API_URL}/api/user/token/scopes`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setScopes)
            .catch(console.error)
            .finally(() => setScopesLoading(false));
    };

    const payStars = async (plan) => {
        if (!plan.stars) return;
        try {
            const res = await fetch(`${API_URL}/api/payment/stars_link`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ plan_id: plan.id, amount: plan.stars })
            });
            const d = await res.json();
            if (d.invoice_link && window.Telegram?.WebApp?.openInvoice) {
                window.Telegram.WebApp.openInvoice(d.invoice_link, (status) => {
                    if (status === 'paid') {
                        alert("Оплата прошла успешно!");
                        window.location.reload();
                    }
                });
            } else {
                alert("Ошибка создания ссылки или нет Telegram WebApp");
            }
        } catch (e) {
            alert(e.message);
        }
    };

    const payRubles = async (plan) => {
        if (!plan.price || plan.price === "0 ₽") return;
        setPayLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/payment/yookassa/create`, {
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
                throw new Error(data.detail || "Ошибка платежного провайдера");
            }
        } catch (e) {
            alert(`Ошибка: ${e.message}`);
        } finally {
            setPayLoading(false);
        }
    };

    const saveToken = async () => {
        // Блокируем сохранение маскированного токена
        if (!wbToken || wbToken.includes("*****")) return;
        
        setTokenLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/user/token`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ token: wbToken })
            });
            
            if (res.ok) {
                alert("Токен успешно сохранен!");
                const uRes = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
                if (uRes.ok) {
                    const uData = await uRes.json();
                    setUser(uData);
                    fetchScopes(); // Обновляем права
                }
            } else {
                const d = await res.json();
                throw new Error(d.detail || "Ошибка сохранения");
            }
        } catch (e) {
            alert(e.message);
        } finally {
            setTokenLoading(false);
        }
    };

    const deleteToken = async () => {
        if (!confirm("Удалить токен?")) return;
        setTokenLoading(true);
        try {
            await fetch(`${API_URL}/api/user/token`, { method: 'DELETE', headers: getTgHeaders() });
            setWbToken('');
            setScopes(null);
            setUser(prev => ({ ...prev, has_wb_token: false }));
        } catch (e) {
            console.error(e);
        } finally {
            setTokenLoading(false);
        }
    };

    const ScopeBadge = ({ label, active, loading }) => (
        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all ${active ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-slate-50 border-slate-200 text-slate-400 opacity-60'}`}>
            {loading ? <Loader2 size={12} className="animate-spin" /> : active ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
            {label}
        </div>
    );

    const RenderTariffCard = ({ plan }) => (
        <div className={`p-5 rounded-2xl border-2 transition-all ${plan.current ? 'border-emerald-500 bg-emerald-50/50' : 'border-slate-100 bg-white'}`}>
            <div className="flex justify-between items-start mb-3">
                <div>
                    <h3 className="font-bold text-lg flex items-center gap-2">
                        {plan.name}
                        {plan.current && <span className="bg-emerald-500 text-white text-[10px] px-2 py-0.5 rounded-full">CURRENT</span>}
                    </h3>
                    <div className="text-2xl font-black mt-1">{plan.price} <span className="text-sm font-normal text-slate-400">/ мес</span></div>
                </div>
                {plan.stars > 0 && (
                    <div className="text-right">
                        <div className="text-amber-500 font-bold text-sm flex items-center justify-end gap-1">
                            ★ {plan.stars}
                        </div>
                    </div>
                )}
            </div>

            <ul className="space-y-2 mb-4">
                {plan.features.map((f, i) => (
                    <li key={i} className="text-sm text-slate-600 flex items-center gap-2">
                        <div className={`w-1.5 h-1.5 rounded-full ${plan.current ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                        {f}
                    </li>
                ))}
            </ul>

            {!plan.current && plan.price !== "0 ₽" && (
                <div className="grid grid-cols-2 gap-2 mt-4">
                    <button onClick={() => payStars(plan)} className="flex items-center justify-center gap-2 py-2.5 bg-amber-400 text-white rounded-xl font-bold text-sm hover:bg-amber-500 transition-colors">
                        <span>Stars</span>
                    </button>
                    <button onClick={() => payRubles(plan)} disabled={payLoading} className="flex items-center justify-center gap-2 py-2.5 bg-slate-900 text-white rounded-xl font-bold text-sm hover:bg-slate-800 transition-colors">
                        {payLoading ? <Loader2 className="animate-spin" size={16} /> : <CreditCard size={16} />}
                        <span>РФ Карта</span>
                    </button>
                </div>
            )}
        </div>
    );

    // Логика состояния кнопки: 
    // Дизейблим если идет загрузка ИЛИ (если токен уже есть и поле содержит маску '*****')
    // Это предотвращает отправку маскированного токена, но разрешает отправку, если пользователь начал вводить новый
    const isSaveDisabled = tokenLoading || (user?.has_wb_token && wbToken.includes('*****')) || !wbToken;

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            {error && (
                <div className="bg-red-50 p-4 rounded-2xl border border-red-100 flex flex-col gap-2">
                    <div className="flex items-start gap-3">
                        <AlertTriangle className="text-red-500 shrink-0" size={20} />
                        <div>
                            <h3 className="font-bold text-red-800 text-sm">Ошибка загрузки</h3>
                            <p className="text-xs text-red-600 mt-1">{error}</p>
                        </div>
                    </div>
                </div>
            )}

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                    <User size={32} />
                </div>
                <div>
                    <h2 className="text-xl font-bold">{user?.name || 'Загрузка...'}</h2>
                    <p className="text-sm text-slate-400">@{user?.username || '...'}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                        <div className="inline-flex items-center gap-1 bg-black text-white px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                            {user?.plan || 'Free'} Plan
                        </div>
                        {user?.days_left > 0 && (
                            <div className="inline-flex items-center gap-1 bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded text-[10px] font-bold">
                                {user.days_left} дн.
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                <div className="flex items-center gap-2 mb-4">
                    <Key className="text-indigo-600" size={20} />
                    <h2 className="font-bold text-lg">API Ключ WB</h2>
                </div>

                <div className="relative">
                    <input
                        type="text"
                        value={wbToken}
                        onChange={(e) => setWbToken(e.target.value)}
                        onFocus={(e) => { if (user?.has_wb_token) e.target.select() }} // Удобство для выделения старого токена
                        placeholder="Введите токен..."
                        className="w-full bg-slate-50 border border-slate-100 rounded-xl p-3 pr-10 text-sm font-medium outline-none focus:ring-2 ring-indigo-100 transition-all"
                    />
                    {user?.has_wb_token && (
                        <button onClick={deleteToken} className="absolute right-2 top-2 p-1 text-slate-300 hover:text-red-500 transition-colors">
                            <X size={16} />
                        </button>
                    )}
                </div>

                {/* SCOPES DISPLAY */}
                {(user?.has_wb_token || scopes) && (
                    <div className="mt-4">
                        <div className="text-[10px] uppercase font-bold text-slate-400 mb-2">Доступные разделы API</div>
                        <div className="flex flex-wrap gap-2">
                            <ScopeBadge label="Статистика" active={scopes?.statistics} loading={scopesLoading} />
                            <ScopeBadge label="Контент/Цены" active={scopes?.standard} loading={scopesLoading} />
                            <ScopeBadge label="Реклама" active={scopes?.promotion} loading={scopesLoading} />
                            <ScopeBadge label="Вопросы" active={scopes?.questions} loading={scopesLoading} />
                        </div>
                    </div>
                )}

                {/* Кнопка сохранения теперь видна всегда, но блокируется если токен не изменен */}
                <button
                    onClick={saveToken}
                    disabled={isSaveDisabled}
                    className={`w-full mt-4 py-3 rounded-xl font-bold text-sm transition-all flex justify-center items-center gap-2
                        ${isSaveDisabled
                            ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                            : 'bg-indigo-600 text-white shadow-lg shadow-indigo-200 active:scale-95 hover:bg-indigo-700'
                        }`}
                >
                    {tokenLoading ? <Loader2 className="animate-spin" size={18} /> : (user?.has_wb_token ? 'Обновить токен' : 'Сохранить токен')}
                </button>
            </div>

            <h2 className="font-bold text-lg px-2 mt-4">Тарифы</h2>
            <div className="space-y-4">
                {tariffs.map(plan => (
                    <RenderTariffCard key={plan.id} plan={plan} />
                ))}
            </div>

            {user?.is_admin && (
                <button onClick={() => onNavigate('admin')} className="w-full bg-slate-900 text-white p-4 rounded-2xl shadow-lg flex items-center justify-between active:scale-95 transition-transform mt-4">
                    <div className="flex items-center gap-3">
                        <Shield size={20} className="text-emerald-400" />
                        <span className="font-bold text-sm">Админ-панель</span>
                    </div>
                    <ArrowUpRight size={18} />
                </button>
            )}

            <div className="mt-8 pt-8 border-t border-slate-100 text-center space-y-2">
                <div className="flex justify-center gap-4 text-xs text-slate-400">
                    <a href="#" className="hover:text-slate-600 transition-colors">Публичная оферта</a>
                    <span>•</span>
                    <a href="#" className="hover:text-slate-600 transition-colors">Политика конфиденциальности</a>
                </div>
                <p className="text-[10px] text-slate-300">
                    Сервис не является аффилированным лицом Wildberries.<br />
                    Обработка персональных данных в соответствии с 152-ФЗ.
                </p>
            </div>
        </div>
    );
};

export default ProfilePage;