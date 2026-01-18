import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { API_URL, getTgHeaders } from './config';
import TabNav from './components/TabNav';

// Pages
import DashboardPage from './pages/DashboardPage';
import MonitorPage from './pages/MonitorPage';
import FinancePage from './pages/FinancePage';
import AIAnalysisPage from './pages/AIAnalysisPage';
import SeoGeneratorPage from './pages/SeoGeneratorPage';
import SeoTrackerPage from './pages/SeoTrackerPage';
import SupplyPage from './pages/SupplyPage';
import ProfilePage from './pages/ProfilePage';
import AdminPage from './pages/AdminPage';
import AdvancedAnalyticsPage from './pages/AdvancedAnalyticsPage';
import SlotsPage from './pages/SlotsPage';
import NotificationsPage from './pages/NotificationsPage';
import OfferPage from './pages/OfferPage';
import PrivacyPage from './pages/PrivacyPage';
import SupportPage from './pages/SupportPage';
import TariffsPage from './pages/TariffsPage';
import FunnelPage from './pages/FunnelPage';

const AppContent = () => {
  const [user, setUser] = useState(null);
  const [showOfferModal, setShowOfferModal] = useState(false);
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // Функция загрузки пользователя (вызывается при старте и при обновлении токена)
  const fetchUser = () => {
      fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
        .then(r => r.json())
        .then(data => {
          setUser(data);
          // Проверяем, принята ли оферта
          if (!data.offer_accepted) {
            setShowOfferModal(true);
          } else if (!data.privacy_accepted) {
            // Показываем политику конфиденциальности только после принятия оферты
            setShowPrivacyModal(true);
          }
        })
        .catch(console.error); 
  };

  useEffect(() => { 
      fetchUser(); 
  }, []);
  
  const handleAcceptOffer = async () => {
    try {
      const res = await fetch(`${API_URL}/api/user/accept-offer`, {
        method: 'POST',
        headers: getTgHeaders()
      });
      if (res.ok) {
        setShowOfferModal(false);
        fetchUser(); // Обновляем данные пользователя
      }
    } catch (e) {
      console.error('Failed to accept offer:', e);
    }
  };
  
  const handleAcceptPrivacy = async () => {
    try {
      const res = await fetch(`${API_URL}/api/user/accept-privacy`, {
        method: 'POST',
        headers: getTgHeaders()
      });
      if (res.ok) {
        setShowPrivacyModal(false);
        fetchUser(); // Обновляем данные пользователя
      }
    } catch (e) {
      console.error('Failed to accept privacy:', e);
    }
  };

  const activeTab = location.pathname === '/' ? 'home' : location.pathname.substring(1);

  const handleTabChange = (tab) => {
      if (tab === 'home') navigate('/');
      else navigate(`/${tab}`);
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 select-none pb-24">
        {/* Модальное окно с офертой при первом запуске */}
        {showOfferModal && (
          <div className="fixed top-0 left-0 right-0 bottom-0 z-[9999] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
              <OfferPage onBack={null} onAccept={handleAcceptOffer} isModal={true} />
            </div>
          </div>
        )}
        
        {/* Модальное окно с политикой конфиденциальности */}
        {showPrivacyModal && (
          <div className="fixed top-0 left-0 right-0 bottom-0 z-[9999] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
              <PrivacyPage onBack={null} onAccept={handleAcceptPrivacy} isModal={true} />
            </div>
          </div>
        )}
        <Routes>
            <Route path="/" element={<DashboardPage user={user} onNavigate={handleTabChange} />} />
            <Route path="/monitor" element={<MonitorPage />} />
            <Route path="/seo" element={<SeoGeneratorPage user={user} onUserUpdate={fetchUser} />} />
            <Route path="/seo_tracker" element={<SeoTrackerPage />} />
            <Route path="/finance" element={<FinancePage user={user} onNavigate={handleTabChange} />} />
            <Route path="/ai" element={<AIAnalysisPage user={user} onUserUpdate={fetchUser} />} />
            <Route path="/supply" element={<SupplyPage />} />
            
            {/* Передаем user в SlotsPage */}
            <Route path="/slots" element={<SlotsPage user={user} onNavigate={handleTabChange} />} />
            
            {/* Передаем функцию refreshUser в ProfilePage */}
            <Route path="/profile" element={<ProfilePage onNavigate={handleTabChange} refreshUser={fetchUser} />} />
            
            <Route path="/admin" element={<AdminPage onBack={() => navigate('/profile')} />} />
            <Route path="/analytics_advanced" element={<AdvancedAnalyticsPage onBack={() => navigate('/')} user={user} />} />
            <Route path="/funnel" element={<FunnelPage onBack={() => navigate('/')} />} />
            <Route path="/notifications" element={<NotificationsPage onNavigate={handleTabChange} user={user} />} />
            <Route path="/offer" element={<OfferPage onBack={() => navigate('/profile')} />} />
            <Route path="/privacy" element={<PrivacyPage onBack={() => navigate('/profile')} />} />
            <Route path="/support" element={<SupportPage onBack={() => navigate('/profile')} />} />
            <Route path="/tariffs" element={<TariffsPage onBack={() => navigate('/profile')} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <TabNav active={activeTab} setTab={handleTabChange} isAdmin={user?.is_admin} />
    </div>
  );
};

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}