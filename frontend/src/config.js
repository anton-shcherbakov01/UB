export const API_URL = "https://api.juicystat.ru";

export const getTgHeaders = () => ({
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'X-TG-Data': window.Telegram?.WebApp?.initData || ""
});