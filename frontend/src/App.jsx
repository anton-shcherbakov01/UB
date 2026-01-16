import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { API_URL, getTgHeaders } from './config';
import TabNav from './components/TabNav';

// Pages
import DashboardPage from './pages/DashboardPage';
import ScannerPage from './pages/ScannerPage';
import MonitorPage from './pages/MonitorPage';
import FinancePage from './pages/FinancePage';
import AIAnalysisPage from './pages/AIAnalysisPage';
import SeoGeneratorPage from './pages/SeoGeneratorPage';
import SeoTrackerPage from './pages/SeoTrackerPage';
import BidderPage from './pages/BidderPage';
import SupplyPage from './pages/SupplyPage';
import ProfilePage from './pages/ProfilePage';
import AdminPage from './pages/AdminPage';
import AdvancedAnalyticsPage from './pages/AdvancedAnalyticsPage';

// Внутренний компонент, который находится ВНУТРИ Router
const AppContent = () => {
  const [user, setUser] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();

  // Определяем активную вкладку по URL (для подсветки TabNav)
  // Если путь "/", то активная вкладка 'home', иначе убираем слэш (например "/bidder" -> "bidder")
  const activeTab = location.pathname === '/' ? 'home' : location.pathname.substring(1);

  useEffect(() => { 
      fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
        .then(r => r.json())
        .then(setUser)
        .catch(console.error); 
  }, []);

  // Функция для переключения, которую мы передаем в TabNav
  const handleTabChange = (tab) => {
      if (tab === 'home') navigate('/');
      else navigate(`/${tab}`);
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 select-none pb-24">
        <Routes>
            {/* Главная */}
            <Route path="/" element={<DashboardPage user={user} onNavigate={handleTabChange} />} />
            
            {/* Основные модули */}
            {/* В РАЗРАБОТКЕ: <Route path="/bidder" element={<BidderPage />} /> */}
            {/* В РАЗРАБОТКЕ: <Route path="/scanner" element={<ScannerPage />} /> */}
            <Route path="/monitor" element={<MonitorPage />} />
            <Route path="/seo" element={<SeoGeneratorPage />} />
            
            {/* Дополнительные страницы */}
            <Route path="/seo_tracker" element={<SeoTrackerPage />} />
            <Route path="/finance" element={<FinancePage onNavigate={handleTabChange} />} />
            <Route path="/ai" element={<AIAnalysisPage user={user} />} />
            <Route path="/supply" element={<SupplyPage />} />
            <Route path="/profile" element={<ProfilePage onNavigate={handleTabChange} />} />
            <Route path="/admin" element={<AdminPage onBack={() => navigate('/profile')} />} />
            <Route path="/analytics_advanced" element={<AdvancedAnalyticsPage onBack={() => navigate('/')} />} />

            {/* Редирект для несуществующих путей */}
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

        {/* Навигация снизу */}
        <TabNav active={activeTab} setTab={handleTabChange} isAdmin={user?.is_admin} />
    </div>
  );
};

// Главная обертка
export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}