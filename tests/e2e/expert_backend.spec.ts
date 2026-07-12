import { expect, test } from "@playwright/test";

// Expert-user flows over the seeded, mocked backend (run `python seed.py` first).
// Normal users work in the dashboard; THIS UI is the expert backend.
test.describe("Expert Backend", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("open-expert").click();
    await expect(page.getByTestId("expert-backend")).toBeVisible();
  });

  test("edits the threshold, versioned", async ({ page }) => {
    const threshold = page.getByTestId("expert-threshold");
    await expect(threshold).toBeVisible();
    await threshold.fill("42");
    await page.getByTestId("expert-save").click();
    await expect(page.getByTestId("expert-msg")).toContainText("saved", { ignoreCase: true });
    // History records the change.
    await expect(page.getByTestId("expert-history")).toContainText("Edited in expert backend");
  });

  test("adds a category with headline + explanation", async ({ page }) => {
    await page.getByTestId("expert-new-headline").fill("Partner ecosystem");
    await page
      .locator(".expert-add .lib-q")
      .fill("Do we have partners to close capability gaps? High score = signed partner available.");
    await page.getByTestId("expert-add").click();
    // Headlines render as <input> values (not textContent) — assert on the value.
    await expect(page.locator('[data-testid="expert-category"] input').last()).toHaveValue("Partner ecosystem");
  });

  test("edits the AI prompts (requirement + date detection)", async ({ page }) => {
    const prompts = page.getByTestId("expert-prompt");
    await expect(prompts).toHaveCount(2);
    const first = prompts.first();
    await first.locator("textarea").fill("Extract ALL required documents, incl. Eigenerklärungen and Bindefrist.");
    await first.getByRole("button", { name: "Save prompt" }).click();
    await expect(page.getByTestId("expert-prompts")).toContainText("v1");
  });
});
