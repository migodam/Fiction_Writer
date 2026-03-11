import React, { useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { 
    Users, Heart, Brain, Search, MessageSquare, 
    Star, TrendingUp, ChevronDown, BarChart3,
    Sparkles, UserCheck, Flame, Zap
} from 'lucide-react';

export const BetaReaderWorkspace = () => {
  const { chapters, scenes } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  
  const [isRunning, setIsRunning] = useState(false);
  const [activeReader, setActiveReader] = useState<string | null>(null);

  const readers = [
    { id: 'read_1', name: 'The Logician', profile: 'Focuses on plot holes and cause-effect chains.', icon: <Brain size={14} />, color: 'text-blue' },
    { id: 'read_2', name: 'The Empath', profile: 'Tracks character emotional resonance and arcs.', icon: <Heart size={14} />, color: 'text-red' },
    { id: 'read_3', name: 'The Generalist', profile: 'Represents average reader enjoyment and pacing.', icon: <Star size={14} />, color: 'text-amber' },
  ];

  const handleRunSimulation = () => {
    setIsRunning(true);
    setTimeout(() => {
        setIsRunning(false);
        setLastActionStatus('Beta simulation complete');
    }, 2000);
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      {/* Left: Readers Panel */}
      <div className="w-72 border-r border-border flex flex-col bg-bg-elev-1 shadow-1" data-testid="beta-reader-list">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Synthetic Cohort</h3>
            <button className="p-1 hover:bg-hover rounded-lg text-brand transition-colors"><Users size={16} /></button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
            {readers.map(reader => (
                <div 
                    key={reader.id}
                    className={`px-4 py-4 rounded-xl cursor-pointer transition-all group ${
                        activeReader === reader.id ? 'bg-active text-text shadow-sm' : 'text-text-3 hover:bg-hover'
                    }`}
                    onClick={() => setActiveReader(reader.id)}
                >
                    <div className="flex items-center gap-3 mb-2">
                        <div className={`p-1.5 rounded-lg bg-bg border border-divider ${activeReader === reader.id ? reader.color : 'opacity-40'}`}>
                            {reader.icon}
                        </div>
                        <span className="text-[11px] font-black uppercase tracking-widest">{reader.name}</span>
                    </div>
                    <p className="text-[10px] opacity-60 leading-relaxed ml-9 font-medium">{reader.profile}</p>
                </div>
            ))}
        </div>
      </div>

      {/* Main Analysis View */}
      <div className="flex-1 flex flex-col bg-bg overflow-y-auto custom-scrollbar p-12">
        {activeReader ? (
            <div className="max-w-5xl mx-auto w-full animate-in fade-in duration-500">
                <div className="flex items-center justify-between mb-12">
                    <div className="flex items-center gap-5">
                        <div className="w-16 h-16 rounded-2xl bg-bg-elev-2 border border-border flex items-center justify-center text-brand shadow-2">
                            {readers.find(r => r.id === activeReader)?.icon && React.cloneElement(readers.find(r => r.id === activeReader)!.icon as any, { size: 32 })}
                        </div>
                        <div>
                            <h2 className="text-3xl font-black text-text uppercase tracking-tight">{readers.find(r => r.id === activeReader)?.name}</h2>
                            <div className="flex items-center gap-3 mt-1">
                                <span className="text-[10px] font-bold text-text-3 uppercase tracking-[0.3em]">Analysis Mode: {activeReader === 'read_1' ? 'Syntactic / Logical' : 'Affective / Emotional'}</span>
                                <div className="w-1 h-1 rounded-full bg-divider"></div>
                                <span className="text-[10px] font-bold text-green uppercase tracking-[0.3em]">Confidence: 94%</span>
                            </div>
                        </div>
                    </div>
                    <button 
                        data-testid="run-beta-reader-btn"
                        className={`px-10 py-3.5 bg-brand hover:bg-brand-2 text-white font-black rounded-xl text-[11px] uppercase tracking-widest shadow-2 active:scale-95 transition-all flex items-center gap-3 ring-1 ring-white/10 ${isRunning ? 'opacity-50 pointer-events-none' : ''}`}
                        onClick={handleRunSimulation}
                    >
                        {isRunning ? <Sparkles size={18} className="animate-spin" /> : <Flame size={18} />}
                        {isRunning ? 'Deconstructing...' : 'Ignite Simulation'}
                    </button>
                </div>

                {/* Sentiment Grid */}
                <div className="grid grid-cols-3 gap-6 mb-12">
                    <SentimentCard label="Engagement" value={82} icon={<TrendingUp size={14} />} color="bg-brand" />
                    <SentimentCard label="Retention" value={65} icon={<UserCheck size={14} />} color="bg-blue" />
                    <SentimentCard label="Resonance" value={91} icon={<Heart size={14} />} color="bg-red" />
                </div>

                {/* Detailed Feedback Feed */}
                <div className="space-y-6">
                    <div className="flex items-center gap-3 mb-8 opacity-40">
                        <MessageSquare size={16} />
                        <h3 className="text-[11px] font-black uppercase tracking-[0.4em]">Reader Impressions</h3>
                        <div className="h-px flex-1 bg-divider"></div>
                    </div>

                    <FeedbackItem 
                        title="Chapter 1: Pacing" 
                        text="The introduction of Alice is strong, but the transition to the market scene feels abrupt. I wanted more time to process her internal state."
                        tag="Pacing"
                        type="constructive"
                    />
                    <FeedbackItem 
                        title="Chapter 2: Logic" 
                        text="The revelation of the map makes sense, but how did Alice know the cipher? It wasn't established that she has a background in linguistics."
                        tag="Plot Hole"
                        type="critical"
                    />
                    <FeedbackItem 
                        title="Character: Bob" 
                        text="Bob's dialogue in the tavern is hilarious. Great consistency with his established voice."
                        tag="Voice"
                        type="positive"
                    />
                </div>
            </div>
        ) : (
            <div className="h-full flex flex-col items-center justify-center text-text-3 select-none">
                <Users size={120} className="opacity-5 mb-8" />
                <p className="text-[11px] font-black uppercase tracking-[0.5em] opacity-40 text-center">Beta Simulation Matrix<br/><span className="text-[9px] font-medium tracking-widest opacity-50 mt-4 block">Select a synthetic profile to generate feedback</span></p>
            </div>
        )}
      </div>
    </div>
  );
};

const SentimentCard = ({ label, value, icon, color }: { label: string, value: number, icon: any, color: string }) => (
    <div className="bg-bg-elev-1 border border-border rounded-2xl p-6 shadow-1 hover:border-brand/20 transition-all group">
        <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] font-black uppercase tracking-widest text-text-3">{label}</span>
            <div className={`p-1.5 rounded-lg bg-bg border border-divider text-text-3 group-hover:text-brand transition-colors`}>{icon}</div>
        </div>
        <div className="flex items-end gap-3">
            <span className="text-3xl font-black text-text leading-none">{value}%</span>
            <div className="flex-1 h-1.5 bg-bg rounded-full overflow-hidden mb-1 border border-divider">
                <div className={`h-full ${color} transition-all duration-1000 ease-out`} style={{ width: `${value}%` }}></div>
            </div>
        </div>
    </div>
);

const FeedbackItem = ({ title, text, tag, type }: { title: string, text: string, tag: string, type: 'positive' | 'critical' | 'constructive' }) => (
    <div className="bg-bg-elev-1 border border-border rounded-2xl p-6 hover:bg-bg-elev-2/50 transition-all group">
        <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-black text-text uppercase tracking-tight group-hover:text-brand transition-colors">{title}</h4>
            <span className={`text-[9px] font-black uppercase tracking-widest px-2.5 py-1 rounded-full border ${
                type === 'positive' ? 'bg-green/5 border-green/20 text-green' :
                type === 'critical' ? 'bg-red/5 border-red/20 text-red' :
                'bg-blue/5 border-blue/20 text-blue'
            }`}>{tag}</span>
        </div>
        <p className="text-sm text-text-2 leading-relaxed opacity-80">{text}</p>
    </div>
);
