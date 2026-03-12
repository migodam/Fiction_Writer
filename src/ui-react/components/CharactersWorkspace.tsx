import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useProjectStore, useUIStore } from '../store';
import { Plus, Check, X, User, Link as LinkIcon, Clock, Trash2, ChevronRight, UserPlus, Info, Sparkles, Upload, CalendarDays, ShieldCheck, Building2, Image as ImageIcon } from 'lucide-react';
import { projectService } from '../services/projectService';
import { useI18n } from '../i18n';

type CharacterTab = 'profile' | 'relationships' | 'timeline';

export const CharactersWorkspace = () => {
  const navigate = useNavigate();
  const { characterId } = useParams();
  const {
    characters,
    candidates,
    selectedEntity,
    setSelectedEntity,
    addCharacter,
    updateCharacter,
    confirmCandidate,
    rejectCandidate,
    relationships,
    addRelationship,
    deleteRelationship,
    timelineEvents,
    worldItems,
    projectRoot,
    scenes,
  } = useProjectStore();
  const { setLastActionStatus, sidebarSection } = useUIStore();
  const { t } = useI18n();

  const portraitInputRef = useRef<HTMLInputElement | null>(null);
  const [activeTab, setActiveTab] = useState<CharacterTab>('profile');
  const [editChar, setEditChar] = useState<any>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const showCandidates = sidebarSection === 'candidates';
  const invalidProfileId = Boolean(characterId && characterId !== 'new' && !characters.some((character) => character.id === characterId));

  useEffect(() => {
    if (!characterId) {
      return;
    }

    if (characterId === 'new') {
      if (selectedEntity.type !== 'character' || selectedEntity.id !== 'new') {
        setSelectedEntity('character', 'new');
      }
      setActiveTab('profile');
      return;
    }

    if (!invalidProfileId && (selectedEntity.type !== 'character' || selectedEntity.id !== characterId)) {
      setSelectedEntity('character', characterId);
    }
  }, [characterId, invalidProfileId, selectedEntity.id, selectedEntity.type, setSelectedEntity]);

  useEffect(() => {
    if (selectedEntity.type !== 'character' || !selectedEntity.id) {
      setEditChar(null);
      return;
    }

    if (selectedEntity.id === 'new') {
      setEditChar({
        id: `char_${Date.now()}`,
        name: '',
        summary: '',
        background: '',
        aliases: '',
        birthdayText: '',
        portraitAssetId: null,
        traits: '',
        goals: '',
        fears: '',
        secrets: '',
        speechStyle: '',
        arc: '',
        tagIds: [],
        organizationIds: [],
        linkedSceneIds: [],
        linkedEventIds: [],
        linkedWorldItemIds: [],
        statusFlags: { alive: true },
      });
      setValidationError(null);
      return;
    }

    const character = characters.find((item) => item.id === selectedEntity.id);
    if (character) {
      setEditChar({
        ...character,
        aliases: character.aliases.join(', '),
        organizationText: character.organizationIds.join(', '),
      });
      setValidationError(null);
    }
  }, [selectedEntity, characters]);

  const charRelationships = relationships.filter((relationship) => relationship.sourceId === selectedEntity.id || relationship.targetId === selectedEntity.id);
  const charEvents = timelineEvents.filter((event) => event.participantCharacterIds.includes(selectedEntity.id || ''));
  const linkedScenes = scenes.filter((scene) => scene.linkedCharacterIds.includes(selectedEntity.id || ''));

  const handleSave = () => {
    if (!editChar) {
      return;
    }
    if (!editChar.name || !editChar.background) {
      setValidationError('Name and background are required.');
      return;
    }

    const normalizedCharacter = {
      ...editChar,
      summary: editChar.summary || editChar.background,
      aliases: typeof editChar.aliases === 'string' ? editChar.aliases.split(',').map((value: string) => value.trim()).filter(Boolean) : editChar.aliases || [],
      organizationIds: typeof editChar.organizationText === 'string' ? editChar.organizationText.split(',').map((value: string) => value.trim()).filter(Boolean) : editChar.organizationIds || [],
    };
    delete normalizedCharacter.organizationText;

    if (characters.some((character) => character.id === normalizedCharacter.id)) {
      updateCharacter(normalizedCharacter);
    } else {
      addCharacter(normalizedCharacter);
    }

    setSelectedEntity('character', normalizedCharacter.id);
    navigate(`/characters/profile/${normalizedCharacter.id}`);
    setValidationError(null);
    setLastActionStatus(t('shell.saved'));
  };

  const handleConfirmCandidate = (candidateId: string) => {
    const confirmedId = confirmCandidate(candidateId);
    if (!confirmedId) {
      return;
    }
    setSelectedEntity('character', confirmedId);
    navigate(`/characters/profile/${confirmedId}`);
    setLastActionStatus(t('shell.saved'));
  };

  const handleUploadPortrait = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !editChar) {
      return;
    }

    const assetPath = await projectService.importAsset(file, 'portraits', projectRoot);
    setEditChar({ ...editChar, portraitAssetId: assetPath });
    setLastActionStatus('Portrait attached');
  };

  if (invalidProfileId) {
    return (
      <div className="flex h-full overflow-hidden bg-bg">
        <div className="flex-1 flex items-center justify-center px-12" data-testid="entity-not-found">
          <div className="max-w-xl rounded-2xl border border-red/30 bg-red/5 p-10 text-center shadow-1">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-red/30 text-red"><Info size={24} /></div>
            <h2 className="text-2xl font-bold text-text">{t('characters.notFound')}</h2>
            <button type="button" data-testid="entity-not-found-back" className="mt-6 inline-flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-[11px] font-bold uppercase tracking-widest text-text-2 transition-all hover:border-brand hover:text-text" onClick={() => navigate('/characters/list')}>
              {t('characters.backToList')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <div className="w-72 border-r border-border flex flex-col bg-bg-elev-1" data-testid="character-list">
        <div className="p-4 border-b border-border flex items-center justify-between gap-2 bg-bg-elev-2">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-text-3">{showCandidates ? t('characters.candidates') : t('characters.confirmed')}</h3>
          <div className="flex items-center gap-2">
            <button type="button" data-testid="generate-character-btn" className="rounded border border-border px-2.5 py-1 text-[9px] font-bold uppercase tracking-widest text-text-3 transition-colors hover:border-brand hover:text-text" onClick={() => setLastActionStatus('AI unavailable')}>
              {t('characters.generate')}
            </button>
            {!showCandidates && (
              <button type="button" data-testid="new-character-btn" className="p-1 hover:bg-hover rounded text-brand transition-colors" onClick={() => navigate('/characters/profile/new')}>
                <Plus size={16} />
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {showCandidates ? (
            <div className="p-3">
              {candidates.map((candidate) => (
                <div key={candidate.id} data-testid={`candidate-card-${candidate.id}`} className="p-4 mb-3 bg-card border border-border rounded-md shadow-1 group hover:border-border-2 transition-all">
                  <div className="font-bold text-sm mb-2 text-text">{candidate.name}</div>
                  <p className="text-[11px] text-text-2 mb-4 line-clamp-3 leading-relaxed opacity-80">{candidate.background}</p>
                  <div className="flex gap-2">
                    <button type="button" data-testid="candidate-confirm-btn" className="flex-1 py-1.5 bg-green text-text-invert rounded text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1.5" onClick={() => handleConfirmCandidate(candidate.id)}><Check size={12} /> Confirm</button>
                    <button type="button" data-testid="candidate-reject-btn" className="p-1.5 bg-bg-elev-2 hover:bg-red/20 hover:text-red border border-border rounded text-text-3 transition-colors" onClick={() => rejectCandidate(candidate.id)}><X size={14} /></button>
                  </div>
                </div>
              ))}
              {candidates.length === 0 && <div className="p-12 text-center"><UserPlus size={32} className="mx-auto mb-3 text-text-3 opacity-20" /><p className="text-[10px] text-text-3 uppercase font-bold tracking-widest">{t('characters.noCandidates')}</p></div>}
            </div>
          ) : (
            characters.map((character) => (
              <div key={character.id} data-testid={`character-card-${character.id}`} className={`p-4 border-b border-divider cursor-pointer hover:bg-hover transition-all group relative ${selectedEntity.id === character.id ? 'bg-selected' : ''}`} onClick={() => navigate(`/characters/profile/${character.id}`)}>
                {selectedEntity.id === character.id && <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand"></div>}
                <div className="flex items-center justify-between"><div className="font-bold text-sm text-text truncate pr-4">{character.name}</div><ChevronRight size={14} className={`transition-opacity text-text-3 ${selectedEntity.id === character.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`} /></div>
                <div className="text-[11px] text-text-2 truncate mt-1.5 opacity-80">{character.summary}</div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col bg-bg shadow-2xl relative z-0">
        {selectedEntity.id && !showCandidates ? (
          <>
            <div className="h-11 border-b border-border flex items-center px-8 gap-10 bg-bg-elev-1">
              <TabButton active={activeTab === 'profile'} label="Profile" onClick={() => setActiveTab('profile')} testId="char-tab-profile" />
              <TabButton active={activeTab === 'relationships'} label={t('characters.relationships')} onClick={() => setActiveTab('relationships')} testId="char-tab-relationships" />
              <TabButton active={activeTab === 'timeline'} label={t('characters.timeline')} onClick={() => setActiveTab('timeline')} testId="char-tab-timeline" />
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {activeTab === 'profile' && editChar && (
                <div className="max-w-5xl mx-auto p-12">
                  <div className="flex items-start gap-8 mb-12">
                    <div className="relative h-36 w-28 overflow-hidden rounded-2xl border border-border bg-bg-elev-2 shadow-1">
                      {editChar.portraitAssetId ? (
                        <img src={editChar.portraitAssetId} alt={editChar.name} className="h-full w-full object-cover" data-testid="character-portrait-preview" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-text-3"><ImageIcon size={36} /></div>
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="mb-1 text-brand text-[10px] font-bold uppercase tracking-[0.25em]">{t('characters.identity')}</div>
                      <input data-testid="character-name-input" className="bg-transparent text-5xl font-extrabold text-text outline-none w-full tracking-tight focus:text-brand transition-colors" placeholder="Character Name" value={editChar.name} onChange={(event) => setEditChar({ ...editChar, name: event.target.value })} />
                      <div className="mt-6 flex flex-wrap gap-3">
                        <button type="button" className="rounded-xl border border-border px-4 py-2 text-sm text-text" onClick={() => portraitInputRef.current?.click()} data-testid="character-upload-portrait-btn"><Upload size={14} className="inline mr-2" /> Upload Portrait</button>
                        <button type="button" className="rounded-xl border border-border px-4 py-2 text-sm text-text" onClick={() => setLastActionStatus('Portrait generator unavailable')} data-testid="character-generate-portrait-btn"><Sparkles size={14} className="inline mr-2" /> Generate Portrait</button>
                        <input ref={portraitInputRef} type="file" accept="image/*" className="hidden" onChange={handleUploadPortrait} data-testid="character-portrait-input" />
                      </div>
                    </div>
                  </div>

                  {validationError && <div className="mb-8 p-4 bg-red/10 border border-red/30 rounded-lg text-red text-xs font-bold">{validationError}</div>}

                  <div className="grid gap-10 xl:grid-cols-[1.5fr_1fr]">
                    <div className="space-y-8">
                      <Field label={t('characters.background')}>
                        <textarea data-testid="character-background-input" className="w-full h-44 bg-bg-elev-1 border border-border rounded-xl p-5 text-sm text-text-2 focus:border-brand outline-none transition-all font-serif leading-relaxed shadow-inner" value={editChar.background} onChange={(event) => setEditChar({ ...editChar, background: event.target.value })} />
                      </Field>
                      <div className="grid grid-cols-2 gap-6">
                        <Field label={t('characters.aliases')}>
                          <input data-testid="character-alias-input" className="w-full bg-bg-elev-1 border border-border rounded-lg p-3 text-sm text-text-2 focus:border-brand outline-none transition-all" value={editChar.aliases || ''} onChange={(event) => setEditChar({ ...editChar, aliases: event.target.value })} />
                        </Field>
                        <Field label={t('characters.traits')}>
                          <input data-testid="character-traits-input" className="w-full bg-bg-elev-1 border border-border rounded-lg p-3 text-sm text-text-2 focus:border-brand outline-none transition-all" value={editChar.traits || ''} onChange={(event) => setEditChar({ ...editChar, traits: event.target.value })} />
                        </Field>
                      </div>
                    </div>
                    <div className="space-y-6">
                      <Field label="Birthday"><div className="relative"><CalendarDays size={14} className="absolute left-3 top-3 text-text-3" /><input data-testid="character-birthday-input" className="w-full bg-bg-elev-1 border border-border rounded-lg py-3 pl-10 pr-3 text-sm text-text-2 focus:border-brand outline-none transition-all" value={editChar.birthdayText || ''} onChange={(event) => setEditChar({ ...editChar, birthdayText: event.target.value })} /></div></Field>
                      <Field label="Organizations"><div className="relative"><Building2 size={14} className="absolute left-3 top-3 text-text-3" /><input data-testid="character-organization-input" className="w-full bg-bg-elev-1 border border-border rounded-lg py-3 pl-10 pr-3 text-sm text-text-2 focus:border-brand outline-none transition-all" value={editChar.organizationText || ''} onChange={(event) => setEditChar({ ...editChar, organizationText: event.target.value })} /></div></Field>
                      <Field label="Status Flags">
                        <div className="grid gap-3">
                          {[
                            ['protagonist', 'Protagonist'],
                            ['antagonist', 'Antagonist'],
                            ['alive', 'Alive'],
                            ['deceased', 'Deceased'],
                          ].map(([key, label]) => (
                            <label key={key} className="flex items-center justify-between rounded-xl border border-border bg-bg px-4 py-3 text-sm text-text">
                              <span className="flex items-center gap-3"><ShieldCheck size={14} /> {label}</span>
                              <input type="checkbox" checked={Boolean(editChar.statusFlags?.[key])} onChange={(event) => setEditChar({ ...editChar, statusFlags: { ...editChar.statusFlags, [key]: event.target.checked } })} data-testid={`character-status-${key}`} />
                            </label>
                          ))}
                        </div>
                      </Field>
                    </div>
                  </div>

                  <div className="mt-10 rounded-2xl border border-border bg-card p-6 shadow-1">
                    <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Linked Scenes</div>
                    <div className="flex flex-wrap gap-3">
                      {linkedScenes.map((scene) => (
                        <button key={scene.id} type="button" className="rounded-xl border border-border px-4 py-2 text-sm text-text hover:border-brand" onClick={() => { setSelectedEntity('scene', scene.id); navigate('/writing/scenes'); }} data-testid="character-linked-scene-btn">
                          {scene.title}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="pt-10 flex justify-end gap-4 border-t border-divider mt-10">
                    <button type="button" data-testid="open-character-timeline-btn" className="px-5 py-3 border border-border hover:border-brand text-text-2 rounded-lg text-[11px] font-bold uppercase tracking-widest transition-all" onClick={() => navigate(`/timeline/events?character=${selectedEntity.id}`)}>{t('characters.timeline')}</button>
                    <button type="button" data-testid="open-character-relationships-btn" className="px-5 py-3 border border-border hover:border-brand text-text-2 rounded-lg text-[11px] font-bold uppercase tracking-widest transition-all" onClick={() => navigate('/graph/relationships')}>{t('characters.relationships')}</button>
                    <button type="button" data-testid="inspector-save" className="px-10 py-3 bg-brand hover:bg-brand-2 text-white font-bold rounded-lg text-[11px] uppercase tracking-widest shadow-2 transition-all flex items-center gap-2" onClick={handleSave}><Check size={16} /> {t('characters.persist')}</button>
                  </div>
                </div>
              )}

              {activeTab === 'relationships' && (
                <div className="max-w-4xl mx-auto p-12">
                  <div className="flex items-center justify-between mb-10">
                    <h2 className="text-2xl font-bold text-text flex items-center gap-3"><LinkIcon size={24} className="text-brand" /> {t('characters.network')}</h2>
                    <button type="button" className="px-5 py-2 border border-brand text-brand hover:bg-brand hover:text-white rounded-lg text-[11px] font-bold uppercase tracking-wider transition-all" onClick={() => {
                      const other = characters.find((character) => character.id !== selectedEntity.id);
                      if (other) {
                        addRelationship({ id: `rel_${Date.now()}`, sourceId: selectedEntity.id!, targetId: other.id, type: 'Ally' });
                      }
                    }} data-testid="add-relationship-btn">Add Relationship</button>
                  </div>
                  <div className="grid grid-cols-1 gap-4">
                    {charRelationships.map((relationship) => {
                      const otherId = relationship.sourceId === selectedEntity.id ? relationship.targetId : relationship.sourceId;
                      const otherCharacter = characters.find((character) => character.id === otherId);
                      return (
                        <div key={relationship.id} className="bg-bg-elev-1 border border-border rounded-xl p-5 flex items-center justify-between group hover:border-border-2 transition-all shadow-1" data-testid="relationship-card">
                          <div className="flex items-center gap-5">
                            <div className="w-12 h-12 bg-bg-elev-2 rounded-full flex items-center justify-center border border-border shadow-inner"><User size={22} className="text-text-3" /></div>
                            <div>
                              <div className="text-base font-bold text-text">{otherCharacter?.name || 'Unknown Entity'}</div>
                              <div className="inline-flex items-center px-2 py-0.5 rounded bg-brand/10 border border-brand/20 text-[10px] text-brand-2 uppercase font-bold tracking-widest mt-1.5">{relationship.type}</div>
                            </div>
                          </div>
                          <button type="button" className="p-2.5 text-text-3 hover:text-red hover:bg-red/10 rounded-lg opacity-0 group-hover:opacity-100 transition-all" onClick={() => deleteRelationship(relationship.id)}>
                            <Trash2 size={16} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {activeTab === 'timeline' && (
                <div className="max-w-4xl mx-auto p-12">
                  <h2 className="text-2xl font-bold text-text mb-12 flex items-center gap-3"><Clock size={24} className="text-brand" /> {t('characters.temporal')}</h2>
                  <div className="space-y-6 relative before:absolute before:left-[17px] before:top-2 before:bottom-2 before:w-0.5 before:bg-divider">
                    {charEvents.map((event) => (
                      <div key={event.id} className="relative pl-12 pb-10 last:pb-0" data-testid="char-timeline-event">
                        <div className="absolute left-0 top-1 w-[36px] h-[36px] rounded-full bg-bg border-2 border-brand flex items-center justify-center z-10 shadow-1"><div className="w-2 h-2 rounded-full bg-brand"></div></div>
                        <button type="button" className="w-full text-left bg-bg-elev-1 border border-border rounded-xl p-6 hover:border-brand/40 transition-all shadow-1" onClick={() => navigate(`/timeline/events?character=${selectedEntity.id}&event=${event.id}`)}>
                          <div className="flex items-center justify-between mb-3">
                            <div className="text-[10px] text-brand-2 font-black uppercase tracking-[0.2em]">{event.time || 'Timeline'}</div>
                            <ChevronRight size={14} className="text-text-3" />
                          </div>
                          <div className="text-lg font-bold text-text">{event.title}</div>
                          <p className="text-sm text-text-2 mt-3 line-clamp-3 leading-relaxed opacity-80">{event.summary}</p>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-text-3 select-none">
            {showCandidates ? <Sparkles size={140} className="opacity-5" /> : <User size={140} className="opacity-5" />}
          </div>
        )}
      </div>
    </div>
  );
};

const TabButton = ({ active, label, onClick, testId }: { active: boolean; label: string; onClick: () => void; testId: string }) => (
  <button type="button" data-testid={testId} className={`h-full px-1 text-[11px] font-bold uppercase tracking-[0.2em] transition-all relative ${active ? 'text-brand' : 'text-text-3 hover:text-text-2'}`} onClick={onClick}>
    {label}
    {active && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand rounded-t"></div>}
  </button>
);

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="group">
    <label className="block text-[10px] font-bold text-text-3 uppercase tracking-[0.3em] mb-4">{label}</label>
    {children}
  </div>
);
