import React, { useState, useEffect } from 'react';
import { 
  Gavel, 
  Clock, 
  Trophy, 
  TrendingUp, 
  Search, 
  Bell, 
  User, 
  CreditCard,
  ChevronRight,
  DollarSign,
  AlertCircle,
  Package
} from 'lucide-react';

// --- Components defined in the same file to prevent import errors ---

const Card = ({ children, className = "" }) => (
  <div className={`bg-white rounded-xl shadow-sm border border-slate-200 ${className}`}>
    {children}
  </div>
);

const Badge = ({ status }) => {
  const styles = {
    winning: "bg-emerald-100 text-emerald-700 border-emerald-200",
    outbid: "bg-red-100 text-red-700 border-red-200",
    pending: "bg-amber-100 text-amber-700 border-amber-200",
    ended: "bg-slate-100 text-slate-600 border-slate-200",
  };
  
  const labels = {
    winning: "Winning",
    outbid: "Outbid",
    pending: "Processing",
    ended: "Ended",
  };

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[status] || styles.pending}`}>
      {labels[status] || status}
    </span>
  );
};

// --- Mock Data ---

const MOCK_USER = {
  name: "Alex Bidder",
  balance: 4500.00,
  activeBidsCount: 5,
  itemsWon: 12
};

const MOCK_ACTIVE_BIDS = [
  {
    id: 1,
    title: "Vintage Leica M3 Camera",
    thumbnail: "camera", // Simplified for icon placeholder
    currentBid: 1250.00,
    myBid: 1250.00,
    status: "winning",
    timeLeft: "2h 15m",
    bids: 14
  },
  {
    id: 2,
    title: "Eames Lounge Chair Replica",
    thumbnail: "chair",
    currentBid: 850.00,
    myBid: 800.00,
    status: "outbid",
    timeLeft: "45m",
    bids: 23
  },
  {
    id: 3,
    title: "MacBook Pro M2 (Refurbished)",
    thumbnail: "laptop",
    currentBid: 1100.00,
    myBid: 1100.00,
    status: "winning",
    timeLeft: "5h 30m",
    bids: 8
  }
];

const MOCK_WATCHLIST = [
  {
    id: 4,
    title: "Sony A7III Body Only",
    currentBid: 1400.00,
    timeLeft: "1d 2h",
    bids: 45
  },
  {
    id: 5,
    title: "Herman Miller Aeron",
    currentBid: 400.00,
    timeLeft: "3h 10m",
    bids: 12
  }
];

// --- Main Dashboard Component ---

const BidderDashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [bids, setBids] = useState(MOCK_ACTIVE_BIDS);
  const [notification, setNotification] = useState(null);

  // Simulate a live update
  useEffect(() => {
    const interval = setInterval(() => {
      // Randomly outbid the user on the first item occasionally
      if (Math.random() > 0.8) {
        setBids(prev => {
          const newBids = [...prev];
          if (newBids[0].status === 'winning') {
             newBids[0] = {
               ...newBids[0],
               currentBid: newBids[0].currentBid + 50,
               status: 'outbid'
             };
             setNotification({
               type: 'error',
               message: `You've been outbid on ${newBids[0].title}!`
             });
          }
          return newBids;
        });
      }
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const handlePlaceBid = (id, amount) => {
    setBids(prev => prev.map(item => {
      if (item.id === id) {
        return {
          ...item,
          currentBid: amount,
          myBid: amount,
          status: 'winning'
        };
      }
      return item;
    }));
    setNotification({ type: 'success', message: 'Bid placed successfully!' });
    setTimeout(() => setNotification(null), 3000);
  };

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      {/* Navigation */}
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <div className="flex-shrink-0 flex items-center gap-2 text-blue-600">
                <Gavel className="h-8 w-8" />
                <span className="font-bold text-xl tracking-tight">BidMaster</span>
              </div>
              <div className="hidden sm:ml-8 sm:flex sm:space-x-8">
                {['Overview', 'My Bids', 'Watchlist', 'Won Items'].map((item) => (
                  <button
                    key={item}
                    onClick={() => setActiveTab(item.toLowerCase().replace(' ', ''))}
                    className={`inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium ${
                      activeTab === item.toLowerCase().replace(' ', '')
                        ? 'border-blue-500 text-slate-900'
                        : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700'
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <button className="p-2 rounded-full text-slate-400 hover:text-slate-500 relative">
                <Bell className="h-6 w-6" />
                <span className="absolute top-2 right-2 block h-2 w-2 rounded-full bg-red-500 ring-2 ring-white" />
              </button>
              <div className="flex items-center gap-3 pl-4 border-l border-slate-200">
                <div className="text-right hidden sm:block">
                  <p className="text-sm font-medium text-slate-900">{MOCK_USER.name}</p>
                  <p className="text-xs text-slate-500">${MOCK_USER.balance.toFixed(2)}</p>
                </div>
                <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold">
                  {MOCK_USER.name.charAt(0)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* Notification Toast */}
        {notification && (
          <div className={`fixed bottom-4 right-4 p-4 rounded-lg shadow-lg border-l-4 transform transition-all duration-500 ease-in-out z-50 flex items-center gap-3 ${
            notification.type === 'error' ? 'bg-white border-red-500' : 'bg-white border-green-500'
          }`}>
            {notification.type === 'error' ? <AlertCircle className="text-red-500 h-5 w-5" /> : <TrendingUp className="text-green-500 h-5 w-5" />}
            <span className="text-sm font-medium">{notification.message}</span>
            <button onClick={() => setNotification(null)} className="ml-4 text-slate-400 hover:text-slate-600">×</button>
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4 mb-8">
          <Card className="p-5 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500 truncate">Active Bids</p>
              <p className="mt-1 text-3xl font-semibold text-slate-900">{bids.length}</p>
            </div>
            <div className="p-3 bg-blue-50 rounded-lg text-blue-600">
              <Gavel className="h-6 w-6" />
            </div>
          </Card>

          <Card className="p-5 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500 truncate">Items Won</p>
              <p className="mt-1 text-3xl font-semibold text-slate-900">{MOCK_USER.itemsWon}</p>
            </div>
            <div className="p-3 bg-emerald-50 rounded-lg text-emerald-600">
              <Trophy className="h-6 w-6" />
            </div>
          </Card>

          <Card className="p-5 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500 truncate">Total Spent</p>
              <p className="mt-1 text-3xl font-semibold text-slate-900">$12,450</p>
            </div>
            <div className="p-3 bg-purple-50 rounded-lg text-purple-600">
              <CreditCard className="h-6 w-6" />
            </div>
          </Card>

          <Card className="p-5 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500 truncate">Wallet Balance</p>
              <p className="mt-1 text-3xl font-semibold text-slate-900">${MOCK_USER.balance}</p>
            </div>
            <div className="p-3 bg-amber-50 rounded-lg text-amber-600">
              <DollarSign className="h-6 w-6" />
            </div>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Main Column: Active Bids */}
          <div className="lg:col-span-2 space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Active Bids</h2>
              <button className="text-sm text-blue-600 hover:text-blue-700 font-medium">View All</button>
            </div>

            <div className="space-y-4">
              {bids.map((bid) => (
                <Card key={bid.id} className="p-0 overflow-hidden hover:shadow-md transition-shadow">
                  <div className="p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex gap-4">
                        <div className="h-16 w-16 bg-slate-100 rounded-lg flex items-center justify-center flex-shrink-0 text-slate-400">
                          <Package className="h-8 w-8" />
                        </div>
                        <div>
                          <h3 className="text-lg font-medium text-slate-900">{bid.title}</h3>
                          <div className="flex items-center gap-4 mt-1 text-sm text-slate-500">
                            <span className="flex items-center gap-1">
                              <Clock className="h-4 w-4" /> {bid.timeLeft}
                            </span>
                            <span className="flex items-center gap-1">
                              <User className="h-4 w-4" /> {bid.bids} bids
                            </span>
                          </div>
                        </div>
                      </div>
                      <Badge status={bid.status} />
                    </div>

                    <div className="mt-6 flex items-end justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Current Bid</p>
                        <div className="flex items-baseline gap-2">
                          <span className="text-2xl font-bold text-slate-900">${bid.currentBid.toFixed(2)}</span>
                          {bid.status === 'outbid' && (
                             <span className="text-sm font-medium text-red-600 flex items-center gap-1">
                               <TrendingUp className="h-3 w-3" /> Outbid by ${ (bid.currentBid - bid.myBid).toFixed(0) }
                             </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mt-1">Your max: ${bid.myBid.toFixed(2)}</p>
                      </div>
                      
                      <div className="flex gap-2">
                        <button className="px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50">
                          Edit Max
                        </button>
                        <button 
                          onClick={() => handlePlaceBid(bid.id, bid.currentBid + 50)}
                          className={`px-4 py-2 rounded-lg text-sm font-medium text-white shadow-sm flex items-center gap-2 ${
                            bid.status === 'outbid' 
                              ? 'bg-red-600 hover:bg-red-700 animate-pulse' 
                              : 'bg-blue-600 hover:bg-blue-700'
                          }`}
                        >
                          <Gavel className="h-4 w-4" />
                          {bid.status === 'outbid' ? 'Bid Now' : 'Increase Bid'}
                        </button>
                      </div>
                    </div>
                  </div>
                  {/* Progress Bar for Time */}
                  <div className="h-1 w-full bg-slate-100">
                    <div 
                      className={`h-full ${bid.status === 'outbid' ? 'bg-red-500' : 'bg-blue-500'}`} 
                      style={{ width: '65%' }} 
                    />
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Sidebar: Watchlist & Recommendations */}
          <div className="space-y-6">
            <Card className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-bold text-slate-900">Watchlist</h3>
                <Search className="h-4 w-4 text-slate-400" />
              </div>
              <ul className="divide-y divide-slate-100">
                {MOCK_WATCHLIST.map((item) => (
                  <li key={item.id} className="py-3 flex items-center justify-between group cursor-pointer hover:bg-slate-50 -mx-2 px-2 rounded-lg transition-colors">
                    <div>
                      <p className="text-sm font-medium text-slate-900 group-hover:text-blue-600">{item.title}</p>
                      <p className="text-xs text-slate-500 mt-0.5">Ending in {item.timeLeft}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-bold text-slate-900">${item.currentBid}</p>
                      <button className="text-xs text-blue-600 hover:text-blue-700 font-medium">Bid</button>
                    </div>
                  </li>
                ))}
              </ul>
              <button className="w-full mt-4 py-2 text-sm text-slate-500 border border-slate-200 rounded-lg hover:border-slate-300 hover:text-slate-700 transition-colors">
                View All Watched Items
              </button>
            </Card>

            <Card className="bg-gradient-to-br from-blue-600 to-indigo-700 text-white border-none p-6 relative overflow-hidden">
              {/* Decorative Circle */}
              <div className="absolute top-0 right-0 -mt-4 -mr-4 w-24 h-24 bg-white opacity-10 rounded-full" />
              
              <div className="relative z-10">
                <h3 className="text-lg font-bold">Premium Membership</h3>
                <p className="text-blue-100 text-sm mt-2 mb-4">
                  Get zero fees on auctions over $1,000 and early access to estate sales.
                </p>
                <button className="w-full bg-white text-blue-600 py-2 rounded-lg text-sm font-bold hover:bg-blue-50 transition-colors shadow-sm">
                  Upgrade Now
                </button>
              </div>
            </Card>
          </div>

        </div>
      </main>
    </div>
  );
};

// --- App Entry Point ---

export default function App() {
  return (
    <BidderDashboard />
  );
}