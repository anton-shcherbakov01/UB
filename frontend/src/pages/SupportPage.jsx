import React, { useState } from 'react';
import { ArrowLeft, Send, Mail, MessageSquare, User, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_URL, getTgHeaders } from '../config';

const SupportPage = ({ onBack }) => {
    const navigate = useNavigate();
    const [subject, setSubject] = useState('');
    const [message, setMessage] = useState('');
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [sent, setSent] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!subject.trim() || !message.trim()) {
            alert('Заполните тему и сообщение');
            return;
        }

        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/support/contact`, {
                method: 'POST',
                headers: getTgHeaders(),
                body: JSON.stringify({
                    subject: subject.trim(),
                    message: message.trim(),
                    email: email.trim() || null
                })
            });

            const data = await res.json();
            if (res.ok) {
                setSent(true);
                setSubject('');
                setMessage('');
                setEmail('');
                setTimeout(() => {
                    if (onBack) onBack();
                    else navigate('/profile');
                }, 2000);
            } else {
                alert(data.detail || 'Ошибка при отправке сообщения');
            }
        } catch (e) {
            alert('Ошибка: ' + e.message);
        } finally {
            setLoading(false);
        }
    };

    if (sent) {
        return (
            <div className="p-4 max-w-2xl mx-auto pb-32">
                <div className="bg-white p-8 rounded-3xl shadow-sm border border-slate-100 text-center">
                    <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Send className="text-emerald-600" size={32} />
                    </div>
                    <h2 className="text-2xl font-black text-slate-800 mb-2">Сообщение отправлено!</h2>
                    <p className="text-slate-600 mb-4">Мы свяжемся с вами в ближайшее время.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="p-4 max-w-2xl mx-auto pb-32">
            <div className="flex items-center gap-3 mb-6">
                <button 
                    onClick={onBack || (() => navigate('/profile'))} 
                    className="text-slate-400 hover:text-slate-600"
                >
                    <ArrowLeft size={24} />
                </button>
                <h1 className="text-2xl font-black text-slate-800">Служба поддержки</h1>
            </div>

            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                <div className="mb-6 p-4 bg-slate-50 rounded-2xl border border-slate-100">
                    <h3 className="font-bold text-sm text-slate-700 mb-2 flex items-center gap-2">
                        <MessageSquare size={16} className="text-indigo-600" />
                        Как мы можем помочь?
                    </h3>
                    <p className="text-xs text-slate-600 leading-relaxed">
                        Опишите вашу проблему или вопрос, и мы ответим вам в Telegram или на указанный email в ближайшее время.
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-5">
                    {/* Subject */}
                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-2">
                            <User size={14} /> Тема обращения
                        </label>
                        <input
                            type="text"
                            value={subject}
                            onChange={(e) => setSubject(e.target.value)}
                            placeholder="Например: Проблема с оплатой"
                            className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 transition-all placeholder:text-slate-400"
                            maxLength={100}
                            required
                        />
                    </div>

                    {/* Email (optional) */}
                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-2">
                            <Mail size={14} /> Email для ответа (необязательно)
                        </label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="your@email.com"
                            className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 transition-all placeholder:text-slate-400"
                        />
                    </div>

                    {/* Message */}
                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">
                            Ваше сообщение
                        </label>
                        <textarea
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            placeholder="Опишите вашу проблему или вопрос подробно..."
                            rows={8}
                            className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 transition-all placeholder:text-slate-400 resize-none"
                            maxLength={2000}
                            required
                        />
                        <div className="text-right mt-1">
                            <span className="text-xs text-slate-400">{message.length} / 2000</span>
                        </div>
                    </div>

                    {/* Submit Button */}
                    <button
                        type="submit"
                        disabled={loading || !subject.trim() || !message.trim()}
                        className={`w-full py-4 rounded-xl font-bold text-sm transition-all flex justify-center items-center gap-2 ${
                            loading || !subject.trim() || !message.trim()
                                ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                                : 'bg-indigo-600 text-white shadow-lg shadow-indigo-200 active:scale-95 hover:bg-indigo-700'
                        }`}
                    >
                        {loading ? (
                            <>
                                <Loader2 className="animate-spin" size={18} />
                                Отправка...
                            </>
                        ) : (
                            <>
                                <Send size={18} />
                                Отправить сообщение
                            </>
                        )}
                    </button>
                </form>

                <div className="mt-6 pt-6 border-t border-slate-100 text-center">
                    <p className="text-xs text-slate-500 mb-2">Также вы можете связаться с нами:</p>
                    <div className="flex justify-center gap-4 text-xs">
                        <a 
                            href="mailto:anton.sherbakov.01@gmail.com" 
                            className="text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1"
                        >
                            <Mail size={12} />
                            Email
                        </a>
                        <span className="text-slate-300">•</span>
                        <a 
                            href="https://t.me/AAntonShch" 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="text-indigo-600 hover:text-indigo-700 font-medium"
                        >
                            Telegram: @AAntonShch
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SupportPage;

