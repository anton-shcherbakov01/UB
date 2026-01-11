import React from 'react';
import { LayoutGrid, BarChart3, DollarSign, Brain, User } from 'lucide-react';

const TabNav = ({ active, setTab, isAdmin }) => (
  <div className="fixed bottom-0 left-0 right-0 bg-white/95 backdrop-blur-md border-t border-slate-100 px-2 py-3 flex justify-between items-end z-50 pb-8 safe-area-pb shadow-[0_-5px_20px_rgba(0,0,0,0.03)]">
    <button onClick={() => setTab('home')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'home' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <LayoutGrid size={22} strokeWidth={active === 'home' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">Главная</span>
    </button>
    <button onClick={() => setTab('monitor')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'monitor' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <BarChart3 size={22} strokeWidth={active === 'monitor' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">Цены</span>
    </button>
    
    <div className="relative -top-5 w-[20%] flex justify-center">
        <button 
            onClick={() => setTab('finance')} 
            className="bg-indigo-600 text-white w-14 h-14 rounded-full shadow-xl shadow-indigo-300 active:scale-95 transition-transform border-4 border-white flex items-center justify-center"
        >
            <DollarSign size={28} strokeWidth={3} />
        </button>
    </div>

    <button onClick={() => setTab('ai')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'ai' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <Brain size={22} strokeWidth={active === 'ai' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">ИИ</span>
    </button>
    
    <button onClick={() => setTab('profile')} className={`flex flex-col items-center gap-1 w-[20%] transition-colors ${active === 'profile' ? 'text-indigo-600' : 'text-slate-400'}`}>
      <User size={22} strokeWidth={active === 'profile' ? 2.5 : 2} />
      <span className="text-[9px] font-bold">Профиль</span>
    </button>
  </div>
);

export default TabNav;