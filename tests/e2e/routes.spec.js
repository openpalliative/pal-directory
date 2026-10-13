import { test, expect, checkA11y } from "../../opsite/tests/fixtures.js";

async function routes(page) {
  return (await (await page.request.get("data/v1/routes.json")).json()).items;
}

test("все перечни открываются: черновик, ссылка на публикацию, таблицы дословно", async ({ page }) => {
  test.setTimeout(240000);
  const items = await routes(page);
  expect(items.length).toBeGreaterThan(0);
  for (const r of items) {
    await page.goto(`routes/${r.id}/`);
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator(".op-badges").first()).toContainText("Черновик");
    if (!r.verified) await expect(page.locator(".op-badges").first()).toContainText("Не проверено");
    await expect(page.locator(`a[href="${r.act.url}"]`).first()).toBeVisible();
    const pages = [page.url(), ...await page.locator(".pd-parts a").evaluateAll((els) => els.map((a) => a.href))];
    let units = 0;
    let map = "";
    const anchors = [];
    for (const href of pages) {
      if (href !== page.url()) await page.goto(href);
      await expect(page.locator("h1")).toHaveCount(1);
      units += await page.locator(".pd-unit").count();
      map += (await page.locator(".pd-map__from").allTextContents()).join(" ");
      anchors.push(...await page.locator(".pd-map__to a").evaluateAll((els) => els.map((a) => a.href)));
      expect(await page.locator("main").innerText()).not.toMatch(/балл|положительных ответ|прогноз/i);
      await checkA11y(page);
    }
    expect(units).toBe(r.units.length);
    for (const d of [...(r.districts || []).map((x) => x.name), ...(r.referrals || []).map((x) => x.org)]) expect(map).toContain(d);
    for (const href of [...new Set(anchors)].slice(0, 40)) {
      await page.goto(href);
      await expect(page.locator(`[id="${decodeURIComponent(new URL(href).hash.slice(1))}"]`)).toHaveCount(1);
    }
  }
});

test("список перечней ведёт на каждый перечень", async ({ page }) => {
  const items = await routes(page);
  await page.goto("routes/");
  for (const r of items) await expect(page.locator(`.pd-route-list a[href="../routes/${r.id}/"]`)).toHaveCount(1);
});

test("индекс регионов: 83 ссылки на карточки", async ({ page }) => {
  await page.goto("regions/");
  await expect(page.locator("[data-pd-regions] a")).toHaveCount(83);
  await expect(page.locator("h1")).toHaveText("Все регионы");
});

test("таблицы CSV в UTF-8 с BOM и ссылки на них с /data/", async ({ page }) => {
  await page.goto("data/");
  for (const name of ["region-lines", "addressees"]) {
    const link = page.locator(`a[href="../data/v1/${name}.csv"]`);
    await expect(link).toHaveCount(1);
    const body = await (await page.request.get(`data/v1/${name}.csv`)).body();
    expect([...body.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
    expect(body.subarray(3, 6).toString()).toBe("id,");
  }
});
