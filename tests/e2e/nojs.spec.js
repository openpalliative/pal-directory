import { test, expect } from "../../opsite/tests/fixtures.js";

test("без JS: 83 региона ссылками и буквы от 44px @nojs", async ({ page }) => {
  await page.goto("");
  await expect(page.locator("[data-pd-regions] a")).toHaveCount(83);
  const sizes = await page.locator(".pd-letters a").evaluateAll((els) => els.map((a) => {
    const r = a.getBoundingClientRect();
    return [Math.round(r.width), Math.round(r.height)];
  }));
  expect(sizes.length).toBeGreaterThan(10);
  for (const [w, h] of sizes) {
    expect(w).toBeGreaterThanOrEqual(44);
    expect(h).toBeGreaterThanOrEqual(44);
  }
  await expect(page.getByRole("link", { name: "Моего региона нет в списке" })).toHaveAttribute("href", "federal/");
});

test("без JS: карточка читается целиком @nojs", async ({ page }) => {
  await page.goto("regions/ru-irk/");
  await expect(page.locator("a.pd-line__num").first()).toBeVisible();
  await expect(page.locator(".pd-report__link")).toBeVisible();
});
