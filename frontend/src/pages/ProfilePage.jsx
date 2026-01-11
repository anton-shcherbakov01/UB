import React, { useState, useEffect } from 'react';
import { User, Key, X, Loader2, Shield, ArrowUpRight } from 'lucide-react';
import { API_URL, getTgHeaders } from '../config';
import TariffCard from '../components/TariffCard';

const ProfilePage = ({ onNavigate }) => {
    const [tariffs, setTariffs] = useState([]);
    const [user, setUser] = useState(null);
    const [wbToken, setWbToken] = useState('');
    const [tokenLoading, setTokenLoading] = useState(false);

    useEffect(() => {
        fetch(`${API_URL}/api/user/tariffs`, { headers: getTgHeaders() }).then(r=>r.json()).then(setTariffs);
        fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() }).then(r=>r.json()).then(data => {
            setUser(data);
            if (data.has_wb_token) {
                setWbToken(data.wb_token_preview);
            }
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
            if (d.invoice_link) {
                 window.Telegram?.WebApp?.openInvoice(d.invoice_link, (status) => {
                     if (status === 'paid') {
                         alert("Оплата прошла успешно!");
                         window.location.reload();
                     }
                 });
            } else {
                alert("Ошибка создания ссылки");
            }
        } catch (e) {
            alert(e.message);
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
            const data = await res.json();
            if (res.status === 200) {
                alert("Токен успешно сохранен!");
                const uRes = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
                setUser(await uRes.json());
            } else {
                throw new Error(data.detail || "Ошибка");
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
            setUser({...user, has_wb_token: false});
        } finally {
            setTokenLoading(false);
        }
    };

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in slide-in-from-bottom-4">
            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                    <User size={32} />
                </div>
                <div>
                    <h2 className="text-xl font-bold">{user?.name || 'Гость'}</h2>
                    <p className="text-sm text-slate-400">@{user?.username}</p>
                    <div className="mt-2 inline-flex items-center gap-1 bg-black text-white px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                        {user?.plan || 'Free'} Plan
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

            <h2 className="font-bold text-lg px-2 mt-4">Тарифы (Stars)</h2>
            <div className="space-y-4">
                {tariffs.map(plan => (
                    <TariffCard key={plan.id} plan={plan} onPay={payStars} />
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
        </div>
    );
};

export default ProfilePage;