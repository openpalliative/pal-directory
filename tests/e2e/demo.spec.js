import { test, expect } from "../../opsite/tests/fixtures.js";

test("демо: плашка и ни одного настоящего звонка на выдуманный номер", async ({ page }) => {
  const lines = (await (await page.request.get("data/v1/region-lines.json")).json()).items;
  test.skip(!lines.some((l) => l.origin === "synthetic"), "сборка с настоящими данными");
  for (const path of ["", "regions/ru-kgd/", "regions/ru-irk/"]) {
    await page.goto(path);
    await expect(page.locator(".pd-demo")).toContainText("Пример на выдуманных данных");
    await expect(page.locator('a[href^="tel:+700"]')).toHaveCount(0);
  }
});
