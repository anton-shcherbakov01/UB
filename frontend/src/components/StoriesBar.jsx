import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Percent, Star, Wallet, X, ChevronRight, ChevronLeft } from 'lucide-react';

const StoriesBar = ({ stories }) => {
    const [activeIndex, setActiveIndex] = useState(null);
    const [progress, setProgress] = useState(0);

    // Блокировка прокрутки фона при открытых сторис
    useEffect(() => {
        if (activeIndex !== null) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'auto';
        }
        return () => { document.body.style.overflow = 'auto'; };
    }, [activeIndex]);

    // Таймер для авто-переключения
    useEffect(() => {
        let timer;
        if (activeIndex !== null) {
            setProgress(0);
            const duration = 5000; // 5 секунд на сторис
            const interval = 50;
            const step = 100 / (duration / interval);

            timer = setInterval(() => {
                setProgress(prev => {
                    if (prev >= 100) {
                        handleNext();
                        return 0;
                    }
                    return prev + step;
                });
            }, interval);
        }
        return () => clearInterval(timer);
    }, [activeIndex]);

    if (!stories || stories.length === 0) return null;

    const handleNext = () => {
        if (activeIndex < stories.length - 1) {
            setActiveIndex(activeIndex + 1);
            setProgress(0);
        } else {
            closeStories();
        }
    };

    const handlePrev = () => {
        if (activeIndex > 0) {
            setActiveIndex(activeIndex - 1);
            setProgress(0);
        } else {
            setActiveIndex(0); // Или закрывать, если нужно
        }
    };

    const closeStories = () => {
        setActiveIndex(null);
        setProgress(0);
    };

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

    const activeStory = activeIndex !== null ? stories[activeIndex] : null;

    return (
        <>
            {/* Лента кружочков */}
            <div className="flex gap-4 overflow-x-auto pb-4 px-2 scrollbar-hide select-none z-10 relative">
                {stories.map((s, idx) => (
                    <div key={s.id} onClick={() => setActiveIndex(idx)} className="flex flex-col items-center gap-2 min-w-[72px] cursor-pointer group transition-transform active:scale-95">
                        <div className={`w-[72px] h-[72px] rounded-full p-[3px] ${s.color} shadow-sm`}>
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

            {/* Полноэкранный просмотр */}
            {activeStory && (
                <div className="fixed inset-0 z-[100] bg-black text-white flex flex-col animate-in fade-in duration-200 safe-area-pb">
                    
                    {/* Фон с блюром */}
                    <div className={`absolute inset-0 opacity-30 blur-3xl ${activeStory.color.replace('bg-gradient-to-tr', 'bg-gradient-to-b')}`}></div>

                    {/* Верхняя панель прогресса */}
                    <div className="absolute top-4 left-2 right-2 flex gap-1 z-20">
                        {stories.map((_, idx) => (
                            <div key={idx} className="h-1 bg-white/20 flex-1 rounded-full overflow-hidden">
                                <div 
                                    className={`h-full bg-white transition-all duration-100 ease-linear ${idx === activeIndex ? '' : (idx < activeIndex ? 'w-full' : 'w-0')}`}
                                    style={{ width: idx === activeIndex ? `${progress}%` : undefined }}
                                ></div>
                            </div>
                        ))}
                    </div>

                    {/* Кнопка закрытия */}
                    <button 
                        onClick={closeStories} 
                        className="absolute top-8 right-4 z-30 p-2 bg-black/20 rounded-full backdrop-blur-md active:bg-white/20 transition"
                    >
                        <X size={24} color="white" />
                    </button>

                    {/* Зоны клика (навигация тапами) */}
                    <div className="absolute inset-0 z-10 flex">
                        <div className="w-1/3 h-full" onClick={handlePrev}></div>
                        <div className="w-2/3 h-full" onClick={handleNext}></div>
                    </div>

                    {/* Контент сторис */}
                    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center relative z-0 pointer-events-none mt-10">
                        <div className="w-32 h-32 rounded-full bg-white shadow-[0_0_50px_rgba(255,255,255,0.3)] flex items-center justify-center mb-10 text-6xl animate-in zoom-in duration-300">
                            {getIcon(activeStory.icon, 64)}
                        </div>
                        
                        <h2 className="text-5xl font-black mb-4 tracking-tight drop-shadow-lg">
                            {activeStory.val}
                        </h2>
                        
                        <h3 className="text-2xl font-bold text-white/80 mb-8 uppercase tracking-widest border-b border-white/20 pb-2">
                            {activeStory.title}
                        </h3>
                        
                        <div className="bg-white/10 backdrop-blur-md p-6 rounded-3xl border border-white/10 shadow-xl max-w-xs">
                            <p className="text-lg font-medium leading-relaxed text-slate-100">
                                {activeStory.details || "Информация обновляется в реальном времени."}
                            </p>
                        </div>
                    </div>

                    <div className="pb-12 text-center text-white/40 text-sm animate-pulse">
                        Нажми справа, чтобы продолжить
                    </div>
                </div>
            )}
        </>
    )
}

export default StoriesBar;