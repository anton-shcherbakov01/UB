import React from 'react';
import { Check, Star, CreditCard, Loader2, Sparkles, Zap } from 'lucide-react';

const TariffCard = ({ plan, onPayStars, onPayRubles, loading }) => {
  // Логика определения "Лучшего выбора" (Analyst/Pro)
  const isBestValue = plan.is_best || plan.id === 'pro';
  const isCurrent = plan.current;

  return (
    <div className={`relative p-6 rounded-[24px] border-2 transition-all duration-300 flex flex-col h-full ${
      isCurrent 
        ? 'border-emerald-500 bg-white shadow-emerald-100 shadow-xl scale-[1.01]' 
        : isBestValue
          ? 'border-indigo-500/30 bg-white shadow-indigo-100 shadow-lg scale-[1.01] z-10' // Выделяем Analyst
          : 'border-slate-100 bg-white hover:border-slate-200'
    }`}>
      {/* Бейджик BEST VALUE */}
      {isBestValue && !isCurrent && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-[10px] font-black uppercase tracking-widest px-4 py-1.5 rounded-full shadow-lg shadow-indigo-200 flex items-center gap-1 whitespace-nowrap">
          <Sparkles size={10} className="text-yellow-300 fill-yellow-300" /> Best Value
        </div>
      )}

      {/* Бейджик CURRENT */}
      {isCurrent && (
        <div className="absolute top-0 right-0 bg-emerald-500 text-white text-[10px] font-bold px-3 py-1 rounded-bl-xl rounded-tr-[20px]">
          АКТИВЕН
        </div>
      )}

      <div className="mb-4">
        <h3 className={`font-black text-xl flex items-center gap-2 ${isCurrent ? 'text-emerald-900' : 'text-slate-800'}`}>
          {plan.name}
        </h3>
        <div className="flex items-baseline gap-1 mt-2">
          <span className="text-3xl font-black text-slate-900">{plan.price}</span>
          {plan.price !== "0 ₽" && <span className="text-xs font-bold text-slate-400">/мес</span>}
        </div>
      </div>

      {/* Список фич */}
      <div className="space-y-3 mb-6 flex-1">
        {plan.features.map((feature, i) => (
          <div key={i} className="flex items-start gap-3 text-xs font-bold text-slate-600">
            <div className={`mt-0.5 min-w-[14px] h-[14px] rounded-full flex items-center justify-center ${
                isCurrent ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-400"
            }`}>
                <Check size={10} strokeWidth={4} />
            </div>
            <span className="leading-snug">{feature}</span>
          </div>
        ))}
      </div>

      {/* Кнопки оплаты */}
      <div className="mt-auto">
        {isCurrent ? (
          <div className="w-full py-3.5 rounded-xl font-bold text-sm bg-emerald-50 text-emerald-600 flex justify-center items-center gap-2 border border-emerald-100">
            <Check size={16} /> Ваш текущий план
          </div>
        ) : plan.price === "0 ₽" ? (
          <button disabled className="w-full py-3.5 rounded-xl font-bold text-sm border-2 border-slate-100 text-slate-400 bg-slate-50 cursor-not-allowed">
            Бесплатно навсегда
          </button>
        ) : (
          <div className="grid grid-cols-2 gap-2">
             <button 
               onClick={() => onPayStars(plan)}
               className="py-3 rounded-xl font-bold text-xs bg-amber-400 text-white hover:bg-amber-500 active:scale-95 transition-all flex flex-col justify-center items-center shadow-lg shadow-amber-100"
             >
               <div className="flex items-center gap-1">
                 <Star size={14} fill="currentColor" /> Telegram Stars
               </div>
               <span className="text-[10px] opacity-90 font-medium">{plan.stars} звёзд</span>
             </button>
             <button 
               onClick={() => onPayRubles(plan)}
               disabled={loading}
               className="py-3 rounded-xl font-bold text-xs bg-slate-900 text-white hover:bg-slate-800 active:scale-95 transition-all flex flex-col justify-center items-center shadow-xl shadow-slate-200"
             >
               <div className="flex items-center gap-1">
                 {loading ? <Loader2 size={14} className="animate-spin" /> : <CreditCard size={14} />} Карта РФ
               </div>
               <span className="text-[10px] opacity-70 font-medium">Для юр. и физ. лиц</span>
             </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default TariffCard;