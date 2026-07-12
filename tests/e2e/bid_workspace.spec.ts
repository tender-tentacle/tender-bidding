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
    // Wait for the async readiness score to render — it shifts the layout while
    // loading, which makes a click on the checklist unstable.
    await expect(page.getByTestId("score-panel")).toBeVisible();

    // The check control is a styled icon button (aria-pressed), not a native checkbox.
    const firstBox = page.getByTestId("item-checkbox").first();
    await firstBox.scrollIntoViewIfNeeded();
    await firstBox.click();
    await expect(firstBox).toHaveAttribute("aria-pressed", "true"); // survives the reload after PATCH
  });

  test("shows the transparent readiness score and a recommendation", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("bid-list-item").filter({ hasText: "Rahmenvertrag" }).first().click();
    await expect(page.getByTestId("workspace")).toBeVisible();

    // Recommendation banner with explicit decision + confidence.
    await expect(page.getByTestId("recommendation")).toContainText(/Recommendation: (BID|REVIEW|NO BID)/);
    await expect(page.getByTestId("recommendation")).toContainText("confidence");

    // Transparent score: total + all five weighted criteria with detail lines.
    const panel = page.getByTestId("score-panel");
    await expect(panel).toContainText("Readiness Score");
    for (const label of [
      "Formal readiness",
      "Suitability coverage",
      "Award preparation",
      "Document evidence",
      "Deadline buffer",
    ]) {
      await expect(panel).toContainText(label);
    }
    await expect(panel.locator(".score-row")).toHaveCount(5);
  });

  test("surfaces reusable cross-bid evidence and accepts it with provenance", async ({ page }) => {
    await page.goto("/");
    // The seeded TED bid has no own documents; the won 2023 bid's corpus serves it.
    await page.getByTestId("bid-list-item").filter({ hasText: "Framework for Software" }).first().click();
    await expect(page.getByTestId("workspace")).toBeVisible();

    const evidence = page.getByTestId("reusable-evidence");
    await expect(evidence).toBeVisible();
    await expect(evidence).toContainText("reusable corpus");

    // Accept the first proposal → the checklist item shows matched evidence.
    await page.getByTestId("evidence-accept").first().click();
    await expect(page.locator('[data-testid="checklist-item"]').filter({ hasText: "matched" }).first()).toBeVisible();
  });

  test("exploring workspace shows the provisional banner and promotes to draft", async ({ page }) => {
    // Repeatable: relay a fresh provisional bid (as enriching does on "interesting"),
    // instead of consuming the seeded one.
    const ref = `E2E-EXPLORING-${Date.now()}`;
    const relay = await page.request.post("/api/v1/internal/bids/relay", {
      data: {
        source_ref: ref,
        title: `E2E Exploring ${ref}`,
        customer: "E2E Kreisverwaltung",
        deadline_at: "2099-11-20T12:00:00Z",
        document_text: "Betrieb eines Fachverfahrens. Referenzen erforderlich.",
        provisional: true,
      },
    });
    expect(relay.ok()).toBeTruthy();

    await page.goto("/");
    await page.getByTestId("bid-list-item").filter({ hasText: ref }).first().click();
    await expect(page.getByTestId("workspace")).toBeVisible();

    // Provisional banner: analysis ran, but nobody committed yet.
    await expect(page.getByTestId("exploring-banner")).toContainText("Provisional workspace");
    await expect(page.getByTestId("workspace")).toContainText("exploring");

    // Promote → the workspace becomes a real draft bid; the banner disappears.
    await page.getByText("Start bid preparation").click();
    await expect(page.getByTestId("exploring-banner")).toHaveCount(0);
    await expect(page.getByTestId("workspace")).toContainText("draft");
  });
});
