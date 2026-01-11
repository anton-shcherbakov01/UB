export const API_URL = "https://api.ulike-bot.ru";

export const getTgHeaders = () => ({
  'Content-Type': 'application/json',
  'X-TG-Data': window.Telegram?.WebApp?.initData || ""
});