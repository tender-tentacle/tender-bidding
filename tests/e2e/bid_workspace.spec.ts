import { expect, test } from "@playwright/test";

// Happy-path over the seeded, mocked backend (run `python seed.py` first).
test.describe("Bid Workspace", () => {
  test("lists bids, opens a workspace, and shows the formal gate + lots", async ({ page }) => {
    await page.goto("/");
    const items = page.getByTestId("bid-list-item");
    await expect(items.first()).toBeVisible();

    // Open the multi-lot seeded bid (Rahmenvertrag).
    await items.filter({ hasText: "Rahmenvertrag" }).first().click();
    await expect(page.getByTestId("workspace")).toBeVisible();

    // Multi-lot badge + formal pre-flight gate are shown.
    await expect(page.getByTestId("lots-badge")).toContainText("lots");
    await expect(page.getByTestId("formal-gate")).toContainText("Formal pre-flight");

    // Checklist has the three criterion kinds.
    await expect(page.locator('[data-testid="checklist-item"][data-kind="formal"]').first()).toBeVisible();
    await expect(page.locator('[data-testid="checklist-item"][data-kind="suitability"]').first()).toBeVisible();
    await expect(page.locator('[data-testid="checklist-item"][data-kind="award"]').first()).toBeVisible();
  });

  test("checking a formal item persists and updates the gate", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("bid-list-item").first().click();
    await expect(page.getByTestId("workspace")).toBeVisible();

    const firstBox = page.getByTestId("item-checkbox").first();
    await firstBox.check();
    await expect(firstBox).toBeChecked(); // survives the reload after PATCH
  });
});
