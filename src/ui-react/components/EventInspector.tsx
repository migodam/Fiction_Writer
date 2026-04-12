import React, { useEffect, useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { Save, Trash, Clock, MapPin, Users, BookOpen, ChevronRight, Info } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../i18n';

export const EventInspector = () => {
  const {
    timelineEvents, timelineBranches, characters, selectedEntity,
    addTimelineEvent, updateTimelineEvent, setSelectedEntity
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const navigate = useNavigate();
  const { t } = useI18n();

  const [editEvent, setEditEvent] = useState<any>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedEntity.type === 'timeline_event' && selectedEntity.id) {
      if (selectedEntity.id === 'new') {
        setEditEvent({
          id: 'event_' + Date.now(),
          title: '',
          summary: '',
          time: '',
          branchId: timelineBranches[0]?.id || 'branch_main',
          orderIndex: timelineEvents.length,
          locationIds: [],
          participantCharacterIds: [],
          linkedSceneIds: [],
          linkedWorldItemIds: [],
          tags: [],
        });
      } else {
        const event = timelineEvents.find(e => e.id === selectedEntity.id);
        if (event) {
          setEditEvent({
            ...event,
            location: event.locationIds[0]?.replace(/-/g, ' ') || '',
            participants: event.participantCharacterIds,
          });
        }
      }
      setValidationError(null);
    } else {
      setEditEvent(null);
    }
  }, [selectedEntity, timelineEvents, timelineBranches]);

  const handleSave = () => {
    if (!editEvent) return;
    if (!editEvent.title || !editEvent.summary) {
        setValidationError(t('event.validationError'));
        return;
    }

    const normalizedEvent = {
      ...editEvent,
      locationIds: editEvent.location
        ? [String(editEvent.location).trim().toLowerCase().replace(/\s+/g, '-')]
        : [],
      participantCharacterIds: editEvent.participants || [],
      linkedSceneIds: editEvent.linkedSceneIds || [],
      linkedWorldItemIds: editEvent.linkedWorldItemIds || [],
      tags: editEvent.tags || [],
    };

    delete normalizedEvent.location;
    delete normalizedEvent.participants;

    if (timelineEvents.find(e => e.id === editEvent.id)) {
      updateTimelineEvent(normalizedEvent);
    } else {
      addTimelineEvent(normalizedEvent);
    }
    setValidationError(null);
    setSelectedEntity(null, null);
    setLastActionStatus(t('event.saved'));
  };

  const toggleParticipant = (charId: string) => {
      const current = editEvent.participants || [];
      if (current.includes(charId)) {
          setEditEvent({ ...editEvent, participants: current.filter((id: string) => id !== charId) });
      } else {
          setEditEvent({ ...editEvent, participants: [...current, charId] });
      }
  };

  if (!editEvent) return null;

  return (
    <div className="flex flex-col h-full bg-bg-elev-1 animate-in slide-in-from-right duration-300">
      <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
         <div className="flex items-center gap-2">
           <div className="w-2.5 h-2.5 rounded-full bg-brand shadow-[0_0_8px_rgba(124,58,237,0.4)]"></div>
           <span className="text-[10px] font-black uppercase tracking-[0.25em] text-text-2">{t('event.config')}</span>
         </div>
         <button
            className="p-1.5 hover:bg-hover rounded-lg text-text-3 hover:text-red transition-all group"
            title={t('event.deleteEvent')}
         >
             <Trash size={16} className="group-active:scale-90" />
         </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
        {validationError && (
            <div className="p-3 bg-red/10 border border-red/30 rounded-lg flex items-center gap-2.5 text-red text-[10px] font-bold animate-in zoom-in-95">
                <Info size={14} />
                {validationError}
            </div>
        )}

        <div className="space-y-2 group">
          <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.2em] ml-1 group-focus-within:text-brand transition-colors">{t('event.title')}</label>
          <input
            data-testid="event-title-input"
            className="w-full bg-bg border border-border rounded-xl p-3.5 text-sm text-text focus:border-brand focus:ring-1 focus:ring-brand/30 outline-none transition-all shadow-inner"
            placeholder={t('event.titlePlaceholder')}
            value={editEvent.title}
            onChange={e => setEditEvent({...editEvent, title: e.target.value})}
          />
        </div>

        <div className="space-y-2 group">
          <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.2em] ml-1 group-focus-within:text-brand transition-colors">{t('event.summary')}</label>
          <textarea
            data-testid="event-summary-input"
            className="w-full h-40 bg-bg border border-border rounded-xl p-4 text-sm text-text-2 focus:border-brand focus:ring-1 focus:ring-brand/30 outline-none resize-none shadow-inner font-serif leading-relaxed"
            placeholder={t('event.summaryPlaceholder')}
            value={editEvent.summary}
            onChange={e => setEditEvent({...editEvent, summary: e.target.value})}
          />
        </div>

        <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2 group">
                <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.2em] ml-1 group-focus-within:text-brand transition-colors">{t('event.temporal')}</label>
                <div className="flex items-center bg-bg border border-border rounded-xl px-3.5 group-focus-within:border-brand transition-all shadow-inner">
                    <Clock size={14} className="text-text-3 group-focus-within:text-brand" />
                    <input
                        data-testid="event-time-input"
                        className="w-full bg-transparent p-3 text-[11px] text-text-2 outline-none font-mono"
                        placeholder={t('event.temporalPlaceholder')}
                        value={editEvent.time || ''}
                        onChange={e => setEditEvent({...editEvent, time: e.target.value})}
                    />
                </div>
            </div>
            <div className="space-y-2 group">
                <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.2em] ml-1 group-focus-within:text-brand transition-colors">{t('event.locus')}</label>
                <div className="flex items-center bg-bg border border-border rounded-xl px-3.5 group-focus-within:border-brand transition-all shadow-inner">
                    <MapPin size={14} className="text-text-3 group-focus-within:text-brand" />
                    <input
                        data-testid="event-location-input"
                        className="w-full bg-transparent p-3 text-[11px] text-text-2 outline-none"
                        placeholder={t('event.location')}
                        value={editEvent.location || ''}
                        onChange={e => setEditEvent({...editEvent, location: e.target.value})}
                    />
                </div>
            </div>
        </div>

        <div className="space-y-4">
          <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.2em] flex items-center justify-between ml-1">
            <span>{t('event.participants')}</span>
            <Users size={12} className="opacity-30" />
          </label>
          <div className="bg-bg border border-border rounded-xl p-4 min-h-[100px] shadow-inner">
             {characters.length === 0 ? (
                 <div className="text-[10px] text-text-3 italic text-center py-6 font-medium">{t('event.noEntities')}</div>
             ) : (
                 <div className="flex flex-wrap gap-2.5">
                    {characters.map(char => {
                        const isSelected = editEvent.participants?.includes(char.id);
                        return (
                            <div
                                key={char.id}
                                className={`px-3 py-1.5 rounded-lg border text-[10px] font-bold cursor-pointer transition-all active:scale-95 ${
                                    isSelected
                                    ? 'bg-brand border-brand text-white shadow-lg shadow-brand/20'
                                    : 'bg-bg-elev-2 border-border text-text-3 hover:border-brand-2 hover:text-text-2'
                                }`}
                                onClick={() => toggleParticipant(char.id)}
                            >
                                {char.name}
                            </div>
                        );
                    })}
                 </div>
             )}
          </div>
        </div>
      </div>

      <div className="p-6 border-t border-border flex flex-col gap-3 bg-bg-elev-2">
         <button
           data-testid="open-scene-btn"
           className="w-full py-2.5 border border-border hover:bg-bg hover:border-brand-2 text-text-2 text-[11px] font-bold uppercase tracking-widest rounded-lg flex items-center justify-center gap-2.5 transition-all shadow-sm group"
           onClick={() => navigate('/writing/scenes')}
         >
           <BookOpen size={16} className="text-text-3 group-hover:text-brand" /> {t('event.writingStudio')}
         </button>
         <button
           data-testid="inspector-save"
           className="w-full py-3 bg-brand hover:bg-brand-2 text-white text-[11px] font-bold uppercase tracking-widest rounded-xl flex items-center justify-center gap-2.5 transition-all shadow-2 active:scale-95 ring-1 ring-white/10"
           onClick={handleSave}
         >
           <Save size={16} /> {t('event.persist')}
         </button>
      </div>
    </div>
  );
};
