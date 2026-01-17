import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
    User, Key, X, Loader2, Shield, ArrowUpRight, 
    AlertTriangle, Check, Lock, 
    Package, Store, PieChart, Megaphone, RotateCcw, FileText, 
    BarChart3, Wallet, Truck, MessageSquare, MessageCircle, 
    Tag, Users
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import TariffCard from '../components/TariffCard';

// Added refreshUser to props
const ProfilePage = ({ onNavigate, refreshUser }) => {
    const navigate = useNavigate();
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);
    const [wbToken, setWbToken] = useState('');
    const [tokenLoading, setTokenLoading] = useState(false);
    const [scopes, setScopes] = useState(null);
    const [scopesLoading, setScopesLoading] = useState(false);
    const [payLoading, setPayLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => { loadData(); }, []);

    const loadData = async () => {
        try {
            const tRes = await fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() });
            const tData = await tRes.json();
            if (Array.isArray(tData)) setTariffs(tData);

            const uRes = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
            if (!uRes.ok) throw new Error("Ошибка загрузки профиля");
            const uData = await uRes.json();
            setUser(uData);

            if (uData && uData.has_wb_token) {
                setWbToken(uData.wb_token_preview || '');
                fetchScopes();
            }
        } catch (e) {
            console.error(e);
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
                    if (status === 'paid') { alert("Оплата успешна!"); window.location.reload(); }
                });
            } else { alert("Ошибка WebApp (откройте в Telegram)"); }
        } catch (e) { alert(e.message); }
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
            } else { throw new Error(data.detail || "Ошибка инициализации платежа"); }
        } catch (e) { alert(e.message); } finally { setPayLoading(false); }
    };

    const saveToken = async () => {
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
                setUser(prev => ({ ...prev, has_wb_token: true }));
                if (d.scopes) setScopes(d.scopes); else fetchScopes();
                
                // --- FIX START: Notify App.jsx about the change ---
                if (refreshUser) refreshUser();
                // --- FIX END ---

                alert("Токен успешно сохранен!");
            } else { throw new Error(d.detail); }
        } catch (e) { alert(e.message); } finally { setTokenLoading(false); }
    };

    const deleteToken = async () => {
        if (!confirm("Вы уверены, что хотите удалить токен?")) return;
        setTokenLoading(true);
        try {
            await fetch(`${API_URL}/api/user/token`, { method: 'DELETE', headers: getTgHeaders() });
            setWbToken('');
            setScopes(null);
            setUser(prev => ({ ...prev, has_wb_token: false }));

            // --- FIX START: Notify App.jsx about the change ---
            if (refreshUser) refreshUser();
            // --- FIX END ---

        } catch (e) { console.error(e); } finally { setTokenLoading(false); }
    };

    const SCOPE_CONFIG = [
        { key: 'content', label: 'Контент', icon: Package, color: 'blue' },
        { key: 'marketplace', label: 'Маркетплейс', icon: Store, color: 'indigo' },
        { key: 'analytics', label: 'Аналитика', icon: PieChart, color: 'orange' },
        { key: 'promotion', label: 'Продвижение', icon: Megaphone, color: 'violet' },
        { key: 'returns', label: 'Возвраты', icon: RotateCcw, color: 'rose' },
        { key: 'documents', label: 'Документы', icon: FileText, color: 'slate' },
        { key: 'statistics', label: 'Статистика', icon: BarChart3, color: 'emerald' },
        { key: 'finance', label: 'Финансы', icon: Wallet, color: 'green' },
        { key: 'supplies', label: 'Поставки', icon: Truck, color: 'amber' },
        { key: 'chat', label: 'Чат с клиентом', icon: MessageSquare, color: 'cyan' },
        { key: 'questions', label: 'Вопросы/Отзывы', icon: MessageCircle, color: 'pink' },
        { key: 'prices', label: 'Цены и Скидки', icon: Tag, color: 'teal' },
        { key: 'users', label: 'Пользователи', icon: Users, color: 'purple' },
    ];

    const ScopeCard = ({ config, active }) => {
        const Icon = config.icon;
        const activeBg = `bg-${config.color}-50`;
        const activeBorder = `border-${config.color}-200`;
        const activeIconBg = `bg-${config.color}-100`;
        const activeText = `text-${config.color}-600`;
        return (
            <div className={`flex flex-col items-center justify-center p-2 rounded-xl border transition-all duration-300 min-h-[70px] ${
                active ? `${activeBg} ${activeBorder}` : 'bg-slate-50 border-slate-100 opacity-60 grayscale'
            }`}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center mb-1 ${
                    active ? `${activeIconBg} ${activeText}` : 'bg-slate-200 text-slate-400'
                }`}>
                    {active ? <Icon size={14} /> : <Lock size={12} />}
                </div>
                <span className={`text-[9px] font-bold text-center leading-none ${active ? 'text-slate-700' : 'text-slate-400'}`}>
                    {config.label}
                </span>
            </div>
        );
    };

    const isSaveDisabled = tokenLoading || (user?.has_wb_token && (wbToken.includes('****') || wbToken.includes('••••'))) || !wbToken;

    const getPlanDisplayName = (planId) => {
        switch(planId) {
            case 'analyst': return 'Аналитик';
            case 'strategist': return 'Стратег';
            case 'start': return 'Старт';
            default: return 'Старт';
        }
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            
            {error && (
                <div className="bg-red-50 p-4 rounded-2xl border border-red-100 flex items-start gap-3">
                    <AlertTriangle className="text-red-500 shrink-0" size={20} />
                    <div>
                        <h3 className="font-bold text-red-800 text-sm">Ошибка</h3>
                        <p className="text-xs text-red-600 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* HEADER */}
            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 relative">
                    <User size={32} />
                    <div className={`absolute bottom-0 right-0 w-5 h-5 border-4 border-white rounded-full ${user?.plan === 'analyst' || user?.plan === 'strategist' ? 'bg-indigo-500' : 'bg-emerald-500'}`}></div>
                </div>
                <div>
                    <h2 className="text-xl font-black text-slate-800">{user?.name || 'Загрузка...'}</h2>
                    <p className="text-sm text-slate-400 mb-2">@{user?.username || '...'}</p>
                    <div className="flex flex-wrap gap-2">
                         <span className="bg-slate-900 text-white px-2.5 py-0.5 rounded-lg text-[10px] font-bold uppercase tracking-wider">
                            {getPlanDisplayName(user?.plan)}
                        </span>
                        {user?.days_left > 0 && (
                            <span className="bg-emerald-100 text-emerald-700 px-2.5 py-0.5 rounded-lg text-[10px] font-bold">
                                {user.days_left} дн.
                            </span>
                        )}
                        {user?.ai_requests_limit > 0 && (
                            <span className="bg-indigo-100 text-indigo-700 px-2.5 py-0.5 rounded-lg text-[10px] font-bold">
                                AI: {user.ai_requests_used || 0}/{user.ai_requests_limit}
                                {user?.extra_ai_balance > 0 && ` +${user.extra_ai_balance}`}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* API SETTINGS */}
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
                        placeholder="Вставьте токен WB..."
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3.5 pr-10 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 transition-all placeholder:text-slate-400"
                    />
                    {user?.has_wb_token && wbToken && (
                        <button onClick={deleteToken} className="absolute right-3 top-3.5 text-slate-400 hover:text-red-500 transition-colors">
                            <X size={18} />
                        </button>
                    )}
                </div>

                {(user?.has_wb_token || scopes) && (
                    <div className="mb-5">
                         <div className="flex justify-between items-center mb-2 px-1">
                            <span className="text-[10px] uppercase font-bold text-slate-400">Доступные разделы</span>
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

            {/* TARIFFS */}
            <h2 className="font-bold text-lg px-2 mt-2">Тарифные планы</h2>
            <div className="space-y-4">
                {tariffs.map(plan => (
                    <TariffCard 
                        key={plan.id}
                        plan={plan}
                        onPayStars={payStars}
                        onPayRubles={payRubles}
                        loading={payLoading}
                    />
                ))}
            </div>

            {/* ADMIN */}
            {user?.is_admin && (
                <button onClick={() => onNavigate('admin')} className="w-full bg-gradient-to-r from-slate-800 to-slate-900 text-white p-4 rounded-2xl shadow-lg flex items-center justify-between active:scale-95 transition-transform mt-2">
                    <div className="flex items-center gap-3">
                        <Shield size={20} className="text-emerald-400" />
                        <span className="font-bold text-sm">Панель администратора</span>
                    </div>
                    <ArrowUpRight size={18} />
                </button>
            )}

            {/* FOOTER */}
            <div className="pt-6 pb-6 text-center border-t border-slate-100 mt-4">
                <div className="flex justify-center gap-4 text-[10px] text-slate-400 font-medium uppercase tracking-wide mb-2">
                    <button onClick={() => navigate('/offer')} className="hover:text-slate-600">Оферта</button> • 
                    <button onClick={() => navigate('/privacy')} className="hover:text-slate-600">Конфиденциальность</button> • 
                    <a href="mailto:anton.sherbakov.01@gmail.com" className="hover:text-slate-600">Поддержка</a>
                </div>
                <p className="text-[10px] text-slate-300">ИП Щербаков Антон Алексеевич</p>
                <p className="text-[10px] text-slate-300">ИНН: 712807221159 • ОГРНИП: 325710000062103</p>
                <p className="text-[10px] text-slate-300">Email: anton.sherbakov.01@gmail.com</p>
                <p className="text-[10px] text-slate-300">Telegram Support: <a href="https://t.me/AAntonShch" target="_blank" rel="noopener noreferrer" className="hover:text-slate-400">@AAntonShch</a></p>
                <p className="text-[10px] text-slate-300 mt-2">ID: {user?.id} • Версия: 2.2.0</p>
            </div>
        </div>
    );
};

export default ProfilePage;