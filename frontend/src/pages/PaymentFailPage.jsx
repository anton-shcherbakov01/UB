import React, { useEffect, useState } from 'react';
import { XCircle, Loader2, RefreshCw } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

const PaymentFailPage = () => {
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

    const goToTariffs = () => {
        navigate('/tariffs');
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
        <div className="min-h-screen bg-gradient-to-br from-red-400 via-pink-500 to-rose-600 flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl p-8 max-w-md w-full text-center shadow-2xl animate-in fade-in zoom-in-95">
                <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
                    <XCircle className="text-red-600" size={48} />
                </div>
                
                <h1 className="text-3xl font-black text-slate-900 mb-3">
                    Оплата не завершена
                </h1>
                
                <p className="text-slate-600 mb-6 leading-relaxed">
                    Похоже, оплата не была завершена. Вы можете попробовать снова или выбрать другой метод оплаты.
                </p>

                {redirecting ? (
                    <div className="flex items-center justify-center gap-2 text-slate-500 mb-4">
                        <Loader2 className="animate-spin" size={20} />
                        <span className="text-sm">Перенаправление...</span>
                    </div>
                ) : (
                    <>
                        <p className="text-sm text-slate-500 mb-4">
                            Автоматическое перенаправление через <span className="font-bold text-red-600">{countdown}</span> секунд
                        </p>
                        <div className="space-y-3">
                            <button
                                onClick={goToTariffs}
                                className="w-full bg-red-600 hover:bg-red-700 text-white font-bold py-4 px-6 rounded-2xl transition-all active:scale-95 shadow-lg shadow-red-200 flex items-center justify-center gap-2"
                            >
                                <RefreshCw size={20} />
                                Попробовать снова
                            </button>
                            <button
                                onClick={redirectToApp}
                                className="w-full bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold py-4 px-6 rounded-2xl transition-all active:scale-95"
                            >
                                Вернуться в приложение
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};

export default PaymentFailPage;

