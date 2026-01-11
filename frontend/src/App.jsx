import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, Wallet, CreditCard, AlertCircle, Loader2, Sparkles, BarChart3, 
  ArrowUpRight, Plus, User, Shield, Brain, Star, ThumbsDown, CheckCircle2, 
  Crown, LayoutGrid, Trash2, RefreshCw, X, Clock, 
  ChevronLeft, FileDown, LogOut, Receipt, Wand2, Copy, Edit2, Check, Hash,
  Key, TrendingUp, Package, Coins, Calculator, DollarSign, PieChart, Truck, 
  Scale, Target, PlayCircle, ShieldCheck, Settings, Save, Info, AlertTriangle, ArrowDown,
  ThumbsUp, XCircle, ChevronRight, Zap, MoreHorizontal
} from 'lucide-react';
import { 
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area, CartesianGrid,
  BarChart, Bar, Cell
} from 'recharts';

// --- CONFIG ---
const API_URL = "https://api.ulike-bot.ru";

// --- HOOKS: TELEGRAM INTEGRATION ---

const useTelegram = () => {
    const [theme, setTheme] = useState({
        bg: 'var(--tg-theme-bg-color, #f2f2f7)',
        text: 'var(--tg-theme-text-color, #000000)',
        hint: 'var(--tg-theme-hint-color, #8e8e93)',
        link: 'var(--tg-theme-link-color, #007aff)',
        button: 'var(--tg-theme-button-color, #007aff)',
        buttonText: 'var(--tg-theme-button-text-color, #ffffff)',
        secondaryBg: 'var(--tg-theme-secondary-bg-color, #ffffff)',
        headerBg: 'var(--tg-theme-header-bg-color, #f2f2f7)',
    });

    useEffect(() => {
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
            try {
                tg.enableClosingConfirmation();
                tg.setHeaderColor(tg.themeParams.secondary_bg_color || '#f2f2f7');
                tg.setBackgroundColor(tg.themeParams.secondary_bg_color || '#f2f2f7');
            } catch (e) {
                console.warn('Telegram WebApp styling not fully supported');
            }
        }
    }, []);

    const haptic = (style = 'light') => {
        if (window.Telegram?.WebApp?.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
        }
    };

    return { theme, haptic, tg: window.Telegram?.WebApp };
};

// --- NATIVE UI COMPONENTS (iOS Design System) ---

const NativePage = ({ children, className = "" }) => (
    <div className={`min-h-screen pb-32 animate-in fade-in duration-300 ${className}`} style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, #f2f2f7)' }}>
        {children}
    </div>
);

const IOSSection = ({ title, children, action, className = "" }) => (
    <div className={`mb-6 ${className}`}>
        {(title || action) && (
            <div className="px-4 mb-2 flex justify-between items-end">
                {title && <h3 className="text-[13px] uppercase text-[var(--tg-theme-hint-color)] font-semibold tracking-wide ml-1">{title}</h3>}
                {action}
            </div>
        )}
        <div className="bg-[var(--tg-theme-bg-color)] overflow-hidden sm:rounded-xl border-y sm:border border-black/5 shadow-sm">
            {children}
        </div>
    </div>
);

const IOSCell = ({ icon, title, subtitle, value, onClick, isLast, color = "bg-blue-500", destructive, rightIcon, children }) => {
    const { haptic } = useTelegram();
    
    if (children) { // Custom content mode
         return (
            <div className={`pl-4 pr-4 py-3 bg-[var(--tg-theme-bg-color)] ${!isLast ? 'border-b border-black/5' : ''}`}>
                {children}
            </div>
         );
    }

    return (
        <div 
            onClick={() => { if(onClick) { haptic('selection'); onClick(); } }}
            className={`pl-4 pr-4 py-3 flex items-center gap-3 bg-[var(--tg-theme-bg-color)] active:bg-black/5 transition-colors cursor-pointer ${!isLast ? 'border-b border-black/5' : ''}`}
        >
            {icon && (
                <div className={`w-7 h-7 rounded-lg ${color} flex items-center justify-center text-white shrink-0 shadow-sm`}>
                    {React.cloneElement(icon, { size: 16 })}
                </div>
            )}
            <div className="flex-1 min-w-0 flex flex-col justify-center">
                <div className={`text-[17px] leading-snug ${destructive ? 'text-red-500' : 'text-[var(--tg-theme-text-color)]'}`}>{title}</div>
                {subtitle && <div className="text-[13px] text-[var(--tg-theme-hint-color)] leading-none mt-1 truncate">{subtitle}</div>}
            </div>
            {(value || rightIcon || onClick) && (
                <div className="flex items-center gap-2 text-[var(--tg-theme-hint-color)] pl-2">
                    {value && <span className="text-[17px] text-[var(--tg-theme-hint-color)]">{value}</span>}
                    {rightIcon}
                    {onClick && !rightIcon && <ChevronRight size={16} className="opacity-40" />}
                </div>
            )}
        </div>
    );
};

const NativeButton = ({ children, onClick, variant = 'primary', className = "", disabled, loading, size = 'default' }) => {
    const { haptic } = useTelegram();
    
    const baseStyle = "w-full rounded-xl font-semibold flex items-center justify-center gap-2 transition-transform active:scale-[0.98]";
    const sizeStyle = size === 'sm' ? "py-2 text-[15px]" : "py-3.5 text-[17px]";
    
    const variants = {
        primary: "bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] shadow-md shadow-blue-500/20",
        secondary: "bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-button-color)]",
        destructive: "bg-red-500 text-white shadow-md shadow-red-500/20",
        ghost: "bg-transparent text-[var(--tg-theme-hint-color)]"
    };

    return (
        <button 
            onClick={() => { if(!disabled && !loading) { haptic('light'); onClick(); } }}
            disabled={disabled || loading}
            className={`${baseStyle} ${sizeStyle} ${variants[variant]} ${disabled ? 'opacity-50' : ''} ${className}`}
        >
            {loading ? <Loader2 className="animate-spin" /> : children}
        </button>
    );
};

const NativeInput = ({ value, onChange, placeholder, type = "text", className = "", label, rightElement }) => (
    <div className={`bg-[var(--tg-theme-bg-color)] px-4 py-3 flex items-center justify-between ${className}`}>
        {label && <span className="text-[17px] w-1/3 shrink-0">{label}</span>}
        <input 
            type={type}
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            className="flex-1 bg-transparent text-[17px] outline-none text-right placeholder-[var(--tg-theme-hint-color)]"
        />
        {rightElement && <div className="ml-2">{rightElement}</div>}
    </div>
);

