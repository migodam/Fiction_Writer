import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Building2, Check, ChevronRight, Clock3, Image as ImageIcon, Info, Link2, Plus, Search, Sparkles, Tag, Trash2, Upload, User, UserPlus } from 'lucide-react';
import { projectService } from '../services/projectService';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

export const CharactersWorkspace = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { characterId } = useParams();
  const [searchParams] = useSearchParams();
  const {
    characters,
    characterTags,
    candidates,
    relationships,
    timelineEvents,
    scenes,
    projectRoot,
    selectedEntity,
    setSelectedEntity,
    addCharacter,
    updateCharacter,
    addCharacterTag,
    updateCharacterTag,
    deleteCharacterTag,
    toggleCharacterTagMembership,
    confirmCandidate,
    rejectCandidate,
    addRelationship,
    deleteRelationship,
  } = useProjectStore();
  const { setLastActionStatus, openContextMenu } = useUIStore();
  const { t } = useI18n();

  const portraitInputRef = useRef<HTMLInputElement | null>(null);
  const [editChar, setEditChar] = useState<(typeof characters)[number] & { aliasesText: string; organizationText: string } | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [relationshipFilter, setRelationshipFilter] = useState('');
  const [tagDraft, setTagDraft] = useState({ name: '', color: '#f59e0b', description: '' });

  const isCandidatesRoute = location.pathname.endsWith('/candidates');
  const isRelationshipsRoute = location.pathname.endsWith('/relationships');
  const isTagsRoute = location.pathname.endsWith('/tags');
  const isListRoute = location.pathname.endsWith('/list');
  const isProfileRoute = location.pathname.includes('/profile/');
  const activeProfilePanel = searchParams.get('panel') === 'timeline' ? 'timeline' : 'profile';
  const invalidProfileId = Boolean(characterId && characterId !== 'new' && !characters.some((character) => character.id === characterId));

  const selectedCharacterId =
    characterId && characterId !== 'new'
      ? characterId
      : selectedEntity.type === 'character'
      ? selectedEntity.id
      : characters[0]?.id || null;
  const selectedCharacter = characters.find((character) => character.id === selectedCharacterId) || null;

  useEffect(() => {
    if (characterId === 'new') {
      setEditChar({
        id: `char_${Date.now()}`,
        name: '',
        summary: '',
        background: '',
        aliases: [],
        aliasesText: '',
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
        organizationText: '',
        linkedSceneIds: [],
        linkedEventIds: [],
        linkedWorldItemIds: [],
        statusFlags: { alive: true },
      });
      setSelectedEntity('character', 'new');
      return;
    }

    if (!selectedCharacter) {
      setEditChar(null);
      return;
    }

    setSelectedEntity('character', selectedCharacter.id);
    setEditChar({
      ...selectedCharacter,
      aliasesText: selectedCharacter.aliases.join(', '),
      organizationText: selectedCharacter.organizationIds.join(', '),
    });
  }, [characterId, selectedCharacter, setSelectedEntity]);

  const charRelationships = relationships.filter((relationship) => !selectedCharacterId || relationship.sourceId === selectedCharacterId || relationship.targetId === selectedCharacterId);
  const charTimeline = timelineEvents.filter((event) => !selectedCharacterId || event.participantCharacterIds.includes(selectedCharacterId));
  const linkedScenes = scenes.filter((scene) => !selectedCharacterId || scene.linkedCharacterIds.includes(selectedCharacterId));
  const filteredRelationships = charRelationships.filter((relationship) => {
    if (!relationshipFilter) return true;
    const otherId = relationship.sourceId === selectedCharacterId ? relationship.targetId : relationship.sourceId;
    const other = characters.find((character) => character.id === otherId);
    return `${relationship.type} ${other?.name || ''}`.toLowerCase().includes(relationshipFilter.toLowerCase());
  });

  const openCharacterPanel = (panel: 'profile' | 'timeline' | 'relationships') => {
    if (!selectedCharacterId) return;
    if (panel === 'relationships') {
      navigate('/characters/relationships');
      return;
    }
    navigate(panel === 'timeline' ? `/characters/profile/${selectedCharacterId}?panel=timeline` : `/characters/profile/${selectedCharacterId}`);
  };

  const handleSave = () => {
    if (!editChar || !editChar.name.trim() || !editChar.background.trim()) {
      setValidationError('Name and background are required.');
      return;
    }
    const normalized = {
      ...editChar,
      name: editChar.name.trim(),
      background: editChar.background.trim(),
      summary: editChar.summary || editChar.background.trim(),
      aliases: editChar.aliasesText.split(',').map((value) => value.trim()).filter(Boolean),
      organizationIds: editChar.organizationText.split(',').map((value) => value.trim()).filter(Boolean),
    };
    delete (normalized as { aliasesText?: string }).aliasesText;
    delete (normalized as { organizationText?: string }).organizationText;
    if (characters.some((character) => character.id === normalized.id)) updateCharacter(normalized);
    else addCharacter(normalized);
    navigate(`/characters/profile/${normalized.id}`);
    setValidationError(null);
    setLastActionStatus(t('shell.saved'));
  };

  const handleUploadPortrait = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !editChar) return;
    const assetPath = await projectService.importAsset(file, 'portraits', projectRoot);
    setEditChar({ ...editChar, portraitAssetId: assetPath });
    setLastActionStatus('Portrait attached');
  };

  if (invalidProfileId) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="entity-not-found">
        <div className="rounded-3xl border border-red/30 bg-red/5 p-10 text-center shadow-1">
          <Info className="mx-auto mb-4 text-red" size={24} />
          <h2 className="text-2xl font-black text-text">{t('characters.notFound')}</h2>
          <button type="button" data-testid="entity-not-found-back" className="mt-6 rounded-xl border border-border px-5 py-2 text-sm text-text-2 hover:border-brand hover:text-text" onClick={() => navigate('/characters/list')}>
            {t('characters.backToList')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-72 border-r border-border bg-bg-elev-1" data-testid="character-list">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('routes.characters.label')}</div>
              <div className="text-sm font-black text-text">{isCandidatesRoute ? t('characters.candidates') : t('characters.confirmed')}</div>
            </div>
            {!isCandidatesRoute && (
              <button type="button" data-testid="new-character-btn" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => navigate('/characters/profile/new')}>
                <Plus size={16} />
              </button>
            )}
          </div>
          <div className="rounded-2xl border border-border bg-bg px-3 py-2 text-sm text-text-2">
            <div className="flex items-center gap-2"><Search size={13} /> {characters.length} profiles</div>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar">
          {isCandidatesRoute ? (
            <div className="space-y-3 p-3">
              {candidates.map((candidate) => (
                <div key={candidate.id} data-testid={`candidate-card-${candidate.id}`} className="rounded-2xl border border-border bg-card p-4">
                  <div className="text-sm font-black text-text">{candidate.name}</div>
                  <p className="mt-2 text-xs leading-relaxed text-text-2">{candidate.background}</p>
                  <div className="mt-4 flex gap-2">
                    <button type="button" data-testid="candidate-confirm-btn" className="flex-1 rounded-xl bg-green px-3 py-2 text-[11px] font-black uppercase tracking-wider text-text-invert" onClick={() => {
                      const confirmedId = confirmCandidate(candidate.id);
                      if (confirmedId) navigate(`/characters/profile/${confirmedId}`);
                    }}>
                      <Check size={12} className="mr-2 inline" />Confirm
                    </button>
                    <button type="button" data-testid="candidate-reject-btn" className="rounded-xl border border-red/40 px-3 py-2 text-red" onClick={() => rejectCandidate(candidate.id)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
              {!candidates.length && <div className="p-10 text-center text-text-3"><UserPlus className="mx-auto mb-3 opacity-30" /><div className="text-xs uppercase tracking-[0.3em]">{t('characters.noCandidates')}</div></div>}
            </div>
          ) : (
            characters.map((character) => (
              <button
                type="button"
                key={character.id}
                data-testid={`character-card-${character.id}`}
                className={cn('relative flex w-full items-center justify-between border-b border-divider px-4 py-4 text-left transition-colors', selectedCharacterId === character.id ? 'bg-selected text-text' : 'text-text-2 hover:bg-hover')}
                onClick={() => navigate(isListRoute || isRelationshipsRoute || isTagsRoute ? `/characters/profile/${character.id}` : `/characters/profile/${character.id}`)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  openContextMenu({
                    x: event.clientX,
                    y: event.clientY,
                    items: [
                      { id: 'open', label: 'Open Profile', action: () => navigate(`/characters/profile/${character.id}`) },
                      { id: 'timeline', label: 'Open Timeline', action: () => navigate(`/timeline/events?character=${character.id}`) },
                      { id: 'graph', label: 'Open Relationship Graph', action: () => navigate('/graph/relationships') },
                    ],
                  });
                }}
              >
                <div className="pr-3">
                  <div className="text-sm font-black">{character.name}</div>
                  <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-text-3">{character.summary}</div>
                </div>
                <ChevronRight size={14} />
              </button>
            ))
          )}
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">
        {isRelationshipsRoute ? (
          <div className="h-full overflow-y-auto custom-scrollbar p-8">
            {selectedCharacter && (
              <CharacterTabs active="relationships" onSelect={openCharacterPanel} />
            )}
            <div className="mb-6 flex items-center justify-between gap-4">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Relationship network</div>
                <h2 className="text-3xl font-black text-text">{selectedCharacter?.name || 'Character Network'}</h2>
              </div>
              <button type="button" data-testid="add-relationship-btn" className="rounded-xl border border-brand px-4 py-3 text-sm font-bold text-brand" onClick={() => {
                const source = selectedCharacterId || characters[0]?.id;
                const target = characters.find((character) => character.id !== source);
                if (!source || !target) return;
                addRelationship({ id: `rel_${Date.now()}`, sourceId: source, targetId: target.id, type: 'New bond', description: 'Editable connection', strength: 50 });
                setLastActionStatus('Relationship created');
              }}>
                <Plus size={14} className="mr-2 inline" />Add Relationship
              </button>
            </div>
            <div className="mb-6 rounded-2xl border border-border bg-bg px-4 py-3">
              <div className="flex items-center gap-2"><Search size={14} /><input value={relationshipFilter} onChange={(event) => setRelationshipFilter(event.target.value)} placeholder="Filter by type or character..." className="w-full bg-transparent outline-none" /></div>
            </div>
            <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-3xl border border-border bg-card p-6 shadow-1">
                <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Network view</div>
                <div className="grid gap-4 md:grid-cols-2">
                  {filteredRelationships.map((relationship) => {
                    const otherId = relationship.sourceId === selectedCharacterId ? relationship.targetId : relationship.sourceId;
                    const other = characters.find((character) => character.id === otherId);
                    return (
                      <div key={relationship.id} data-testid="relationship-card" className="rounded-2xl border border-border bg-bg-elev-1 p-5" onContextMenu={(event) => {
                        event.preventDefault();
                        openContextMenu({ x: event.clientX, y: event.clientY, items: [{ id: 'delete-rel', label: 'Delete Relationship', action: () => deleteRelationship(relationship.id), destructive: true }] });
                      }}>
                        <div className="mb-2 flex items-center justify-between">
                          <div className="text-sm font-black text-text">{other?.name || relationship.targetId}</div>
                          <div className="rounded-full border border-brand/30 bg-brand/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-brand-2">{relationship.type}</div>
                        </div>
                        <div className="text-xs leading-relaxed text-text-2">{relationship.description}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="rounded-3xl border border-border bg-card p-6 shadow-1">
                <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Presence on timeline</div>
                <div className="space-y-3">
                  {charTimeline.map((event) => (
                    <button key={event.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand" onClick={() => navigate(`/timeline/events?character=${selectedCharacterId}&event=${event.id}`)}>
                      <div>
                        <div className="text-sm font-bold text-text">{event.title}</div>
                        <div className="mt-1 text-[11px] uppercase tracking-[0.2em] text-text-3">{event.time}</div>
                      </div>
                      <Clock3 size={14} />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : isTagsRoute ? (
          <div className="h-full overflow-y-auto custom-scrollbar p-8">
            <div className="mb-8 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Tag system</div>
                <h2 className="text-3xl font-black text-text">Character Tags</h2>
              </div>
            </div>
            <div className="mb-8 grid gap-4 rounded-3xl border border-border bg-card p-6 lg:grid-cols-[1fr_1fr_auto_auto]">
              <input value={tagDraft.name} onChange={(event) => setTagDraft({ ...tagDraft, name: event.target.value })} placeholder="Tag name" className="rounded-xl border border-border bg-bg px-4 py-3 outline-none" />
              <input value={tagDraft.description} onChange={(event) => setTagDraft({ ...tagDraft, description: event.target.value })} placeholder="Description" className="rounded-xl border border-border bg-bg px-4 py-3 outline-none" />
              <input value={tagDraft.color} onChange={(event) => setTagDraft({ ...tagDraft, color: event.target.value })} className="h-12 rounded-xl border border-border bg-bg px-4 py-3 outline-none" />
              <button type="button" className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white" onClick={() => {
                if (!tagDraft.name.trim()) return;
                addCharacterTag({ id: `tag_${Date.now()}`, name: tagDraft.name.trim(), color: tagDraft.color, description: tagDraft.description.trim(), characterIds: [] });
                setTagDraft({ name: '', color: '#f59e0b', description: '' });
                setLastActionStatus('Tag created');
              }}>
                <Plus size={14} className="mr-2 inline" />Create Tag
              </button>
            </div>
            <div className="grid gap-5 lg:grid-cols-2">
              {characterTags.map((tagEntry) => (
                <div key={tagEntry.id} className="rounded-3xl border border-border bg-card p-6 shadow-1">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-3 w-3 rounded-full" style={{ background: tagEntry.color }} />
                      <div>
                        <div className="text-lg font-black text-text">{tagEntry.name}</div>
                        <div className="text-sm text-text-2">{tagEntry.description}</div>
                      </div>
                    </div>
                    <button type="button" className="rounded-xl border border-red/40 px-3 py-2 text-red" onClick={() => deleteCharacterTag(tagEntry.id)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {characters.map((character) => {
                      const active = tagEntry.characterIds.includes(character.id);
                      return (
                        <button key={character.id} type="button" className={cn('rounded-full border px-3 py-2 text-xs font-bold transition-colors', active ? 'border-brand bg-brand/15 text-brand-2' : 'border-border text-text-2 hover:border-brand')} onClick={() => toggleCharacterTagMembership(tagEntry.id, character.id)}>
                          <Tag size={10} className="mr-2 inline" />{character.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="h-full overflow-y-auto custom-scrollbar p-10">
            {editChar ? (
              <div className="mx-auto max-w-5xl">
                <CharacterTabs active={activeProfilePanel} onSelect={openCharacterPanel} />
                <div className="mb-10 flex items-start gap-8">
                  <div className="relative h-44 w-32 overflow-hidden rounded-3xl border border-border bg-bg-elev-2">
                    {editChar.portraitAssetId ? <img src={editChar.portraitAssetId} alt={editChar.name} className="h-full w-full object-cover" data-testid="character-portrait-preview" /> : <div className="flex h-full items-center justify-center text-text-3"><ImageIcon size={42} /></div>}
                  </div>
                  <div className="flex-1">
                    <div className="mb-2 text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('characters.identity')}</div>
                    <input data-testid="character-name-input" value={editChar.name} onChange={(event) => setEditChar({ ...editChar, name: event.target.value })} placeholder="Character Name" className="w-full bg-transparent text-5xl font-black tracking-tight outline-none" />
                    <div className="mt-6 flex flex-wrap gap-3">
                      <button type="button" data-testid="character-upload-portrait-btn" className="rounded-xl border border-border px-4 py-2 text-sm text-text" onClick={() => portraitInputRef.current?.click()}><Upload size={14} className="mr-2 inline" />Upload Portrait</button>
                      <button type="button" data-testid="character-generate-portrait-btn" className="rounded-xl border border-border px-4 py-2 text-sm text-text" onClick={() => setLastActionStatus('Portrait generator unavailable')}><Sparkles size={14} className="mr-2 inline" />Generate Portrait</button>
                      <input ref={portraitInputRef} type="file" accept="image/*" className="hidden" onChange={handleUploadPortrait} data-testid="character-portrait-input" />
                    </div>
                  </div>
                </div>
                {validationError && <div className="mb-8 rounded-2xl border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">{validationError}</div>}
                <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
                  <div className="space-y-6">
                    <textarea data-testid="character-background-input" value={editChar.background} onChange={(event) => setEditChar({ ...editChar, background: event.target.value })} className="h-56 w-full rounded-3xl border border-border bg-bg-elev-1 p-6 font-serif text-sm leading-relaxed text-text-2 outline-none" />
                    <input data-testid="character-alias-input" value={editChar.aliasesText} onChange={(event) => setEditChar({ ...editChar, aliasesText: event.target.value })} placeholder="Aliases, comma separated" className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
                    <input data-testid="character-traits-input" value={editChar.traits || ''} onChange={(event) => setEditChar({ ...editChar, traits: event.target.value })} placeholder="Traits" className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
                  </div>
                  <div className="space-y-4">
                    <input data-testid="character-birthday-input" value={editChar.birthdayText || ''} onChange={(event) => setEditChar({ ...editChar, birthdayText: event.target.value })} placeholder="Birthday" className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
                    <div className="relative">
                      <Building2 size={14} className="absolute left-4 top-4 text-text-3" />
                      <input data-testid="character-organization-input" value={editChar.organizationText} onChange={(event) => setEditChar({ ...editChar, organizationText: event.target.value })} placeholder="Organizations" className="w-full rounded-2xl border border-border bg-bg py-3 pl-11 pr-4 outline-none" />
                    </div>
                    <div className="rounded-3xl border border-border bg-card p-4">
                      <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Tags</div>
                      <div className="flex flex-wrap gap-2">
                        {characterTags.map((tagEntry) => (
                          <button key={tagEntry.id} type="button" className={cn('rounded-full border px-3 py-2 text-xs font-bold', editChar.tagIds.includes(tagEntry.id) ? 'border-brand bg-brand/15 text-brand-2' : 'border-border text-text-2')} onClick={() => setEditChar({ ...editChar, tagIds: editChar.tagIds.includes(tagEntry.id) ? editChar.tagIds.filter((id) => id !== tagEntry.id) : [...editChar.tagIds, tagEntry.id] })}>
                            {tagEntry.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="mt-10 flex flex-wrap gap-3 rounded-3xl border border-border bg-card p-5">
                  {linkedScenes.map((scene) => (
                    <button key={scene.id} type="button" data-testid="character-linked-scene-btn" className="rounded-xl border border-border px-4 py-2 text-sm text-text hover:border-brand" onClick={() => navigate(`/writing/scenes?scene=${scene.id}`)}>
                      {scene.title}
                    </button>
                  ))}
                </div>
                <div className="mt-8 rounded-3xl border border-border bg-card p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Temporal Presence</div>
                      <div className="text-sm font-black text-text">Where this character intersects the narrative clock</div>
                    </div>
                    <button type="button" className={cn('rounded-xl border px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em]', activeProfilePanel === 'timeline' ? 'border-brand bg-brand/10 text-brand' : 'border-border text-text-2 hover:border-brand')} onClick={() => openCharacterPanel('timeline')}>
                      Timeline
                    </button>
                  </div>
                  <div className="space-y-3">
                    {charTimeline.map((event) => (
                      <button key={event.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand" onClick={() => navigate(`/timeline/events?character=${selectedCharacterId}&event=${event.id}`)}>
                        <div>
                          <div className="text-sm font-bold text-text">{event.title}</div>
                          <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-text-3">{event.time}</div>
                        </div>
                        <Clock3 size={14} />
                      </button>
                    ))}
                    {!charTimeline.length && <div className="rounded-2xl border border-dashed border-border bg-bg px-4 py-5 text-sm text-text-3">No timeline events linked yet.</div>}
                  </div>
                </div>
                <div className="mt-10 flex justify-end gap-4 border-t border-divider pt-8">
                  <button type="button" data-testid="open-character-timeline-btn" className="rounded-xl border border-border px-5 py-3 text-sm text-text-2 hover:border-brand" onClick={() => navigate(`/timeline/events?character=${editChar.id}`)}>
                    <Clock3 size={14} className="mr-2 inline" />{t('characters.timeline')}
                  </button>
                  <button type="button" data-testid="open-character-relationships-btn" className="rounded-xl border border-border px-5 py-3 text-sm text-text-2 hover:border-brand" onClick={() => navigate('/graph/relationships')}>
                    <Link2 size={14} className="mr-2 inline" />{t('characters.relationships')}
                  </button>
                  <button type="button" data-testid="inspector-save" className="rounded-xl bg-brand px-8 py-3 text-sm font-black text-white" onClick={handleSave}>
                    <Check size={14} className="mr-2 inline" />{t('characters.persist')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-text-3"><User size={120} className="opacity-15" /></div>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

const CharacterTabs = ({
  active,
  onSelect,
}: {
  active: 'profile' | 'timeline' | 'relationships';
  onSelect: (panel: 'profile' | 'timeline' | 'relationships') => void;
}) => (
  <div className="mb-8 flex flex-wrap gap-3 rounded-full border border-border bg-bg-elev-1 p-2">
    <button
      type="button"
      data-testid="char-tab-profile"
      className={cn('rounded-full px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em]', active === 'profile' ? 'bg-brand text-white' : 'text-text-2 hover:bg-hover')}
      onClick={() => onSelect('profile')}
    >
      Profile
    </button>
    <button
      type="button"
      data-testid="char-tab-relationships"
      className={cn('rounded-full px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em]', active === 'relationships' ? 'bg-brand text-white' : 'text-text-2 hover:bg-hover')}
      onClick={() => onSelect('relationships')}
    >
      Relationships
    </button>
    <button
      type="button"
      data-testid="char-tab-timeline"
      className={cn('rounded-full px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em]', active === 'timeline' ? 'bg-brand text-white' : 'text-text-2 hover:bg-hover')}
      onClick={() => onSelect('timeline')}
    >
      Timeline
    </button>
  </div>
);
