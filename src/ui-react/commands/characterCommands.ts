import type { Character } from "../models/project";
import { commandClipboard } from "./clipboard";
import type { AppCommand, CommandContext } from "./types";

export type CharacterCommandId = "character:duplicate" | "character:archive";

export interface CharacterCommandContext {
  character: Character;
  characters: Character[];
  navigate: (path: string) => void;
  addCharacter: (c: Character) => void;
  setConfirmArchiveId: (id: string) => void;
}

export interface CharacterCommandSpec {
  id: CharacterCommandId;
  labelKey: string;
  destructive?: boolean;
  execute: (ctx: CharacterCommandContext) => void;
}

export const CHARACTER_COMMANDS: Record<
  CharacterCommandId,
  CharacterCommandSpec
> = {
  "character:duplicate": {
    id: "character:duplicate",
    labelKey: "characters.duplicateCharacter",
    execute: (ctx) => {
      const newId = `char_${Date.now()}`;
      ctx.addCharacter({
        ...ctx.character,
        id: newId,
        name: `${ctx.character.name} (copy)`,
        relationshipIds: [],
        linkedSceneIds: [],
        linkedEventIds: [],
      });
      ctx.navigate(`/characters/profile/${newId}`);
    },
  },
  "character:archive": {
    id: "character:archive",
    labelKey: "characters.archiveCharacter",
    destructive: true,
    execute: (ctx) => ctx.setConfirmArchiveId(ctx.character.id),
  },
};

export interface CharacterMenuContext extends CommandContext {
  character: Character;
  addCharacter: (character: Character) => void;
  setConfirmArchiveId: (id: string) => void;
  navigate: (path: string) => void;
}

const duplicateCharacter = (character: Character): Character => ({
  ...character,
  id: `char_${Date.now()}`,
  name: `${character.name} (copy)`,
  relationshipIds: [],
  linkedSceneIds: [],
  linkedEventIds: [],
});

/** Shared command contract for character cards and future keyboard bindings. */
export const getCharacterContextCommands = (
  canPaste: boolean,
): AppCommand<CharacterMenuContext>[] => [
  {
    id: "character-open-profile",
    label: {
      key: "contextMenu.character.openProfile",
      fallback: "Open Profile",
    },
    execute: ({ character, navigate }) =>
      navigate(`/characters/profile/${character.id}`),
  },
  {
    id: "character-duplicate",
    label: { key: "contextMenu.character.duplicate", fallback: "Duplicate" },
    execute: ({ character, addCharacter, navigate }) => {
      const duplicate = duplicateCharacter(character);
      addCharacter(duplicate);
      navigate(`/characters/profile/${duplicate.id}`);
    },
  },
  {
    id: "character-copy",
    label: { key: "contextMenu.copy", fallback: "Copy" },
    shortcut: "Ctrl+C",
    execute: ({ character }) =>
      commandClipboard.set("character", "copy", character),
  },
  {
    id: "character-paste",
    label: { key: "contextMenu.paste", fallback: "Paste" },
    shortcut: "Ctrl+V",
    disabled: !canPaste,
    disabledReason: canPaste
      ? undefined
      : {
          key: "contextMenu.character.pasteUnavailable",
          fallback: "Copy a character first",
        },
    execute: ({ addCharacter }) => {
      const entry = commandClipboard.get<Character>("character");
      if (!entry) return;
      addCharacter(duplicateCharacter(entry.value));
      commandClipboard.clear();
    },
  },
  {
    id: "character-open-relationship-graph",
    label: {
      key: "contextMenu.character.openRelationshipGraph",
      fallback: "Open Relationship Graph",
    },
    execute: ({ character, navigate }) =>
      navigate(
        `/characters/relationship-graph?characterId=${encodeURIComponent(character.id)}`,
      ),
  },
  {
    id: "character-archive",
    label: { key: "contextMenu.archive", fallback: "Archive" },
    destructive: true,
    execute: ({ character, setConfirmArchiveId }) =>
      setConfirmArchiveId(character.id),
  },
];