const SegmentedControl = ({ options, active, onChange }) => {
    const { haptic } = useTelegram();
    return (
        <div className="bg-[#767680]/15 p-0.5 rounded-lg flex mx-4 mb-4">
            {options.map(opt => {
                const isActive = active === opt.id;
                return (
                    <button
                        key={opt.id}
                        onClick={() => { haptic('selection'); onChange(opt.id); }}
                        className={`flex-1 py-1.5 text-[13px] font-medium rounded-md transition-all ${
                            isActive 
                            ? 'bg-[var(--tg-theme-bg-color)] text-[var(--tg-theme-text-color)] shadow-sm' 
                            : 'text-[var(--tg-theme-text-color)] opacity-60'
                        }`}
                    >
                        {opt.label}
                    </button>
                )
            })}
        </div>
    );
};

const NativeModal = ({ isOpen, onClose, title, children }) => {
    if (!isOpen) return null;
    return (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
            <div className="absolute inset-0 bg-black/40 backdrop-blur-sm animate-in fade-in" onClick={onClose} />
            <div className="relative w-full max-w-md bg-[var(--tg-theme-secondary-bg-color)] rounded-t-3xl sm:rounded-3xl p-6 shadow-2xl animate-in slide-in-from-bottom-full duration-300 max-h-[90vh] overflow-y-auto">
                <div className="flex justify-between items-center mb-6">
                    <h3 className="text-xl font-bold">{title}</h3>
                    <button onClick={onClose} className="p-1 bg-[#767680]/15 rounded-full">
                        <X size={20} className="text-[var(--tg-theme-hint-color)]"/>
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
};

// --- FEATURES: STORIES & SWIPE ---

const StoryViewer = ({ stories, initialIndex, onClose }) => {
    const [index, setIndex] = useState(initialIndex);
    const [progress, setProgress] = useState(0);
    const { haptic } = useTelegram();

    useEffect(() => {
        setProgress(0);
        const interval = setInterval(() => {
            setProgress(p => {
                if (p >= 100) {
                    if (index < stories.length - 1) {
                        setIndex(i => i + 1);
                        return 0;
                    } else {
                        onClose();
                        return 100;
                    }
                }
                return p + 1.5; 
            });
        }, 50);
        return () => clearInterval(interval);
    }, [index]);

    const handleTap = (e) => {
        const { clientX } = e;
        const width = window.innerWidth;
        if (clientX < width / 3) {
            if (index > 0) { haptic('selection'); setIndex(index - 1); }
        } else {
            if (index < stories.length - 1) { haptic('selection'); setIndex(index + 1); } else { onClose(); }
        }
    };

    const story = stories[index];
    const gradients = {
        'bg-emerald-500': 'from-emerald-600 to-teal-900',
        'bg-red-500': 'from-red-600 to-rose-900',
        'bg-purple-500': 'from-purple-600 to-violet-900',
        'bg-blue-500': 'from-blue-600 to-indigo-900',
        'bg-green-500': 'from-green-600 to-emerald-900',
    };
    const bg = gradients[story.color] || 'from-gray-600 to-slate-900';

    return (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col" onClick={handleTap}>
            <div className="flex gap-1.5 p-3 pt-safe-top z-20">
                {stories.map((s, i) => (
                    <div key={s.id} className="h-1 flex-1 bg-white/30 rounded-full overflow-hidden">
                        <div className="h-full bg-white transition-all duration-75 ease-linear" style={{ width: i < index ? '100%' : i === index ? `${progress}%` : '0%' }} />
                    </div>
                ))}
            </div>
            <div className={`flex-1 relative flex flex-col items-center justify-center p-8 text-white bg-gradient-to-b ${bg}`}>
                <button onClick={(e) => { e.stopPropagation(); onClose(); }} className="absolute top-6 right-4 p-2 bg-black/20 backdrop-blur rounded-full"><X size={24} /></button>
                <div className="animate-in zoom-in-95 duration-500 flex flex-col items-center text-center">
                    <div className="text-sm font-bold uppercase tracking-[0.2em] opacity-80 mb-6">{story.title}</div>
                    <div className="text-7xl font-black mb-6 drop-shadow-xl">{story.val}</div>
                    <div className="px-6 py-3 bg-white/20 backdrop-blur-md rounded-2xl text-lg font-medium leading-relaxed">{story.subtitle}</div>
                </div>
            </div>
        </div>
    );
};

const StoriesRow = () => {
    const [stories, setStories] = useState([]);
    const [activeIndex, setActiveIndex] = useState(null);
    const { haptic } = useTelegram();

    useEffect(() => {
        fetch(`${API_URL}/api/internal/stories`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } })
            .then(r => r.json())
            .then(setStories)
            .catch(() => {
                setStories([
                    { id: 1, title: 'Продажи', val: '245к', subtitle: '+12% за сегодня', color: 'bg-emerald-500' },
                    { id: 2, title: 'Биддер', val: 'ON', subtitle: 'Экономия 1500₽', color: 'bg-purple-500' },
                    { id: 3, title: 'Склад', val: 'Low', subtitle: 'SKU 12345 заканчивается', color: 'bg-red-500' }
                ]);
            });
    }, []);

    if (!stories.length) return null;

    return (
        <div className="pt-2 pb-4">
             <div className="flex gap-4 overflow-x-auto px-4 scrollbar-hide">
                {stories.map((s, i) => (
                    <div key={s.id} onClick={() => { haptic('medium'); setActiveIndex(i); }} className="flex flex-col items-center gap-1.5 cursor-pointer active:opacity-70 transition-opacity min-w-[72px]">
                        <div className="w-[72px] h-[72px] rounded-full p-[3px] bg-gradient-to-tr from-yellow-400 via-red-500 to-purple-600">
                            <div className="w-full h-full rounded-full bg-[var(--tg-theme-secondary-bg-color)] border-[3px] border-[var(--tg-theme-secondary-bg-color)] overflow-hidden flex items-center justify-center relative">
                                <div className={`absolute inset-0 opacity-20 ${s.color}`} />
                                <span className="font-bold text-[13px] z-10 text-[var(--tg-theme-text-color)]">{s.val}</span>
                            </div>
                        </div>
                        <span className="text-[11px] font-medium truncate w-full text-center text-[var(--tg-theme-hint-color)]">{s.title}</span>
                    </div>
                ))}
            </div>
            {activeIndex !== null && <StoryViewer stories={stories} initialIndex={activeIndex} onClose={() => setActiveIndex(null)} />}
        </div>
    );
};

