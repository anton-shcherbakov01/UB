import React, { useState } from 'react';
import { TrendingUp, TrendingDown, Percent, Star, Wallet, X } from 'lucide-react';

const StoriesBar = ({ stories }) => {
    const [activeStory, setActiveStory] = useState(null);

    if (!stories || stories.length === 0) return null;

    const getIcon = (iconName, size=16) => {
        switch(iconName) {
            case 'trending-up': return <TrendingUp size={size} className="text-emerald-600" />;
            case 'trending-down': return <TrendingDown size={size} className="text-rose-500" />;
            case 'percent': return <Percent size={size} className="text-violet-600" />;
            case 'star': return <Star size={size} className="text-amber-500" fill="currentColor" />;
            case 'wallet': return <Wallet size={size} className="text-blue-500" />;
            default: return <Star size={size} className="text-slate-400" />;
        }
    };

    return (
        <>
            {/* Лента сторис */}
            <div className="flex gap-4 overflow-x-auto pb-4 px-2 scrollbar-hide select-none">
                {stories.map(s => (
                    <div key={s.id} onClick={() => setActiveStory(s)} className="flex flex-col items-center gap-2 min-w-[72px] cursor-pointer group">
                        <div className={`w-[72px] h-[72px] rounded-full p-[3px] ${s.color} transition-transform group-active:scale-95 shadow-sm`}>
                            <div className="w-full h-full rounded-full bg-white border-[3px] border-white flex flex-col items-center justify-center relative overflow-hidden">
                                <div className="mb-0.5">{getIcon(s.icon)}</div>
                                <span className="text-[11px] font-black text-slate-800 leading-none text-center px-1 truncate w-full">
                                    {s.val}
                                </span>
                            </div>
                        </div>
                        <span className="text-[10px] font-medium text-slate-500 tracking-wide">{s.title}</span>
                    </div>
                ))}
            </div>

            {/* Просмотр сторис (Модалка) */}
            {activeStory && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setActiveStory(null)}>
                    <div className="w-[85%] max-w-sm aspect-[9/16] max-h-[80vh] bg-white rounded-3xl relative overflow-hidden flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
                        {/* Фон сторис */}
                        <div className={`absolute inset-0 opacity-20 ${activeStory.color.replace('bg-gradient-to-tr', 'bg-gradient-to-b')}`}></div>
                        
                        {/* Прогресс бар (имитация) */}
                        <div className="absolute top-2 left-2 right-2 h-1 bg-black/10 rounded-full overflow-hidden">
                            <div className="h-full bg-slate-800 w-full animate-[progress_5s_linear]"></div>
                        </div>

                        <button onClick={() => setActiveStory(null)} className="absolute top-4 right-4 text-slate-500 p-2 bg-white/50 rounded-full backdrop-blur-md z-10">
                            <X size={20} />
                        </button>

                        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center relative z-0">
                            <div className="w-24 h-24 rounded-full bg-white shadow-xl flex items-center justify-center mb-6 text-4xl">
                                {getIcon(activeStory.icon, 48)}
                            </div>
                            <h2 className="text-3xl font-black text-slate-800 mb-2">{activeStory.val}</h2>
                            <h3 className="text-xl font-bold text-slate-500 mb-6">{activeStory.title}</h3>
                            <p className="text-slate-600 font-medium leading-relaxed bg-white/60 p-4 rounded-2xl backdrop-blur-sm">
                                {activeStory.details || "Нет дополнительных данных"}
                            </p>
                        </div>
                        
                        <div className="p-6 pb-8">
                            <button onClick={() => setActiveStory(null)} className="w-full bg-slate-900 text-white py-4 rounded-xl font-bold">
                                Закрыть
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    )
}

export default StoriesBar;