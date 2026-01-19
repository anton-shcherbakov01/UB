import React from 'react';
import { Construction, Bell, X } from 'lucide-react';

const ComingSoonModal = ({ isOpen, onClose, title = "Сервис", icon, description }) => {
    if (!isOpen) return null;

    return (
        <div 
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200 p-4"
            onClick={onClose}
        >
            <div 
                className="bg-white w-full max-w-md rounded-[32px] p-8 shadow-2xl animate-in slide-in-from-bottom-4 duration-300 relative"
                onClick={(e) => e.stopPropagation()}
            >
                <button 
                    onClick={onClose}
                    className="absolute top-4 right-4 p-2 text-slate-400 hover:text-slate-600 rounded-full hover:bg-slate-100 transition-colors"
                >
                    <X size={20} />
                </button>

                <div className="flex flex-col items-center text-center mt-4">
                    <div className="w-20 h-20 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center mb-6 shadow-inner">
                        {icon || <Construction size={40} />}
                    </div>

                    <h2 className="text-2xl font-black text-slate-800 mb-2">
                        {title}
                    </h2>
                    
                    <div className="inline-block px-3 py-1 bg-amber-100 text-amber-700 rounded-lg text-xs font-bold uppercase tracking-wider mb-6">
                        В разработке
                    </div>

                    <p className="text-slate-500 max-w-xs leading-relaxed mb-6">
                        {description || "Мы прямо сейчас работаем над этим модулем. Он будет включать автоматизацию, аналитику и AI-прогнозы."}
                    </p>

                    <button 
                        onClick={onClose}
                        className="flex items-center gap-2 bg-slate-900 text-white px-6 py-3 rounded-2xl font-bold shadow-xl active:scale-95 transition-transform"
                    >
                        <Bell size={18} />
                        Сообщить о запуске
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ComingSoonModal;

