import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useProjectStore, useUIStore } from '../store';
import {
  Plus,
  Check,
  X,
  User,
  Link as LinkIcon,
  Clock,
  Trash2,
  ChevronRight,
  UserPlus,
  Info,
  Sparkles,
} from 'lucide-react';

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
  } = useProjectStore();
  const { setLastActionStatus, sidebarSection } = useUIStore();

  const [activeTab, setActiveTab] = useState<CharacterTab>('profile');
  const [editChar, setEditChar] = useState<any>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const showCandidates = sidebarSection === 'candidates';
  const selectedCharacter = selectedEntity.type === 'character'
    ? characters.find((character) => character.id === selectedEntity.id) || null
    : null;
  const invalidProfileId = Boolean(
    characterId &&
    characterId !== 'new' &&
    !characters.some((character) => character.id === characterId)
  );

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

    if (invalidProfileId) {
      return;
    }

    if (selectedEntity.type !== 'character' || selectedEntity.id !== characterId) {
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
        background: '',
        aliases: '',
        traits: '',
      });
      setValidationError(null);
      return;
    }

    const character = characters.find((item) => item.id === selectedEntity.id);
    if (character) {
      setEditChar({ ...character });
      setValidationError(null);
    }
  }, [selectedEntity, characters]);

  const charRelationships = relationships.filter(
    (relationship) =>
      relationship.sourceId === selectedEntity.id || relationship.targetId === selectedEntity.id
  );
  const charEvents = timelineEvents.filter((event) =>
    event.participants?.includes(selectedEntity.id || '')
  );

  const handleSave = () => {
    if (!editChar) {
      return;
    }

    if (!editChar.name || !editChar.background) {
      setValidationError('Name and Background are required fields.');
      return;
    }

    const targetId = editChar.id;
    if (characters.some((character) => character.id === targetId)) {
      updateCharacter(editChar);
    } else {
      addCharacter(editChar);
    }

    setSelectedEntity('character', targetId);
    navigate(`/characters/profile/${targetId}`);
    setValidationError(null);
    setLastActionStatus('Saved');
  };

  const handleConfirmCandidate = (candidateId: string) => {
    const confirmedId = confirmCandidate(candidateId);
    if (!confirmedId) {
      return;
    }

    setSelectedEntity('character', confirmedId);
    setActiveTab('profile');
    navigate(`/characters/profile/${confirmedId}`);
    setLastActionStatus('Saved');
  };

  const handleRejectCandidate = (candidateId: string) => {
    rejectCandidate(candidateId);
    setLastActionStatus('Candidate rejected');
  };

  const handleCreateCharacter = () => {
    setActiveTab('profile');
    setSelectedEntity('character', 'new');
    navigate('/characters/profile/new');
  };

  if (invalidProfileId) {
    return (
      <div className="flex h-full overflow-hidden bg-bg">
        <div className="w-72 border-r border-border flex flex-col bg-bg-elev-1" data-testid="character-list">
          <div className="p-4 border-b border-border bg-bg-elev-2">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-text-3">
              Confirmed Characters
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            {characters.map((character) => (
              <div
                key={character.id}
                data-testid={`character-card-${character.id}`}
                className="p-4 border-b border-divider cursor-pointer hover:bg-hover transition-all group"
                onClick={() => navigate(`/characters/profile/${character.id}`)}
              >
                <div className="flex items-center justify-between">
                  <div className="font-bold text-sm text-text truncate pr-4">{character.name}</div>
                  <ChevronRight size={14} className="text-text-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <div className="text-[11px] text-text-2 truncate mt-1.5 opacity-80">
                  {character.background}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center px-12" data-testid="entity-not-found">
          <div className="max-w-xl rounded-2xl border border-red/30 bg-red/5 p-10 text-center shadow-1">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-red/30 text-red">
              <Info size={24} />
            </div>
            <h2 className="text-2xl font-bold text-text">Entity not found</h2>
            <p className="mt-3 text-sm text-text-2 leading-relaxed">
              The requested character profile does not exist in the current seed project.
            </p>
            <button
              type="button"
              data-testid="entity-not-found-back"
              className="mt-6 inline-flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-[11px] font-bold uppercase tracking-widest text-text-2 transition-all hover:border-brand hover:text-text"
              onClick={() => navigate('/characters/list')}
            >
              Back to Characters
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
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-text-3">
            {showCandidates ? 'Candidate Queue' : 'Confirmed Characters'}
          </h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="generate-character-btn"
              className="rounded border border-border px-2.5 py-1 text-[9px] font-bold uppercase tracking-widest text-text-3 transition-colors hover:border-brand hover:text-text"
              onClick={() => setLastActionStatus('AI unavailable')}
            >
              Generate
            </button>
            {!showCandidates && (
              <button
                type="button"
                data-testid="new-character-btn"
                className="p-1 hover:bg-hover rounded text-brand transition-colors"
                onClick={handleCreateCharacter}
              >
                <Plus size={16} />
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {showCandidates ? (
            <div className="p-3">
              {candidates.map((candidate) => (
                <div
                  key={candidate.id}
                  data-testid={`candidate-card-${candidate.id}`}
                  className="p-4 mb-3 bg-card border border-border rounded-md shadow-1 group hover:border-border-2 transition-all"
                >
                  <div className="font-bold text-sm mb-2 text-text">{candidate.name}</div>
                  <p className="text-[11px] text-text-2 mb-4 line-clamp-3 leading-relaxed opacity-80">
                    {candidate.background}
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      data-testid="candidate-confirm-btn"
                      className="flex-1 py-1.5 bg-green text-text-invert rounded text-[10px] font-bold uppercase tracking-wider flex items-center justify-center gap-1.5 hover:brightness-110 active:scale-95 transition-all"
                      onClick={() => handleConfirmCandidate(candidate.id)}
                    >
                      <Check size={12} /> Confirm
                    </button>
                    <button
                      type="button"
                      data-testid="candidate-reject-btn"
                      className="p-1.5 bg-bg-elev-2 hover:bg-red/20 hover:text-red border border-border rounded text-text-3 transition-colors"
                      onClick={() => handleRejectCandidate(candidate.id)}
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ))}
              {candidates.length === 0 && (
                <div className="p-12 text-center">
                  <UserPlus size={32} className="mx-auto mb-3 text-text-3 opacity-20" />
                  <p className="text-[10px] text-text-3 uppercase font-bold tracking-widest">
                    No Candidates
                  </p>
                </div>
              )}
            </div>
          ) : (
            <>
              {characters.map((character) => (
                <div
                  key={character.id}
                  data-testid={`character-card-${character.id}`}
                  className={`p-4 border-b border-divider cursor-pointer hover:bg-hover transition-all group relative ${
                    selectedEntity.id === character.id ? 'bg-selected' : ''
                  }`}
                  onClick={() => navigate(`/characters/profile/${character.id}`)}
                >
                  {selectedEntity.id === character.id && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand"></div>
                  )}
                  <div className="flex items-center justify-between">
                    <div className="font-bold text-sm text-text truncate pr-4">{character.name}</div>
                    <ChevronRight
                      size={14}
                      className={`transition-opacity text-text-3 ${
                        selectedEntity.id === character.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      }`}
                    />
                  </div>
                  <div className="text-[11px] text-text-2 truncate mt-1.5 opacity-80">
                    {character.background}
                  </div>
                </div>
              ))}
              {characters.length === 0 && (
                <div className="p-12 text-center">
                  <User size={32} className="mx-auto mb-3 text-text-3 opacity-20" />
                  <p className="text-[10px] text-text-3 uppercase font-bold tracking-widest">
                    No Characters
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col bg-bg shadow-2xl relative z-0">
        {selectedEntity.id && !showCandidates ? (
          <>
            <div className="h-11 border-b border-border flex items-center px-8 gap-10 bg-bg-elev-1">
              <TabButton active={activeTab === 'profile'} label="Profile" onClick={() => setActiveTab('profile')} testId="char-tab-profile" />
              <TabButton active={activeTab === 'relationships'} label="Relationships" onClick={() => setActiveTab('relationships')} testId="char-tab-relationships" />
              <TabButton active={activeTab === 'timeline'} label="Timeline" onClick={() => setActiveTab('timeline')} testId="char-tab-timeline" />
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {activeTab === 'profile' && editChar && (
                <div className="max-w-4xl mx-auto p-12 animate-in fade-in slide-in-from-bottom-2 duration-300">
                  <div className="flex items-start gap-8 mb-16">
                    <div className="w-24 h-24 bg-bg-elev-2 rounded-2xl flex items-center justify-center border border-border shadow-1 relative group overflow-hidden">
                      <User size={48} className="text-text-3 group-hover:scale-110 transition-transform duration-500" />
                      <div className="absolute inset-0 bg-brand/10 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                    </div>
                    <div className="flex-1 pt-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-brand text-[10px] font-bold uppercase tracking-[0.25em]">Identity Record</span>
                        <div className="h-px flex-1 bg-divider"></div>
                      </div>
                      <input
                        data-testid="character-name-input"
                        className="bg-transparent text-5xl font-extrabold text-text outline-none placeholder:text-text-3/20 w-full tracking-tight focus:text-brand transition-colors"
                        placeholder="Character Name"
                        value={editChar.name}
                        onChange={(event) => setEditChar({ ...editChar, name: event.target.value })}
                      />
                    </div>
                  </div>

                  {validationError && (
                    <div className="mb-8 p-4 bg-red/10 border border-red/30 rounded-lg flex items-center gap-3 text-red text-xs font-bold animate-in zoom-in duration-200">
                      <Info size={16} />
                      {validationError}
                    </div>
                  )}

                  <div className="space-y-10">
                    <Field label="Background & Origins">
                      <textarea
                        data-testid="character-background-input"
                        className="w-full h-48 bg-bg-elev-1 border border-border rounded-xl p-5 text-sm text-text-2 focus:border-brand focus:ring-1 focus:ring-brand/30 outline-none transition-all font-serif leading-relaxed shadow-inner"
                        placeholder="Describe their history, motivations, and the secrets that define them..."
                        value={editChar.background}
                        onChange={(event) => setEditChar({ ...editChar, background: event.target.value })}
                      />
                    </Field>

                    <div className="grid grid-cols-2 gap-10">
                      <Field label="Aliases / Titles">
                        <input
                          data-testid="character-alias-input"
                          className="w-full bg-bg-elev-1 border border-border rounded-lg p-3 text-sm text-text-2 focus:border-brand focus:ring-1 focus:ring-brand/30 outline-none transition-all"
                          placeholder="Nicknames, ranks, or hidden names"
                          value={editChar.aliases || ''}
                          onChange={(event) => setEditChar({ ...editChar, aliases: event.target.value })}
                        />
                      </Field>
                      <Field label="Distinguishing Traits">
                        <input
                          data-testid="character-traits-input"
                          className="w-full bg-bg-elev-1 border border-border rounded-lg p-3 text-sm text-text-2 focus:border-brand focus:ring-1 focus:ring-brand/30 outline-none transition-all"
                          placeholder="Physical or behavioral markers"
                          value={editChar.traits || ''}
                          onChange={(event) => setEditChar({ ...editChar, traits: event.target.value })}
                        />
                      </Field>
                    </div>

                    <div className="pt-16 flex justify-end gap-4 border-t border-divider">
                      <button
                        type="button"
                        data-testid="open-character-timeline-btn"
                        className="px-5 py-3 border border-border hover:border-brand text-text-2 hover:text-text rounded-lg text-[11px] font-bold uppercase tracking-widest transition-all"
                        onClick={() => navigate('/timeline/events')}
                      >
                        Timeline
                      </button>
                      <button
                        type="button"
                        data-testid="open-character-relationships-btn"
                        className="px-5 py-3 border border-border hover:border-brand text-text-2 hover:text-text rounded-lg text-[11px] font-bold uppercase tracking-widest transition-all"
                        onClick={() => navigate('/graph/relationships')}
                      >
                        Relationships
                      </button>
                      <button
                        type="button"
                        data-testid="inspector-save"
                        className="px-10 py-3 bg-brand hover:bg-brand-2 text-white font-bold rounded-lg text-[11px] uppercase tracking-widest shadow-2 active:scale-95 transition-all flex items-center gap-2"
                        onClick={handleSave}
                      >
                        <Check size={16} /> Persist Record
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'relationships' && (
                <div className="max-w-4xl mx-auto p-12 animate-in fade-in duration-300">
                  <div className="flex items-center justify-between mb-10">
                    <h2 className="text-2xl font-bold text-text flex items-center gap-3">
                      <LinkIcon size={24} className="text-brand" /> Network Matrix
                    </h2>
                    <button
                      type="button"
                      className="px-5 py-2 border border-brand text-brand hover:bg-brand hover:text-white rounded-lg text-[11px] font-bold uppercase tracking-wider transition-all active:scale-95"
                      onClick={() => {
                        const other = characters.find((character) => character.id !== selectedEntity.id);
                        if (other) {
                          addRelationship({
                            id: `rel_${Date.now()}`,
                            sourceId: selectedEntity.id!,
                            targetId: other.id,
                            type: 'Ally',
                          });
                        }
                      }}
                      data-testid="add-relationship-btn"
                    >
                      Forge Connection
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-4">
                    {charRelationships.map((relationship) => {
                      const otherId = relationship.sourceId === selectedEntity.id
                        ? relationship.targetId
                        : relationship.sourceId;
                      const otherCharacter = characters.find((character) => character.id === otherId);
                      return (
                        <div
                          key={relationship.id}
                          className="bg-bg-elev-1 border border-border rounded-xl p-5 flex items-center justify-between group hover:border-border-2 transition-all shadow-1"
                          data-testid="relationship-card"
                        >
                          <div className="flex items-center gap-5">
                            <div className="w-12 h-12 bg-bg-elev-2 rounded-full flex items-center justify-center border border-border shadow-inner">
                              <User size={22} className="text-text-3" />
                            </div>
                            <div>
                              <div className="text-base font-bold text-text">
                                {otherCharacter?.name || 'Unknown Entity'}
                              </div>
                              <div className="inline-flex items-center px-2 py-0.5 rounded bg-brand/10 border border-brand/20 text-[10px] text-brand-2 uppercase font-bold tracking-widest mt-1.5">
                                {relationship.type}
                              </div>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="p-2.5 text-text-3 hover:text-red hover:bg-red/10 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                            onClick={() => deleteRelationship(relationship.id)}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      );
                    })}
                    {charRelationships.length === 0 && (
                      <div className="py-24 border-2 border-dashed border-divider rounded-2xl flex flex-col items-center justify-center text-text-3 opacity-40">
                        <LinkIcon size={48} className="mb-4" />
                        <p className="text-xs uppercase font-bold tracking-[0.3em]">No Neural Connections</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'timeline' && (
                <div className="max-w-4xl mx-auto p-12 animate-in fade-in duration-300">
                  <h2 className="text-2xl font-bold text-text mb-12 flex items-center gap-3">
                    <Clock size={24} className="text-brand" /> Temporal Presence
                  </h2>
                  <div className="space-y-6 relative before:absolute before:left-[17px] before:top-2 before:bottom-2 before:w-0.5 before:bg-divider">
                    {charEvents.map((event) => (
                      <div key={event.id} className="relative pl-12 pb-10 last:pb-0" data-testid="char-timeline-event">
                        <div className="absolute left-0 top-1 w-[36px] h-[36px] rounded-full bg-bg border-2 border-brand flex items-center justify-center z-10 shadow-1">
                          <div className="w-2 h-2 rounded-full bg-brand animate-pulse"></div>
                        </div>
                        <div className="bg-bg-elev-1 border border-border rounded-xl p-6 hover:border-brand/40 transition-all cursor-pointer shadow-1 group">
                          <div className="flex items-center justify-between mb-3">
                            <div className="text-[10px] text-brand-2 font-black uppercase tracking-[0.2em]">
                              {event.time || 'Timestamp Undefined'}
                            </div>
                            <ChevronRight size={14} className="text-text-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                          <div className="text-lg font-bold text-text group-hover:text-brand transition-colors">
                            {event.title}
                          </div>
                          <p className="text-sm text-text-2 mt-3 line-clamp-3 leading-relaxed opacity-80">
                            {event.summary}
                          </p>
                        </div>
                      </div>
                    ))}
                    {charEvents.length === 0 && (
                      <div className="py-24 border-2 border-dashed border-divider rounded-2xl flex flex-col items-center justify-center text-text-3 opacity-40">
                        <Clock size={48} className="mb-4" />
                        <p className="text-xs uppercase font-bold tracking-[0.3em]">No Temporal Records</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-text-3 select-none">
            <div className="relative mb-8">
              {showCandidates ? (
                <Sparkles size={140} className="opacity-5" />
              ) : (
                <User size={140} className="opacity-5" />
              )}
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-24 h-24 rounded-full border border-divider animate-ping opacity-10"></div>
              </div>
            </div>
            <p className="text-[11px] font-bold uppercase tracking-[0.5em] opacity-40">
              {showCandidates ? 'Review Candidates' : 'Awaiting Selection'}
            </p>
            <p className="text-[9px] mt-4 opacity-20 uppercase tracking-widest font-medium">
              {showCandidates
                ? 'Confirm or reject candidates from the queue'
                : 'Select a character record from the left panel'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

const TabButton = ({
  active,
  label,
  onClick,
  testId,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  testId: string;
}) => (
  <button
    type="button"
    data-testid={testId}
    className={`h-full px-1 text-[11px] font-bold uppercase tracking-[0.2em] transition-all relative ${
      active ? 'text-brand' : 'text-text-3 hover:text-text-2'
    }`}
    onClick={onClick}
  >
    {label}
    {active && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand rounded-t shadow-[0_-4px_10px_rgba(124,58,237,0.3)]"></div>}
  </button>
);

const Field = ({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) => (
  <div className="group">
    <label className="block text-[10px] font-bold text-text-3 uppercase tracking-[0.3em] mb-4 group-focus-within:text-brand transition-colors">
      {label}
    </label>
    {children}
  </div>
);
