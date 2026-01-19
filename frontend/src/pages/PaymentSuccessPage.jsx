import React, { useEffect, useState } from 'react';
import { CheckCircle, Loader2 } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

const PaymentSuccessPage = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [countdown, setCountdown] = useState(5);
    const [redirecting, setRedirecting] = useState(false);

    const redirectToApp = () => {
        setRedirecting(true);
        const telegramAppUrl = "https://t.me/WbAnalyticsBot/app";
        
        if (window.Telegram?.WebApp?.openLink) {
            window.Telegram.WebApp.openLink(telegramAppUrl);
        } else {
            window.location.href = telegramAppUrl;
        }
    };

    useEffect(() => {
        const timer = setInterval(() => {
            setCountdown((prev) => {
                if (prev <= 1) {
                    clearInterval(timer);
                    redirectToApp();
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(timer);
    }, []);

    return (
        <div className="min-h-screen bg-gradient-to-br from-emerald-400 via-blue-500 to-purple-600 flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl p-8 max-w-md w-full text-center shadow-2xl animate-in fade-in zoom-in-95">
                <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-6">
                    <CheckCircle className="text-emerald-600" size={48} />
                </div>
                
                <h1 className="text-3xl font-black text-slate-900 mb-3">
                    Оплата успешна!
                </h1>
                
                <p className="text-slate-600 mb-6 leading-relaxed">
                    Ваша подписка активирована. Вы будете перенаправлены в приложение через{' '}
                    <span className="font-bold text-emerald-600">{countdown}</span> секунд.
                </p>

                {redirecting ? (
                    <div className="flex items-center justify-center gap-2 text-slate-500">
                        <Loader2 className="animate-spin" size={20} />
                        <span className="text-sm">Перенаправление...</span>
                    </div>
                ) : (
                    <button
                        onClick={redirectToApp}
                        className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-4 px-6 rounded-2xl transition-all active:scale-95 shadow-lg shadow-emerald-200"
                    >
                        Вернуться в приложение
                    </button>
                )}
            </div>
        </div>
    );
};

export default PaymentSuccessPage;

