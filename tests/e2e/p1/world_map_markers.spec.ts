import { expect, test } from '@playwright/test';

test('world map markers use stable selectors and open the filtered timeline events view', async ({ page }) => {
  await page.goto('http://localhost:3000/world/maps');

  const markers = page.getByTestId('world-map-marker');
  await expect(markers).toHaveCount(4);
  await markers.filter({ hasText: 'Glass Bridge' }).click();

  await expect(page).toHaveURL(/\/timeline\/timeline\?worldItem=loc_glass_bridge/);
  await expect(page.getByTestId('timeline-filter-state')).toContainText('Glass Bridge');
});
