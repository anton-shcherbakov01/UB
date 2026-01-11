import React, { useState, useEffect } from 'react';
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

export default function App() {
  const [activeTab, setActiveTab] = useState('home');
  const [user, setUser] = useState(null);

  useEffect(() => { 
      fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() })
        .then(r => r.json())
        .then(setUser)
        .catch(console.error); 
  }, [activeTab]);

  const renderContent = () => {
      switch(activeTab) {
          case 'home': return <DashboardPage onNavigate={setActiveTab} user={user} />;
          case 'scanner': return <ScannerPage onNavigate={setActiveTab} />;
          case 'monitor': return <MonitorPage />;
          case 'finance': return <FinancePage onNavigate={setActiveTab} />;
          case 'ai': return <AIAnalysisPage />;
          case 'seo': return <SeoGeneratorPage />;
          case 'seo_tracker': return <SeoTrackerPage />; 
          case 'bidder': return <BidderPage />; 
          case 'supply': return <SupplyPage />; 
          case 'profile': return <ProfilePage onNavigate={setActiveTab} />;
          case 'admin': return <AdminPage onBack={() => setActiveTab('profile')} />;
          default: return <DashboardPage onNavigate={setActiveTab} user={user} />;
      }
  };

  return (
    <div className="min-h-screen bg-[#F4F4F9] font-sans text-slate-900 select-none pb-24">
        {renderContent()}
        <TabNav active={activeTab} setTab={setActiveTab} isAdmin={user?.is_admin} />
    </div>
  );
}