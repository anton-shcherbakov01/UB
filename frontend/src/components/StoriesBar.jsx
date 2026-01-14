import React from 'react';
import { TrendingUp, TrendingDown, Percent, Star, AlertCircle } from 'lucide-react';

const StoriesBar = ({ stories }) => {
    if (!stories || stories.length === 0) return null;

    const getIcon = (iconName) => {
        switch(iconName) {
            case 'trending-up': return <TrendingUp size={16} className="text-emerald-600" />;
            case 'trending-down': return <TrendingDown size={16} className="text-rose-500" />;
            case 'percent': return <Percent size={16} className="text-violet-600" />;
            case 'star': return <Star size={16} className="text-amber-500" fill="currentColor" />;
            default: return <AlertCircle size={16} className="text-slate-400" />;
        }
    };

    return (
        <div className="flex gap-4 overflow-x-auto pb-4 px-2 scrollbar-hide select-none">
            {stories.map(s => (
                <div key={s.id} className="flex flex-col items-center gap-2 min-w-[72px] cursor-pointer group">
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
    )
}

export default StoriesBar;