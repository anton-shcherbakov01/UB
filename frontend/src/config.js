export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const getTgHeaders = () => {
    const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    };
    
    // Безопасная проверка: код не упадет, даже если window.Telegram undefined
    try {
        if (
            typeof window !== 'undefined' && 
            window.Telegram && 
            window.Telegram.WebApp && 
            window.Telegram.WebApp.initData
        ) {
            headers['X-TG-Data'] = window.Telegram.WebApp.initData;
        }
    } catch (e) {
        console.warn("Telegram WebApp initData missing (running locally?)", e);
    }
    
    return headers;
};