import { test, expect } from "../../opsite/tests/fixtures.js";

test("карточка: у каждого номера tel: и статус, круглосуточно только по данным", async ({ page }) => {
  const res = await page.request.get("data/v1/region-lines.json");
  const all = (await res.json()).items;
  test.skip(all.length === 0, "сборка без номеров регионов");
  const lines = all.filter((l) => l.region_id === "RU-IRK");
  await page.goto("regions/ru-irk/");
  const shown = page.locator(".pd-lines li[data-number]");
  const n = await shown.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const li = shown.nth(i);
    const id = await li.getAttribute("data-line");
    const line = lines.find((l) => l.id === id);
    expect(line, id).toBeTruthy();
    if (line.origin !== "synthetic") await expect(li.locator("a.pd-line__num")).toHaveAttribute("href", `tel:${line.tel}`);
    await expect(li.locator(".op-status--unverified")).toHaveText("Не проверено");
    const flag = li.locator(".pd-line__flag");
    await expect(flag).toHaveCount(line.is_24x7 ? 1 : 0);
  }
});

test("карточка: служебные номера не показаны", async ({ page }) => {
  const res = await page.request.get("data/v1/region-lines.json");
  const hidden = (await res.json()).items.filter((l) => l.region_id === "RU-KGD" &&
    (l.hidden || l.topics.every((t) => t === "other" || t === "staff")));
  await page.goto("regions/ru-kgd/");
  for (const l of hidden) await expect(page.locator(`li[data-line="${l.id}"]`)).toHaveCount(0);
});

test("карточка: ссылки в другие инструменты", async ({ page }) => {
  await page.goto("regions/ru-kgd/");
  await expect(page.getByRole("link", { name: "Написать жалобу или заявление" }))
    .toHaveAttribute("href", "/obrashchenie-kit/case/#new=1&region=RU-KGD");
  await expect(page.getByRole("link", { name: "Вписать номера в карту на ночь" }))
    .toHaveAttribute("href", "/home-care-kit/night/#region=RU-KGD");
  await expect(page.getByRole("link", { name: "Если не ответили: что дальше" }))
    .toHaveAttribute("href", "/pal-norms/escalation/");
  await expect(page.locator(".pd-who--route a")).toHaveAttribute("href", "../../routes/ru-kgd/");
});

test("карточка без номеров не пустая", async ({ page }) => {
  await page.goto("regions/ru-chu/");
  await expect(page.locator(".pd-section").first()).toBeVisible();
  expect(await page.locator("main .pd-line, main .op-status").count()).toBeGreaterThan(0);
  await expect(page.locator(".op-now")).toBeVisible();
});

test("пустой блок по обезболиванию без слов «ниже» и с ссылкой на федеральные номера", async ({ page }) => {
  const lines = (await (await page.request.get("data/v1/region-lines.json")).json()).items;
  test.skip(lines.length === 0, "сборка без номеров регионов");
  const withPain = new Set(lines.filter((l) => !l.hidden && l.topics.some((t) => t === "pain" || t === "pmp")).map((l) => l.region_id));
  const regions = (await (await page.request.get("data/v1/regions.json")).json()).items;
  const target = regions.find((r) => !withPain.has(r.id) && lines.some((l) => l.region_id === r.id));
  test.skip(!target, "у всех регионов есть линия по обезболиванию");
  await page.goto(`regions/${target.slug}/`);
  const box = page.locator('section[aria-labelledby="pd-s-pain"] .op-status--info');
  await expect(box).toContainText("нет отдельной линии");
  await expect(box.locator("a")).toHaveAttribute("href", "../../federal/");
  expect(await box.evaluate((el) => getComputedStyle(el).borderLeftStyle)).toBe("solid");
});

test("Москва: пробел по Росздравнадзору объяснён, без синтетики", async ({ page }) => {
  await page.goto("regions/ru-mow/");
  await expect(page.locator("main")).toContainText("нет территориального органа по этому региону");
  await expect(page.locator('a[href^="tel:+700"]')).toHaveCount(0);
});

test("номера: непроверенные обычного размера, текст в одном виде", async ({ page }) => {
  await page.goto("regions/ru-irk/");
  const nums = page.locator(".pd-line:not(.pd-line--verified) a.pd-line__num");
  test.skip((await nums.count()) === 0, "сборка без номеров регионов");
  const body = await page.evaluate(() => parseFloat(getComputedStyle(document.body).fontSize));
  for (const size of await nums.evaluateAll((els) => els.map((a) => parseFloat(getComputedStyle(a).fontSize)))) {
    expect(size).toBeLessThanOrEqual(body + 0.5);
  }
  for (const t of await nums.allTextContents()) expect(t.trim()).toMatch(/^(\d{3}|8 \d{3,5} (\d{1,3}-)?\d{2}-\d{2})$/);
});

test("маршрутизатор Москвы: внешняя ссылка и отказ от связи", async ({ page }) => {
  await page.goto("regions/ru-mow/");
  const who = page.locator(".pd-who").first();
  await expect(who).toContainText("Проект с этой организацией не связан");
  await expect(who).toContainText("откроется сайт cpmdzm.ru");
  await expect(who.locator(".op-status--unverified")).toBeVisible();
});

test("ссылки подчёркнуты", async ({ page }) => {
  await page.goto("regions/ru-irk/");
  const bad = await page.locator("main a:not(.op-btn):not(.op-now__tel)").evaluateAll((els) => els
    .filter((a) => a.offsetParent && !getComputedStyle(a).textDecorationLine.includes("underline"))
    .map((a) => a.textContent.trim()));
  expect(bad).toEqual([]);
});
