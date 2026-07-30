import { expect, test } from "@playwright/test";

test("capture prompt to applied calendar story", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Portfolio GIF is captured at desktop size");
  await page.route("**/api/v1/auth/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        user: {
          id: "7f995be5-d1ae-4473-915a-c67b6a28d204",
          email: "student@example.com",
          full_name: "Jamie Chen",
          timezone: "UTC",
          has_google_calendar: true,
        },
      }),
    });
  });
  const plan = {
    id: "1bf04082-87db-4b6a-a8f5-08d9f6f3400e",
    summary: "Add one statistics review during your high-energy window.",
    changes: [{ type: "create", client_ref: "stats", title: "Statistics review", start_at: "2026-05-13T11:30:00Z", end_at: "2026-05-13T13:00:00Z", timezone: "UTC" }],
    conflicts: [],
    warnings: [],
    status: "pending",
    expires_at: "2026-08-01T00:00:00Z",
  };
  await page.route("**/api/v1/assistant/messages", (route) => route.fulfill({
    contentType: "text/event-stream",
    body: `event: status\ndata: {"stage":"plan"}\n\nevent: delta\ndata: {"text":"I found a high-energy window on Tuesday."}\n\nevent: plan\ndata: ${JSON.stringify(plan)}\n\nevent: done\ndata: {"status":"awaiting_approval"}\n\n`,
  }));
  await page.route("**/api/v1/plans/1bf04082-87db-4b6a-a8f5-08d9f6f3400e/apply", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ plan: { ...plan, status: "applied" }, applied_event_ids: ["google-1"], rolled_back: false }),
  }));
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /may 12–16/i })).toBeVisible();
  const composer = page.getByRole("textbox", { name: /message ai planner/i });
  await composer.fill("Fit in a 90-minute statistics review before Friday.");
  await page.screenshot({ path: "../../output/playwright/story/frame-1.png" });
  await page.getByRole("button", { name: /send message/i }).click();
  await expect(page.getByText(/proposed calendar change/i)).toBeVisible();
  await page.screenshot({ path: "../../output/playwright/story/frame-2.png" });
  await page.getByRole("button", { name: /^apply change$/i }).click();
  await expect(page.getByRole("button", { name: "Applied" })).toBeVisible();
  await page.screenshot({ path: "../../output/playwright/story/frame-3.png" });
});