const TasksSwipeInterface = () => {
    const { haptic } = useTelegram();
    const [cards, setCards] = useState([
        { id: 1, type: 'price', title: 'Поднять цену +5%', desc: 'SKU 123456 торгуется ниже рынка. Рекомендуемая цена: 2500₽.', color: 'text-emerald-500', icon: <TrendingUp/> },
        { id: 2, type: 'stock', title: 'Срочная поставка', desc: 'SKU 987654. Остаток на 3 дня. Сделайте поставку на Коледино.', color: 'text-orange-500', icon: <Package/> },
        { id: 3, type: 'ad', title: 'Отключить рекламу', desc: 'Кампания "Платья лето" имеет CTR < 1%. Сливает бюджет.', color: 'text-red-500', icon: <Zap/> },
    ]);

    const handleSwipe = (dir, id) => {
        haptic(dir === 'right' ? 'success' : 'medium');
        setCards(prev => prev.filter(c => c.id !== id));
    };

    if (cards.length === 0) return (
        <IOSSection>
            <div className="p-8 flex flex-col items-center justify-center text-center">
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4 text-green-600">
                    <CheckCircle2 size={32} />
                </div>
                <h3 className="text-xl font-bold mb-1">Все задачи решены!</h3>
                <p className="text-[var(--tg-theme-hint-color)] text-sm">Отдыхайте, ваш бизнес под контролем.</p>
            </div>
        </IOSSection>
    );

    const SwipeCard = ({ card, onSwipe }) => {
        const [offset, setOffset] = useState({ x: 0, y: 0 });
        const [isDragging, setIsDragging] = useState(false);
        const startPos = useRef({ x: 0, y: 0 });

        const handleStart = (e) => {
            setIsDragging(true);
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;
            startPos.current = { x: clientX, y: clientY };
        };

        const handleMove = (e) => {
            if (!isDragging) return;
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;
            setOffset({ x: clientX - startPos.current.x, y: clientY - startPos.current.y });
        };

        const handleEnd = () => {
            setIsDragging(false);
            if (offset.x > 100) onSwipe('right', card.id);
            else if (offset.x < -100) onSwipe('left', card.id);
            else setOffset({ x: 0, y: 0 });
        };

        const rotation = offset.x * 0.05;
        const borderColor = offset.x > 50 ? 'border-emerald-500' : offset.x < -50 ? 'border-red-500' : 'border-transparent';

        return (
            <div 
                className={`absolute inset-0 bg-[var(--tg-theme-bg-color)] rounded-2xl shadow-lg border-2 ${borderColor} p-6 flex flex-col justify-between select-none touch-none`}
                style={{ transform: `translate(${offset.x}px, ${offset.y}px) rotate(${rotation}deg)`, transition: isDragging ? 'none' : 'all 0.3s' }}
                onTouchStart={handleStart} onTouchMove={handleMove} onTouchEnd={handleEnd}
                onMouseDown={handleStart} onMouseMove={handleMove} onMouseUp={handleEnd}
            >
                <div>
                    <div className="flex justify-between items-start mb-4">
                        <div className={`p-3 rounded-2xl bg-opacity-10 ${card.color.replace('text-', 'bg-')}`}>
                            {React.cloneElement(card.icon, { className: `w-8 h-8 ${card.color}` })}
                        </div>
                        <span className="bg-gray-100 text-gray-500 px-2 py-1 rounded text-xs font-bold uppercase">Задача</span>
                    </div>
                    <h3 className="text-2xl font-bold mb-2 leading-tight">{card.title}</h3>
                    <p className="text-[var(--tg-theme-hint-color)] leading-relaxed">{card.desc}</p>
                </div>
                <div className="flex gap-4">
                    <div className={`flex-1 py-3 rounded-xl border-2 border-red-100 text-red-500 font-bold flex justify-center items-center gap-2 ${offset.x < -50 ? 'bg-red-50' : ''}`}>
                        <XCircle size={20} /> Скрыть
                    </div>
                    <div className={`flex-1 py-3 rounded-xl bg-emerald-500 text-white font-bold flex justify-center items-center gap-2 shadow-lg shadow-emerald-200 ${offset.x > 50 ? 'scale-105' : ''}`}>
                        <CheckCircle2 size={20} /> Принять
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div className="relative h-[380px] w-full px-4 mb-8">
             {cards.slice().reverse().map((card, index) => {
                 const isTop = index === cards.length - 1;
                 return (
                    <div key={card.id} className={isTop ? 'relative w-full h-full z-10' : 'absolute inset-0 px-4 py-6 scale-95 opacity-50 translate-y-4 z-0'}>
                        {isTop ? <SwipeCard card={card} onSwipe={handleSwipe} /> : (
                            <div className="w-full h-full bg-white rounded-2xl shadow-sm border border-black/5 p-6" />
                        )}
                    </div>
                 );
             })}
        </div>
    );
};

// --- FEATURE MODULES (PORTED LOGIC) ---

const SupplyPage = () => {
  const [products, setProducts] = useState([]);
  const [volume, setVolume] = useState(1000);
  const [calculation, setCalculation] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
      fetch(`${API_URL}/api/finance/products`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } })
          .then(r => r.json()).then(data => { setProducts(data); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const handleCalculate = async () => {
      if (!volume) return;
      const res = await fetch(`${API_URL}/api/internal/transit_calc`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }, body: JSON.stringify({ volume: Number(volume) }) });
      setCalculation(await res.json());
  };

  return (
      <NativePage className="pt-4">
          <div className="px-4 mb-6">
              <div className="bg-gradient-to-r from-orange-400 to-amber-500 p-6 rounded-2xl text-white shadow-lg shadow-orange-200">
                  <h1 className="text-2xl font-black flex items-center gap-2"><Truck className="text-white" /> Supply Chain</h1>
                  <p className="text-sm opacity-90 mt-2">Умное управление поставками (ROP/SS).</p>
              </div>
          </div>
          
          <IOSSection title="Рекомендации к заказу">
              {loading ? <div className="p-8 flex justify-center"><Loader2 className="animate-spin text-orange-500"/></div> : 
               products.filter(p => p.supply?.recommendation > 0).length === 0 ? 
               <div className="p-6 text-center text-gray-400">Всё отлично! Поставок не требуется.</div> :
               products.filter(p => p.supply?.recommendation > 0).map((p, i) => (
                  <IOSCell 
                      key={p.sku}
                      title={`SKU ${p.sku}`}
                      subtitle={`Остаток: ${p.quantity} шт • Продаж: ${p.supply.metrics?.avg_sales}/день`}
                      rightIcon={
                          <div className="text-right">
                              <div className="text-[10px] text-orange-500 font-bold uppercase">Заказать</div>
                              <div className="text-xl font-black">{p.supply.recommendation}</div>
                          </div>
                      }
                      icon={<Package size={16}/>}
                      color="bg-orange-500"
                      isLast={i === products.length - 1}
                  />
               ))
              }
          </IOSSection>

          <IOSSection title="Калькулятор транзита">
              <NativeInput 
                  label="Объем (л)" 
                  value={volume} 
                  onChange={e => setVolume(e.target.value)} 
                  type="number"
                  className="border-b border-black/5"
              />
              <div className="p-4">
                  <NativeButton onClick={handleCalculate} variant="primary">Рассчитать выгоду</NativeButton>
                  {calculation && (
                      <div className="mt-4 bg-gray-50 p-4 rounded-xl border border-black/5 text-sm space-y-2">
                          <div className="flex justify-between"><span className="text-gray-500">Прямая:</span><span className="font-bold">{calculation.direct_cost} ₽</span></div>
                          <div className="flex justify-between"><span className="text-gray-500">Транзит:</span><span className="font-bold text-emerald-600">{calculation.transit_cost} ₽</span></div>
                          <div className={`text-xs font-bold p-2 rounded text-center mt-2 ${calculation.is_profitable ? 'bg-emerald-100 text-emerald-700' : 'bg-orange-100 text-orange-700'}`}>{calculation.recommendation}</div>
                      </div>
                  )}
              </div>
          </IOSSection>
      </NativePage>
  )
}

