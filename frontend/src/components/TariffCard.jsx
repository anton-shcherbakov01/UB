import React from 'react';
import { Star, CheckCircle2 } from 'lucide-react';

const TariffCard = ({ plan, onPay }) => (
  <div className={`p-6 rounded-3xl border-2 relative overflow-hidden transition-all ${plan.is_best ? 'border-indigo-600 bg-indigo-50/50 scale-[1.02] shadow-lg' : 'border-slate-100 bg-white'}`}>
    {plan.is_best && (
      <div className="absolute top-0 right-0 bg-indigo-600 text-white px-3 py-1 rounded-bl-xl text-[10px] font-black uppercase">
        ХИТ
      </div>
    )}
    <h3 className={`text-xl font-black uppercase ${plan.is_best ? 'text-indigo-700' : 'text-slate-800'}`}>{plan.name}</h3>
    <div className="flex items-baseline gap-2 mt-2 mb-4">
        <span className="text-3xl font-black text-slate-900">{plan.price}</span>
        {plan.stars > 0 && <span className="text-xs font-bold text-amber-500 bg-amber-100 px-2 py-0.5 rounded-full flex items-center gap-1"><Star size={10} fill="currentColor"/> {plan.stars} Stars</span>}
    </div>
    
    <ul className="space-y-3 mb-6">
      {plan.features.map((f, i) => (
        <li key={i} className="flex items-start gap-3 text-sm font-medium text-slate-600">
          <CheckCircle2 size={16} className={`mt-0.5 ${plan.is_best ? 'text-indigo-600' : 'text-slate-400'}`} />
          <span>{f}</span>
        </li>
      ))}
    </ul>
    
    <button 
        onClick={() => !plan.current && onPay(plan)}
        className={`w-full py-4 rounded-xl font-bold text-sm shadow-lg active:scale-95 transition-all flex justify-center items-center gap-2 ${plan.current ? 'bg-slate-200 text-slate-500 cursor-not-allowed' : plan.is_best ? 'bg-indigo-600 text-white shadow-indigo-200' : 'bg-slate-900 text-white'}`}
    >
      {plan.current ? 'Ваш текущий план' : <>{plan.stars > 0 && <Star size={16} fill="currentColor" className="text-amber-400"/>} Оплатить Stars</>}
    </button>
  </div>
);

export default TariffCard;