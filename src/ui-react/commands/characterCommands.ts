import type { Character } from '../models/project';
import { commandClipboard } from './clipboard';
import type { AppCommand, CommandContext } from './types';

export type CharacterCommandId = 'character:duplicate' | 'character:archive';

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

export const CHARACTER_COMMANDS: Record<CharacterCommandId, CharacterCommandSpec> = {
  'character:duplicate': {
    id: 'character:duplicate',
    labelKey: 'characters.duplicateCharacter',
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
  'character:archive': {
    id: 'character:archive',
    labelKey: 'characters.archiveCharacter',
    destructive: true,
    execute: (ctx) => ctx.setConfirmArchiveId(ctx.character.id),
  },
};

export interface CharacterMenuContext extends CommandContext {
  character: Character;
  addCharacter: (character: Character) => void;
  setConfirmArchiveId: (id: string) => void;
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
export const getCharacterContextCommands = (canPaste: boolean): AppCommand<CharacterMenuContext>[] => [
  {
    id: 'character-new',
    label: 'New',
    disabled: true,
    disabledReason: 'Use the New Character button to choose the character type',
    execute: () => undefined,
  },
  {
    id: 'character-copy',
    label: 'Copy',
    shortcut: 'Ctrl+C',
    execute: ({ character }) => commandClipboard.set('character', 'copy', character),
  },
  {
    id: 'character-cut',
    label: 'Cut',
    shortcut: 'Ctrl+X',
    disabled: true,
    disabledReason: 'Cut is unavailable because characters can have linked records',
    execute: () => undefined,
  },
  {
    id: 'character-paste',
    label: 'Paste',
    shortcut: 'Ctrl+V',
    disabled: !canPaste,
    disabledReason: canPaste ? undefined : 'Copy a character first',
    execute: ({ addCharacter }) => {
      const entry = commandClipboard.get<Character>('character');
      if (!entry) return;
      addCharacter(duplicateCharacter(entry.value));
      commandClipboard.clear();
    },
  },
  {
    id: 'character-rename',
    label: 'Rename',
    disabled: true,
    disabledReason: 'Rename characters in the profile editor',
    execute: () => undefined,
  },
  {
    id: 'character-move',
    label: 'Move',
    disabled: true,
    disabledReason: 'Drag a character to an importance group to move it',
    execute: () => undefined,
  },
  {
    id: 'character-merge',
    label: 'Merge',
    disabled: true,
    disabledReason: 'Character merge is not available yet',
    execute: () => undefined,
  },
  {
    id: 'character-archive',
    label: 'Archive',
    destructive: true,
    execute: ({ character, setConfirmArchiveId }) => setConfirmArchiveId(character.id),
  },
  {
    id: 'character-delete',
    label: 'Delete',
    destructive: true,
    execute: ({ character, setConfirmArchiveId }) => setConfirmArchiveId(character.id),
  },
];
