import { expect, test, type Page } from '@playwright/test';

type Box = { x: number; y: number; width: number; height: number };

const STAR_CHARACTERS = [
  { id: 'char_han_li', name: '韩立', importance: 'core' },
  { id: 'char_mo_daifu', name: '莫大夫', importance: 'major' },
  { id: 'char_zhang_tie', name: '张铁', importance: 'major' },
  { id: 'char_wu_yan', name: '武言', importance: 'supporting' },
  { id: 'char_han_sanshu', name: '韩三叔', importance: 'supporting' },
].map((entry) => ({
  ...entry,
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
  groupKey: entry.importance,
  relationshipIds: [],
  povInsights: null,
  statusFlags: { alive: true },
}));

const STAR_RELATIONSHIPS = [
  ['rel_han_mo', 'char_han_li', 'char_mo_daifu', '师徒控制'],
  ['rel_han_zhang', 'char_han_li', 'char_zhang_tie', '同门伙伴'],
  ['rel_han_wu', 'char_han_li', 'char_wu_yan', '门内竞争'],
  ['rel_han_sanshu', 'char_han_li', 'char_han_sanshu', '家族牵引'],
].map(([id, sourceId, targetId, type]) => ({
  id,
  sourceId,
  targetId,
  type,
  description: '',
  category: 'general',
  directionality: 'bidirectional',
  status: 'active',
  strength: 7,
  sourceNotes: '',
}));

async function openRelationshipGraphWithStar(page: Page) {
  await page.goto('/characters/relationship-graph');
  await page.evaluate(
    ({ characters, relationships }) => {
      const store = (window as any).__narrativeStore;
      if (!store) throw new Error('__narrativeStore not exposed');
      store.setState((state: any) => ({
        ...state,
        characters,
        relationships,
        graphImportanceFilter: [],
        characterGroupCollapsed: {},
      }));
    },
    { characters: STAR_CHARACTERS, relationships: STAR_RELATIONSHIPS },
  );
  await expect(page.getByTestId('character-relationship-flow')).toBeVisible();
  await expect(page.getByTestId('relationship-character-node-char_han_li')).toBeVisible();
  await expect(page.getByTestId('relationship-edge-label-rel_han_mo')).toBeVisible();
}

function overlapArea(a: Box, b: Box) {
  const width = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
  const height = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
  return width * height;
}

test.describe('Cluster and force-lite layout modes', () => {
  test('cluster layout places core and supporting tiers in distinct columns', async ({ page }) => {
    await openRelationshipGraphWithStar(page);
    await page.getByTestId('graph-layout-mode-cluster').click();
    await page.waitForTimeout(300);

    const coreBox = await page.getByTestId('relationship-character-node-char_han_li').boundingBox();
    const supportBox = await page.getByTestId('relationship-character-node-char_wu_yan').boundingBox();
    expect(coreBox).not.toBeNull();
    expect(supportBox).not.toBeNull();
    expect(Math.abs(coreBox!.x - supportBox!.x)).toBeGreaterThan(100);
  });

  test('force-lite layout is deterministic — same rounded positions after toggle away and back', async ({ page }) => {
    await openRelationshipGraphWithStar(page);
    await page.getByTestId('graph-layout-mode-force-lite').click();
    await page.waitForTimeout(300);

    const capture = async () =>
      Promise.all(
        STAR_CHARACTERS.map(async (c) => {
          const box = await page.getByTestId(`relationship-character-node-${c.id}`).boundingBox();
          return { id: c.id, x: Math.round((box?.x ?? 0) / 5), y: Math.round((box?.y ?? 0) / 5) };
        }),
      );

    const pos1 = await capture();
    await page.getByTestId('graph-layout-mode-radial').click();
    await page.waitForTimeout(150);
    await page.getByTestId('graph-layout-mode-force-lite').click();
    await page.waitForTimeout(300);
    const pos2 = await capture();

    for (const p1 of pos1) {
      const p2 = pos2.find((p) => p.id === p1.id)!;
      expect(Math.abs(p1.x - p2.x)).toBeLessThanOrEqual(1);
      expect(Math.abs(p1.y - p2.y)).toBeLessThanOrEqual(1);
    }
  });
});

test.describe('Character relationship graph layout', () => {
  test('star topology nodes are radially distributed instead of a single row', async ({ page }) => {
    await openRelationshipGraphWithStar(page);

    const boxes = await Promise.all(
      STAR_CHARACTERS.map(async (char) => {
        const box = await page.getByTestId(`relationship-character-node-${char.id}`).boundingBox();
        expect(box, `${char.id} should have a rendered node box`).not.toBeNull();
        return box!;
      }),
    );

    const roundedYValues = new Set(boxes.map((box) => Math.round(box.y / 10) * 10));
    expect(roundedYValues.size).toBeGreaterThan(2);

    const centerRole = await page.getByTestId('relationship-character-node-char_han_li').getAttribute('data-layout-role');
    expect(centerRole).toBe('center');
  });

  test('relationship edge labels have separate readable boxes', async ({ page }) => {
    await openRelationshipGraphWithStar(page);

    const labelBoxes = await Promise.all(
      STAR_RELATIONSHIPS.map(async (rel) => {
        const box = await page.getByTestId(`relationship-edge-label-${rel.id}`).boundingBox();
        expect(box, `${rel.id} should have a rendered edge label box`).not.toBeNull();
        return { id: rel.id, box: box! };
      }),
    );

    for (let i = 0; i < labelBoxes.length; i++) {
      for (let j = i + 1; j < labelBoxes.length; j++) {
        const area = overlapArea(labelBoxes[i].box, labelBoxes[j].box);
        expect(area, `${labelBoxes[i].id} label overlaps ${labelBoxes[j].id}`).toBeLessThan(8);
      }
    }
  });
});
