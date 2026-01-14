import React, { useState, useEffect } from 'react';
import { 
    User, Key, X, Loader2, Shield, ArrowUpRight, CreditCard, 
    AlertTriangle, Check, Lock, BarChart3, Package, Megaphone, 
    MessageCircle, Tag, PieChart, Wallet
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const ProfilePage = ({ onNavigate }) => {
    // --- STATE ---
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);
    
    // Токен и Доступы
    const [wbToken, setWbToken] = useState('');
    const [tokenLoading, setTokenLoading] = useState(false);
    const [scopes, setScopes] = useState(null);
    const [scopesLoading, setScopesLoading] = useState(false);
    
    // Оплата и Ошибки
    const [payLoading, setPayLoading] = useState(false);
    const [error, setError] = useState(null);

    // --- INITIAL LOAD ---
    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            // 1. Тарифы
            const tRes = await fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() });
            const tData = await tRes.json();
            if (Array.isArray(tData)) setTariffs(tData);

            // 2. Профиль (Твоя надежная логика обработки ошибок)
            const uRes = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
            if (!uRes.ok) {
                const text = await uRes.text();
                try {
                    const json = JSON.parse(text);
                    throw new Error(json.detail || `Статус ${uRes.status}`);
                } catch {
                    throw new Error(`Ошибка сервера: ${uRes.status}`);
                }
            }
            const uData = await uRes.json();
            setUser(uData);

            // 3. Если есть токен — подгружаем его превью и права
            if (uData && uData.has_wb_token) {
                setWbToken(uData.wb_token_preview || '');
                fetchScopes();
            }
        } catch (e) {
            console.error("Profile load failed:", e);
            setError(e.message);
        }
    };

    const fetchScopes = () => {
        setScopesLoading(true);
        fetch(`${API_URL}/api/user/token/scopes`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setScopes)
            .catch(console.error)
            .finally(() => setScopesLoading(false));
    };

    // --- PAYMENT LOGIC (Твоя реализация) ---
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

    // --- TOKEN LOGIC ---
    const saveToken = async () => {
        // Блокируем сохранение маскированного токена
        if (!wbToken || wbToken.includes("••••") || wbToken.includes("****")) return;
        
        setTokenLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/user/token`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ token: wbToken })
            });
            
            const d = await res.json();
            
            if (res.ok) {
                // Локальное обновление без перезагрузки
                setUser(prev => ({ ...prev, has_wb_token: true }));
                
                // Если бэкенд сразу вернул scopes (как я предлагал в users.py), используем их
                if (d.scopes) setScopes(d.scopes);
                else fetchScopes();
                
                alert("Токен успешно сохранен и проверен!");
            } else {
                throw new Error(d.detail || "Ошибка сохранения");
            }
        } catch (e) {
            alert(e.message);
        } finally {
            setTokenLoading(false);
        }
    };

    const deleteToken = async () => {
        if (!confirm("Удалить токен? Сбор данных остановится.")) return;
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

    // --- UI HELPERS ---

    // Актуальные категории API WB
    const SCOPE_CONFIG = [
        { key: 'content', label: 'Контент', icon: Package, color: 'blue' },
        { key: 'prices', label: 'Цены', icon: Tag, color: 'emerald' },
        { key: 'statistics', label: 'Статистика', icon: BarChart3, color: 'indigo' },
        { key: 'analytics', label: 'Аналитика', icon: PieChart, color: 'orange' },
        { key: 'promotion', label: 'Реклама', icon: Megaphone, color: 'violet' },
        { key: 'questions', label: 'Вопросы', icon: MessageCircle, color: 'rose' },
    ];

    const ScopeCard = ({ config, active }) => {
        const Icon = config.icon;
        return (
            <div className={`flex flex-col items-center justify-center p-2.5 rounded-2xl border transition-all duration-300 ${
                active 
                ? `bg-${config.color}-50 border-${config.color}-200` 
                : 'bg-slate-50 border-slate-100 opacity-50 grayscale'
            }`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center mb-1.5 ${
                    active ? `bg-${config.color}-100 text-${config.color}-600` : 'bg-slate-200 text-slate-400'
                }`}>
                    {active ? <Icon size={16} /> : <Lock size={14} />}
                </div>
                <span className={`text-[9px] font-bold text-center leading-tight ${active ? 'text-slate-700' : 'text-slate-400'}`}>
                    {config.label}
                </span>
            </div>
        );
    };

    const isSaveDisabled = tokenLoading || (user?.has_wb_token && (wbToken.includes('****') || wbToken.includes('••••'))) || !wbToken;

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            
            {/* 1. Блок Ошибок */}
            {error && (
                <div className="bg-red-50 p-4 rounded-2xl border border-red-100 flex items-start gap-3">
                    <AlertTriangle className="text-red-500 shrink-0" size={20} />
                    <div>
                        <h3 className="font-bold text-red-800 text-sm">Ошибка загрузки</h3>
                        <p className="text-xs text-red-600 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* 2. Шапка Профиля */}
            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 relative">
                    <User size={32} />
                    <div className="absolute bottom-0 right-0 w-5 h-5 bg-emerald-500 border-4 border-white rounded-full"></div>
                </div>
                <div>
                    <h2 className="text-xl font-black text-slate-800">{user?.name || 'Загрузка...'}</h2>
                    <p className="text-sm text-slate-400 mb-2">@{user?.username || '...'}</p>
                    <div className="flex gap-2">
                         <span className="bg-slate-900 text-white px-2 py-0.5 rounded-lg text-[10px] font-bold uppercase tracking-wider">
                            {user?.plan || 'Free'} Plan
                        </span>
                        {user?.days_left > 0 && (
                            <span className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-lg text-[10px] font-bold">
                                {user.days_left} дн.
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* 3. API Настройки */}
            <div className="bg-white p-5 rounded-[28px] shadow-sm border border-slate-100">
                <div className="flex items-center justify-between mb-4 px-1">
                    <div className="flex items-center gap-2">
                        <div className="bg-indigo-100 p-1.5 rounded-lg text-indigo-600"><Key size={18} /></div>
                        <h2 className="font-bold text-lg">API Wildberries</h2>
                    </div>
                    {user?.has_wb_token && (
                        <div className="flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-full border border-emerald-100">
                            <Check size={10} strokeWidth={4} /> ПОДКЛЮЧЕНО
                        </div>
                    )}
                </div>

                <div className="relative mb-5">
                    <input
                        type="text"
                        value={wbToken}
                        onChange={(e) => setWbToken(e.target.value)}
                        onFocus={(e) => { if (user?.has_wb_token) e.target.select() }}
                        placeholder="Вставьте токен..."
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3.5 pr-10 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 transition-all placeholder:text-slate-400"
                    />
                    {user?.has_wb_token && wbToken && (
                        <button onClick={deleteToken} className="absolute right-3 top-3.5 text-slate-400 hover:text-red-500 transition-colors">
                            <X size={18} />
                        </button>
                    )}
                </div>

                {/* Сетка Доступов (Grid) */}
                {(user?.has_wb_token || scopes) && (
                    <div className="mb-5">
                         <div className="flex justify-between items-center mb-2 px-1">
                            <span className="text-[10px] uppercase font-bold text-slate-400">Статус разрешений</span>
                            {scopesLoading && <Loader2 size={12} className="animate-spin text-indigo-600"/>}
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                            {SCOPE_CONFIG.map(cfg => (
                                <ScopeCard 
                                    key={cfg.key} 
                                    config={cfg} 
                                    active={scopes ? scopes[cfg.key] : false} 
                                />
                            ))}
                        </div>
                    </div>
                )}

                <button
                    onClick={saveToken}
                    disabled={isSaveDisabled}
                    className={`w-full py-3.5 rounded-xl font-bold text-sm transition-all flex justify-center items-center gap-2
                        ${isSaveDisabled
                            ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                            : 'bg-indigo-600 text-white shadow-lg shadow-indigo-200 active:scale-95 hover:bg-indigo-700'
                        }`}
                >
                    {tokenLoading ? <Loader2 className="animate-spin" size={18} /> : (user?.has_wb_token ? 'Обновить токен' : 'Сохранить токен')}
                </button>
            </div>

            {/* 4. Тарифы */}
            <h2 className="font-bold text-lg px-2 mt-2">Ваш тариф</h2>
            <div className="space-y-4">
                {tariffs.map(plan => (
                    <div key={plan.id} className={`p-5 rounded-[24px] border-2 transition-all relative overflow-hidden ${plan.current ? 'border-emerald-500 bg-white shadow-emerald-100 shadow-lg' : 'border-slate-100 bg-white'}`}>
                        {plan.is_best && !plan.current && (
                            <div className="absolute top-0 right-0 bg-indigo-600 text-white text-[10px] font-bold px-3 py-1 rounded-bl-xl">
                                BEST CHOICE
                            </div>
                        )}
                        
                        <div className="flex justify-between items-start mb-2">
                            <div>
                                <h4 className="font-bold text-lg flex items-center gap-2">
                                    {plan.name}
                                    {plan.current && <span className="bg-emerald-500 text-white text-[10px] px-2 py-0.5 rounded-full">АКТИВЕН</span>}
                                </h4>
                                <div className="text-slate-900 font-black text-2xl mt-1">{plan.price}</div>
                            </div>
                            {plan.stars > 0 && (
                                <div className="bg-amber-100 text-amber-700 px-2 py-1 rounded-lg text-xs font-bold flex items-center gap-1">
                                    <Shield size={12} fill="currentColor" /> {plan.stars}
                                </div>
                            )}
                        </div>

                        <ul className="space-y-2 mb-4">
                            {plan.features.slice(0, 4).map((f, i) => (
                                <li key={i} className="text-xs font-medium text-slate-600 flex items-center gap-2">
                                    <div className={`w-1.5 h-1.5 rounded-full ${plan.current ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                                    {f}
                                </li>
                            ))}
                        </ul>

                        {!plan.current && plan.price !== "0 ₽" && (
                            <div className="grid grid-cols-2 gap-2 mt-4">
                                <button onClick={() => payStars(plan)} className="flex items-center justify-center gap-1.5 py-2.5 bg-amber-400 text-white rounded-xl font-bold text-xs hover:bg-amber-500 transition-colors shadow-sm active:scale-95">
                                    <Shield size={14} fill="currentColor" />
                                    <span>Stars</span>
                                </button>
                                <button onClick={() => payRubles(plan)} disabled={payLoading} className="flex items-center justify-center gap-1.5 py-2.5 bg-slate-900 text-white rounded-xl font-bold text-xs hover:bg-slate-800 transition-colors shadow-sm active:scale-95">
                                    {payLoading ? <Loader2 className="animate-spin" size={14} /> : <CreditCard size={14} />}
                                    <span>Карта РФ</span>
                                </button>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* 5. Админка и Футер */}
            {user?.is_admin && (
                <button onClick={() => onNavigate('admin')} className="w-full bg-gradient-to-r from-slate-800 to-slate-900 text-white p-4 rounded-2xl shadow-lg flex items-center justify-between active:scale-95 transition-transform mt-2">
                    <div className="flex items-center gap-3">
                        <Shield size={20} className="text-emerald-400" />
                        <span className="font-bold text-sm">Панель администратора</span>
                    </div>
                    <ArrowUpRight size={18} />
                </button>
            )}

            <div className="pt-6 pb-6 text-center border-t border-slate-100 mt-4">
                <div className="flex justify-center gap-4 text-[10px] text-slate-400 font-medium uppercase tracking-wide mb-2">
                    <a href="#" className="hover:text-slate-600">Оферта</a>
                    <span>•</span>
                    <a href="#" className="hover:text-slate-600">Конфиденциальность</a>
                    <span>•</span>
                    <a href="#" className="hover:text-slate-600">Поддержка</a>
                </div>
                <p className="text-[10px] text-slate-300">
                    ID: {user?.id} • Ver: 2.1.0 (Beta)
                </p>
            </div>
        </div>
    );
};

export default ProfilePage;