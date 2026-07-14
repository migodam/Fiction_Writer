import React, { useMemo, useState, useEffect, useCallback } from "react";
import {
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  Check,
  Clock3,
  ImageIcon,
  Link2,
  Plus,
  Search,
  Tag,
  Trash2,
  Upload,
} from "lucide-react";
import { useProjectStore, useUIStore } from "../store";
import { RadarChart } from "./RadarChart";
import { cn } from "../utils";
import { useI18n } from "../i18n";
import { CharacterRelationshipFlow } from "./graph";
import { AIPortraitModal } from "./ai/AIPortraitModal";
import { electronApi } from "../services/electronApi";
import { TagTreePanel } from "./TagTreePanel";
import { ArchiveImpactModal } from "./ArchiveImpactModal";
import { getCharacterContextCommands } from "../commands/characterCommands";
import { commandClipboard } from "../commands/clipboard";
import { toMenuItem } from "../commands/menu";
import type {
  CharacterCustomAttribute,
  CharacterExperienceEntry,
  CharacterTag,
} from "../models/project";

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
    archiveCharacter,
    hardDeleteCharacter,
    addCharacterTag,
    addRelationship,
    updateRelationship,
    deleteRelationship,
    confirmCandidate,
    rejectCandidate,
    toggleCharacterTagMembership,
    characterPartitions,
    addCharacterPartition,
    deleteCharacterPartition,
    graphImportanceFilter,
    characterGroupCollapsed,
    graphSidebarLinkageEnabled,
    setGraphImportanceFilter,
    setCharacterGroupCollapsed,
    toggleCharacterGroupCollapsed,
    setGraphSidebarLinkageEnabled,
    setSelectedEntity,
  } = useProjectStore();
  const { t } = useI18n();
  const { openContextMenu, setLastActionStatus } = useUIStore();
  const [search, setSearch] = useState("");
  const [showMinor, setShowMinor] = useState(false);
  const [showNewPartition, setShowNewPartition] = useState(false);
  const [newPartitionName, setNewPartitionName] = useState("");
  const [dragCharacterId, setDragCharacterId] = useState<string | null>(null);
  const [confirmArchiveId, setConfirmArchiveId] = useState<string | null>(null);
  const route = location.pathname.includes("/relationship-graph")
    ? "relationship-graph"
    : location.pathname.includes("/tags")
      ? "tags"
      : location.pathname.includes("/candidates")
        ? "candidates"
        : "overview";
  const tab =
    (params.get("tab") as "profile" | "relationships" | "timeline" | "pov") ||
    "profile";

  const grouped = useMemo(
    () =>
      characterPartitions
        .map((group) => ({
          group,
          items: characters.filter((character) => {
            const imp = character.importance || "ungrouped";
            if (!showMinor && imp === "minor") return false;
            return (
              imp === group &&
              character.name.toLowerCase().includes(search.toLowerCase())
            );
          }),
        }))
        .filter((group) => group.items.length > 0),
    [characters, search, characterPartitions, showMinor],
  );

  const foundCharacter = characterId
    ? (characters.find((c) => c.id === characterId) ?? null)
    : null;
  const selected =
    foundCharacter ?? (characterId ? null : (grouped[0]?.items[0] ?? null));

  useEffect(() => {
    if (characterId && foundCharacter) {
      setSelectedEntity("character", characterId);
    }
  }, [characterId, foundCharacter?.id, setSelectedEntity]);

  const handleAddPartition = () => {
    const name = newPartitionName.trim();
    if (!name) return;
    addCharacterPartition(name);
    setNewPartitionName("");
    setShowNewPartition(false);
  };

  const handleDeletePartition = (groupName: string) => {
    const charsInGroup = characters.filter(
      (c) => (c.importance || "ungrouped") === groupName,
    );
    if (charsInGroup.length > 0) {
      setLastActionStatus(t("characters.partitionNotEmpty"));
      return;
    }
    deleteCharacterPartition(groupName);
    setLastActionStatus(t("characters.partitionDeleted"));
  };

  const handleDropOnGroup = useCallback(
    (e: React.DragEvent, groupName: string) => {
      e.preventDefault();
      const charId = e.dataTransfer.getData("text/plain");
      if (!charId) return;
      const char = characters.find((c) => c.id === charId);
      if (char && (char.importance || "ungrouped") !== groupName) {
        updateCharacter({
          ...char,
          importance: groupName as any,
          groupKey: groupName,
        });
        setLastActionStatus(`${char.name} → ${groupName}`);
      }
      setDragCharacterId(null);
    },
    [characters, updateCharacter, setLastActionStatus],
  );

  const handleGroupToggle = useCallback(
    (groupName: string) => {
      toggleCharacterGroupCollapsed(groupName);
    },
    [toggleCharacterGroupCollapsed],
  );

  useEffect(() => {
    if (!graphSidebarLinkageEnabled) return;
    const hidden = Object.entries(characterGroupCollapsed)
      .filter(([, isCollapsed]) => isCollapsed)
      .map(([g]) => g);
    setGraphImportanceFilter(hidden);
  }, [
    characterGroupCollapsed,
    graphSidebarLinkageEnabled,
    setGraphImportanceFilter,
  ]);

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside
        className="w-72 border-r border-border bg-bg-elev-1"
        data-testid="character-list"
      >
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
                {t("characters.characters")}
              </div>
              <div className="text-sm font-black text-text">
                {route === "candidates"
                  ? t("characters.candidateQueue")
                  : t("characters.characterNavigator")}
              </div>
            </div>
            {route !== "candidates" && (
              <button
                type="button"
                data-testid="new-character-btn"
                className="rounded-xl border border-border p-2 text-brand hover:border-brand"
                onClick={() => {
                  const id = `char_${Date.now()}`;
                  addCharacter({
                    id,
                    name: t("characters.newCharacter"),
                    summary: "",
                    background: "",
                    aliases: [],
                    birthdayText: "",
                    portraitAssetId: null,
                    traits: "",
                    goals: "",
                    fears: "",
                    secrets: "",
                    speechStyle: "",
                    arc: "",
                    tagIds: [],
                    organizationIds: [],
                    linkedSceneIds: [],
                    linkedEventIds: [],
                    linkedWorldItemIds: [],
                    importance: "supporting",
                    groupKey: "supporting",
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
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="w-full bg-transparent text-sm outline-none"
                placeholder={t("characters.searchCharacters")}
              />
            </div>
          </div>
          {route !== "candidates" && (
            <button
              type="button"
              data-testid="characters-show-minor-toggle"
              onClick={() => setShowMinor((v) => !v)}
              className={`mt-2 w-full rounded-lg border px-3 py-1 text-xs font-medium transition-colors ${showMinor ? "border-brand/40 bg-brand/10 text-brand" : "border-border text-text-3 hover:bg-hover hover:text-text-2"}`}
            >
              {showMinor
                ? t("characters.hideMinor")
                : t("characters.showMinor")}
            </button>
          )}
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {route === "candidates" ? (
            candidates.map((candidate) => (
              <div
                key={candidate.id}
                data-testid={`candidate-card-${candidate.id}`}
                className="mb-3 rounded-2xl border border-border bg-card p-4"
              >
                <div className="text-sm font-black text-text">
                  {candidate.name}
                </div>
                <div className="mt-2 text-xs leading-relaxed text-text-2">
                  {candidate.background}
                </div>
                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    data-testid="candidate-confirm-btn"
                    className="flex-1 rounded-xl bg-green px-3 py-2 text-[11px] font-black uppercase tracking-wider text-text-invert"
                    onClick={() => {
                      const confirmedId = confirmCandidate(candidate.id);
                      if (confirmedId)
                        navigate(`/characters/profile/${confirmedId}`);
                    }}
                  >
                    <Check size={12} className="mr-2 inline" />
                    {t("characters.confirmCandidateBtn")}
                  </button>
                  <button
                    type="button"
                    className="rounded-xl border border-red/40 px-3 py-2 text-red"
                    onClick={() => rejectCandidate(candidate.id)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))
          ) : (
            <>
              {grouped.map((group) => (
                <div
                  key={group.group}
                  className={cn(
                    "mb-3 rounded-2xl border bg-card transition-colors",
                    dragCharacterId ? "border-brand/60" : "border-border",
                  )}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={(e) => handleDropOnGroup(e, group.group)}
                >
                  <button
                    type="button"
                    data-testid={`character-group-header-${group.group}`}
                    className="flex w-full items-center justify-between px-4 py-3 text-left"
                    onClick={() => handleGroupToggle(group.group)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      openContextMenu({
                        x: e.clientX,
                        y: e.clientY,
                        items: [
                          {
                            id: "delete-partition",
                            label: t("characters.deletePartition"),
                            action: () => handleDeletePartition(group.group),
                            destructive: true,
                          },
                        ],
                      });
                    }}
                  >
                    <span className="text-[11px] font-black uppercase tracking-[0.22em] text-text-3">
                      {t(
                        "characters.importance." + group.group,
                        group.group.charAt(0).toUpperCase() +
                          group.group.slice(1),
                      )}
                    </span>
                    <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] font-black text-text-3">
                      {group.items.length}
                    </span>
                  </button>
                  {!characterGroupCollapsed[group.group] &&
                    group.items.map((character) => (
                      <button
                        key={character.id}
                        type="button"
                        data-testid={`character-card-${character.id}`}
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData("text/plain", character.id);
                          e.dataTransfer.effectAllowed = "move";
                          setDragCharacterId(character.id);
                        }}
                        onDragEnd={() => setDragCharacterId(null)}
                        className={cn(
                          "flex w-full items-center justify-between border-t border-divider px-4 py-3 text-left cursor-grab active:cursor-grabbing",
                          selected?.id === character.id
                            ? "bg-selected text-text"
                            : "text-text-2 hover:bg-hover",
                        )}
                        onClick={() =>
                          navigate(`/characters/profile/${character.id}`)
                        }
                        onContextMenu={(e) => {
                          e.preventDefault();
                          const context = {
                            target: {
                              kind: "character" as const,
                              id: character.id,
                            },
                            source: "context-menu" as const,
                            character,
                            addCharacter,
                            setConfirmArchiveId,
                            navigate,
                          };
                          openContextMenu({
                            x: e.clientX,
                            y: e.clientY,
                            returnFocus: e.currentTarget,
                            items: getCharacterContextCommands(
                              Boolean(commandClipboard.get("character")),
                            ).map((command) => toMenuItem(command, context, t)),
                          });
                        }}
                      >
                        <span className="text-sm font-black">
                          {character.name}
                        </span>
                      </button>
                    ))}
                </div>
              ))}
              <div className="mt-2">
                {showNewPartition ? (
                  <div className="flex items-center gap-2 rounded-2xl border border-dashed border-border bg-card px-3 py-2">
                    <input
                      value={newPartitionName}
                      onChange={(e) => setNewPartitionName(e.target.value)}
                      className="flex-1 rounded-xl border border-border bg-bg px-3 py-2 text-sm outline-none"
                      placeholder={t("characters.partitionName")}
                      data-testid="new-partition-input"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleAddPartition();
                        if (e.key === "Escape") {
                          setShowNewPartition(false);
                          setNewPartitionName("");
                        }
                      }}
                    />
                    <button
                      type="button"
                      data-testid="add-partition-submit-btn"
                      className="rounded-xl bg-brand px-3 py-2 text-xs font-black text-white"
                      onClick={handleAddPartition}
                    >
                      <Plus size={12} />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    data-testid="add-partition-btn"
                    className="flex w-full items-center justify-center gap-1 rounded-2xl border border-dashed border-border px-4 py-2 text-xs text-text-3 hover:border-brand hover:text-brand"
                    onClick={() => setShowNewPartition(true)}
                  >
                    <Plus size={12} />
                    {t("characters.addPartition")}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </aside>

      <main
        className={
          route === "relationship-graph"
            ? "flex flex-1 flex-col overflow-hidden"
            : "flex-1 overflow-y-auto custom-scrollbar p-8"
        }
      >
        {route === "relationship-graph" ? (
          <RelationshipGraphPanel />
        ) : route === "tags" ? (
          <TagsPanel />
        ) : characterId && !foundCharacter ? (
          <div
            data-testid="entity-not-found"
            className="flex min-h-[480px] flex-col items-center justify-center gap-4 text-text-3"
          >
            <p className="text-lg font-black">
              {t("common.entityNotFound", "Entity not found")}
            </p>
            <button
              type="button"
              data-testid="entity-not-found-back"
              className="rounded-xl border border-border px-4 py-2 text-sm text-text-2 hover:bg-hover"
              onClick={() => navigate("/characters/list")}
            >
              {t("common.backToList", "Back to list")}
            </button>
          </div>
        ) : selected ? (
          <CharacterDetail
            character={selected}
            tab={tab}
            setConfirmArchiveId={setConfirmArchiveId}
          />
        ) : (
          <div className="flex min-h-[480px] items-center justify-center text-text-3">
            {t("characters.noCharactersYet")}
          </div>
        )}
      </main>
      {confirmArchiveId && (
        <ArchiveImpactModal
          characterId={confirmArchiveId}
          characterName={
            characters.find((c) => c.id === confirmArchiveId)?.name || ""
          }
          onArchive={() => {
            archiveCharacter(confirmArchiveId);
            setConfirmArchiveId(null);
            setLastActionStatus(
              t("characters.characterArchived", "Character archived"),
            );
            navigate("/characters");
          }}
          onHardDelete={() => {
            hardDeleteCharacter(confirmArchiveId);
            setConfirmArchiveId(null);
            setLastActionStatus(t("characters.characterDeleted"));
            navigate("/characters");
          }}
          onCancel={() => setConfirmArchiveId(null)}
        />
      )}
    </div>
  );
};

type RelDirection = "bidirectional" | "outgoing" | "incoming";
interface RelGroup {
  dir: RelDirection;
  label: string;
  rels: any[];
}

function groupRelationshipsByDirection(
  characterId: string,
  rels: any[],
): RelGroup[] {
  const statusOrder: Record<string, number> = {
    active: 0,
    strained: 1,
    broken: 2,
    unknown: 3,
  };
  const sort = (a: any, b: any) =>
    (statusOrder[a.status || "unknown"] ?? 3) -
    (statusOrder[b.status || "unknown"] ?? 3);
  const bidir = rels.filter((r) => r.directionality === "bidirectional");
  const out = rels.filter(
    (r) =>
      r.sourceId === characterId &&
      r.directionality !== "target_to_source" &&
      r.directionality !== "bidirectional",
  );
  const inc = rels.filter(
    (r) =>
      r.targetId === characterId &&
      r.directionality !== "source_to_target" &&
      r.directionality !== "bidirectional",
  );
  const groups: RelGroup[] = [];
  if (bidir.length)
    groups.push({
      dir: "bidirectional",
      label: "↔",
      rels: [...bidir].sort(sort),
    });
  if (out.length)
    groups.push({ dir: "outgoing", label: "→", rels: [...out].sort(sort) });
  if (inc.length)
    groups.push({ dir: "incoming", label: "←", rels: [...inc].sort(sort) });
  return groups;
}

const CharacterDetail = ({ character, tab, setConfirmArchiveId }: any) => {
  const navigate = useNavigate();
  const { t } = useI18n();
  const { openContextMenu, setLastActionStatus } = useUIStore();
  const {
    characters,
    relationships,
    timelineEvents,
    characterTags,
    updateCharacter,
    addCharacter,
    addCharacterTag,
    toggleCharacterTagMembership,
    addRelationship,
    deleteRelationship,
    projectRoot,
    characterPartitions,
  } = useProjectStore();
  const [draft, setDraft] = useState(character);
  const [newTag, setNewTag] = useState("");
  const [tagOpen, setTagOpen] = useState(false);
  const [portraitModalOpen, setPortraitModalOpen] = useState(false);
  const [relationTargetId, setRelationTargetId] = useState("");
  const [relationType, setRelationType] = useState("");
  const [relationDescription, setRelationDescription] = useState("");
  const relatedRelationships = relationships.filter(
    (relationship) =>
      relationship.sourceId === character.id ||
      relationship.targetId === character.id,
  );
  const relatedEvents = timelineEvents.filter((event) =>
    event.participantCharacterIds.includes(character.id),
  );
  const activeTags = characterTags.filter((tag) =>
    draft.tagIds.includes(tag.id),
  );

  React.useEffect(() => {
    setDraft(character);
    // Reset relationTargetId to first available other character
    const others = characters.filter((c) => c.id !== character.id);
    setRelationTargetId(others[0]?.id || "");
  }, [character]);

  const updateExperience = (entries: CharacterExperienceEntry[]) =>
    setDraft({ ...draft, experience: entries });
  const updateCustomAttributes = (entries: CharacterCustomAttribute[]) =>
    setDraft({ ...draft, customAttributes: entries });

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
              {t("characters.characterDetail")}
            </div>
            <div className="mt-2 text-3xl font-black text-text">
              {t("characters.profile")}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              data-testid="character-duplicate-btn"
              className="rounded-xl border border-border px-3 py-2 text-sm text-text-2 hover:bg-hover"
              onClick={() => {
                const newId = `char_${Date.now()}`;
                addCharacter({
                  ...draft,
                  id: newId,
                  name: `${draft.name} (copy)`,
                  relationshipIds: [],
                  linkedSceneIds: [],
                  linkedEventIds: [],
                });
                navigate(`/characters/profile/${newId}`);
              }}
            >
              {t("characters.duplicateCharacter", "Duplicate")}
            </button>
            <button
              type="button"
              data-testid="character-archive-btn"
              className="rounded-xl border border-border px-3 py-2 text-sm text-text-2 hover:bg-hover"
              onClick={() =>
                setConfirmArchiveId && setConfirmArchiveId(character.id)
              }
            >
              {t("characters.archiveCharacter", "Archive")}
            </button>
            <button
              type="button"
              data-testid="character-merge-btn"
              className="rounded-xl border border-border px-3 py-2 text-sm text-text-3 cursor-not-allowed opacity-50"
              disabled
              title={t("characters.mergeComingSoon", "Merge (coming soon)")}
            >
              {t("characters.mergeCharacter", "Merge")}
            </button>
            <button
              type="button"
              data-testid="delete-character-btn"
              className="rounded-xl border border-red/40 p-2 text-red hover:bg-red/10"
              onClick={() =>
                setConfirmArchiveId && setConfirmArchiveId(character.id)
              }
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            data-testid="open-character-relationships-btn"
            className="rounded-xl border border-border px-4 py-3 text-sm text-text-2"
            onClick={() => navigate("/graph/relationships")}
          >
            <Link2 size={14} className="mr-2 inline" />
            {t("characters.relationshipGraph")}
          </button>
          <button
            type="button"
            data-testid="open-character-timeline-btn"
            className="rounded-xl border border-border px-4 py-3 text-sm text-text-2"
            onClick={() => navigate(`/timeline/timeline?character=${draft.id}`)}
          >
            <Clock3 size={14} className="mr-2 inline" />
            {t("characters.openGlobalTimeline")}
          </button>
          <button
            type="button"
            className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white"
            data-testid="inspector-save"
            onClick={() => {
              updateCharacter(draft);
              setLastActionStatus(t("characters.saved"));
            }}
          >
            {t("characters.saveCharacter")}
          </button>
        </div>
      </div>

      <div className="mb-8 flex flex-wrap gap-3 rounded-full border border-border bg-bg-elev-1 p-2">
        {[
          ["profile", t("characters.profile")],
          ["relationships", t("characters.relationshipsTab")],
          ["timeline", t("characters.timelineTab")],
          ["pov", "POV Insights"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={cn(
              "rounded-full px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em]",
              tab === id ? "bg-brand text-white" : "text-text-2 hover:bg-hover",
            )}
            onClick={() =>
              navigate(`/characters/profile/${draft.id}?tab=${id}`)
            }
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "relationships" ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_0.85fr]">
          <div className="rounded-3xl border border-border bg-card p-6">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t("characters.relationshipsConnected")}
            </div>
            {(() => {
              const relGroups = groupRelationshipsByDirection(
                draft.id,
                relatedRelationships,
              );
              const statusCls: Record<string, string> = {
                active: "border-green/30 bg-green/5",
                strained: "border-amber/30 bg-amber/5",
                broken: "border-red/30 bg-red/5",
                unknown: "border-border bg-bg-elev-1",
              };
              if (relGroups.length === 0) {
                return (
                  <div className="py-6 text-center text-sm text-text-3">
                    {t("characters.noCharactersYet")}
                  </div>
                );
              }
              return relGroups.map((group) => (
                <div
                  key={group.dir}
                  data-testid={`relationship-section-${group.dir}`}
                  className="mb-4"
                >
                  <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-text-3">
                    {group.label} {t(`characters.rel_${group.dir}`, group.dir)}{" "}
                    ({group.rels.length})
                  </div>
                  {group.rels.map((rel: any) => {
                    const otherId =
                      rel.sourceId === draft.id ? rel.targetId : rel.sourceId;
                    const other = characters.find((e) => e.id === otherId);
                    return (
                      <div
                        key={rel.id}
                        className={`mb-2 rounded-2xl border p-4 ${statusCls[rel.status || "unknown"]}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-black text-text">
                              {other?.name || otherId}
                            </div>
                            <div className="mt-1 text-xs text-text-3">
                              {rel.type}
                            </div>
                          </div>
                          <button
                            type="button"
                            className="rounded border border-red/40 p-1 text-red"
                            onClick={() => deleteRelationship(rel.id)}
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                        {rel.description && (
                          <div className="mt-2 text-sm leading-relaxed text-text-2">
                            {rel.description}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ));
            })()}
          </div>
          <div className="rounded-3xl border border-brand/30 bg-brand/5 p-6">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-brand">
              {t("characters.createRelationshipLabel")}
            </div>
            <div className="grid gap-3">
              <select
                value={relationTargetId}
                onChange={(event) => setRelationTargetId(event.target.value)}
                className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
              >
                <option value="" disabled>
                  {t("characters.characterName")}
                </option>
                {characters
                  .filter((entry) => entry.id !== draft.id)
                  .map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.name}
                    </option>
                  ))}
              </select>
              <input
                value={relationType}
                onChange={(event) => setRelationType(event.target.value)}
                className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                placeholder={t("characters.relationshipTypePlaceholder")}
              />
              <textarea
                value={relationDescription}
                onChange={(event) => setRelationDescription(event.target.value)}
                className="h-28 rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                placeholder={t("characters.relationshipDescriptionPlaceholder")}
              />
              <button
                type="button"
                data-testid="create-relationship-btn"
                className="rounded-xl bg-brand px-4 py-3 text-sm font-black text-white disabled:opacity-40"
                disabled={!relationTargetId || !relationType.trim()}
                onClick={() => {
                  if (!relationTargetId || !relationType.trim()) return;
                  addRelationship({
                    id: `rel_${Date.now()}`,
                    sourceId: draft.id,
                    targetId: relationTargetId,
                    type: relationType.trim(),
                    description: relationDescription,
                    category: "general",
                    directionality: "bidirectional",
                    status: "active",
                    sourceNotes: "",
                  });
                  setRelationType("");
                  setRelationDescription("");
                  setLastActionStatus(t("characters.saved"));
                }}
              >
                <Plus size={14} className="mr-2 inline" />
                {t("characters.createRelationshipBtn")}
              </button>
            </div>
          </div>
        </div>
      ) : tab === "timeline" ? (
        <div className="rounded-3xl border border-border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t("characters.characterTimeline")}
            </div>
            <button
              type="button"
              className="rounded-xl border border-border px-4 py-2 text-sm text-text-2"
              onClick={() =>
                navigate(`/timeline/timeline?character=${draft.id}`)
              }
            >
              <Clock3 size={14} className="mr-2 inline" />
              {t("characters.openGlobalTimeline")}
            </button>
          </div>
          <div className="space-y-3">
            {relatedEvents.map((event) => (
              <button
                key={event.id}
                type="button"
                className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg-elev-1 px-4 py-3 text-left"
                onClick={() => navigate(`/timeline/timeline?event=${event.id}`)}
              >
                <div>
                  <div className="text-sm font-black text-text">
                    {event.title}
                  </div>
                  <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">
                    {event.time || "Timeline"}
                  </div>
                </div>
                <Clock3 size={14} />
              </button>
            ))}
          </div>
        </div>
      ) : tab === "pov" ? (
        <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-3xl border border-border bg-card p-6">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              POV Insights
            </div>
            <div className="h-[320px] rounded-3xl border border-border bg-bg-elev-1 p-4">
              {draft.povInsights ? (
                <RadarChart metrics={draft.povInsights.radar} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-text-3">
                  {t("characters.noPovInsights")}
                </div>
              )}
            </div>
          </div>
          <div className="space-y-4">
            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                {t("characters.profile")}
              </div>
              <div className="text-sm leading-relaxed text-text-2">
                {draft.povInsights?.summary ||
                  t("characters.summaryPlaceholder")}
              </div>
            </div>
            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                {t("characters.scoresLabel")}
              </div>
              <div className="space-y-3">
                {(draft.povInsights?.scores || []).map((score: any) => (
                  <div key={score.key} className="flex items-center gap-4">
                    <div className="w-28 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      {score.label}
                    </div>
                    <div className="h-2 flex-1 overflow-hidden rounded-full border border-divider bg-bg">
                      <div
                        className="h-full bg-brand"
                        style={{ width: `${score.score}%` }}
                      />
                    </div>
                    <div className="w-12 text-right text-sm font-black text-text">
                      {score.score}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
          <div className="space-y-6">
            <input
              data-testid="character-name-input"
              value={draft.name}
              onChange={(event) =>
                setDraft({ ...draft, name: event.target.value })
              }
              className="w-full bg-transparent text-5xl font-black tracking-tight outline-none"
              placeholder={t("characters.characterName")}
            />
            <textarea
              data-testid="character-background-input"
              value={draft.background}
              onChange={(event) =>
                setDraft({ ...draft, background: event.target.value })
              }
              className="h-56 w-full rounded-3xl border border-border bg-bg-elev-1 p-6 font-serif text-sm leading-relaxed text-text-2 outline-none"
              placeholder={t("characters.characterBackground")}
            />
            <textarea
              data-testid="character-summary-input"
              value={draft.summary}
              onChange={(event) =>
                setDraft({ ...draft, summary: event.target.value })
              }
              className="h-28 w-full rounded-3xl border border-border bg-bg p-5 text-sm leading-relaxed text-text-2 outline-none"
              placeholder={t("characters.characterSummaryPlaceholder")}
            />
            <section
              data-testid="character-experience-list"
              className="rounded-3xl border border-border bg-card p-5"
            >
              <div className="mb-3 flex items-center justify-between text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                <span>Experience</span>
                <button
                  type="button"
                  data-testid="character-experience-add"
                  className="rounded border border-border px-2 py-1 text-text-2"
                  onClick={() =>
                    updateExperience([
                      ...(draft.experience || []),
                      {
                        id: `experience_${Date.now()}`,
                        chapter: "",
                        fact: "",
                        evidence: "",
                      },
                    ])
                  }
                >
                  Add
                </button>
              </div>
              <div className="space-y-2">
                {(draft.experience || []).map(
                  (entry: CharacterExperienceEntry, index: number) => (
                    <div
                      key={entry.id}
                      className="grid gap-2 md:grid-cols-[100px_1fr_1fr_auto]"
                    >
                      <input
                        data-testid={`character-experience-chapter-${entry.id}`}
                        value={entry.chapter}
                        onChange={(event) =>
                          updateExperience(
                            (draft.experience || []).map(
                              (item: CharacterExperienceEntry, i: number) =>
                                i === index
                                  ? { ...item, chapter: event.target.value }
                                  : item,
                            ),
                          )
                        }
                        placeholder="Chapter"
                        className="rounded-xl border border-border bg-bg px-3 py-2 text-sm"
                      />
                      <input
                        data-testid={`character-experience-fact-${entry.id}`}
                        value={entry.fact}
                        onChange={(event) =>
                          updateExperience(
                            (draft.experience || []).map(
                              (item: CharacterExperienceEntry, i: number) =>
                                i === index
                                  ? { ...item, fact: event.target.value }
                                  : item,
                            ),
                          )
                        }
                        placeholder="Fact"
                        className="rounded-xl border border-border bg-bg px-3 py-2 text-sm"
                      />
                      <input
                        data-testid={`character-experience-evidence-${entry.id}`}
                        value={entry.evidence || ""}
                        onChange={(event) =>
                          updateExperience(
                            (draft.experience || []).map(
                              (item: CharacterExperienceEntry, i: number) =>
                                i === index
                                  ? { ...item, evidence: event.target.value }
                                  : item,
                            ),
                          )
                        }
                        placeholder="Evidence"
                        className="rounded-xl border border-border bg-bg px-3 py-2 text-sm"
                      />
                      <button
                        type="button"
                        data-testid={`character-experience-delete-${entry.id}`}
                        className="rounded-xl border border-red/40 px-2 text-red"
                        onClick={() =>
                          updateExperience(
                            (draft.experience || []).filter(
                              (_: CharacterExperienceEntry, i: number) =>
                                i !== index,
                            ),
                          )
                        }
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ),
                )}
              </div>
            </section>
            <div className="grid gap-4 md:grid-cols-2">
              <input
                data-testid="character-traits-input"
                value={draft.traits || ""}
                onChange={(event) =>
                  setDraft({ ...draft, traits: event.target.value })
                }
                className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                placeholder={t("characters.traitsPlaceholder")}
              />
              <input
                data-testid="character-goals-input"
                value={draft.goals || ""}
                onChange={(event) =>
                  setDraft({ ...draft, goals: event.target.value })
                }
                className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                placeholder={t("characters.goalsPlaceholder")}
              />
              <input
                data-testid="character-fears-input"
                value={draft.fears || ""}
                onChange={(event) =>
                  setDraft({ ...draft, fears: event.target.value })
                }
                className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                placeholder={t("characters.fearsPlaceholder")}
              />
              <select
                value={draft.importance || "ungrouped"}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    importance: event.target.value,
                    groupKey: event.target.value,
                  })
                }
                className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
              >
                {characterPartitions.map((group) => (
                  <option key={group} value={group}>
                    {group.charAt(0).toUpperCase() + group.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-6">
            <div className="rounded-3xl border border-border bg-card p-5">
              <div className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                {t("aiPortrait.characterSummary")}
              </div>
              <div
                className="mb-3 flex items-center justify-center overflow-hidden rounded-2xl border border-border bg-bg-elev-1"
                style={{ minHeight: 160 }}
              >
                {draft.portrait ? (
                  <img
                    data-testid="character-portrait-img"
                    src={draft.portrait}
                    alt={draft.name}
                    className="max-h-48 w-full object-cover rounded-2xl"
                  />
                ) : (
                  <div
                    data-testid="character-portrait-placeholder"
                    className="flex flex-col items-center gap-2 py-8 text-text-3"
                  >
                    <ImageIcon size={32} />
                    <span className="text-xs">
                      {t("aiPortrait.noPortrait")}
                    </span>
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  data-testid="character-portrait-upload-btn"
                  className="flex-1 rounded-xl border border-border px-3 py-2 text-xs font-black text-text-2 hover:bg-hover"
                  onClick={async () => {
                    const paths = await electronApi.pickFiles({
                      filters: [
                        {
                          name: "Images",
                          extensions: ["png", "jpg", "jpeg", "webp"],
                        },
                      ],
                      multiple: false,
                    });
                    if (paths.length === 0) return;
                    const filePath = paths[0];
                    try {
                      const fileUrl = await electronApi.portraitUpload(
                        projectRoot,
                        draft.id,
                        filePath,
                      );
                      const updated = { ...draft, portrait: fileUrl };
                      setDraft(updated);
                      updateCharacter(updated);
                      setLastActionStatus(t("characters.portraitUploaded"));
                    } catch (err) {
                      setLastActionStatus(String(err));
                    }
                  }}
                >
                  <Upload size={12} className="mr-1 inline" />
                  {t("aiPortrait.upload")}
                </button>
                <button
                  type="button"
                  data-testid="character-portrait-ai-btn"
                  className="flex-1 rounded-xl bg-brand px-3 py-2 text-xs font-black text-white"
                  onClick={() => setPortraitModalOpen(true)}
                >
                  <ImageIcon size={12} className="mr-1 inline" />
                  {t("aiPortrait.generate")}
                </button>
              </div>
            </div>
            <section
              data-testid="character-custom-attributes"
              className="rounded-3xl border border-border bg-card p-5"
            >
              <div className="mb-3 flex items-center justify-between text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                <span>Custom attributes</span>
                <button
                  type="button"
                  data-testid="character-custom-attribute-add"
                  className="rounded border border-border px-2 py-1 text-text-2"
                  onClick={() =>
                    updateCustomAttributes([
                      ...(draft.customAttributes || []),
                      { id: `attribute_${Date.now()}`, label: "", value: "" },
                    ])
                  }
                >
                  Add
                </button>
              </div>
              <div className="space-y-2">
                {(draft.customAttributes || []).map(
                  (attribute: CharacterCustomAttribute, index: number) => (
                    <div key={attribute.id} className="flex gap-2">
                      <input
                        data-testid={`character-custom-attribute-label-${attribute.id}`}
                        value={attribute.label}
                        onChange={(event) =>
                          updateCustomAttributes(
                            (draft.customAttributes || []).map(
                              (item: CharacterCustomAttribute, i: number) =>
                                i === index
                                  ? { ...item, label: event.target.value }
                                  : item,
                            ),
                          )
                        }
                        placeholder="Label"
                        className="flex-1 rounded-xl border border-border bg-bg px-3 py-2 text-sm"
                      />
                      <input
                        data-testid={`character-custom-attribute-value-${attribute.id}`}
                        value={attribute.value}
                        onChange={(event) =>
                          updateCustomAttributes(
                            (draft.customAttributes || []).map(
                              (item: CharacterCustomAttribute, i: number) =>
                                i === index
                                  ? { ...item, value: event.target.value }
                                  : item,
                            ),
                          )
                        }
                        placeholder="Value"
                        className="flex-1 rounded-xl border border-border bg-bg px-3 py-2 text-sm"
                      />
                      <button
                        type="button"
                        data-testid={`character-custom-attribute-up-${attribute.id}`}
                        disabled={index === 0}
                        className="rounded-xl border border-border px-2 disabled:opacity-40"
                        onClick={() => {
                          const next = [...(draft.customAttributes || [])];
                          [next[index - 1], next[index]] = [
                            next[index],
                            next[index - 1],
                          ];
                          updateCustomAttributes(next);
                        }}
                      >
                        Up
                      </button>
                      <button
                        type="button"
                        data-testid={`character-custom-attribute-down-${attribute.id}`}
                        disabled={
                          index === (draft.customAttributes || []).length - 1
                        }
                        className="rounded-xl border border-border px-2 disabled:opacity-40"
                        onClick={() => {
                          const next = [...(draft.customAttributes || [])];
                          [next[index], next[index + 1]] = [
                            next[index + 1],
                            next[index],
                          ];
                          updateCustomAttributes(next);
                        }}
                      >
                        Down
                      </button>
                      <button
                        type="button"
                        data-testid={`character-custom-attribute-delete-${attribute.id}`}
                        className="rounded-xl border border-red/40 px-2 text-red"
                        onClick={() =>
                          updateCustomAttributes(
                            (draft.customAttributes || []).filter(
                              (_: CharacterCustomAttribute, i: number) =>
                                i !== index,
                            ),
                          )
                        }
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ),
                )}
              </div>
            </section>
            <div className="rounded-3xl border border-border bg-card p-5">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                  {t("characters.tagSystem")}
                </div>
                <button
                  type="button"
                  className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-2"
                  onClick={() => setTagOpen((current) => !current)}
                >
                  <Plus size={12} className="mr-1 inline" />
                  {t("characters.addTag")}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {activeTags.map((tag) => (
                  <button
                    key={tag.id}
                    type="button"
                    className="rounded-full border border-brand bg-brand/10 px-3 py-2 text-xs font-bold text-brand-2"
                    onClick={() =>
                      toggleCharacterTagMembership(tag.id, draft.id)
                    }
                  >
                    <Tag size={10} className="mr-2 inline" />
                    {tag.name}
                  </button>
                ))}
              </div>
              {tagOpen && (
                <div className="mt-4 rounded-2xl border border-border bg-bg p-4">
                  <div className="mb-3 flex flex-wrap gap-2">
                    {characterTags
                      .filter((tag) => !draft.tagIds.includes(tag.id))
                      .map((tag) => (
                        <button
                          key={tag.id}
                          type="button"
                          className="rounded-full border border-border px-3 py-2 text-xs text-text-2"
                          onClick={() =>
                            toggleCharacterTagMembership(tag.id, draft.id)
                          }
                        >
                          {tag.name}
                        </button>
                      ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      value={newTag}
                      onChange={(event) => setNewTag(event.target.value)}
                      className="flex-1 rounded-xl border border-border bg-bg px-3 py-2 outline-none"
                      placeholder={t("characters.newTagPlaceholder")}
                    />
                    <button
                      type="button"
                      className="rounded-xl bg-brand px-4 py-2 text-xs font-black text-white"
                      onClick={() => {
                        if (!newTag.trim()) return;
                        const tagId = `tag_${Date.now()}`;
                        addCharacterTag({
                          id: tagId,
                          name: newTag.trim(),
                          color: "#f59e0b",
                          description: "",
                          characterIds: [draft.id],
                        });
                        toggleCharacterTagMembership(tagId, draft.id);
                        setNewTag("");
                        setTagOpen(false);
                      }}
                    >
                      {t("characters.createBtn")}
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="rounded-3xl border border-border bg-card p-5">
              <div className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                {t("characters.profileMeta")}
              </div>
              <div className="grid gap-3">
                <input
                  data-testid="character-birthday-input"
                  value={draft.birthdayText || ""}
                  onChange={(event) =>
                    setDraft({ ...draft, birthdayText: event.target.value })
                  }
                  className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                  placeholder={t("characters.birthdayPlaceholder")}
                />
                <input
                  data-testid="character-speechstyle-input"
                  value={draft.speechStyle || ""}
                  onChange={(event) =>
                    setDraft({ ...draft, speechStyle: event.target.value })
                  }
                  className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                  placeholder={t("characters.speechStylePlaceholder")}
                />
                <textarea
                  data-testid="character-arc-input"
                  value={draft.arc || ""}
                  onChange={(event) =>
                    setDraft({ ...draft, arc: event.target.value })
                  }
                  className="h-32 rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                  placeholder={t("characters.characterArcPlaceholder")}
                />
              </div>
            </div>
          </div>
        </div>
      )}
      {portraitModalOpen && (
        <AIPortraitModal
          character={draft}
          projectRoot={projectRoot}
          onSave={(portraitUrl) => {
            const updated = { ...draft, portrait: portraitUrl };
            setDraft(updated);
            updateCharacter(updated);
            setPortraitModalOpen(false);
            setLastActionStatus(t("characters.portraitSaved"));
          }}
          onClose={() => setPortraitModalOpen(false)}
        />
      )}
    </div>
  );
};

const RelationshipGraphPanel: React.FC = () => {
  const {
    characters,
    characterPartitions,
    addRelationship,
    graphImportanceFilter,
    characterGroupCollapsed,
    graphSidebarLinkageEnabled,
    setGraphImportanceFilter,
    setCharacterGroupCollapsed,
    setGraphSidebarLinkageEnabled,
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [relType, setRelType] = useState("");

  const handleCreate = () => {
    if (!sourceId || !targetId || !relType.trim() || sourceId === targetId)
      return;
    addRelationship({
      id: `rel_${Date.now()}`,
      sourceId,
      targetId,
      type: relType.trim(),
      description: "",
      category: "general",
      directionality: "bidirectional",
      status: "active",
      sourceNotes: "",
    });
    setRelType("");
    setSourceId("");
    setTargetId("");
    setShowCreateForm(false);
    setLastActionStatus(t("characters.saved"));
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-6 py-4">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
            {t("characters.relationshipGraph")}
          </div>
          <div className="text-sm font-black text-text">
            {t("characters.characterNavigator")}
          </div>
        </div>
        <button
          type="button"
          data-testid="graph-create-relationship-btn"
          className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white"
          onClick={() => setShowCreateForm(!showCreateForm)}
        >
          <Plus size={13} className="mr-2 inline" />
          {t("characters.createRelationshipLabel")}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-6 py-2">
        <button
          type="button"
          data-testid="graph-importance-filter-all"
          onClick={() => {
            if (graphSidebarLinkageEnabled) {
              setCharacterGroupCollapsed({});
            } else {
              setGraphImportanceFilter([]);
            }
          }}
          className={cn(
            "rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-widest transition-colors",
            graphImportanceFilter.length === 0
              ? "border-brand bg-brand text-white"
              : "border-border text-text-3 hover:border-brand hover:text-brand",
          )}
        >
          {t("characters.filterAll", "All")}
        </button>
        {characterPartitions.map((imp) => {
          const isHidden = graphImportanceFilter.includes(imp);
          return (
            <button
              key={imp}
              type="button"
              data-testid={`graph-importance-filter-${imp}`}
              onClick={() => {
                const newFilter = isHidden
                  ? graphImportanceFilter.filter((f) => f !== imp)
                  : [...graphImportanceFilter, imp];
                if (graphSidebarLinkageEnabled) {
                  // Let useEffect derive graphImportanceFilter from collapse state
                  const nextCollapsed: Record<string, boolean> = {};
                  newFilter.forEach((g) => {
                    nextCollapsed[g] = true;
                  });
                  setCharacterGroupCollapsed(nextCollapsed);
                } else {
                  setGraphImportanceFilter(newFilter);
                }
              }}
              className={cn(
                "rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-widest transition-colors",
                isHidden
                  ? "border-border bg-bg text-text-3 opacity-40"
                  : "border-border text-text-3 hover:border-brand hover:text-brand",
              )}
            >
              {imp}
            </button>
          );
        })}
        <button
          type="button"
          data-testid="graph-sidebar-linkage-toggle"
          onClick={() =>
            setGraphSidebarLinkageEnabled(!graphSidebarLinkageEnabled)
          }
          className={cn(
            "ml-auto rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-widest transition-colors",
            graphSidebarLinkageEnabled
              ? "border-brand bg-brand/10 text-brand"
              : "border-border text-text-3",
          )}
        >
          {graphSidebarLinkageEnabled
            ? t("characters.linkageOn", "Linked")
            : t("characters.linkageOff", "Unlinked")}
        </button>
      </div>
      {showCreateForm && (
        <div className="flex items-center gap-3 border-b border-border bg-brand/5 px-6 py-3">
          <select
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            className="rounded-xl border border-border bg-bg px-3 py-2 text-sm outline-none"
          >
            <option value="" disabled>
              {t("characters.characterName")}
            </option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <span className="text-text-3">→</span>
          <select
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            className="rounded-xl border border-border bg-bg px-3 py-2 text-sm outline-none"
          >
            <option value="" disabled>
              {t("characters.characterName")}
            </option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <input
            value={relType}
            onChange={(e) => setRelType(e.target.value)}
            className="rounded-xl border border-border bg-bg px-3 py-2 text-sm outline-none"
            placeholder={t("characters.relationshipTypePlaceholder")}
          />
          <button
            type="button"
            className="rounded-xl bg-brand px-4 py-2 text-xs font-black text-white disabled:opacity-40"
            disabled={
              !sourceId || !targetId || !relType.trim() || sourceId === targetId
            }
            onClick={handleCreate}
          >
            {t("characters.createRelationshipBtn")}
          </button>
          <button
            type="button"
            className="rounded-xl border border-border px-3 py-2 text-xs text-text-2"
            onClick={() => setShowCreateForm(false)}
          >
            {t("common.cancel")}
          </button>
        </div>
      )}
      <div className="flex-1 overflow-hidden">
        <CharacterRelationshipFlow />
      </div>
    </div>
  );
};

const TagsPanel = () => {
  const {
    characters,
    characterTags,
    addCharacterTag,
    toggleCharacterTagMembership,
    moveCharacterTag,
    toggleCharacterTagCollapsed,
  } = useProjectStore();
  const { t } = useI18n();
  const [draft, setDraft] = useState({ name: "", color: "#f59e0b" });
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);
  const [tagSearch, setTagSearch] = useState("");

  useEffect(() => {
    setTagSearch("");
  }, [selectedTagId]);

  const filteredCharacters = useMemo(() => {
    if (!tagSearch.trim()) return characters;
    return characters
      .filter((c) => c.name.toLowerCase().includes(tagSearch.toLowerCase()))
      .slice(0, 20);
  }, [characters, tagSearch]);

  const renderTagNode = (tagEntry: CharacterTag) => {
    const isSelected = selectedTagId === tagEntry.id;
    return (
      <div className="rounded-2xl border border-border bg-card p-4 shadow-1">
        <button
          type="button"
          data-testid={`character-tag-select-${tagEntry.id}`}
          className="flex w-full items-center gap-3 text-left"
          onClick={() => setSelectedTagId(isSelected ? null : tagEntry.id)}
        >
          <div
            className="h-3 w-3 flex-shrink-0 rounded-full"
            style={{ background: tagEntry.color }}
          />
          <div className="text-sm font-black text-text">{tagEntry.name}</div>
          <span className="ml-auto rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] font-black text-text-3">
            ({tagEntry.characterIds.length})
          </span>
        </button>
        {isSelected && (
          <div className="mt-3">
            <input
              type="text"
              data-testid="tag-character-search-input"
              value={tagSearch}
              onChange={(event) => setTagSearch(event.target.value)}
              placeholder={t("tags.searchCharacters")}
              className="mb-3 w-full rounded-xl border border-border bg-bg px-3 py-2 text-sm outline-none"
            />
            <div className="flex flex-wrap gap-2">
              {filteredCharacters.map((character) => {
                const active = tagEntry.characterIds.includes(character.id);
                return (
                  <button
                    key={character.id}
                    type="button"
                    className={cn(
                      "rounded-full border px-3 py-2 text-xs font-bold transition-colors",
                      active
                        ? "border-brand bg-brand/15 text-brand-2"
                        : "border-border text-text-2 hover:border-brand",
                    )}
                    onClick={() =>
                      toggleCharacterTagMembership(tagEntry.id, character.id)
                    }
                  >
                    {character.name}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
          {t("characters.tagSystem")}
        </div>
        <div className="mt-2 text-3xl font-black text-text">
          {t("characters.characterTags")}
        </div>
      </div>
      <div className="mb-8 grid gap-4 rounded-3xl border border-border bg-card p-6 lg:grid-cols-[1fr_auto_auto]">
        <input
          value={draft.name}
          onChange={(event) =>
            setDraft((current) => ({ ...current, name: event.target.value }))
          }
          placeholder={t("characters.tagNamePlaceholder")}
          className="rounded-xl border border-border bg-bg px-4 py-3 outline-none"
        />
        <input
          value={draft.color}
          onChange={(event) =>
            setDraft((current) => ({ ...current, color: event.target.value }))
          }
          className="h-12 rounded-xl border border-border bg-bg px-4 py-3 outline-none"
        />
        <button
          type="button"
          className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white"
          onClick={() => {
            if (!draft.name.trim()) return;
            addCharacterTag({
              id: `tag_${Date.now()}`,
              name: draft.name.trim(),
              color: draft.color,
              description: "",
              characterIds: [],
              parentTagId: null,
              sortOrder: characterTags.length,
            });
            setDraft({ name: "", color: "#f59e0b" });
          }}
        >
          <Plus size={14} className="mr-2 inline" />
          {t("characters.createTagBtn")}
        </button>
      </div>
      <TagTreePanel
        nodes={characterTags}
        renderNodeContent={(node) => renderTagNode(node as CharacterTag)}
        onMove={(dragId, newParentId, insertBeforeSiblingId) =>
          moveCharacterTag(dragId, newParentId, insertBeforeSiblingId)
        }
        onToggleCollapse={toggleCharacterTagCollapsed}
        testIdPrefix="character-tag"
      />
    </div>
  );
};