const BidderPage = () => {
  const [configs, setConfigs] = useState([]);
  const [simLogs, setSimLogs] = useState([]);
  const [activeTab, setActiveTab] = useState('config'); 
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ campaign_id: '', target_position: 5, max_bid: 300, kp: 1.0, ki: 0.1, kd: 0.05, is_active: true });

  useEffect(() => {
     fetch(`${API_URL}/api/bidder/list`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } }).then(r=>r.json()).then(setConfigs);
     fetch(`${API_URL}/api/bidder/simulation`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } }).then(r=>r.json()).then(d => setSimLogs(d.logs));
  }, []);

  const handleSaveConfig = async () => {
      const res = await fetch(`${API_URL}/api/bidder/config`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }, body: JSON.stringify({...editForm, campaign_id: Number(editForm.campaign_id)}) });
      if (res.ok) { setEditingId(null); fetch(`${API_URL}/api/bidder/list`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } }).then(r=>r.json()).then(setConfigs); }
  };

  return (
      <NativePage className="pt-4">
           <div className="px-4 mb-4">
              <div className="bg-gradient-to-r from-purple-600 to-indigo-600 p-6 rounded-2xl text-white shadow-lg shadow-purple-200 mb-6">
                  <h1 className="text-2xl font-black flex items-center gap-2"><Target className="text-white" /> Автобиддер</h1>
                  <p className="text-sm opacity-90 mt-2">PID-регулятор ставок. Защита бюджета.</p>
              </div>
              <SegmentedControl options={[{id: 'config', label: 'Настройки'}, {id: 'sim', label: 'Логи (Live)'}]} active={activeTab} onChange={setActiveTab} />
          </div>

          {activeTab === 'config' ? (
              <>
                  <div className="px-4 mb-4">
                      <NativeButton onClick={() => setEditingId('new')}><Plus size={20}/> Добавить кампанию</NativeButton>
                  </div>
                  <IOSSection title="Кампании">
                      {configs.map((c, i) => (
                          <IOSCell 
                              key={c.id} 
                              title={`ID ${c.campaign_id}`} 
                              subtitle={`Target: #${c.target_position} • Max: ${c.max_bid}₽`}
                              value={c.is_active ? 'ON' : 'OFF'}
                              onClick={() => { setEditingId(c.id); setEditForm(c); }}
                              icon={<Target size={16}/>}
                              color="bg-purple-500"
                              isLast={i === configs.length - 1}
                          />
                      ))}
                  </IOSSection>
              </>
          ) : (
              <IOSSection title="Лог операций">
                  {simLogs.map((l, i) => (
                      <div key={i} className="px-4 py-2 border-b border-black/5 last:border-0 text-xs flex gap-2">
                          <span className="font-bold text-gray-400 whitespace-nowrap">{l.time}</span>
                          <span className="text-gray-700">{l.msg}</span>
                      </div>
                  ))}
              </IOSSection>
          )}

          <NativeModal isOpen={!!editingId} onClose={() => setEditingId(null)} title={editingId === 'new' ? 'Новая кампания' : 'Редактирование'}>
              <div className="space-y-4">
                  <IOSSection>
                      <NativeInput label="ID Кампании" value={editForm.campaign_id} onChange={e=>setEditForm({...editForm, campaign_id: e.target.value})} type="number" className="border-b border-black/5"/>
                      <NativeInput label="Целевая поз." value={editForm.target_position} onChange={e=>setEditForm({...editForm, target_position: Number(e.target.value)})} type="number" className="border-b border-black/5"/>
                      <NativeInput label="Макс. ставка" value={editForm.max_bid} onChange={e=>setEditForm({...editForm, max_bid: Number(e.target.value)})} type="number" />
                  </IOSSection>
                  <IOSSection title="PID Коэффициенты">
                      <div className="flex gap-2 p-4">
                          <input placeholder="Kp" value={editForm.kp} onChange={e=>setEditForm({...editForm, kp: e.target.value})} className="flex-1 bg-gray-100 p-2 rounded text-center"/>
                          <input placeholder="Ki" value={editForm.ki} onChange={e=>setEditForm({...editForm, ki: e.target.value})} className="flex-1 bg-gray-100 p-2 rounded text-center"/>
                          <input placeholder="Kd" value={editForm.kd} onChange={e=>setEditForm({...editForm, kd: e.target.value})} className="flex-1 bg-gray-100 p-2 rounded text-center"/>
                      </div>
                  </IOSSection>
                  <div className="flex items-center justify-between px-4 py-3 bg-white rounded-xl mb-4">
                      <span>Активен</span>
                      <input type="checkbox" checked={editForm.is_active} onChange={e=>setEditForm({...editForm, is_active: e.target.checked})} className="w-6 h-6 accent-purple-600"/>
                  </div>
                  <NativeButton onClick={handleSaveConfig}>Сохранить</NativeButton>
              </div>
          </NativeModal>
      </NativePage>
  );
}

