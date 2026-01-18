import React, { useState, useEffect } from 'react';
import { 
    ChevronLeft, Loader2, RefreshCw, Users, DollarSign, Activity, 
    TrendingUp, TrendingDown, Server, BarChart3, PieChart, LineChart,
    ArrowUp, ArrowDown, Minus, Search, Filter, Check, Settings
} from 'lucide-react';
import { 
    BarChart, Bar, LineChart as RechartsLineChart, Line, PieChart as RechartsPieChart, 
    Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer 
} from 'recharts';
import { API_URL, getTgHeaders } from '../config';

const AdminPage = ({ onBack }) => {
    const [activeTab, setActiveTab] = useState('dashboard');
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    
    // Data states (New Admin Panel)
    const [usersStats, setUsersStats] = useState(null);
    const [servicesStats, setServicesStats] = useState(null);
    const [servicesDetailed, setServicesDetailed] = useState(null);
    const [serverMetrics, setServerMetrics] = useState(null);
    const [analytics, setAnalytics] = useState(null);
    
    // Data states (Old Admin Panel - User Management)
    const [currentUser, setCurrentUser] = useState(null);
    const [planChanging, setPlanChanging] = useState(false);
    
    // Table sorting
    const [sortField, setSortField] = useState('total_usage');
    const [sortDirection, setSortDirection] = useState('desc');
    const [searchQuery, setSearchQuery] = useState('');

    useEffect(() => {
        fetchAllData();
        // Auto-refresh server metrics every 30 seconds
        const metricsInterval = setInterval(() => {
            if (activeTab === 'load') {
                fetchServerMetrics();
            }
        }, 30000);
        return () => clearInterval(metricsInterval);
    }, [activeTab]);

    const fetchAllData = async () => {
        setLoading(true);
        try {
            await Promise.all([
                fetchUsersStats(),
                fetchServicesStats(),
                fetchServicesDetailed(),
                fetchServerMetrics(),
                fetchAnalytics(),
                fetchCurrentUser() // Added from old version
            ]);
        } catch (e) {
            console.error('Error fetching admin data:', e);
        } finally {
            setLoading(false);
        }
    };

    const refreshData = async () => {
        setRefreshing(true);
        await fetchAllData();
        setRefreshing(false);
    };

    // --- API Fetchers ---

    const fetchUsersStats = async () => {
        const res = await fetch(`${API_URL}/api/admin/users/stats`, { headers: getTgHeaders() });
        if (res.ok) setUsersStats(await res.json());
    };

    const fetchServicesStats = async () => {
        const res = await fetch(`${API_URL}/api/admin/services/stats`, { headers: getTgHeaders() });
        if (res.ok) setServicesStats(await res.json());
    };

    const fetchServicesDetailed = async () => {
        const res = await fetch(`${API_URL}/api/admin/services/detailed`, { headers: getTgHeaders() });
        if (res.ok) setServicesDetailed(await res.json());
    };

    const fetchServerMetrics = async () => {
        const res = await fetch(`${API_URL}/api/admin/server/metrics`, { headers: getTgHeaders() });
        if (res.ok) setServerMetrics(await res.json());
    };

    const fetchAnalytics = async () => {
        const res = await fetch(`${API_URL}/api/admin/analytics/overview`, { headers: getTgHeaders() });
        if (res.ok) setAnalytics(await res.json());
    };

    // Added from old version
    const fetchCurrentUser = async () => {
        const res = await fetch(`${API_URL}/api/user/me`, { headers: getTgHeaders() });
        if (res.ok) setCurrentUser(await res.json());
    };

    // --- Old Admin Panel Logic (Plan Changing) ---

    const plans = [
        { id: 'start', name: 'Старт', color: 'bg-slate-900' },
        { id: 'analyst', name: 'Аналитик', color: 'bg-indigo-600' },
        { id: 'strategist', name: 'Стратег', color: 'bg-slate-700' }
    ];

    const getPlanDisplayName = (planId) => {
        switch(planId) {
            case 'analyst': return 'Аналитик';
            case 'strategist': return 'Стратег';
            case 'start': return 'Старт';
            default: return planId || 'Не определено';
        }
    };

    const changePlan = async (planId) => {
        setPlanChanging(true);
        try {
            const res = await fetch(`${API_URL}/api/admin/set-plan`, {
                method: 'POST',
                headers: {
                    ...getTgHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ plan_id: planId })
            });
            
            if (res.ok) {
                const data = await res.json();
                
                // Сразу обновляем локальное состояние из ответа сервера
                if (data.plan) {
                    setCurrentUser(prev => prev ? { ...prev, plan: data.plan } : null);
                }
                
                // Затем обновляем полную информацию о пользователе с небольшой задержкой
                setTimeout(async () => {
                    try {
                        await fetchCurrentUser();
                    } catch (e) {
                        console.error('Failed to refresh user data:', e);
                    }
                }, 500);
                
                alert(`✅ Тариф изменен на: ${data.plan_name || planId}`);
            } else {
                const error = await res.json().catch(() => ({ detail: 'Ошибка изменения тарифа' }));
                alert(`❌ ${error.detail || 'Ошибка изменения тарифа'}`);
            }
        } catch (e) {
            console.error('Plan change error:', e);
            alert(`❌ Ошибка: ${e.message}`);
        } finally {
            setPlanChanging(false);
        }
    };

    // --- Sorting & Helpers ---

    const handleSort = (field) => {
        if (sortField === field) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDirection('desc');
        }
    };

    const getSortedServices = () => {
        if (!servicesDetailed?.services) return [];
        
        let filtered = servicesDetailed.services.filter(s => 
            s.service_name.toLowerCase().includes(searchQuery.toLowerCase())
        );
        
        filtered.sort((a, b) => {
            let aVal, bVal;
            
            if (sortField === 'total_usage') {
                aVal = a.usage.total;
                bVal = b.usage.total;
            } else if (sortField === 'unique_users') {
                aVal = a.unique_users;
                bVal = b.unique_users;
            } else if (sortField === 'last_used') {
                aVal = a.last_used ? new Date(a.last_used).getTime() : 0;
                bVal = b.last_used ? new Date(b.last_used).getTime() : 0;
            } else if (sortField === 'peak_usage') {
                aVal = a.peak_usage;
                bVal = b.peak_usage;
            } else {
                return 0;
            }
            
            if (sortDirection === 'asc') {
                return aVal > bVal ? 1 : -1;
            } else {
                return aVal < bVal ? 1 : -1;
            }
        });
        
        return filtered;
    };

    const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'];

    if (loading && !usersStats) {
        return (
            <div className="h-screen flex items-center justify-center bg-[#F4F4F9]">
                <Loader2 className="animate-spin text-indigo-600" size={32} />
            </div>
        );
    }

    return (
        <div className="p-4 space-y-6 pb-32 animate-in fade-in bg-[#F4F4F9] min-h-screen">
            {/* Header */}
            <div className="flex justify-between items-stretch h-20 mb-6">
                <div className="bg-gradient-to-r from-slate-800 to-slate-900 p-6 rounded-[28px] text-white shadow-xl shadow-slate-200 relative overflow-hidden flex-1 mr-3 flex items-center justify-between">
                    <div className="relative z-10">
                        <h1 className="text-lg md:text-xl font-black flex items-center gap-2">
                            <Activity size={24} /> Админ панель
                        </h1>
                        <p className="text-xs md:text-sm opacity-90 mt-1 font-medium text-white/90">
                            Аналитика и управление системой
                        </p>
                    </div>
                    
                    <button
                        onClick={refreshData}
                        disabled={refreshing}
                        className="bg-white/20 backdrop-blur-md p-2.5 rounded-full hover:bg-white/30 transition-colors flex items-center justify-center text-white border border-white/10 active:scale-95 shadow-sm disabled:opacity-50"
                        title="Обновить данные"
                    >
                        {refreshing ? <Loader2 size={20} className="animate-spin" /> : <RefreshCw size={20} />}
                    </button>
                    
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-10 -mt-10 blur-2xl"></div>
                </div>
                
                <div className="flex flex-col gap-2 w-14 shrink-0">
                    <button 
                        onClick={onBack} 
                        className="bg-white h-full rounded-2xl shadow-sm text-slate-400 hover:text-indigo-600 transition-colors flex items-center justify-center active:scale-95"
                        title="Назад"
                    >
                        <ChevronLeft size={24} />
                    </button>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                {[
                    { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
                    { id: 'users', label: 'Пользователи', icon: Users },
                    { id: 'services', label: 'Сервисы', icon: Activity },
                    { id: 'load', label: 'Нагрузка', icon: Server },
                    { id: 'analytics', label: 'Аналитика', icon: PieChart },
                    { id: 'testing', label: 'Тестирование', icon: Settings } // New tab for plan switching
                ].map(tab => {
                    const Icon = tab.icon;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`px-4 py-2 rounded-xl text-sm font-bold transition-all whitespace-nowrap flex items-center gap-2 ${
                                activeTab === tab.id
                                    ? 'bg-slate-900 text-white shadow-md'
                                    : 'bg-white text-slate-500 hover:bg-slate-50'
                            }`}
                        >
                            <Icon size={18} />
                            {tab.label}
                        </button>
                    );
                })}
            </div>

            {/* Dashboard Tab */}
            {activeTab === 'dashboard' && usersStats && (
                <div className="space-y-4 animate-in fade-in">
                    {/* Stats Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-slate-400 font-bold uppercase">Всего</p>
                                <Users className="text-indigo-600" size={20} />
                            </div>
                            <p className="text-3xl font-black text-indigo-600">{usersStats.total_users || 0}</p>
                            <p className="text-[10px] text-slate-400 mt-1">пользователей</p>
                        </div>
                        
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-slate-400 font-bold uppercase">Платных</p>
                                <DollarSign className="text-emerald-600" size={20} />
                            </div>
                            <p className="text-3xl font-black text-emerald-600">{usersStats.paid_users || 0}</p>
                            <p className="text-[10px] text-slate-400 mt-1">{usersStats.paid_percentage || 0}% от общего</p>
                        </div>
                        
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-slate-400 font-bold uppercase">Активных</p>
                                <Activity className="text-blue-600" size={20} />
                            </div>
                            <p className="text-3xl font-black text-blue-600">{usersStats.active_users?.last_7_days || 0}</p>
                            <p className="text-[10px] text-slate-400 mt-1">за 7 дней</p>
                        </div>
                        
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-slate-400 font-bold uppercase">Нагрузка</p>
                                <Server className="text-amber-600" size={20} />
                            </div>
                            <p className="text-3xl font-black text-amber-600">
                                {serverMetrics?.system?.cpu_percent 
                                    ? `${Math.round(serverMetrics.system.cpu_percent)}%`
                                    : '—'
                                }
                            </p>
                            <p className="text-[10px] text-slate-400 mt-1">CPU</p>
                        </div>
                    </div>

                    {/* Quick Charts */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Plan Distribution */}
                        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                            <h3 className="text-lg font-bold text-slate-800 mb-4">Распределение по тарифам</h3>
                            {analytics?.plan_distribution && (
                                <ResponsiveContainer width="100%" height={250}>
                                    <RechartsPieChart>
                                        <Pie
                                            data={analytics.plan_distribution}
                                            dataKey="count"
                                            nameKey="plan"
                                            cx="50%"
                                            cy="50%"
                                            outerRadius={80}
                                            label={({ plan, percentage }) => `${plan}: ${percentage}%`}
                                        >
                                            {analytics.plan_distribution.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                            ))}
                                        </Pie>
                                        <Tooltip />
                                    </RechartsPieChart>
                                </ResponsiveContainer>
                            )}
                        </div>

                        {/* Top Services */}
                        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                            <h3 className="text-lg font-bold text-slate-800 mb-4">Топ-5 сервисов</h3>
                            {servicesStats?.popularity_ranking?.slice(0, 5) && (
                                <ResponsiveContainer width="100%" height={250}>
                                    <BarChart data={servicesStats.popularity_ranking.slice(0, 5)}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="service_name" angle={-45} textAnchor="end" height={80} />
                                        <YAxis />
                                        <Tooltip />
                                        <Bar dataKey="total_usage" fill="#3b82f6" />
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Users Tab */}
            {activeTab === 'users' && usersStats && (
                <div className="space-y-4 animate-in fade-in">
                    {/* Plan Distribution Table */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <h3 className="text-lg font-bold text-slate-800 mb-4">Пользователи по тарифам</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-slate-200">
                                        <th className="text-left py-3 px-4 font-bold text-slate-600">Тариф</th>
                                        <th className="text-right py-3 px-4 font-bold text-slate-600">Количество</th>
                                        <th className="text-right py-3 px-4 font-bold text-slate-600">Процент</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {Object.entries(usersStats.plan_distribution || {}).map(([plan, count]) => {
                                        const percentage = usersStats.total_users > 0 
                                            ? round((count / usersStats.total_users) * 100, 2)
                                            : 0;
                                        return (
                                            <tr key={plan} className="border-b border-slate-100 hover:bg-slate-50">
                                                <td className="py-3 px-4 font-medium text-slate-800 capitalize">{plan}</td>
                                                <td className="py-3 px-4 text-right font-bold text-slate-900">{count}</td>
                                                <td className="py-3 px-4 text-right text-slate-600">{percentage}%</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Registration Chart */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <h3 className="text-lg font-bold text-slate-800 mb-4">Регистрации пользователей (30 дней)</h3>
                        {usersStats.registration_chart && (
                            <ResponsiveContainer width="100%" height={300}>
                                <RechartsLineChart data={usersStats.registration_chart}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="date" />
                                    <YAxis />
                                    <Tooltip />
                                    <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} />
                                </RechartsLineChart>
                            </ResponsiveContainer>
                        )}
                    </div>

                    {/* Additional Stats */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <p className="text-xs text-slate-400 font-bold uppercase mb-2">Новых сегодня</p>
                            <p className="text-2xl font-black text-slate-900">{usersStats.new_users?.today || 0}</p>
                        </div>
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <p className="text-xs text-slate-400 font-bold uppercase mb-2">Новых за неделю</p>
                            <p className="text-2xl font-black text-slate-900">{usersStats.new_users?.week || 0}</p>
                        </div>
                        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                            <p className="text-xs text-slate-400 font-bold uppercase mb-2">Новых за месяц</p>
                            <p className="text-2xl font-black text-slate-900">{usersStats.new_users?.month || 0}</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Services Tab */}
            {activeTab === 'services' && servicesDetailed && (
                <div className="space-y-4 animate-in fade-in">
                    {/* Search and Filter */}
                    <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-3">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                            <input
                                type="text"
                                placeholder="Поиск по названию сервиса..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-10 pr-4 py-2 bg-slate-50 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                            />
                        </div>
                    </div>

                    {/* Services Table */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 overflow-x-auto">
                        <h3 className="text-lg font-bold text-slate-800 mb-4">Детальная статистика сервисов</h3>
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-slate-200">
                                    <th 
                                        className="text-left py-3 px-4 font-bold text-slate-600 cursor-pointer hover:bg-slate-50"
                                        onClick={() => handleSort('service_name')}
                                    >
                                        Сервис
                                    </th>
                                    <th 
                                        className="text-right py-3 px-4 font-bold text-slate-600 cursor-pointer hover:bg-slate-50"
                                        onClick={() => handleSort('total_usage')}
                                    >
                                        Использований
                                        {sortField === 'total_usage' && (
                                            sortDirection === 'asc' ? <ArrowUp size={14} className="inline ml-1" /> : <ArrowDown size={14} className="inline ml-1" />
                                        )}
                                    </th>
                                    <th className="text-right py-3 px-4 font-bold text-slate-600">Сегодня</th>
                                    <th className="text-right py-3 px-4 font-bold text-slate-600">Неделя</th>
                                    <th className="text-right py-3 px-4 font-bold text-slate-600">Месяц</th>
                                    <th 
                                        className="text-right py-3 px-4 font-bold text-slate-600 cursor-pointer hover:bg-slate-50"
                                        onClick={() => handleSort('unique_users')}
                                    >
                                        Уникальных
                                        {sortField === 'unique_users' && (
                                            sortDirection === 'asc' ? <ArrowUp size={14} className="inline ml-1" /> : <ArrowDown size={14} className="inline ml-1" />
                                        )}
                                    </th>
                                    <th 
                                        className="text-right py-3 px-4 font-bold text-slate-600 cursor-pointer hover:bg-slate-50"
                                        onClick={() => handleSort('peak_usage')}
                                    >
                                        Пик
                                        {sortField === 'peak_usage' && (
                                            sortDirection === 'asc' ? <ArrowUp size={14} className="inline ml-1" /> : <ArrowDown size={14} className="inline ml-1" />
                                        )}
                                    </th>
                                    <th 
                                        className="text-right py-3 px-4 font-bold text-slate-600 cursor-pointer hover:bg-slate-50"
                                        onClick={() => handleSort('last_used')}
                                    >
                                        Последнее
                                        {sortField === 'last_used' && (
                                            sortDirection === 'asc' ? <ArrowUp size={14} className="inline ml-1" /> : <ArrowDown size={14} className="inline ml-1" />
                                        )}
                                    </th>
                                    <th className="text-center py-3 px-4 font-bold text-slate-600">Тренд</th>
                                </tr>
                            </thead>
                            <tbody>
                                {getSortedServices().map((service) => (
                                    <tr key={service.service_key} className="border-b border-slate-100 hover:bg-slate-50">
                                        <td className="py-3 px-4 font-medium text-slate-800">{service.service_name}</td>
                                        <td className="py-3 px-4 text-right font-bold text-slate-900">{service.usage.total}</td>
                                        <td className="py-3 px-4 text-right text-slate-600">{service.usage.today}</td>
                                        <td className="py-3 px-4 text-right text-slate-600">{service.usage.week}</td>
                                        <td className="py-3 px-4 text-right text-slate-600">{service.usage.month}</td>
                                        <td className="py-3 px-4 text-right text-slate-600">{service.unique_users}</td>
                                        <td className="py-3 px-4 text-right text-slate-600">{service.peak_usage}</td>
                                        <td className="py-3 px-4 text-right text-slate-500 text-xs">
                                            {service.last_used 
                                                ? new Date(service.last_used).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
                                                : '—'
                                            }
                                        </td>
                                        <td className="py-3 px-4 text-center">
                                            {service.trend === 'up' && <TrendingUp className="text-emerald-600 inline" size={18} />}
                                            {service.trend === 'down' && <TrendingDown className="text-red-600 inline" size={18} />}
                                            {service.trend === 'stable' && <Minus className="text-slate-400 inline" size={18} />}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Popularity Ranking */}
                    {servicesStats?.popularity_ranking && (
                        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                            <h3 className="text-lg font-bold text-slate-800 mb-4">Рейтинг популярности (Топ-10)</h3>
                            <ResponsiveContainer width="100%" height={400}>
                                <BarChart data={servicesStats.popularity_ranking.slice(0, 10)} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis type="number" />
                                    <YAxis dataKey="service_name" type="category" width={150} />
                                    <Tooltip />
                                    <Bar dataKey="total_usage" fill="#3b82f6" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    )}
                </div>
            )}

            {/* Load Tab */}
            {activeTab === 'load' && serverMetrics && (
                <div className="space-y-4 animate-in fade-in">
                    {/* System Metrics */}
                    {serverMetrics.system && !serverMetrics.system.error && (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                                <h3 className="text-lg font-bold text-slate-800 mb-4">CPU</h3>
                                <div className="text-center">
                                    <p className="text-4xl font-black text-indigo-600 mb-2">
                                        {Math.round(serverMetrics.system.cpu_percent)}%
                                    </p>
                                    <div className="w-full bg-slate-100 rounded-full h-3 mt-4">
                                        <div 
                                            className="bg-indigo-600 h-3 rounded-full transition-all"
                                            style={{ width: `${serverMetrics.system.cpu_percent}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>
                            
                            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                                <h3 className="text-lg font-bold text-slate-800 mb-4">Память</h3>
                                <div className="text-center">
                                    <p className="text-4xl font-black text-emerald-600 mb-2">
                                        {Math.round(serverMetrics.system.memory.percent)}%
                                    </p>
                                    <p className="text-xs text-slate-500 mt-2">
                                        {Math.round(serverMetrics.system.memory.used_mb)} MB / {Math.round(serverMetrics.system.memory.total_mb)} MB
                                    </p>
                                    <div className="w-full bg-slate-100 rounded-full h-3 mt-4">
                                        <div 
                                            className="bg-emerald-600 h-3 rounded-full transition-all"
                                            style={{ width: `${serverMetrics.system.memory.percent}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>
                            
                            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                                <h3 className="text-lg font-bold text-slate-800 mb-4">Диск</h3>
                                <div className="text-center">
                                    <p className="text-4xl font-black text-amber-600 mb-2">
                                        {Math.round(serverMetrics.system.disk.percent)}%
                                    </p>
                                    <p className="text-xs text-slate-500 mt-2">
                                        {Math.round(serverMetrics.system.disk.used_gb)} GB / {Math.round(serverMetrics.system.disk.total_gb)} GB
                                    </p>
                                    <div className="w-full bg-slate-100 rounded-full h-3 mt-4">
                                        <div 
                                            className="bg-amber-600 h-3 rounded-full transition-all"
                                            style={{ width: `${serverMetrics.system.disk.percent}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Celery Metrics */}
                    {serverMetrics.celery && !serverMetrics.celery.error && (
                        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                            <h3 className="text-lg font-bold text-slate-800 mb-4">Celery задачи</h3>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <div className="text-center p-4 bg-slate-50 rounded-xl">
                                    <p className="text-xs text-slate-500 mb-1">Активные</p>
                                    <p className="text-2xl font-black text-slate-900">{serverMetrics.celery.active_tasks || 0}</p>
                                </div>
                                <div className="text-center p-4 bg-slate-50 rounded-xl">
                                    <p className="text-xs text-slate-500 mb-1">Запланированные</p>
                                    <p className="text-2xl font-black text-slate-900">{serverMetrics.celery.scheduled_tasks || 0}</p>
                                </div>
                                <div className="text-center p-4 bg-slate-50 rounded-xl">
                                    <p className="text-xs text-slate-500 mb-1">Priority очередь</p>
                                    <p className="text-2xl font-black text-indigo-600">{serverMetrics.celery.queue_sizes?.priority || 0}</p>
                                </div>
                                <div className="text-center p-4 bg-slate-50 rounded-xl">
                                    <p className="text-xs text-slate-500 mb-1">Normal очередь</p>
                                    <p className="text-2xl font-black text-blue-600">{serverMetrics.celery.queue_sizes?.normal || 0}</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Redis Metrics */}
                    {serverMetrics.redis && !serverMetrics.redis.error && (
                        <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                            <h3 className="text-lg font-bold text-slate-800 mb-4">Redis</h3>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <div className="text-center p-4 bg-slate-50 rounded-xl">
                                    <p className="text-xs text-slate-500 mb-1">Память</p>
                                    <p className="text-lg font-black text-slate-900">{serverMetrics.redis.used_memory_human || '—'}</p>
                                </div>
                                <div className="text-center p-4 bg-slate-50 rounded-xl">
                                    <p className="text-xs text-slate-500 mb-1">Ключей</p>
                                    <p className="text-2xl font-black text-slate-900">{serverMetrics.redis.total_keys || 0}</p>
                                </div>
                                <div className="text-center p-4 bg-slate-50 rounded-xl">
                                    <p className="text-xs text-slate-500 mb-1">Клиентов</p>
                                    <p className="text-2xl font-black text-slate-900">{serverMetrics.redis.connected_clients || 0}</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {serverMetrics.system?.error && (
                        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
                            <p className="text-sm text-amber-800">
                                <strong>Примечание:</strong> {serverMetrics.system.error}
                            </p>
                        </div>
                    )}
                </div>
            )}

            {/* Analytics Tab */}
            {activeTab === 'analytics' && analytics && (
                <div className="space-y-4 animate-in fade-in">
                    {/* Registration Chart */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <h3 className="text-lg font-bold text-slate-800 mb-4">Регистрации пользователей (30 дней)</h3>
                        <ResponsiveContainer width="100%" height={300}>
                            <RechartsLineChart data={analytics.registration_chart}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="date" />
                                <YAxis />
                                <Tooltip />
                                <Legend />
                                <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} name="Регистраций" />
                            </RechartsLineChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Services Usage Chart */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <h3 className="text-lg font-bold text-slate-800 mb-4">Использование сервисов (30 дней)</h3>
                        {analytics.services_usage_chart && (
                            <ResponsiveContainer width="100%" height={400}>
                                <RechartsLineChart data={analytics.services_usage_chart}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="date" />
                                    <YAxis />
                                    <Tooltip />
                                    <Legend />
                                    <Line type="monotone" dataKey="ai" stroke="#3b82f6" strokeWidth={2} name="AI анализ" />
                                    <Line type="monotone" dataKey="seo" stroke="#10b981" strokeWidth={2} name="SEO генератор" />
                                    <Line type="monotone" dataKey="seo_tracker" stroke="#f59e0b" strokeWidth={2} name="SEO трекер" />
                                    <Line type="monotone" dataKey="pnl" stroke="#ef4444" strokeWidth={2} name="P&L" />
                                    <Line type="monotone" dataKey="supply" stroke="#8b5cf6" strokeWidth={2} name="Поставки" />
                                </RechartsLineChart>
                            </ResponsiveContainer>
                        )}
                    </div>

                    {/* Top Active Users */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <h3 className="text-lg font-bold text-slate-800 mb-4">Топ-10 активных пользователей</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-slate-200">
                                        <th className="text-left py-3 px-4 font-bold text-slate-600">Пользователь</th>
                                        <th className="text-left py-3 px-4 font-bold text-slate-600">Тариф</th>
                                        <th className="text-right py-3 px-4 font-bold text-slate-600">Использований</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {analytics.top_active_users?.map((u, idx) => (
                                        <tr key={u.user_id} className="border-b border-slate-100 hover:bg-slate-50">
                                            <td className="py-3 px-4">
                                                <div className="flex items-center gap-2">
                                                    <span className="w-6 h-6 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center text-xs font-bold">
                                                        {idx + 1}
                                                    </span>
                                                    <span className="font-medium text-slate-800">
                                                        {u.first_name} {u.username ? `(@${u.username})` : ''}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="py-3 px-4">
                                                <span className="px-2 py-1 bg-slate-100 text-slate-700 rounded-lg text-xs font-bold capitalize">
                                                    {u.plan}
                                                </span>
                                            </td>
                                            <td className="py-3 px-4 text-right font-bold text-slate-900">{u.usage_count}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Conversion Rate */}
                    <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                        <h3 className="text-lg font-bold text-slate-800 mb-4">Конверсия</h3>
                        <div className="grid grid-cols-3 gap-4">
                            <div className="text-center p-4 bg-slate-50 rounded-xl">
                                <p className="text-xs text-slate-500 mb-1">Бесплатных</p>
                                <p className="text-2xl font-black text-slate-900">{analytics.free_users || 0}</p>
                            </div>
                            <div className="text-center p-4 bg-slate-50 rounded-xl">
                                <p className="text-xs text-slate-500 mb-1">Платных</p>
                                <p className="text-2xl font-black text-emerald-600">{analytics.paid_users || 0}</p>
                            </div>
                            <div className="text-center p-4 bg-emerald-50 rounded-xl">
                                <p className="text-xs text-emerald-600 mb-1">Конверсия</p>
                                <p className="text-2xl font-black text-emerald-700">{analytics.conversion_rate || 0}%</p>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Testing Tab (Imported from Old Version) */}
            {activeTab === 'testing' && (
                <div className="space-y-4 animate-in fade-in">
                    <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-100">
                        <div className="flex items-center justify-between mb-4">
                            <div>
                                <h3 className="text-lg font-bold text-slate-800">Тестирование тарифов</h3>
                                <p className="text-xs text-slate-500 mt-1">Текущий тариф: <strong className="text-slate-800">{getPlanDisplayName(currentUser?.plan)}</strong></p>
                            </div>
                            <button 
                                onClick={fetchCurrentUser}
                                className="p-2 bg-slate-100 rounded-lg hover:bg-slate-200 active:scale-95 transition-transform"
                                title="Обновить информацию"
                            >
                                <RefreshCw size={18} className="text-slate-600" />
                            </button>
                        </div>
                        
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            {plans.map((plan) => (
                                <button
                                    key={plan.id}
                                    onClick={() => changePlan(plan.id)}
                                    disabled={planChanging || currentUser?.plan === plan.id}
                                    className={`
                                        p-4 rounded-2xl font-bold text-sm text-white shadow-lg active:scale-95 transition-all
                                        ${planChanging ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-xl'}
                                        ${currentUser?.plan === plan.id ? `${plan.color} ring-4 ring-offset-2 ring-offset-white ring-indigo-300` : plan.color}
                                        ${currentUser?.plan === plan.id ? '' : 'hover:opacity-90'}
                                    `}
                                >
                                    {planChanging && currentUser?.plan === plan.id ? (
                                        <Loader2 className="animate-spin mx-auto" size={20} />
                                    ) : currentUser?.plan === plan.id ? (
                                        <div className="flex flex-col items-center gap-2">
                                            <Check size={20} className="text-white" />
                                            <span>{plan.name}</span>
                                            <span className="text-[10px] opacity-80">Активен</span>
                                        </div>
                                    ) : (
                                        <span>{plan.name}</span>
                                    )}
                                </button>
                            ))}
                        </div>
                        
                        <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-xl">
                            <p className="text-xs text-amber-800 leading-relaxed">
                                <strong>⚠️ Для тестирования:</strong> Выберите тариф для немедленного применения. Квоты будут сброшены, срок подписки установлен на 30 дней для платных тарифов.
                            </p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

// Helper function
const round = (num, decimals) => {
    return Math.round(num * Math.pow(10, decimals)) / Math.pow(10, decimals);
};

export default AdminPage;