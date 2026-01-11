import React, { useState, useEffect } from 'react';
import { API_URL, getTgHeaders } from '../config';

const StoriesBar = () => {
    const [stories, setStories] = useState([]);
    
    useEffect(() => {
        fetch(`${API_URL}/api/internal/stories`, {
             headers: getTgHeaders()
        }).then(r => r.json()).then(setStories).catch(console.error);
    }, []);

    if (stories.length === 0) return null;

    return (
        <div className="flex gap-3 overflow-x-auto pb-4 px-2 scrollbar-hide">
            {stories.map(s => (
                <div key={s.id} className="flex flex-col items-center gap-1 min-w-[64px]">
                    <div className={`w-14 h-14 rounded-full p-[2px] ${s.color}`}>
                        <div className="w-full h-full rounded-full bg-white border-2 border-transparent flex items-center justify-center flex-col">
                             <span className="text-[10px] font-bold text-center leading-tight">{s.val}</span>
                        </div>
                    </div>
                    <span className="text-[9px] font-medium text-slate-500">{s.title}</span>
                </div>
            ))}
        </div>
    )
}

export default StoriesBar;