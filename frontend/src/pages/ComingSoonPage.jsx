import React from 'react';
import { Construction, Bell, ArrowLeft } from 'lucide-react';

const ComingSoonPage = ({ onBack, title = "Сервис", icon }) => {
    return (
        <div className="h-screen bg-slate-50 flex flex-col p-6 animate-in fade-in slide-in-from-bottom-8">
            <button 
                onClick={onBack}
                className="self-start p-2 -ml-2 text-slate-400 hover:text-slate-600 mb-8"
            >
                <ArrowLeft size={24} />
            </button>

            <div className="flex-1 flex flex-col items-center justify-center text-center -mt-20">
                <div className="w-24 h-24 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center mb-6 shadow-inner">
                    {icon || <Construction size={48} />}
                </div>

                <h2 className="text-3xl font-black text-slate-800 mb-2">
                    {title}
                </h2>
                
                <div className="inline-block px-3 py-1 bg-amber-100 text-amber-700 rounded-lg text-xs font-bold uppercase tracking-wider mb-6">
                    В разработке
                </div>

                <p className="text-slate-500 max-w-xs leading-relaxed mb-8">
                    Мы прямо сейчас работаем над этим модулем. Он будет включать автоматизацию, аналитику и AI-прогнозы.
                </p>

                <button className="flex items-center gap-2 bg-slate-900 text-white px-6 py-4 rounded-2xl font-bold shadow-xl active:scale-95 transition-transform">
                    <Bell size={18} />
                    Сообщить о запуске
                </button>
            </div>
        </div>
    );
};

export default ComingSoonPage;