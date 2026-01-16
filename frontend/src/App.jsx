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
import SlotsPage from './pages/SlotsPage';

// Внутренний компонент, который находится ВНУТРИ Router
const AppContent = () => {
  const [user, setUser] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();

  // 1. Вынесли загрузку пользователя в функцию, чтобы вызывать её из ProfilePage
  const fetchUser = () => {
      fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
        .then(r => r.json())
        .then(setUser)
        .catch(console.error); 
  };

  useEffect(() => { 
      fetchUser(); 
  }, []);

  const activeTab = location.pathname === '/' ? 'home' : location.pathname.substring(1);

  const handleTabChange = (tab) => {
      if (tab === 'home') navigate('/');
      else navigate(`/${tab}`);
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 select-none pb-24">
        <Routes>
            {/* Главная */}
            <Route path="/" element={<DashboardPage user={user} onNavigate={handleTabChange} />} />
            
            <Route path="/monitor" element={<MonitorPage />} />
            <Route path="/seo" element={<SeoGeneratorPage />} />
            <Route path="/seo_tracker" element={<SeoTrackerPage />} />
            <Route path="/finance" element={<FinancePage onNavigate={handleTabChange} />} />
            <Route path="/ai" element={<AIAnalysisPage user={user} />} />
            <Route path="/supply" element={<SupplyPage />} />
            
            {/* ИСПРАВЛЕНИЕ ЗДЕСЬ: Передаем user и onNavigate */}
            <Route path="/slots" element={<SlotsPage user={user} onNavigate={handleTabChange} />} />
            
            {/* Передаем refreshUser, чтобы обновлять данные после ввода токена */}
            <Route path="/profile" element={<ProfilePage onNavigate={handleTabChange} refreshUser={fetchUser} />} />
            
            <Route path="/admin" element={<AdminPage onBack={() => navigate('/profile')} />} />
            <Route path="/analytics_advanced" element={<AdvancedAnalyticsPage onBack={() => navigate('/')} />} />
            
            {/* Заглушки (если нужны) */}
            {/* <Route path="/bidder" element={<BidderPage />} /> */}
            {/* <Route path="/scanner" element={<ScannerPage />} /> */}

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