const FinancePage = ({ onNavigate }) => {
  const [products, setProducts] = useState([]);
  const [editingCost, setEditingCost] = useState(null);
  
  const loadData = () => {
     fetch(`${API_URL}/api/finance/products`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } })
        .then(r => r.json()).then(setProducts);
  };
  useEffect(() => { loadData(); }, []);

  const handleUpdateCost = async (sku, formData) => {
      await fetch(`${API_URL}/api/finance/cost/${sku}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }, body: JSON.stringify(formData) });
      setEditingCost(null); loadData();
  };

  const CostEditContent = ({ item, onSave }) => {
      const [form, setForm] = useState({ 
          cost_price: item.input_data?.cost_price || 0, 
          logistics: item.input_data?.logistics_fwd || 50, 
          tax: item.input_data?.tax || 6, 
          adv: item.input_data?.adv || 0 
      });
      return (
          <div className="space-y-4">
              <IOSSection>
                   <NativeInput label="Себестоимость" value={form.cost_price} onChange={e=>setForm({...form, cost_price: Number(e.target.value)})} type="number" rightElement="₽" className="border-b border-black/5"/>
                   <NativeInput label="Логистика" value={form.logistics} onChange={e=>setForm({...form, logistics: Number(e.target.value)})} type="number" rightElement="₽" className="border-b border-black/5"/>
                   <NativeInput label="Налог" value={form.tax} onChange={e=>setForm({...form, tax: Number(e.target.value)})} type="number" rightElement="%" className="border-b border-black/5"/>
                   <NativeInput label="Реклама (на шт)" value={form.adv} onChange={e=>setForm({...form, adv: Number(e.target.value)})} type="number" rightElement="₽"/>
              </IOSSection>
              <NativeButton onClick={() => onSave(item.sku, { ...form, logistics_fwd: form.logistics })}>Сохранить</NativeButton>
          </div>
      );
  };

  return (
      <NativePage className="pt-4">
          <div className="px-4 flex justify-between items-center mb-6">
               <h1 className="text-2xl font-black flex items-center gap-2 text-slate-800"><PieChart className="text-indigo-600"/> P&L Отчет</h1>
               <button onClick={loadData} className="p-2 bg-white rounded-full shadow text-gray-400"><RefreshCw size={20}/></button>
          </div>

          <IOSSection>
              {products.map((item, i) => (
                  <div key={item.sku} className={`p-4 bg-[var(--tg-theme-bg-color)] ${i !== products.length - 1 ? 'border-b border-black/5' : ''}`}>
                      <div className="flex justify-between items-start mb-3">
                          <div>
                              <div className="font-bold text-[17px]">SKU {item.sku}</div>
                              <div className="text-[13px] text-gray-400 mt-1">Остаток: {item.quantity} шт</div>
                          </div>
                          <button onClick={() => setEditingCost(item)} className="p-2 bg-indigo-50 text-indigo-600 rounded-lg"><Calculator size={18}/></button>
                      </div>
                      <div className="grid grid-cols-2 gap-2 mb-3">
                          <div className="bg-gray-50 p-2 rounded-lg">
                              <div className="text-[10px] uppercase text-gray-400 font-bold">Gross Sales</div>
                              <div className="font-bold">{item.economics.gross_sales} ₽</div>
                          </div>
                          <div className={`p-2 rounded-lg ${item.economics.is_toxic ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
                              <div className="text-[10px] uppercase font-bold">Чистая прибыль</div>
                              <div className="font-bold">{item.economics.cm3} ₽</div>
                          </div>
                      </div>
                      <div className="flex gap-2">
                           <span className={`text-[10px] font-bold px-2 py-1 rounded-md ${item.economics.roi > 30 ? 'bg-emerald-100 text-emerald-700' : 'bg-orange-100 text-orange-700'}`}>ROI: {item.economics.roi}%</span>
                      </div>
                  </div>
              ))}
          </IOSSection>
          <NativeModal isOpen={!!editingCost} onClose={() => setEditingCost(null)} title="Unit-экономика">
               {editingCost && <CostEditContent item={editingCost} onSave={handleUpdateCost} />}
          </NativeModal>
      </NativePage>
  );
}

const MonitorPage = () => {
    const [list, setList] = useState([]);
    const [historyItem, setHistoryItem] = useState(null);
    const [downloading, setDownloading] = useState(false);

    const loadList = () => fetch(`${API_URL}/api/monitor/list`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } }).then(r=>r.json()).then(setList);
    useEffect(() => { loadList(); }, []);

    const loadHistory = (sku) => {
        fetch(`${API_URL}/api/monitor/history/${sku}`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } }).then(r=>r.json()).then(setHistoryItem);
    }

    const downloadPDF = async (sku) => {
        setDownloading(true);
        try {
            const res = await fetch(`${API_URL}/api/report/pdf/${sku}`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } });
            if (res.status === 403) { alert("Нужен тариф PRO"); return; }
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a'); a.href = url; a.download = `report_${sku}.pdf`; document.body.appendChild(a); a.click(); a.remove();
        } catch(e) { alert("Ошибка загрузки"); } finally { setDownloading(false); }
    }

    const handleDelete = async (sku) => {
        if(confirm("Удалить?")) {
            await fetch(`${API_URL}/api/monitor/delete/${sku}`, { method: 'DELETE', headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } });
            loadList();
        }
    }

    return (
        <NativePage className="pt-4">
             <div className="px-4 mb-6 flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold">Конкуренты</h1>
                    <p className="text-gray-400 text-sm">Внешний мониторинг цен</p>
                </div>
                <button onClick={loadList} className="p-2 bg-white rounded-full shadow text-gray-400"><RefreshCw size={20}/></button>
            </div>
            
            <IOSSection>
                {list.length === 0 ? <div className="p-6 text-center text-gray-400">Список пуст</div> : list.map((item, i) => (
                    <IOSCell
                        key={item.id}
                        title={item.name || `SKU ${item.sku}`}
                        subtitle={`${item.brand || 'WB'} • ${item.sku}`}
                        value={`${item.prices?.[0]?.wallet_price || 0} ₽`}
                        onClick={() => loadHistory(item.sku)}
                        rightIcon={<button onClick={(e) => { e.stopPropagation(); handleDelete(item.sku); }} className="p-2 text-gray-300"><Trash2 size={16}/></button>}
                        icon={<BarChart3 size={16}/>}
                        color="bg-indigo-500"
                        isLast={i === list.length - 1}
                    />
                ))}
            </IOSSection>

            <NativeModal isOpen={!!historyItem} onClose={() => setHistoryItem(null)} title="История цены">
                {historyItem && (
                    <div className="space-y-4">
                        <div className="h-64 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={historyItem.history}>
                                    <defs><linearGradient id="colorWallet" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#4f46e5" stopOpacity={0.3}/><stop offset="95%" stopColor="#4f46e5" stopOpacity={0}/></linearGradient></defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                    <XAxis dataKey="date" tick={{fontSize: 10}} tickLine={false} axisLine={false} />
                                    <Tooltip />
                                    <Area type="monotone" dataKey="wallet" stroke="#4f46e5" strokeWidth={3} fill="url(#colorWallet)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                        <NativeButton onClick={() => downloadPDF(historyItem.sku)} loading={downloading} variant="secondary">
                            <FileDown size={18}/> Скачать PDF отчет
                        </NativeButton>
                    </div>
                )}
            </NativeModal>
        </NativePage>
    );
};

