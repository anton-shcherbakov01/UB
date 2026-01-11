import React, { useState } from 'react';

const CostEditModal = ({ item, onClose, onSave }) => {
    const [cost, setCost] = useState(item.cost_price || 0);
    return (
        <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in">
            <div className="bg-white w-full max-w-sm rounded-[32px] p-6 shadow-2xl">
                <h3 className="font-bold text-lg mb-2">Себестоимость</h3>
                <p className="text-xs text-slate-400 mb-4">Для расчета чистой прибыли SKU {item.sku}</p>
                <input 
                    type="number" 
                    value={cost} 
                    onChange={e => setCost(e.target.value)}
                    className="w-full bg-slate-50 text-2xl font-black text-center p-4 rounded-2xl outline-none focus:ring-2 ring-indigo-500 mb-4"
                />
                <div className="flex gap-2">
                    <button onClick={onClose} className="flex-1 py-3 bg-slate-100 font-bold rounded-xl text-slate-600">Отмена</button>
                    <button onClick={() => onSave(item.sku, cost)} className="flex-1 py-3 bg-indigo-600 text-white font-bold rounded-xl shadow-lg shadow-indigo-200">Сохранить</button>
                </div>
            </div>
        </div>
    );
};

export default CostEditModal;