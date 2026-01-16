import React from 'react';
import { Gavel, Construction } from 'lucide-react';

// СЕРВИС В РАЗРАБОТКЕ - Заглушка
const BidderPage = () => {
    return (
        <div className="p-4 max-w-lg mx-auto pb-32 flex items-center justify-center min-h-[60vh]">
            <div className="text-center">
                <div className="bg-purple-100 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6">
                    <Construction className="text-purple-600" size={40} />
                </div>
                <h2 className="text-2xl font-black text-slate-800 mb-3">Биддер</h2>
                <p className="text-slate-500 mb-1">Сервис находится в разработке</p>
                <p className="text-sm text-slate-400">Скоро вы сможете управлять ставками рекламы автоматически</p>
            </div>
        </div>
    );
};

export default BidderPage;
