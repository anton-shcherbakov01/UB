import React from 'react';
import { Loader2, Info, CheckCircle2 } from 'lucide-react';

const AbcXyzMatrix = ({ data, loading, onCellClick, selectedGroup }) => {
    if (loading) return <div className="p-10 flex justify-center"><Loader2 className="animate-spin text-indigo-600"/></div>;
    if (!data || !data.summary) return null;

    const { summary } = data;

    // Цветовая схема для ячеек
    const getCellColor = (group) => {
        const colors = {
            'AX': 'bg-emerald-100 border-emerald-200 text-emerald-800',
            'AY': 'bg-emerald-50 border-emerald-100 text-emerald-700',
            'AZ': 'bg-yellow-50 border-yellow-100 text-yellow-700',
            'BX': 'bg-emerald-50 border-emerald-100 text-emerald-700',
            'BY': 'bg-slate-50 border-slate-100 text-slate-600',
            'BZ': 'bg-yellow-50 border-yellow-100 text-yellow-700',
            'CX': 'bg-slate-50 border-slate-100 text-slate-500',
            'CY': 'bg-red-50 border-red-100 text-red-600',
            'CZ': 'bg-red-100 border-red-200 text-red-800',
        };
        return colors[group] || 'bg-gray-50 border-gray-100 text-gray-500';
    };

    const descriptions = {
        'A': 'Высокая выручка',
        'B': 'Средняя выручка',
        'C': 'Низкая выручка',
        'X': 'Стабильный спрос',
        'Y': 'Колебания',
        'Z': 'Случайный спрос'
    };

    return (
        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 relative overflow-visible z-10">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <h3 className="font-bold text-lg text-slate-800">Матрица ABC/XYZ</h3>
                    {selectedGroup && (
                        <span className="bg-indigo-600 text-white text-[10px] px-2 py-0.5 rounded-full font-bold animate-in fade-in">
                            Фильтр: {selectedGroup}
                        </span>
                    )}
                </div>
                
                {/* --- ОБНОВЛЕННАЯ ПОДСКАЗКА --- */}
                <div className="group relative z-50">
                    <Info size={18} className="text-slate-400 cursor-help hover:text-indigo-500 transition-colors"/>
                    
                    {/* Контейнер тултипа */}
                    <div className="absolute right-0 top-8 w-[340px] bg-slate-800 text-white rounded-xl p-4 shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 transform origin-top-right translate-y-2 group-hover:translate-y-0">
                        {/* Стрелочка сверху */}
                        <div className="absolute -top-1.5 right-1 w-3 h-3 bg-slate-800 rotate-45"></div>
                        
                        <h4 className="font-bold text-sm mb-3 text-slate-100">Как читать матрицу?</h4>
                        
                        <div className="grid grid-cols-2 gap-4 text-xs">
                            {/* Колонка ABC */}
                            <div>
                                <div className="font-bold text-emerald-400 mb-1 border-b border-slate-600 pb-1">ABC (Выручка)</div>
                                <ul className="space-y-1.5 text-slate-300">
                                    <li><b className="text-white">A</b> — Лидеры (80% денег)</li>
                                    <li><b className="text-white">B</b> — Середняки (15%)</li>
                                    <li><b className="text-white">C</b> — Аутсайдеры (5%)</li>
                                </ul>
                            </div>
                            
                            {/* Колонка XYZ */}
                            <div>
                                <div className="font-bold text-indigo-400 mb-1 border-b border-slate-600 pb-1">XYZ (Спрос)</div>
                                <ul className="space-y-1.5 text-slate-300">
                                    <li><b className="text-white">X</b> — Стабильно</li>
                                    <li><b className="text-white">Y</b> — Сезонно/Скачки</li>
                                    <li><b className="text-white">Z</b> — Хаотично</li>
                                </ul>
                            </div>
                        </div>

                        <div className="mt-3 pt-2 border-t border-slate-600 text-[10px] text-slate-400 italic">
                            💡 Кликните на любую ячейку (например, <span className="text-emerald-400">AX</span>), чтобы увидеть список товаров этой группы.
                        </div>
                    </div>
                </div>
                {/* ----------------------------- */}

            </div>

            <div className="grid grid-cols-[auto_1fr_1fr_1fr] gap-2 select-none relative z-0">
                {/* Заголовки столбцов (XYZ) */}
                <div className="p-2"></div>
                {['X', 'Y', 'Z'].map(axis => (
                    <div key={axis} className="text-center pb-2">
                        <div className="font-bold text-slate-700 text-sm">Группа {axis}</div>
                        <div className="text-[10px] text-slate-400">{descriptions[axis]}</div>
                    </div>
                ))}

                {/* Ряды (ABC) */}
                {['A', 'B', 'C'].map(row => (
                    <React.Fragment key={row}>
                        {/* Заголовок ряда */}
                        <div className="flex flex-col justify-center pr-2">
                            <div className="font-bold text-slate-700 text-sm">Группа {row}</div>
                            <div className="text-[10px] text-slate-400 max-w-[80px] leading-tight">{descriptions[row]}</div>
                        </div>

                        {/* Ячейки матрицы */}
                        {['X', 'Y', 'Z'].map(col => {
                            const group = `${row}${col}`;
                            const count = summary[group] || 0;
                            
                            const isSelected = selectedGroup === group;
                            const isDimmed = selectedGroup && !isSelected;

                            return (
                                <div 
                                    key={group} 
                                    onClick={() => onCellClick && onCellClick(group)}
                                    className={`
                                        relative h-24 rounded-xl border-2 flex flex-col items-center justify-center 
                                        transition-all duration-300 cursor-pointer
                                        ${getCellColor(group)}
                                        ${isSelected 
                                            ? 'ring-4 ring-indigo-500 ring-offset-2 scale-105 z-10 shadow-xl border-indigo-500' 
                                            : 'hover:scale-105 hover:shadow-md'
                                        }
                                        ${isDimmed ? 'opacity-30 grayscale-[0.5] scale-95' : ''}
                                    `}
                                >
                                    {isSelected && (
                                        <div className="absolute -top-2 -right-2 bg-indigo-600 text-white rounded-full p-1 shadow-sm animate-in zoom-in">
                                            <CheckCircle2 size={12} strokeWidth={4} />
                                        </div>
                                    )}
                                    
                                    <div className="text-3xl font-black">{count}</div>
                                    <div className="text-[9px] font-bold uppercase opacity-60">Товаров</div>
                                    
                                    <div className="absolute top-2 left-2 text-[10px] font-bold opacity-30">{group}</div>
                                </div>
                            );
                        })}
                    </React.Fragment>
                ))}
            </div>
            
            <div className="mt-6 p-4 bg-slate-50 rounded-xl text-xs text-slate-500 flex flex-wrap gap-4 justify-center sm:justify-start">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-emerald-100 border border-emerald-200 rounded-full"></div>
                    <span>Драйверы роста</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-yellow-50 border border-yellow-100 rounded-full"></div>
                    <span>Требуют внимания</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-red-100 border border-red-200 rounded-full"></div>
                    <span>Кандидаты на вывод</span>
                </div>
            </div>
        </div>
    );
};

export default AbcXyzMatrix;