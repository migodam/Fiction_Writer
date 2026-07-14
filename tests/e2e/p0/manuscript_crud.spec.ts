import { test, expect } from "@playwright/test";

test.describe("Manuscript workspace", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("http://localhost:3000/writing/manuscript");
  });

  test("manuscript workspace renders", async ({ page }) => {
    await expect(page.getByTestId("manuscript-workspace")).toBeVisible();
  });

  test("add node creates entry in manuscript tree", async ({ page }) => {
    await expect(page.getByTestId("manuscript-workspace")).toBeVisible();

    await page.getByTestId("manuscript-add-node-btn").click();

    await page
      .getByTestId("manuscript-node-title-input")
      .fill("New Chapter Node");
    await page.getByTestId("manuscript-node-confirm-btn").click();

    await expect(page.getByTestId("manuscript-workspace")).toContainText(
      "New Chapter Node",
    );
  });

  test("context menu supports manuscript actions and keyboard navigation", async ({
    page,
  }) => {
    await page.getByTestId("manuscript-add-node-btn").click();
    await page.getByTestId("manuscript-node-title-input").fill("Context Node");
    await page.getByTestId("manuscript-node-confirm-btn").click();

    const node = page
      .getByTestId(/^manuscript-node-(?!toggle-)/)
      .filter({ hasText: "Context Node" });
    await node.click({ button: "right" });
    await expect(page.getByTestId("global-context-menu")).toBeVisible();

    for (const id of [
      "add-child",
      "manuscript-add-sibling",
      "manuscript-duplicate",
      "manuscript-open-editor",
      "copy",
      "cut",
      "paste",
      "edit-title",
      "delete",
    ]) {
      await expect(page.getByTestId(`context-menu-item-${id}`)).toBeVisible();
    }

    await page.keyboard.press("End");
    await expect(page.getByTestId("context-menu-item-delete")).toHaveClass(
      /context-menu__item--active/,
    );
    await page.keyboard.press("Home");
    await expect(page.getByTestId("context-menu-item-add-child")).toHaveClass(
      /context-menu__item--active/,
    );
  });
});
