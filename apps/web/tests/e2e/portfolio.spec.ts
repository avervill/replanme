import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("landing is focused, accessible, and free of overflow", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /make space for what matters/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /explore the demo/i })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((violation) => violation.impact === "critical")).toEqual([]);
  await page.screenshot({ path: `../../output/playwright/landing-${testInfo.project.name}.png`, fullPage: true });
  if (testInfo.project.name === "desktop-chromium") {
    await page.screenshot({ path: "../../docs/assets/landing.png", fullPage: true });
  }
});

test("demo navigation works while writes stay gated", async ({ page }) => {
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: /may 12–16/i })).toBeVisible();
  await page.getByRole("button", { name: "Next week" }).click();
  await expect(page.getByText("May 19–23, 2026")).toBeVisible();
  await page.getByRole("button", { name: /fit in study time/i }).click();
  await expect(page.getByRole("dialog")).toContainText("safely read-only");
});

test("public routes support keyboard navigation", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  for (let index = 0; index < 6; index += 1) await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
});

test("authenticated fake-provider flow reviews imports and voice before planning", async ({ page }) => {
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
  const importedPlan = {
    id: "12bd2c75-6b8f-4672-8f03-6832ee7a0d97",
    summary: "Import two reviewed events",
    changes: [
      { type: "create", client_ref: "workshop", title: "Product strategy workshop", start_at: "2026-05-14T11:00:00Z", end_at: "2026-05-14T12:00:00Z", timezone: "UTC" },
      { type: "create", client_ref: "career", title: "Career fair", start_at: "2026-05-15T15:00:00Z", end_at: "2026-05-15T17:00:00Z", timezone: "UTC" },
    ],
    conflicts: [],
    warnings: [],
    status: "pending",
    expires_at: "2026-08-01T00:00:00Z",
  };
  await page.route("**/api/v1/imports/image", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(importedPlan) }));
  await page.route("**/api/v1/plans/12bd2c75-6b8f-4672-8f03-6832ee7a0d97", (route) => route.fulfill({ contentType: "application/json", body: route.request().postData() ?? JSON.stringify(importedPlan) }));
  await page.route("**/api/v1/voice/transcribe", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ transcript: "Move gym after my lab on Wednesday.", detected_language: "en" }) }));
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /may 12–16/i })).toBeVisible();

  await page.locator("#schedule-image-input").setInputFiles({
    name: "schedule.png",
    mimeType: "image/png",
    buffer: Buffer.from("fake"),
  });
  await expect(page.getByRole("heading", { name: /review extracted events/i })).toBeVisible();
  await page.locator('input[value="Career fair"]').fill("Engineering career fair");
  await page.getByRole("button", { name: /create proposal/i }).click();
  await expect(page.getByText(/proposed calendar change/i)).toBeVisible();

  await page.locator("#voice-recording-input").setInputFiles({ name: "note.webm", mimeType: "audio/webm", buffer: Buffer.from("fake") });
  await expect(page.getByRole("textbox", { name: /message ai planner/i })).toHaveValue("Move gym after my lab on Wednesday.");
});
