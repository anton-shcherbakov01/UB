export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const getTgHeaders = () => {
    const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    };
    
    // Получаем данные инициализации Telegram Mini App
    if (window.Telegram?.WebApp?.initData) {
        headers['X-TG-Data'] = window.Telegram.WebApp.initData;
    }
    
    return headers;
};