const SeoGeneratorPage = () => {
    const [step, setStep] = useState(1);
    const [sku, setSku] = useState('');
    const [keywords, setKeywords] = useState([]);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [tone, setTone] = useState('Продающий');

    const fetchKeywords = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/seo/parse/${sku}`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } });
            const data = await res.json();
            setKeywords(data.keywords || []); setStep(2);
        } catch(e) { alert("Ошибка парсинга"); } finally { setLoading(false); }
    };

    const generate = async () => {
        setLoading(true);
        const res = await fetch(`${API_URL}/api/seo/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }, body: JSON.stringify({ sku: Number(sku), keywords, tone, title_len: 100, desc_len: 1000 }) });
        const data = await res.json();
        // Polling logic simplified for brevity
        setTimeout(async () => {
            const sRes = await fetch(`${API_URL}/api/ai/result/${data.task_id}`);
            const sData = await sRes.json();
            if (sData.status === 'SUCCESS') { setResult(sData.data.generated_content); setStep(3); }
            setLoading(false);
        }, 5000); 
    };

    return (
        <NativePage className="pt-4">
             <div className="px-4 mb-6">
                 <div className="bg-gradient-to-r from-orange-500 to-pink-500 p-6 rounded-2xl text-white shadow-xl shadow-pink-200">
                     <h1 className="text-2xl font-black flex items-center gap-2"><Wand2 className="text-white" /> SEO Gen</h1>
                     <p className="text-sm opacity-90 mt-2">Генератор описаний на базе AI</p>
                 </div>
             </div>

             {step === 1 && (
                 <IOSSection>
                     <NativeInput placeholder="Артикул WB (SKU)" value={sku} onChange={e => setSku(e.target.value)} type="number" className="border-b border-black/5"/>
                     <div className="p-4">
                        <NativeButton onClick={fetchKeywords} loading={loading}>Получить ключи</NativeButton>
                     </div>
                 </IOSSection>
             )}

             {step === 2 && (
                 <div className="space-y-4">
                     <IOSSection title="Ключевые слова">
                         <div className="p-4 flex flex-wrap gap-2">
                             {keywords.map(k => <span key={k} className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm">{k}</span>)}
                         </div>
                     </IOSSection>
                     <IOSSection title="Настроение">
                         <div className="p-4">
                            <SegmentedControl options={['Продающий', 'Дерзкий', 'Info'].map(t=>({id:t, label:t}))} active={tone} onChange={setTone} />
                         </div>
                     </IOSSection>
                     <div className="px-4">
                        <NativeButton onClick={generate} loading={loading} variant="primary"><Sparkles size={18}/> Генерировать</NativeButton>
                     </div>
                 </div>
             )}

             {step === 3 && result && (
                 <IOSSection title="Результат">
                     <div className="p-4 space-y-4">
                         <div>
                             <div className="text-xs uppercase text-gray-400 font-bold mb-1">Заголовок</div>
                             <div className="bg-gray-50 p-3 rounded-xl select-all">{result.title}</div>
                         </div>
                         <div>
                             <div className="text-xs uppercase text-gray-400 font-bold mb-1">Описание</div>
                             <div className="bg-gray-50 p-3 rounded-xl text-sm leading-relaxed h-64 overflow-y-auto select-all">{result.description}</div>
                         </div>
                         <NativeButton onClick={() => setStep(1)} variant="secondary">Новый поиск</NativeButton>
                     </div>
                 </IOSSection>
             )}
        </NativePage>
    );
};

const ScannerPage = ({ onNavigate }) => {
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');

    const handleScan = async () => {
        if (!sku) return;
        setLoading(true); setStatus('Запуск задачи...');
        try {
            const res = await fetch(`${API_URL}/api/monitor/add/${sku}`, { method: 'POST', headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } });
            if (res.status === 403) { alert("Лимит!"); setLoading(false); return; }
            const data = await res.json();
            
            let attempts = 0;
            const poll = setInterval(async () => {
                attempts++;
                const sRes = await fetch(`${API_URL}/api/monitor/status/${data.task_id}`);
                const sData = await sRes.json();
                if (sData.info) setStatus(sData.info);
                if (sData.status === 'SUCCESS' || attempts > 20) {
                    clearInterval(poll); setLoading(false); onNavigate('monitor');
                }
            }, 2000);
        } catch(e) { setLoading(false); }
    };

    return (
        <NativePage className="flex flex-col items-center justify-center h-[80vh]">
            <div className="w-full max-w-sm px-4">
                <div className="bg-white p-8 rounded-[40px] shadow-2xl border border-slate-100 text-center">
                    <div className="w-16 h-16 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-6"><Search size={32} /></div>
                    <h2 className="text-2xl font-black mb-6">Добавить товар</h2>
                    <input 
                        value={sku} onChange={e => setSku(e.target.value)} 
                        placeholder="SKU" 
                        type="number"
                        className="w-full bg-slate-50 border-none rounded-2xl p-5 text-center text-2xl font-black outline-none mb-4"
                    />
                    <NativeButton onClick={handleScan} loading={loading} className="py-4 text-lg bg-black text-white">{loading ? status : 'Отслеживать'}</NativeButton>
                </div>
            </div>
        </NativePage>
    );
};

