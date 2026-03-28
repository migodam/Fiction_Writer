import React, { useMemo, useState, useEffect } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Check, Clock3, Link2, Plus, Search, Tag, Trash2 } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { RadarChart } from './RadarChart';
import { cn } from '../utils';
import { useI18n } from '../i18n';
import { CharacterRelationshipFlow } from './graph';

const GROUPS = ['core', 'major', 'supporting', 'minor', 'ungrouped'] as const;

export const CharactersWorkspace = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { characterId } = useParams();
  const [params] = useSearchParams();
  const {
    characters,
    characterTags,
    candidates,
    relationships,
    timelineEvents,
    addCharacter,
    updateCharacter,
    deleteCharacter,
    addCharacterTag,
    addRelationship,
    updateRelationship,
    deleteRelationship,
    confirmCandidate,
    rejectCandidate,
    toggleCharacterTagMembership,
  } = useProjectStore();
  const { locale, t } = useI18n();
  const { openContextMenu, setLastActionStatus } = useUIStore();
  const zh = locale === 'zh-CN';
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const route = location.pathname.includes('/relationship-graph')
    ? 'relationship-graph'
    : location.pathname.includes('/tags')
    ? 'tags'
    : location.pathname.includes('/candidates')
    ? 'candidates'
    : 'overview';
  const tab = (params.get('tab') as 'profile' | 'relationships' | 'timeline' | 'pov') || 'profile';

  const grouped = useMemo(
    () =>
      GROUPS.map((group) => ({
        group,
        items: characters.filter((character) => (character.importance || 'ungrouped') === group && character.name.toLowerCase().includes(search.toLowerCase())),
      })).filter((group) => group.items.length > 0),
    [characters, search],
  );

  const selected = characters.find((character) => character.id === characterId) || grouped[0]?.items[0] || null;

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-72 border-r border-border bg-bg-elev-1" data-testid="character-list">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '人物' : 'Characters'}</div>
              <div className="text-sm font-black text-text">{route === 'candidates' ? (zh ? '候选队列' : 'Candidate Queue') : zh ? '人物导航' : 'Character Navigator'}</div>
            </div>
            {route !== 'candidates' && (
              <button
                type="button"
                data-testid="new-character-btn"
                className="rounded-xl border border-border p-2 text-brand hover:border-brand"
                onClick={() => {
                  const id = `char_${Date.now()}`;
                  addCharacter({
                    id,
                    name: zh ? '新人物' : 'New Character',
                    summary: '',
                    background: '',
                    aliases: [],
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
                    importance: 'supporting',
                    groupKey: 'supporting',
                    relationshipIds: [],
                    povInsights: null,
                    statusFlags: { alive: true },
                  });
                  navigate(`/characters/profile/${id}`);
                }}
              >
                <Plus size={16} />
              </button>
            )}
          </div>
          <div className="rounded-2xl border border-border bg-bg px-3 py-2">
            <div className="flex items-center gap-2">
              <Search size={13} />
              <input value={search} onChange={(event) => setSearch(event.target.value)} className="w-full bg-transparent text-sm outline-none" placeholder={zh ? '搜索人物' : 'Search characters'} />
            </div>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {route === 'candidates' ? (
            candidates.map((candidate) => (
              <div key={candidate.id} data-testid={`candidate-card-${candidate.id}`} className="mb-3 rounded-2xl border border-border bg-card p-4">
                <div className="text-sm font-black text-text">{candidate.name}</div>
                <div className="mt-2 text-xs leading-relaxed text-text-2">{candidate.background}</div>
                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    data-testid="candidate-confirm-btn"
                    className="flex-1 rounded-xl bg-green px-3 py-2 text-[11px] font-black uppercase tracking-wider text-text-invert"
                    onClick={() => {
                      const confirmedId = confirmCandidate(candidate.id);
                      if (confirmedId) navigate(`/characters/profile/${confirmedId}`);
                    }}
                  >
                    <Check size={12} className="mr-2 inline" />
                    {zh ? '确认' : 'Confirm'}
                  </button>
                  <button type="button" className="rounded-xl border border-red/40 px-3 py-2 text-red" onClick={() => rejectCandidate(candidate.id)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))
          ) : (
            grouped.map((group) => (
              <div key={group.group} className="mb-3 rounded-2xl border border-border bg-card">
                <button type="button" className="flex w-full items-center justify-between px-4 py-3 text-left" onClick={() => setCollapsed((current) => ({ ...current, [group.group]: !current[group.group] }))}>
                  <span className="text-[11px] font-black uppercase tracking-[0.22em] text-text-3">{group.group}</span>
                  <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] font-black text-text-3">{group.items.length}</span>
                </button>
                {!collapsed[group.group] && group.items.map((character) => (
                  <button key={character.id} type="button" data-testid={`character-card-${character.id}`} className={cn('flex w-full items-center justify-between border-t border-divider px-4 py-3 text-left', selected?.id === character.id ? 'bg-selected text-text' : 'text-text-2 hover:bg-hover')} onClick={() => navigate(`/characters/profile/${character.id}`)} onContextMenu={(e) => { e.preventDefault(); openContextMenu({ x: e.clientX, y: e.clientY, items: [{ id: 'delete', label: t('common.delete'), action: () => { deleteCharacter(character.id); setLastActionStatus('Character deleted'); }, destructive: true }] }); }}>
                    <span className="text-sm font-black">{character.name}</span>
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      </aside>

      <main className={route === 'relationship-graph' ? 'flex flex-1 flex-col overflow-hidden' : 'flex-1 overflow-y-auto custom-scrollbar p-8'}>
        {route === 'relationship-graph' ? (
          <RelationshipGraphPanel />
        ) : route === 'tags' ? (
          <TagsPanel />
        ) : selected ? (
          <CharacterDetail character={selected} tab={tab} />
        ) : (
          <div className="flex min-h-[480px] items-center justify-center text-text-3">{zh ? '暂无人物' : 'No characters yet'}</div>
        )}
      </main>
    </div>
  );
};

const CharacterDetail = ({ character, tab }: any) => {
  const navigate = useNavigate();
  const { locale } = useI18n();
  const zh = locale === 'zh-CN';
  const { setLastActionStatus } = useUIStore();
  const { characters, relationships, timelineEvents, characterTags, updateCharacter, addCharacterTag, toggleCharacterTagMembership, addRelationship, deleteRelationship } = useProjectStore();
  const [draft, setDraft] = useState(character);
  const [newTag, setNewTag] = useState('');
  const [tagOpen, setTagOpen] = useState(false);
  const [relationTargetId, setRelationTargetId] = useState(characters.find((entry) => entry.id !== character.id)?.id || '');
  const [relationType, setRelationType] = useState('');
  const [relationDescription, setRelationDescription] = useState('');
  const relatedRelationships = relationships.filter((relationship) => relationship.sourceId === character.id || relationship.targetId === character.id);
  const relatedEvents = timelineEvents.filter((event) => event.participantCharacterIds.includes(character.id));
  const activeTags = characterTags.filter((tag) => draft.tagIds.includes(tag.id));

  React.useEffect(() => setDraft(character), [character]);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '人物详情' : 'Character Detail'}</div>
          <div className="mt-2 text-3xl font-black text-text">{draft.name || (zh ? '未命名人物' : 'Untitled Character')}</div>
        </div>
        <div className="flex gap-3">
          <button type="button" className="rounded-xl border border-border px-4 py-3 text-sm text-text-2" onClick={() => navigate('/characters/relationship-graph')}>
            <Link2 size={14} className="mr-2 inline" />
            {zh ? '关系图' : 'Relationship Graph'}
          </button>
          <button type="button" className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white" data-testid="inspector-save" onClick={() => { updateCharacter(draft); setLastActionStatus(zh ? '已保存' : 'Saved'); }}>
            {zh ? '保存人物' : 'Save Character'}
          </button>
        </div>
      </div>

      <div className="mb-8 flex flex-wrap gap-3 rounded-full border border-border bg-bg-elev-1 p-2">
        {[
          ['profile', zh ? '档案' : 'Profile'],
          ['relationships', zh ? '关系' : 'Relationships'],
          ['timeline', zh ? '时间线' : 'Timeline'],
          ['pov', 'POV Insights'],
        ].map(([id, label]) => (
          <button key={id} type="button" className={cn('rounded-full px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em]', tab === id ? 'bg-brand text-white' : 'text-text-2 hover:bg-hover')} onClick={() => navigate(`/characters/profile/${draft.id}?tab=${id}`)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'profile' ? (
        <div className="mb-6 grid gap-4 rounded-3xl border border-border bg-card p-5 lg:grid-cols-2">
          <input
            data-testid="character-name-input"
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            className="rounded-2xl border border-border bg-bg px-4 py-3 text-sm font-bold outline-none"
            placeholder={zh ? '人物名称' : 'Character name'}
          />
          <textarea
            data-testid="character-background-input"
            value={draft.background}
            onChange={(event) => setDraft({ ...draft, background: event.target.value })}
            className="h-24 rounded-2xl border border-border bg-bg px-4 py-3 text-sm outline-none lg:col-span-2"
            placeholder={zh ? '背景与经历' : 'Background'}
          />
        </div>
      ) : null}

      {tab === 'relationships' ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_0.85fr]">
          <div className="rounded-3xl border border-border bg-card p-6">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '与该人物相关的关系' : 'Relationships connected to this character'}</div>
            <div className="space-y-3">
              {relatedRelationships.map((relationship) => {
                const otherId = relationship.sourceId === draft.id ? relationship.targetId : relationship.sourceId;
                const other = characters.find((entry) => entry.id === otherId);
                return (
                  <div key={relationship.id} className="rounded-2xl border border-border bg-bg-elev-1 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-text">{other?.name || otherId}</div>
                        <div className="mt-1 text-xs text-text-3">{relationship.type}</div>
                      </div>
                      <button type="button" className="rounded border border-red/40 p-1 text-red" onClick={() => deleteRelationship(relationship.id)}>
                        <Trash2 size={12} />
                      </button>
                    </div>
                    <div className="mt-3 text-sm leading-relaxed text-text-2">{relationship.description}</div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="rounded-3xl border border-border bg-card p-6">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '新建关系' : 'Create Relationship'}</div>
            <div className="grid gap-3">
              <select value={relationTargetId} onChange={(event) => setRelationTargetId(event.target.value)} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
                {characters.filter((entry) => entry.id !== draft.id).map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
              </select>
              <input value={relationType} onChange={(event) => setRelationType(event.target.value)} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '关系类型' : 'Relationship type'} />
              <textarea value={relationDescription} onChange={(event) => setRelationDescription(event.target.value)} className="h-28 rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '关系说明' : 'Description'} />
              <button type="button" className="rounded-xl bg-brand px-4 py-3 text-sm font-black text-white" onClick={() => {
                if (!relationTargetId || !relationType.trim()) return;
                addRelationship({ id: `rel_${Date.now()}`, sourceId: draft.id, targetId: relationTargetId, type: relationType.trim(), description: relationDescription, category: 'general', directionality: 'bidirectional', status: 'active', sourceNotes: '' });
                setRelationType('');
                setRelationDescription('');
              }}>
                {zh ? '创建关系' : 'Create Relationship'}
              </button>
            </div>
          </div>
        </div>
      ) : tab === 'timeline' ? (
        <div className="rounded-3xl border border-border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '人物时间线' : 'Character Timeline'}</div>
            <button type="button" className="rounded-xl border border-border px-4 py-2 text-sm text-text-2" onClick={() => navigate(`/timeline/timeline?character=${draft.id}`)}>
              <Clock3 size={14} className="mr-2 inline" />
              {zh ? '打开全局时间线' : 'Open Global Timeline'}
            </button>
          </div>
          <div className="space-y-3">
            {relatedEvents.map((event) => (
              <button key={event.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg-elev-1 px-4 py-3 text-left" onClick={() => navigate(`/timeline/timeline?event=${event.id}`)}>
                <div>
                  <div className="text-sm font-black text-text">{event.title}</div>
                  <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">{event.time || 'Timeline'}</div>
                </div>
                <Clock3 size={14} />
              </button>
            ))}
          </div>
        </div>
      ) : tab === 'pov' ? (
        <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-3xl border border-border bg-card p-6">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">POV Insights</div>
            <div className="h-[320px] rounded-3xl border border-border bg-bg-elev-1 p-4">
              {draft.povInsights ? <RadarChart metrics={draft.povInsights.radar} /> : <div className="flex h-full items-center justify-center text-sm text-text-3">{zh ? '暂未生成 POV Insights' : 'No POV insights generated yet'}</div>}
            </div>
          </div>
          <div className="space-y-4">
            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '摘要' : 'Summary'}</div>
              <div className="text-sm leading-relaxed text-text-2">{draft.povInsights?.summary || (zh ? '当前为占位状态，可稍后由 AI 或人工补充。' : 'Placeholder state. AI or manual insights can be added later.')}</div>
            </div>
            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '评分项' : 'Scores'}</div>
              <div className="space-y-3">
                {(draft.povInsights?.scores || []).map((score: any) => (
                  <div key={score.key} className="flex items-center gap-4">
                    <div className="w-28 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{score.label}</div>
                    <div className="h-2 flex-1 overflow-hidden rounded-full border border-divider bg-bg"><div className="h-full bg-brand" style={{ width: `${score.score}%` }} /></div>
                    <div className="w-12 text-right text-sm font-black text-text">{score.score}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
          <div className="space-y-6">
            <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="w-full bg-transparent text-5xl font-black tracking-tight outline-none" placeholder={zh ? '人物名称' : 'Character name'} />
            <textarea value={draft.background} onChange={(event) => setDraft({ ...draft, background: event.target.value })} className="h-56 w-full rounded-3xl border border-border bg-bg-elev-1 p-6 font-serif text-sm leading-relaxed text-text-2 outline-none" placeholder={zh ? '背景与经历' : 'Background'} />
            <textarea value={draft.summary} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} className="h-28 w-full rounded-3xl border border-border bg-bg p-5 text-sm leading-relaxed text-text-2 outline-none" placeholder={zh ? '人物摘要' : 'Summary'} />
            <div className="grid gap-4 md:grid-cols-2">
              <input value={draft.traits || ''} onChange={(event) => setDraft({ ...draft, traits: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '性格特征' : 'Traits'} />
              <input value={draft.goals || ''} onChange={(event) => setDraft({ ...draft, goals: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '目标' : 'Goals'} />
              <input value={draft.fears || ''} onChange={(event) => setDraft({ ...draft, fears: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '恐惧' : 'Fears'} />
              <select value={draft.importance || 'ungrouped'} onChange={(event) => setDraft({ ...draft, importance: event.target.value as any, groupKey: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
                {GROUPS.map((group) => <option key={group} value={group}>{group}</option>)}
              </select>
            </div>
          </div>
          <div className="space-y-6">
            <div className="rounded-3xl border border-border bg-card p-5">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '标签' : 'Tags'}</div>
                <button type="button" className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-2" onClick={() => setTagOpen((current) => !current)}>
                  <Plus size={12} className="mr-1 inline" />
                  {zh ? '添加' : 'Add'}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {activeTags.map((tag) => (
                  <button key={tag.id} type="button" className="rounded-full border border-brand bg-brand/10 px-3 py-2 text-xs font-bold text-brand-2" onClick={() => toggleCharacterTagMembership(tag.id, draft.id)}>
                    <Tag size={10} className="mr-2 inline" />
                    {tag.name}
                  </button>
                ))}
              </div>
              {tagOpen && (
                <div className="mt-4 rounded-2xl border border-border bg-bg p-4">
                  <div className="mb-3 flex flex-wrap gap-2">
                    {characterTags.filter((tag) => !draft.tagIds.includes(tag.id)).map((tag) => (
                      <button key={tag.id} type="button" className="rounded-full border border-border px-3 py-2 text-xs text-text-2" onClick={() => toggleCharacterTagMembership(tag.id, draft.id)}>
                        {tag.name}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input value={newTag} onChange={(event) => setNewTag(event.target.value)} className="flex-1 rounded-xl border border-border bg-bg px-3 py-2 outline-none" placeholder={zh ? '新标签' : 'New tag'} />
                    <button type="button" className="rounded-xl bg-brand px-4 py-2 text-xs font-black text-white" onClick={() => {
                      if (!newTag.trim()) return;
                      const tagId = `tag_${Date.now()}`;
                      addCharacterTag({ id: tagId, name: newTag.trim(), color: '#f59e0b', description: '', characterIds: [draft.id] });
                      toggleCharacterTagMembership(tagId, draft.id);
                      setNewTag('');
                      setTagOpen(false);
                    }}>
                      {zh ? '创建' : 'Create'}
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="rounded-3xl border border-border bg-card p-5">
              <div className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '人物信息' : 'Profile Meta'}</div>
              <div className="grid gap-3">
                <input value={draft.birthdayText || ''} onChange={(event) => setDraft({ ...draft, birthdayText: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '生日 / 时间标记' : 'Birthday / time marker'} />
                <input value={draft.speechStyle || ''} onChange={(event) => setDraft({ ...draft, speechStyle: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '说话风格' : 'Speech style'} />
                <textarea value={draft.arc || ''} onChange={(event) => setDraft({ ...draft, arc: event.target.value })} className="h-32 rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '人物弧光' : 'Character arc'} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const RelationshipGraphPanel: React.FC = () => {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border bg-bg-elev-2 px-6 py-4">
        <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Relationship Graph</div>
        <div className="text-sm font-black text-text">Interactive character network</div>
      </div>
      <div className="flex-1 overflow-hidden">
        <CharacterRelationshipFlow />
      </div>
    </div>
  );
};

const TagsPanel = () => {
  const { characters, characterTags, addCharacterTag, toggleCharacterTagMembership } = useProjectStore();
  const { locale, t } = useI18n();
  const zh = locale === 'zh-CN';
  const [draft, setDraft] = useState({ name: '', color: '#f59e0b' });
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);
  const [tagSearch, setTagSearch] = useState('');

  useEffect(() => {
    setTagSearch('');
  }, [selectedTagId]);

  const filteredCharacters = useMemo(() => {
    if (!tagSearch.trim()) return characters;
    return characters
      .filter((c) => c.name.toLowerCase().includes(tagSearch.toLowerCase()))
      .slice(0, 20);
  }, [characters, tagSearch]);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '标签系统' : 'Tag System'}</div>
        <div className="mt-2 text-3xl font-black text-text">{zh ? '人物标签管理' : 'Character Tags'}</div>
      </div>
      <div className="mb-8 grid gap-4 rounded-3xl border border-border bg-card p-6 lg:grid-cols-[1fr_auto_auto]">
        <input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder={zh ? '标签名称' : 'Tag name'} className="rounded-xl border border-border bg-bg px-4 py-3 outline-none" />
        <input value={draft.color} onChange={(event) => setDraft((current) => ({ ...current, color: event.target.value }))} className="h-12 rounded-xl border border-border bg-bg px-4 py-3 outline-none" />
        <button type="button" className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white" onClick={() => {
          if (!draft.name.trim()) return;
          addCharacterTag({ id: `tag_${Date.now()}`, name: draft.name.trim(), color: draft.color, description: '', characterIds: [] });
          setDraft({ name: '', color: '#f59e0b' });
        }}>
          <Plus size={14} className="mr-2 inline" />
          {zh ? '创建标签' : 'Create Tag'}
        </button>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        {characterTags.map((tagEntry) => {
          const isSelected = selectedTagId === tagEntry.id;
          return (
            <div key={tagEntry.id} className="rounded-3xl border border-border bg-card p-6 shadow-1">
              <button
                type="button"
                className="mb-4 flex w-full items-center gap-3 text-left"
                onClick={() => setSelectedTagId(isSelected ? null : tagEntry.id)}
              >
                <div className="h-3 w-3 flex-shrink-0 rounded-full" style={{ background: tagEntry.color }} />
                <div className="text-lg font-black text-text">{tagEntry.name}</div>
                <span className="ml-auto rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] font-black text-text-3">
                  ({tagEntry.characterIds.length})
                </span>
              </button>
              {isSelected && (
                <div>
                  <input
                    type="text"
                    data-testid="tag-character-search-input"
                    value={tagSearch}
                    onChange={(event) => setTagSearch(event.target.value)}
                    placeholder={t('tags.searchCharacters')}
                    className="mb-3 w-full rounded-xl border border-border bg-bg px-3 py-2 text-sm outline-none"
                  />
                  <div className="flex flex-wrap gap-2">
                    {filteredCharacters.map((character) => {
                      const active = tagEntry.characterIds.includes(character.id);
                      return (
                        <button key={character.id} type="button" className={cn('rounded-full border px-3 py-2 text-xs font-bold transition-colors', active ? 'border-brand bg-brand/15 text-brand-2' : 'border-border text-text-2 hover:border-brand')} onClick={() => toggleCharacterTagMembership(tagEntry.id, character.id)}>
                          {character.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
