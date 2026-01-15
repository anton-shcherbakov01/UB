import React from 'react';
import { Loader2, Info, CheckCircle2 } from 'lucide-react';

const AbcXyzMatrix = ({ data, loading, onCellClick, selectedGroup }) => {
    if (loading) return <div className="p-10 flex justify-center"><Loader2 className="animate-spin text-indigo-600"/></div>;
    if (!data || !data.summary) return null;

    const { summary } = data;

    // Цветовая схема для ячеек
    const getCellColor = (group) => {
        const colors = {
            'AX': 'bg-emerald-100 border-emerald-200 text-emerald-800', // Лучшие
            'AY': 'bg-emerald-50 border-emerald-100 text-emerald-700',
            'AZ': 'bg-yellow-50 border-yellow-100 text-yellow-700',
            'BX': 'bg-emerald-50 border-emerald-100 text-emerald-700',
            'BY': 'bg-slate-50 border-slate-100 text-slate-600',
            'BZ': 'bg-yellow-50 border-yellow-100 text-yellow-700',
            'CX': 'bg-slate-50 border-slate-100 text-slate-500',
            'CY': 'bg-red-50 border-red-100 text-red-600',
            'CZ': 'bg-red-100 border-red-200 text-red-800', // Худшие
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
        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 relative overflow-hidden">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <h3 className="font-bold text-lg text-slate-800">Матрица ABC/XYZ</h3>
                    {selectedGroup && (
                        <span className="bg-indigo-600 text-white text-[10px] px-2 py-0.5 rounded-full font-bold animate-in fade-in">
                            Фильтр: {selectedGroup}
                        </span>
                    )}
                </div>
                
                <div className="group relative z-20">
                    <Info size={18} className="text-slate-400 cursor-help"/>
                    <div className="absolute right-0 w-64 p-3 bg-slate-800 text-white text-xs rounded-xl opacity-0 group-hover:opacity-100 transition pointer-events-none top-6 shadow-xl">
                        Кликните на ячейку, чтобы отфильтровать список товаров.
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-[auto_1fr_1fr_1fr] gap-2 select-none">
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
                            
                            // Логика выделения
                            const isSelected = selectedGroup === group;
                            const isDimmed = selectedGroup && !isSelected; // Затухание, если выбрано что-то другое

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