const AIAnalysisPage = () => {
    const [sku, setSku] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);

    const analyze = async () => {
        if(!sku) return;
        setLoading(true); setResult(null);
        try {
            const res = await fetch(`${API_URL}/api/ai/analyze/${sku}`, { method: 'POST', headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } });
            const data = await res.json();
            setTimeout(async () => {
                const sRes = await fetch(`${API_URL}/api/ai/result/${data.task_id}`);
                const sData = await sRes.json();
                if (sData.status === 'SUCCESS') setResult(sData.data);
                setLoading(false);
            }, 6000);
        } catch { setLoading(false); }
    };

    return (
        <NativePage className="pt-4">
            <div className="px-4 mb-6">
                <div className="bg-gradient-to-br from-violet-600 to-fuchsia-600 p-6 rounded-2xl text-white shadow-xl shadow-fuchsia-200">
                    <h1 className="text-2xl font-black flex items-center gap-2"><Sparkles className="text-yellow-300" /> AI Стратег</h1>
                </div>
            </div>
            <IOSSection>
                <NativeInput placeholder="Артикул" value={sku} onChange={e=>setSku(e.target.value)} type="number" className="border-b border-black/5"/>
                <div className="p-4">
                    <NativeButton onClick={analyze} loading={loading} className="bg-violet-600 text-white">Анализировать</NativeButton>
                </div>
            </IOSSection>

            {result && (
                <div className="px-4 space-y-4 animate-in fade-in slide-in-from-bottom-8">
                     <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex gap-4">
                         {result.image && <img src={result.image} className="w-16 h-20 object-cover rounded-lg bg-slate-100" />}
                         <div>
                             <div className="flex items-center gap-1 text-amber-500 font-black mb-1"><Star size={16} fill="currentColor" /> {result.rating}</div>
                             <div className="font-bold">{result.reviews_count} отзывов</div>
                         </div>
                     </div>
                     <IOSSection title="ТОП Жалоб" className="!bg-red-50 border-red-100">
                         {result.ai_analysis.flaws?.map((f, i) => (
                             <div key={i} className="px-4 py-2 border-b border-red-100 last:border-0 text-sm font-medium text-slate-700">⛔ {f}</div>
                         ))}
                     </IOSSection>
                     <IOSSection title="Стратегия" className="!bg-indigo-50 border-indigo-100">
                         {result.ai_analysis.strategy?.map((s, i) => (
                             <div key={i} className="px-4 py-2 border-b border-indigo-100 last:border-0 text-sm font-medium text-slate-700">✅ {s}</div>
                         ))}
                     </IOSSection>
                </div>
            )}
        </NativePage>
    );
};

const ProfilePage = ({ onNavigate }) => {
    const [user, setUser] = useState(null);
    const [wbToken, setWbToken] = useState('');
    const [tariffs, setTariffs] = useState([]);

    useEffect(() => {
        const h = { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" };
        fetch(`${API_URL}/api/user/me`, { headers: h }).then(r=>r.json()).then(u => { setUser(u); if(u.has_wb_token) setWbToken(u.wb_token_preview); });
        fetch(`${API_URL}/api/user/tariffs`, { headers: h }).then(r=>r.json()).then(setTariffs);
    }, []);

    const saveToken = async () => {
        await fetch(`${API_URL}/api/user/token`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || "" }, body: JSON.stringify({token: wbToken}) });
        alert("Токен сохранен");
    };

    const payStars = async (plan) => {
        if (!plan.stars) return;
        const res = await fetch(`${API_URL}/api/payment/stars_link`, { method: 'POST', headers: {'Content-Type': 'application/json', 'X-TG-Data': window.Telegram?.WebApp?.initData || ""}, body: JSON.stringify({plan_id: plan.id, amount: plan.stars}) });
        const d = await res.json();
        if (d.invoice_link) window.Telegram?.WebApp?.openInvoice(d.invoice_link);
    };

    return (
        <NativePage className="pt-4">
            <div className="px-4 flex items-center gap-4 mb-8">
                <div className="w-20 h-20 rounded-full bg-gray-200 flex items-center justify-center text-3xl font-bold text-gray-400">{user?.name?.[0] || 'U'}</div>
                <div>
                    <h2 className="text-2xl font-bold">{user?.name || 'User'}</h2>
                    <p className="text-gray-400">@{user?.username}</p>
                    <div className="mt-2 inline-flex px-2 py-0.5 rounded-md bg-blue-100 text-blue-700 text-xs font-bold uppercase">{user?.plan || 'Free'} Plan</div>
                </div>
            </div>

            <IOSSection title="WB API">
                <NativeInput 
                    value={wbToken} onChange={e=>setWbToken(e.target.value)} 
                    placeholder="Токен..." 
                    rightElement={user?.has_wb_token && <X size={20} className="text-red-400" onClick={() => setWbToken('')}/>}
                />
                {!user?.has_wb_token && <div className="p-4"><NativeButton onClick={saveToken}>Сохранить</NativeButton></div>}
            </IOSSection>

            <IOSSection title="Тарифы (Stars)">
                {tariffs.map(plan => (
                    <div key={plan.id} className="p-4 border-b border-black/5 last:border-0">
                        <div className="flex justify-between items-center mb-2">
                             <span className="font-bold text-lg">{plan.name}</span>
                             <span className="font-black text-xl">{plan.price}</span>
                        </div>
                        <ul className="text-sm text-gray-500 space-y-1 mb-4">
                            {plan.features.map((f,i) => <li key={i}>• {f}</li>)}
                        </ul>
                        <NativeButton onClick={() => payStars(plan)} disabled={plan.current} variant={plan.current ? 'secondary' : 'primary'} size="sm">
                            {plan.current ? 'Текущий' : `Оплатить ${plan.stars} Stars`}
                        </NativeButton>
                    </div>
                ))}
            </IOSSection>

            {user?.is_admin && <div className="px-4"><NativeButton variant="secondary" onClick={() => onNavigate('admin')}><ShieldCheck size={18}/> Админ-панель</NativeButton></div>}
        </NativePage>
    );
};

const AdminPage = ({ onBack }) => {
    const [stats, setStats] = useState(null);
    useEffect(() => { fetch(`${API_URL}/api/admin/stats`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } }).then(r=>r.json()).then(setStats); }, []);

    return (
        <NativePage className="pt-4">
            <div className="px-4 mb-4 flex items-center gap-2">
                <button onClick={onBack} className="p-2 bg-white rounded-full shadow"><ChevronLeft size={20}/></button>
                <h1 className="text-2xl font-bold">Admin</h1>
            </div>
            <IOSSection>
                <IOSCell title="Пользователей" value={stats?.total_users || '-'} />
                <IOSCell title="Товаров" value={stats?.total_items_monitored || '-'} />
                <IOSCell title="Сервер" value={stats?.server_status || '-'} color="bg-green-500" />
            </IOSSection>
        </NativePage>
    );
}

// --- MAIN DASHBOARD ---

