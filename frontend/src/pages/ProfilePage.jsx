import React, { useState, useEffect } from 'react';
import { User, Key, X, Loader2, Shield, ArrowUpRight, CreditCard, AlertTriangle } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import TariffCard from '../components/TariffCard';

const ProfilePage = ({ onNavigate }) => {
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);
    const [wbToken, setWbToken] = useState('');
    const [tokenLoading, setTokenLoading] = useState(false);
    const [payLoading, setPayLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Загрузка тарифов
        fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(data => {
                if (Array.isArray(data)) setTariffs(data);
            })
            .catch(e => console.error("Tariffs error:", e));

        // Загрузка профиля с обработкой ошибок
        fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
            .then(async r => {
                if (!r.ok) {
                    const text = await r.text();
                    try {
                        const json = JSON.parse(text);
                        throw new Error(json.detail || `Ошибка ${r.status}`);
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
                }
            })
            .catch(e => {
                console.error("Profile fetch failed:", e);
                setError(e.message);
            });
    }, []);

    const payStars = async (plan) => {
        if (!plan.stars) return;
        try {
            const res = await fetch(`${API_URL}/api/payment/stars_link`, { 
                method: 'POST', 
                headers: getTgHeaders(),
                body: JSON.stringify({plan_id: plan.id, amount: plan.stars})
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
                alert("Ошибка создания ссылки или приложение открыто не в Telegram");
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
        if (!wbToken || wbToken.includes("*****")) return;
        setTokenLoading(true);
        try {
             const res = await fetch(`${API_URL}/api/user/token`, { 
                method: 'POST', 
                headers: getTgHeaders(),
                body: JSON.stringify({token: wbToken})
            });
            
            if (res.ok) {
                alert("Токен успешно сохранен!");
                // Перезагружаем профиль
                const uRes = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
                if(uRes.ok) setUser(await uRes.json());
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
             await fetch(`${API_URL}/api/user/token`, { 
                method: 'DELETE', 
                headers: getTgHeaders()
            });
            setWbToken('');
            setUser(prev => ({...prev, has_wb_token: false}));
        } catch(e) {
            console.error(e);
        } finally {
            setTokenLoading(false);
        }
    };

    // Компонент карточки тарифа
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
                    <button 
                        onClick={() => payStars(plan)}
                        className="flex items-center justify-center gap-2 py-2.5 bg-amber-400 text-white rounded-xl font-bold text-sm hover:bg-amber-500 transition-colors"
                    >
                        <span>Stars</span>
                    </button>
                    <button 
                        onClick={() => payRubles(plan)}
                        disabled={payLoading}
                        className="flex items-center justify-center gap-2 py-2.5 bg-slate-900 text-white rounded-xl font-bold text-sm hover:bg-slate-800 transition-colors"
                    >
                        {payLoading ? <Loader2 className="animate-spin" size={16} /> : <CreditCard size={16}/>}
                        <span>РФ Карта</span>
                    </button>
                </div>
            )}
        </div>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            {error && (
                <div className="bg-red-50 p-4 rounded-2xl border border-red-100 flex items-start gap-3">
                    <AlertTriangle className="text-red-500 shrink-0" size={20}/>
                    <div>
                        <h3 className="font-bold text-red-800 text-sm">Ошибка доступа</h3>
                        <p className="text-xs text-red-600 mt-1">{error}</p>
                        <p className="text-xs text-slate-400 mt-2">
                            Если вы запускаете локально (без Telegram), убедитесь что Backend запущен с <code>DEBUG_MODE=True</code>
                        </p>
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
                        placeholder="Введите токен..."
                        className="w-full bg-slate-50 border border-slate-100 rounded-xl p-3 pr-10 text-sm font-medium outline-none focus:ring-2 ring-indigo-100"
                    />
                    {user?.has_wb_token && (
                        <button onClick={deleteToken} className="absolute right-2 top-2 p-1 text-slate-300 hover:text-red-500"><X size={16}/></button>
                    )}
                </div>
                {!user?.has_wb_token && (
                    <button onClick={saveToken} disabled={tokenLoading} className="w-full mt-3 bg-indigo-600 text-white py-3 rounded-xl font-bold text-sm">
                        {tokenLoading ? <Loader2 className="animate-spin" /> : 'Сохранить токен'}
                    </button>
                )}
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
                         <Shield size={20} className="text-emerald-400"/>
                         <span className="font-bold text-sm">Админ-панель</span>
                     </div>
                     <ArrowUpRight size={18}/>
                 </button>
            )}

            <div className="mt-8 pt-8 border-t border-slate-100 text-center space-y-2">
                <div className="flex justify-center gap-4 text-xs text-slate-400">
                    <a href="#" className="hover:text-slate-600 transition-colors">Публичная оферта</a>
                    <span>•</span>
                    <a href="#" className="hover:text-slate-600 transition-colors">Политика конфиденциальности</a>
                </div>
                <p className="text-[10px] text-slate-300">
                    Сервис не является аффилированным лицом Wildberries.<br/>
                    Обработка персональных данных в соответствии с 152-ФЗ.
                </p>
            </div>
        </div>
    );
};

export default ProfilePage;