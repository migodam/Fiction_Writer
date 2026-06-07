import type { Character } from '../models/project';

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
