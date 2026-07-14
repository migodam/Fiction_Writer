import React from "react";
import { Trash2 } from "lucide-react";
import { useProjectStore } from "../store";
import { useI18n } from "../i18n";

interface ArchiveImpactModalProps {
  characterId: string;
  characterName: string;
  onArchive: () => void;
  onHardDelete: () => void;
  onCancel: () => void;
}

export const ArchiveImpactModal: React.FC<ArchiveImpactModalProps> = ({
  characterId,
  characterName,
  onArchive,
  onHardDelete,
  onCancel,
}) => {
  const {
    relationships,
    timelineEvents,
    scenes,
    worldItems,
    characterTags,
    graphBoards,
    scripts,
    storyboards,
  } = useProjectStore();
  const { t } = useI18n();

  const relCount = relationships.filter(
    (r) => r.sourceId === characterId || r.targetId === characterId,
  ).length;
  const eventCount = timelineEvents.filter((e) =>
    (e.participantCharacterIds ?? []).includes(characterId),
  ).length;
  const sceneCount = scenes.filter((s) =>
    (s.linkedCharacterIds ?? []).includes(characterId),
  ).length;
  const povSceneCount = scenes.filter(
    (s) => s.povCharacterId === characterId,
  ).length;
  const worldItemCount = worldItems.filter((item) =>
    (item.linkedCharacterIds ?? []).includes(characterId),
  ).length;
  const tagCount = characterTags.filter((tag) =>
    (tag.characterIds ?? []).includes(characterId),
  ).length;
  const graphCount = graphBoards.filter((board) =>
    board.nodes.some(
      (node) =>
        node.linkedEntityId === characterId &&
        (node.linkedEntityType === "character" ||
          node.kind === "character_ref"),
    ),
  ).length;
  const scriptCount = scripts.filter((script) =>
    (script.linkedCharacterIds ?? []).includes(characterId),
  ).length;
  const storyboardCount = storyboards.filter((storyboard) =>
    storyboard.shots.some((shot) =>
      (shot.linkedCharacterIds ?? []).includes(characterId),
    ),
  ).length;
  const hasRefs = [
    relCount,
    eventCount,
    sceneCount,
    povSceneCount,
    worldItemCount,
    tagCount,
    graphCount,
    scriptCount,
    storyboardCount,
  ].some((count) => count > 0);

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div
        data-testid="archive-impact-modal"
        className="w-96 rounded-3xl border border-border bg-bg-elev-1 p-6 shadow-2xl"
      >
        <div className="mb-4 text-lg font-black text-text">
          {t("characters.archiveCharacter", "Archive Character")}:{" "}
          {characterName}
        </div>
        {hasRefs && (
          <div
            data-testid="archive-impact-list"
            className="mb-4 rounded-2xl border border-border bg-bg p-4 text-sm text-text-2"
          >
            <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-text-3">
              {t("characters.impactList", "References affected by deletion")}
            </div>
            {relCount > 0 && (
              <div className="text-text-2">
                · {relCount} {t("characters.relationships", "relationship(s)")}
              </div>
            )}
            {eventCount > 0 && (
              <div className="text-text-2">
                · {eventCount}{" "}
                {t("characters.timelineEvents", "timeline event(s)")}
              </div>
            )}
            {sceneCount > 0 && (
              <div data-testid="archive-impact-scenes" className="text-text-2">
                · {sceneCount} {t("characters.scenes", "scene(s)")}
              </div>
            )}
            {povSceneCount > 0 && (
              <div
                data-testid="archive-impact-pov-scenes"
                className="text-text-2"
              >
                · {povSceneCount}{" "}
                {t("characters.povScenes", "scene POV reference(s)")}
              </div>
            )}
            {worldItemCount > 0 && (
              <div data-testid="archive-impact-world-items">
                · {worldItemCount} {t("characters.worldItems", "world item(s)")}
              </div>
            )}
            {tagCount > 0 && (
              <div data-testid="archive-impact-tags">
                · {tagCount} {t("characters.tags", "tag(s)")}
              </div>
            )}
            {graphCount > 0 && (
              <div data-testid="archive-impact-graphs">
                · {graphCount} {t("characters.graphBoards", "graph board(s)")}
              </div>
            )}
            {scriptCount > 0 && (
              <div data-testid="archive-impact-scripts">
                · {scriptCount} {t("characters.scripts", "script(s)")}
              </div>
            )}
            {storyboardCount > 0 && (
              <div data-testid="archive-impact-storyboards">
                · {storyboardCount}{" "}
                {t("characters.storyboards", "storyboard(s)")}
              </div>
            )}
          </div>
        )}
        <div className="flex gap-3">
          <button
            data-testid="archive-confirm-btn"
            type="button"
            className="flex-1 rounded-xl bg-brand px-4 py-2 text-sm font-black text-white"
            onClick={onArchive}
          >
            {t("characters.archiveBtn", "Archive")}
          </button>
          {!hasRefs && (
            <button
              data-testid="hard-delete-confirm-btn"
              type="button"
              className="flex-1 rounded-xl border border-red/40 px-4 py-2 text-sm font-black text-red hover:bg-red/10"
              onClick={onHardDelete}
            >
              <Trash2 size={12} className="mr-1 inline" />
              {t("common.delete", "Delete")}
            </button>
          )}
          <button
            data-testid="archive-cancel-btn"
            type="button"
            className="rounded-xl border border-border px-4 py-2 text-sm text-text-2 hover:bg-hover"
            onClick={onCancel}
          >
            {t("common.cancel", "Cancel")}
          </button>
        </div>
      </div>
    </div>
  );
};
