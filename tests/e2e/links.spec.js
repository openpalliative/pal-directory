import { test, expect } from "../../opsite/tests/fixtures.js";

test("режим links: названия ведомств, ссылка на таблицу, ни одного номера региона", async ({ page }) => {
  const lines = await (await page.request.get("data/v1/region-lines.json")).json();
  test.skip(lines.items.length > 0, "сборка с номерами регионов");
  const addressees = (await (await page.request.get("data/v1/addressees.json")).json()).items
    .filter((a) => a.region_id === "RU-KGD");
  await page.goto("regions/ru-kgd/");
  for (const a of addressees) {
    await expect(page.locator(".pd-agency__title", { hasText: a.name })).toHaveCount(1);
    expect(a.line_ids).toEqual([]);
    if (a.postal_address) await expect(page.locator("main")).toContainText(a.postal_address);
  }
  await expect(page.locator(".pd-links-note a")).toHaveAttribute("href", /roszdravnadzor\.gov\.ru/);
  await expect(page.locator(".pd-links-note")).toContainText(/файл от \d{2}\.\d{2}\.\d{4}/);
  const tels = await page.locator('a[href^="tel:"]').evaluateAll((els) => els.map((a) => a.getAttribute("href")));
  const federal = (await (await page.request.get("data/v1/federal-lines.json")).json()).items.map((f) => `tel:${f.tel}`);
  const allowed = new Set(["tel:112", "tel:103", "tel:+78007008436", ...federal]);
  expect(tels.filter((t) => !allowed.has(t))).toEqual([]);
  await expect(page.locator('a[href^="tel:+700"]')).toHaveCount(0);
  expect(lines.counts.items).toBe(0);
  const one = await (await page.request.get("region-lines/ru-kgd.json")).json();
  expect(one.lines).toEqual([]);
});

test("режим links: на карточках с маршрутизаторами тоже нет номеров региона", async ({ page }) => {
  const lines = await (await page.request.get("data/v1/region-lines.json")).json();
  test.skip(lines.items.length > 0, "сборка с номерами регионов");
  const federal = (await (await page.request.get("data/v1/federal-lines.json")).json()).items.map((f) => `tel:${f.tel}`);
  const allowed = new Set(["tel:112", "tel:103", "tel:+78007008436", ...federal]);
  for (const path of ["regions/ru-mow/", "regions/ru-mos/", "regions/ru-spe/", "regions/ru-len/", "regions/ru-ce/"]) {
    await page.goto(path);
    const tels = await page.locator('a[href^="tel:"]').evaluateAll((els) => els.map((a) => a.getAttribute("href")));
    expect(tels.filter((t) => !allowed.has(t)), path).toEqual([]);
  }
});
