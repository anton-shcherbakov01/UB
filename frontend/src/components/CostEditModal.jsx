import React, { useState } from 'react';

const CostEditModal = ({ item, onClose, onSave }) => {
    // Если значение null (авто), ставим пустую строку, чтобы показать плейсхолдер
    const [cost, setCost] = useState(item.cost_price || 0);
    const [logistics, setLogistics] = useState(item.logistics !== null ? item.logistics : '');
    const [commission, setCommission] = useState(item.commission_percent !== null ? item.commission_percent : '');

    const handleSave = () => {
        onSave(item.sku, {
            cost_price: cost,
            // Если строка пустая, отправляем null (чтобы включить авторасчет на бэке)
            logistics: logistics === '' ? null : logistics,
            commission_percent: commission === '' ? null : commission
        });
    };

    return (
        <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in">
            <div className="bg-white w-full max-w-sm rounded-[32px] p-6 shadow-2xl">
                <h3 className="font-bold text-lg mb-1">Настройки товара</h3>
                <p className="text-xs text-slate-400 mb-6">SKU {item.sku}</p>
                
                <div className="space-y-4 mb-6">
                    {/* Себестоимость (Главное поле) */}
                    <div>
                        <label className="block text-xs font-bold text-slate-500 ml-2 mb-1">
                            Себестоимость закупочная (₽)
                        </label>
                        <input 
                            type="number" 
                            value={cost} 
                            onChange={e => setCost(e.target.value)}
                            className="w-full bg-slate-50 text-xl font-black text-center p-4 rounded-2xl outline-none focus:ring-2 ring-indigo-500 border-transparent border focus:bg-white transition-all"
                        />
                    </div>

                    {/* Дополнительные настройки (Override) */}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-bold text-slate-400 ml-2 mb-1">
                                Логистика (₽)
                            </label>
                            <input 
                                type="number" 
                                placeholder="Авто"
                                value={logistics} 
                                onChange={e => setLogistics(e.target.value)}
                                className="w-full bg-slate-50 text-base font-bold text-center p-3 rounded-xl outline-none focus:ring-2 ring-indigo-500 border-transparent border focus:bg-white transition-all placeholder:text-slate-300 placeholder:font-normal"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-400 ml-2 mb-1">
                                Комиссия (%)
                            </label>
                            <input 
                                type="number" 
                                placeholder="Авто"
                                value={commission} 
                                onChange={e => setCommission(e.target.value)}
                                className="w-full bg-slate-50 text-base font-bold text-center p-3 rounded-xl outline-none focus:ring-2 ring-indigo-500 border-transparent border focus:bg-white transition-all placeholder:text-slate-300 placeholder:font-normal"
                            />
                        </div>
                    </div>

                    <div className="bg-blue-50 p-3 rounded-xl flex items-start gap-2">
                        <div className="text-blue-500 mt-0.5">ℹ️</div>
                        <p className="text-[10px] text-blue-700 leading-tight">
                            Оставьте логистику и комиссию пустыми (плэйсхолдер "Авто"), чтобы брать реальные тарифы Wildberries. Заполните, если хотите задать свои значения вручную.
                        </p>
                    </div>
                </div>

                <div className="flex gap-2">
                    <button onClick={onClose} className="flex-1 py-3 bg-slate-100 font-bold rounded-xl text-slate-600 hover:bg-slate-200 transition-colors">
                        Отмена
                    </button>
                    <button onClick={handleSave} className="flex-1 py-3 bg-indigo-600 text-white font-bold rounded-xl shadow-lg shadow-indigo-200 hover:bg-indigo-700 transition-colors">
                        Сохранить
                    </button>
                </div>
            </div>
        </div>
    );
};

export default CostEditModal;