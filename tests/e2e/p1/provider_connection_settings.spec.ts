import { expect, test } from "@playwright/test";
import { TEST_NARRATIVE_IDE_INVOKE_METHODS } from "../helpers/narrativeIdeBridge";

test.describe("Provider connection settings", () => {
  test("shows verified connection details and activates the tested provider", async ({
    page,
  }) => {
    await page.addInitScript(
      ({ bridgeMethods }) => {
        const savedSettings: Record<string, unknown>[] = [];
        const handlers: Record<
          string,
          (payload?: Record<string, unknown>) => unknown
        > = {
          [bridgeMethods.loadAppSettings]: () => null,
          [bridgeMethods.saveAppSettings]: (payload) => {
            savedSettings.push(payload ?? {});
            return payload;
          },
          [bridgeMethods.testProviderConnection]: (payload) => ({
            ok: true,
            code: "connected",
            message: "Connection verified.",
            httpStatus: 200,
            latencyMs: 42,
            modelCount: 3,
          }),
        };
        (window as any).__providerConnectionSavedSettings = savedSettings;
        (window as any).narrativeIDE = Object.fromEntries(
          Object.entries(bridgeMethods).map(([method, channel]) => [
            method,
            (payload?: Record<string, unknown>) =>
              Promise.resolve(handlers[channel]?.(payload)),
          ]),
        );
      },
      { bridgeMethods: TEST_NARRATIVE_IDE_INVOKE_METHODS },
    );

    await page.goto("http://localhost:3000");
    await page.getByTestId("toolbar-settings").click();
    await page.getByTestId("settings-tab-ai").click();
    await page
      .getByTestId("settings-provider-endpoint")
      .fill("https://models.example.test/v1");
    await page.getByTestId("settings-provider-api-key").fill("test-key");
    await expect(page.getByText(/models\.example\.test\/v1\/models/)).toBeVisible();
    await page.getByTestId("settings-provider-test").click();

    await expect(
      page.getByTestId("settings-provider-test-status"),
    ).toContainText("Connection OK");
    await expect(
      page.getByTestId("settings-provider-test-status"),
    ).toContainText("3 models found in 42 ms");
    await expect(
      page.getByTestId("settings-provider-test-status"),
    ).not.toContainText("test-key");

    await page.getByTestId("settings-provider-activate").click();
    await expect
      .poll(() =>
        page.evaluate(() => (window as any).__providerConnectionSavedSettings),
      )
      .toContainEqual(
        expect.objectContaining({
          selectedProviderProfileId: "provider_openai_default",
        }),
      );
    await expect
      .poll(() =>
        page.evaluate(() => (window as any).__providerConnectionSavedSettings),
      )
      .toContainEqual(
        expect.objectContaining({
          providerProfiles: expect.arrayContaining([
            expect.objectContaining({
              id: "provider_openai_default",
              enabled: true,
            }),
          ]),
        }),
      );
  });
});
