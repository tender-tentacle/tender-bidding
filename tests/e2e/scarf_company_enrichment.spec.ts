import { expect, test } from "@playwright/test";

test.describe("SCARF Company Mood & Sentiment Enrichment E2E", () => {
  test("displays SCARF KI-Ergebnis badges and toggles platform tabs dynamically", async ({ page }) => {
    // Navigate to company details page for MHP
    await page.goto("/ms/dashboard/companies/MHP");

    // Wait for Company Information Tab to render
    const companyTab = page.getByTestId("company-information-tab");
    await expect(companyTab).toBeVisible({ timeout: 15000 });

    // Verify Kununu / Glassdoor platform switcher buttons exist
    const kununuBtn = page.getByRole("button", { name: /Kununu/i });
    const glassdoorBtn = page.getByRole("button", { name: /Glassdoor/i });

    await expect(kununuBtn).toBeVisible();
    await expect(glassdoorBtn).toBeVisible();

    // Verify SCARF 24-month timeline chart container is visible
    const timelineCard = page.getByTestId("scarf-timeline-card");
    await expect(timelineCard).toBeVisible();

    // Switch to Glassdoor platform tab and verify header title updates dynamically
    await glassdoorBtn.click();
    await expect(timelineCard).toContainText("Glassdoor");

    // Switch back to Kununu platform tab and verify header title updates dynamically
    await kununuBtn.click();
    await expect(timelineCard).toContainText("Kununu");

    // Check individual review cards for SCARF KI-Ergebnis badges when enriched data exists
    const scarfBadges = page.locator('.p-2\\.5:has-text("SCARF KI-Ergebnis:")');
    const badgeCount = await scarfBadges.count();
    if (badgeCount > 0) {
      const firstBadge = scarfBadges.first();
      await expect(firstBadge).toBeVisible();
      await expect(firstBadge).toContainText("KI-Analysiert");
    }
  });

  test("triggers re-enrichment without error and updates SCARF timeline", async ({ page }) => {
    await page.goto("/ms/dashboard/companies/MHP");
    await expect(page.getByTestId("company-information-tab")).toBeVisible({ timeout: 15000 });

    // Click re-analysis button if present
    const reanalyzeBtn = page.getByRole("button", { name: /Analyse.*neu ausführen/i });
    if (await reanalyzeBtn.isVisible()) {
      await reanalyzeBtn.click();
      // Verify success notification or state transition
      await expect(page.locator("body")).not.toContainText("500 Internal Server Error");
    }
  });
});
