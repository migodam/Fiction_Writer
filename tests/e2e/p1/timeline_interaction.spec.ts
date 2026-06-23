import { expect, test } from '@playwright/test';

async function openTimelineWorkspace(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
}

async function getPoint(locator: import('@playwright/test').Locator) {
  const x = Number(await locator.getAttribute('data-position-x'));
  const y = Number(await locator.getAttribute('data-position-y'));
  return { x, y };
}

async function dragLocator(
  page: import('@playwright/test').Page,
  locator: import('@playwright/test').Locator,
  dx: number,
  dy: number,
  modifiers: Array<'Alt' | 'Control' | 'Meta' | 'Shift'> = [],
) {
  const box = await locator.boundingBox();
  if (!box) throw new Error('Target locator is not visible');

  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  for (const modifier of modifiers) {
    await page.keyboard.down(modifier);
  }
  await page.mouse.down();
  await page.mouse.move(startX + dx, startY + dy, { steps: 12 });
  await page.mouse.up();
  for (const modifier of modifiers.reverse()) {
    await page.keyboard.up(modifier);
  }
}

test.describe('Timeline branch interactions', () => {
  test.beforeEach(async ({ page }) => {
    await openTimelineWorkspace(page);
  });

  test('branch middle handle exists and can be dragged', async ({ page }) => {
    const middleHandle = page.getByTestId('timeline-branch-handle-middle-branch_main');
    await expect(middleHandle).toBeVisible();

    const before = await getPoint(middleHandle);
    await dragLocator(page, middleHandle, 72, 96);
    const after = await getPoint(middleHandle);

    expect(Math.abs(after.y - before.y)).toBeGreaterThan(20);
  });

  test('branch endpoint handles remain available', async ({ page }) => {
    await expect(page.getByTestId('timeline-branch-handle-start-branch_main')).toBeVisible();
    await expect(page.getByTestId('timeline-branch-handle-end-branch_main')).toBeVisible();
    await expect(page.getByTestId('timeline-branch-handle-start-branch_shadow')).toBeVisible();
    await expect(page.getByTestId('timeline-branch-handle-end-branch_shadow')).toBeVisible();
  });

  test('modifier-key branch interactions keep the canvas stable', async ({ page, browserName }) => {
    const segment = page.getByTestId('timeline-branch-segment-branch_shadow');
    await expect(segment).toBeVisible();

    await dragLocator(page, page.getByTestId('timeline-branch-handle-middle-branch_shadow'), 12, 44, ['Shift']);

    const box = await segment.boundingBox();
    if (!box) throw new Error('Branch segment is not visible');
    await page.keyboard.down('Alt');
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.keyboard.up('Alt');

    const multiSelectModifier = browserName === 'webkit' ? 'Meta' : 'Control';
    await dragLocator(
      page,
      page.getByTestId('timeline-branch-handle-middle-branch_public'),
      8,
      24,
      [multiSelectModifier],
    );

    await expect(page.getByTestId('timeline-canvas')).toBeVisible();
    await expect(page.getByTestId('timeline-branch-handle-middle-branch_public')).toBeVisible();
  });
});
