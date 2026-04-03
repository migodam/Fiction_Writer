import { test, expect } from '@playwright/test';

async function openTimelineWorkspace(page) {
  await page.goto('/');
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
}

async function getPoint(locator) {
  const x = Number(await locator.getAttribute('data-position-x'));
  const y = Number(await locator.getAttribute('data-position-y'));
  return { x, y };
}

async function dragLocator(page, locator, dx, dy) {
  const box = await locator.boundingBox();
  if (!box) {
    throw new Error('Target locator is not visible');
  }

  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + dx, startY + dy, { steps: 12 });
  await page.mouse.up();
}

function expectCloseToPoint(actual, expected, tolerance = 1) {
  expect(Math.abs(actual.x - expected.x)).toBeLessThanOrEqual(tolerance);
  expect(Math.abs(actual.y - expected.y)).toBeLessThanOrEqual(tolerance);
}

test.describe('Timeline canvas', () => {
  test.beforeEach(async ({ page }) => {
    await openTimelineWorkspace(page);
  });

  test('dragging a host timeline handle moves snapped handles on dependent timelines', async ({ page }) => {
    const mainStartHandle = page.getByTestId('timeline-branch-handle-start-branch_main');
    const arrivalNode = page.getByTestId('timeline-event-node-event_arrival');
    const dependentStartHandles = [
      page.getByTestId('timeline-branch-handle-start-branch_shadow'),
      page.getByTestId('timeline-branch-handle-start-branch_public'),
      page.getByTestId('timeline-branch-handle-start-branch_echo'),
    ];

    const initialArrival = await getPoint(arrivalNode);

    await dragLocator(page, mainStartHandle, -28, 82);

    const movedArrival = await getPoint(arrivalNode);
    expect(Math.abs(movedArrival.x - initialArrival.x)).toBeGreaterThan(5);
    expect(Math.abs(movedArrival.y - initialArrival.y)).toBeGreaterThan(5);

    for (const handle of dependentStartHandles) {
      await expect(handle).toBeVisible();
      expectCloseToPoint(await getPoint(handle), movedArrival);
    }
  });

  test('fully overlapped timelines render as parallel offset curves', async ({ page }) => {
    const overlappedBranch = page.getByTestId('timeline-branch-branch_echo');
    const overlapGroup = page.getByTestId('timeline-branch-overlap-branch_echo');

    await expect(overlappedBranch).toBeVisible();
    await expect(overlapGroup).toBeVisible();
    await expect(page.getByTestId('timeline-branch-overlap-path-branch_echo-0')).toBeVisible();
    await expect(page.getByTestId('timeline-branch-overlap-path-branch_echo-1')).toBeVisible();
    await expect(overlappedBranch).toHaveAttribute('data-render-mode', 'parallel');
    await expect(overlappedBranch).toHaveAttribute('data-overlap-host-branch-id', 'branch_main');
  });

  test('can create, edit, and delete a timeline event', async ({ page }) => {
    await page.getByTestId('add-event-btn').click();
    await page.getByTestId('create-event-title-input').fill('Canvas Smoke Event');
    await page.getByTestId('create-event-summary-input').fill('Smoke coverage for timeline event CRUD.');
    await page.getByTestId('create-event-time-input').fill('Day 4 - Noon');
    await page.getByTestId('create-event-save-btn').click();

    const createdEventNode = page.locator('[data-testid^="timeline-event-node-"]').last();
    await expect(page.getByText('Canvas Smoke Event', { exact: true })).toBeVisible();
    await createdEventNode.click();

    await expect(page.getByTestId('event-edit-modal')).toBeVisible();
    await page.getByTestId('event-edit-title').fill('Canvas Smoke Event Updated');
    await page.getByTestId('event-edit-save-btn').click();

    await expect(page.getByText('Canvas Smoke Event Updated', { exact: true })).toBeVisible();
    await createdEventNode.click();
    await expect(page.getByTestId('event-edit-modal')).toBeVisible();
    await page.getByTestId('event-edit-delete-btn').click();

    await expect(page.getByText('Canvas Smoke Event Updated', { exact: true })).toHaveCount(0);
  });
});
