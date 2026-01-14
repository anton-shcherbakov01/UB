import React, { useState, useEffect } from 'react';
import { 
    User, Key, X, Loader2, Shield, ArrowUpRight, CreditCard, 
    AlertTriangle, Check, Lock, BarChart3, Package, Megaphone, MessageCircle 
} from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';

const ProfilePage = ({ onNavigate }) => {
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);
    
    // API Key states
    const [wbToken, setWbToken] = useState('');
    const [tokenLoading, setTokenLoading] = useState(false);
    const [scopes, setScopes] = useState(null);
    const [scopesLoading, setScopesLoading] = useState(false);
    
    const [payLoading, setPayLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        loadProfile();
        loadTariffs();
    }, []);

    const loadTariffs = () => {
        fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(data => { if (Array.isArray(data)) setTariffs(data); });
    };

    const loadProfile = () => {
        fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
            .then(r => r.ok ? r.json() : Promise.reject(r))
            .then(data => {
                setUser(data);
                if (data.has_wb_token) {
                    setWbToken(data.wb_token_preview || '');
                    fetchScopes();
                }
            })
            .catch(e => setError("Не удалось загрузить профиль"));
    };

    const fetchScopes = () => {
        setScopesLoading(true);
        fetch(`${API_URL}/api/user/token/scopes`, { headers: getTgHeaders() })
            .then(r => r.json())
            .then(setScopes)
            .catch(console.error)
            .finally(() => setScopesLoading(false));
    };

    const saveToken = async () => {
        if (!wbToken || wbToken.includes("••••")) return;
        setTokenLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/user/token`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({ token: wbToken })
            });
            const d = await res.json();
            
            if (res.ok) {
                // Обновляем локально без перезагрузки всей страницы
                setUser(prev => ({ ...prev, has_wb_token: true }));
                if (d.scopes) setScopes(d.scopes);
                else fetchScopes();
                
                // Маскируем токен визуально
                setWbToken(wbToken.substring(0, 5) + "••••••••••" + wbToken.substring(wbToken.length - 4));
            } else {
                throw new Error(d.detail || "Ошибка");
            }
        } catch (e) {
            alert(e.message);
        } finally {
            setTokenLoading(false);
        }
    };

    const deleteToken = async () => {
        if (!confirm("Удалить токен и остановить сбор данных?")) return;
        setTokenLoading(true);
        try {
            await fetch(`${API_URL}/api/user/token`, { method: 'DELETE', headers: getTgHeaders() });
            setWbToken('');
            setScopes(null);
            setUser(prev => ({ ...prev, has_wb_token: false }));
        } finally {
            setTokenLoading(false);
        }
    };

    // Оплата (заглушки функций)
    const payStars = (plan) => alert(`Оплата Stars: ${plan.stars}`);
    const payRubles = (plan) => alert(`Оплата картой: ${plan.price}`);

    // --- КОМПОНЕНТЫ UI ---

    const ScopeCard = ({ label, active, icon: Icon, colorClass }) => (
        <div className={`flex flex-col items-center justify-center p-3 rounded-2xl border transition-all duration-300 ${
            active 
            ? `bg-${colorClass}-50 border-${colorClass}-200` 
            : 'bg-slate-50 border-slate-100 opacity-60 grayscale'
        }`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center mb-2 ${
                active ? `bg-${colorClass}-100 text-${colorClass}-600` : 'bg-slate-200 text-slate-400'
            }`}>
                {active ? <Icon size={16} /> : <Lock size={14} />}
            </div>
            <span className={`text-[10px] font-bold text-center leading-tight ${active ? 'text-slate-700' : 'text-slate-400'}`}>
                {label}
            </span>
        </div>
    );

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            
            {/* Header */}
            <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400 relative overflow-hidden">
                    <User size={32} />
                    {/* Статус онлайн/план */}
                    <div className="absolute bottom-1 right-1 w-4 h-4 bg-emerald-500 border-2 border-white rounded-full"></div>
                </div>
                <div>
                    <h2 className="text-xl font-black text-slate-800">{user?.name || 'Loading...'}</h2>
                    <div className="flex items-center gap-2 mt-1">
                        <span className="bg-slate-900 text-white px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider">
                            {user?.plan || 'Free'}
                        </span>
                        {user?.days_left > 0 && (
                            <span className="text-xs font-medium text-emerald-600">
                                {user.days_left} дн.
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* API Settings Section */}
            <div className="bg-white p-5 rounded-[24px] shadow-sm border border-slate-100">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="font-bold text-slate-800 flex items-center gap-2">
                        <Key size={18} className="text-indigo-600" />
                        Подключение WB
                    </h3>
                    {user?.has_wb_token && (
                        <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-lg">
                            Подключено
                        </span>
                    )}
                </div>

                <div className="relative mb-4">
                    <input
                        type="text"
                        value={wbToken}
                        onChange={(e) => setWbToken(e.target.value)}
                        placeholder="Вставьте API токен (Статистика)"
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3.5 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:text-slate-400"
                    />
                    {user?.has_wb_token && wbToken && (
                        <button onClick={deleteToken} className="absolute right-3 top-3 p-1 text-slate-400 hover:text-rose-500 transition-colors">
                            <X size={16} />
                        </button>
                    )}
                </div>

                {/* Scope Grid Visualization */}
                {(user?.has_wb_token || scopes) && (
                    <div className="grid grid-cols-4 gap-2 mb-4">
                        {scopesLoading ? (
                            <div className="col-span-4 text-center py-4 text-slate-400 text-xs flex justify-center gap-2">
                                <Loader2 className="animate-spin" size={14} /> Проверка прав...
                            </div>
                        ) : (
                            <>
                                <ScopeCard 
                                    label="Аналитика" 
                                    active={scopes?.statistics} 
                                    icon={BarChart3} 
                                    colorClass="indigo" 
                                />
                                <ScopeCard 
                                    label="Контент" 
                                    active={scopes?.standard} 
                                    icon={Package} 
                                    colorClass="emerald" 
                                />
                                <ScopeCard 
                                    label="Реклама" 
                                    active={scopes?.promotion} 
                                    icon={Megaphone} 
                                    colorClass="violet" 
                                />
                                <ScopeCard 
                                    label="Вопросы" 
                                    active={scopes?.questions} 
                                    icon={MessageCircle} 
                                    colorClass="amber" 
                                />
                            </>
                        )}
                    </div>
                )}

                {/* Save Button - Only shows if needed */}
                {(!user?.has_wb_token || (wbToken && !wbToken.includes('••••'))) && (
                    <button
                        onClick={saveToken}
                        disabled={tokenLoading || !wbToken}
                        className="w-full py-3 bg-indigo-600 text-white rounded-xl font-bold text-sm shadow-lg shadow-indigo-200 active:scale-95 transition-all disabled:opacity-50 disabled:active:scale-100 flex justify-center items-center gap-2"
                    >
                        {tokenLoading ? <Loader2 className="animate-spin" size={18}/> : 'Сохранить и проверить'}
                    </button>
                )}
            </div>

            {/* Tariffs Section */}
            <h3 className="font-bold text-lg px-2">Тарифы</h3>
            <div className="grid gap-4">
                {tariffs.map(plan => (
                    <div key={plan.id} className={`p-5 rounded-[24px] border-2 transition-all relative overflow-hidden ${plan.current ? 'border-emerald-500 bg-white' : 'border-slate-100 bg-white'}`}>
                        {plan.is_best && (
                            <div className="absolute top-0 right-0 bg-indigo-600 text-white text-[10px] font-bold px-3 py-1 rounded-bl-xl">
                                POPULAR
                            </div>
                        )}
                        
                        <div className="flex justify-between items-start mb-2">
                            <div>
                                <h4 className="font-bold text-lg">{plan.name}</h4>
                                <div className="text-slate-900 font-black text-2xl">{plan.price}</div>
                            </div>
                        </div>

                        <div className="space-y-2 mb-4">
                            {plan.features.slice(0, 3).map((f, i) => (
                                <div key={i} className="flex items-center gap-2 text-xs font-medium text-slate-600">
                                    <div className={`w-1.5 h-1.5 rounded-full ${plan.current ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                                    {f}
                                </div>
                            ))}
                        </div>

                        {!plan.current && plan.price !== "0 ₽" && (
                            <button 
                                onClick={() => payRubles(plan)} 
                                className="w-full py-2.5 rounded-xl bg-slate-100 hover:bg-slate-900 hover:text-white text-slate-900 font-bold text-sm transition-all flex items-center justify-center gap-2"
                            >
                                {payLoading ? <Loader2 size={16} className="animate-spin" /> : 'Выбрать'}
                            </button>
                        )}
                        {plan.current && (
                            <div className="w-full py-2.5 text-center text-xs font-bold text-emerald-600 bg-emerald-50 rounded-xl">
                                Ваш текущий план
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Footer Links */}
            <div className="pt-6 text-center">
                 {user?.is_admin && (
                    <button onClick={() => onNavigate('admin')} className="mb-6 inline-flex items-center gap-2 px-4 py-2 bg-slate-800 text-white rounded-full text-xs font-bold shadow-lg">
                        <Shield size={12} /> Админ-панель
                    </button>
                )}
                <p className="text-[10px] text-slate-300">
                    ID: {user?.id} • Ver: 1.2.0 (Beta)
                </p>
            </div>
        </div>
    );
};

export default ProfilePage;