const Dashboard = ({ onNavigate, user }) => {
    const [stats, setStats] = useState(null);
    useEffect(() => {
        if(user?.has_wb_token) fetch(`${API_URL}/api/internal/stats`, { headers: { 'X-TG-Data': window.Telegram?.WebApp?.initData || "" } }).then(r=>r.json()).then(setStats);
    }, [user]);

    return (
        <NativePage>
            <StoriesRow />
            <div className="px-4 mb-6">
                <div className="bg-gradient-to-br from-[#007aff] to-[#00c6ff] rounded-2xl p-6 text-white shadow-lg shadow-blue-200/50 relative overflow-hidden">
                    <div className="relative z-10">
                        <div className="flex justify-between items-start mb-4">
                            <div>
                                <h1 className="text-3xl font-bold tracking-tight">{stats?.orders_today?.sum ? stats.orders_today.sum.toLocaleString() : '0'} ₽</h1>
                                <p className="text-blue-100 text-sm font-medium mt-1">Продажи сегодня</p>
                            </div>
                            <div className="p-2 bg-white/20 backdrop-blur rounded-lg"><BarChart3 size={20} className="text-white" /></div>
                        </div>
                        <div className="flex gap-4">
                            <div className="px-3 py-1.5 bg-white/20 rounded-lg text-xs font-semibold backdrop-blur-sm">{stats?.orders_today?.count || 0} заказов</div>
                            <div className="px-3 py-1.5 bg-white/20 rounded-lg text-xs font-semibold backdrop-blur-sm">{stats?.stocks?.total_quantity || 0} остаток</div>
                        </div>
                    </div>
                </div>
            </div>

            <IOSSection title="Задачи">
                <TasksSwipeInterface />
            </IOSSection>

            <IOSSection title="Инструменты">
                <div className="grid grid-cols-2 gap-[1px] bg-black/5">
                     <div onClick={() => onNavigate('finance')} className="bg-[var(--tg-theme-bg-color)] p-4 flex flex-col items-center gap-2 active:bg-gray-50 transition-colors cursor-pointer">
                        <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center"><PieChart size={20} /></div>
                        <span className="text-[13px] font-medium">Unit-экономика</span>
                    </div>
                    <div onClick={() => onNavigate('supply')} className="bg-[var(--tg-theme-bg-color)] p-4 flex flex-col items-center gap-2 active:bg-gray-50 transition-colors cursor-pointer">
                        <div className="w-10 h-10 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center"><Truck size={20} /></div>
                        <span className="text-[13px] font-medium">Поставки</span>
                    </div>
                    <div onClick={() => onNavigate('bidder')} className="bg-[var(--tg-theme-bg-color)] p-4 flex flex-col items-center gap-2 active:bg-gray-50 transition-colors cursor-pointer">
                        <div className="w-10 h-10 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center"><Target size={20} /></div>
                        <span className="text-[13px] font-medium">Биддер</span>
                    </div>
                     <div onClick={() => onNavigate('seo')} className="bg-[var(--tg-theme-bg-color)] p-4 flex flex-col items-center gap-2 active:bg-gray-50 transition-colors cursor-pointer">
                        <div className="w-10 h-10 rounded-full bg-pink-100 text-pink-600 flex items-center justify-center"><Wand2 size={20} /></div>
                        <span className="text-[13px] font-medium">SEO Gen</span>
                    </div>
                </div>
            </IOSSection>
        </NativePage>
    );
};

// --- APP ROOT & NAVIGATION ---

const TabBar = ({ active, setTab }) => {
    const { haptic } = useTelegram();
    const tabs = [
        { id: 'home', icon: <LayoutGrid size={24} />, label: 'Главная' },
        { id: 'monitor', icon: <BarChart3 size={24} />, label: 'Монитор' },
        { id: 'scan', icon: <Plus size={32} />, label: '', special: true },
        { id: 'ai', icon: <Brain size={24} />, label: 'ИИ' },
        { id: 'profile', icon: <User size={24} />, label: 'Профиль' },
    ];

    return (
        <div className="fixed bottom-0 left-0 right-0 z-40">
            <div className="absolute inset-0 bg-white/80 backdrop-blur-xl border-t border-black/5" style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color, rgba(255,255,255,0.85))' }} />
            <div className="relative flex justify-between items-end pb-[env(safe-area-inset-bottom,20px)] pt-2 px-2">
                {tabs.map(tab => {
                    const isActive = active === tab.id;
                    if (tab.special) {
                        return (
                            <div key={tab.id} className="w-[20%] flex justify-center relative -top-5">
                                <button onClick={() => { haptic('medium'); setTab('scanner'); }} className="w-14 h-14 rounded-full bg-[#007aff] text-white flex items-center justify-center shadow-lg shadow-blue-500/40 active:scale-95 transition-transform">{tab.icon}</button>
                            </div>
                        );
                    }
                    return (
                        <button key={tab.id} onClick={() => { haptic('light'); setTab(tab.id); }} className={`w-[20%] flex flex-col items-center gap-1 transition-colors ${isActive ? 'text-[#007aff]' : 'text-[#8e8e93]'}`}>
                            {tab.icon}
                            <span className="text-[10px] font-medium">{tab.label}</span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

export default function App() {
    const [activeTab, setActiveTab] = useState('home');
    const [user, setUser] = useState(null);
    const { theme } = useTelegram();

    useEffect(() => {
         fetch(`${API_URL}/api/user/me`, { headers: {'X-TG-Data': window.Telegram?.WebApp?.initData || ""} }).then(r => r.json()).then(setUser).catch(console.error); 
    }, [activeTab]);

    const renderContent = () => {
        switch(activeTab) {
            case 'home': return <Dashboard onNavigate={setActiveTab} user={user} />;
            case 'monitor': return <MonitorPage />;
            case 'profile': return <ProfilePage onNavigate={setActiveTab} />;
            case 'scanner': return <ScannerPage onNavigate={setActiveTab} />;
            case 'finance': return <FinancePage onNavigate={setActiveTab} />;
            case 'bidder': return <BidderPage />;
            case 'supply': return <SupplyPage />;
            case 'seo': return <SeoGeneratorPage />;
            case 'ai': return <AIAnalysisPage />;
            case 'admin': return <AdminPage onBack={() => setActiveTab('profile')} />;
            default: return <Dashboard onNavigate={setActiveTab} user={user} />;
        }
    };

    return (
        <div className="antialiased min-h-screen font-sans selection:bg-blue-100 selection:text-blue-900" style={{ 
                '--tg-theme-bg-color': theme.bg,
                '--tg-theme-text-color': theme.text,
                '--tg-theme-hint-color': theme.hint,
                '--tg-theme-button-color': theme.button,
                '--tg-theme-button-text-color': theme.buttonText,
                '--tg-theme-secondary-bg-color': theme.secondaryBg,
            }}>
            {renderContent()}
            <TabBar active={activeTab} setTab={setActiveTab} />
        </div>
    );
}