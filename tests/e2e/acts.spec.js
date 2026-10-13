import { test, expect, checkA11y } from "../../opsite/tests/fixtures.js";

async function acts(page) {
  const res = await page.request.get("data/v1/region-acts.json");
  return res.ok() ? (await res.json()).items : null;
}

test("официальные документы: Калининград 678 от 09.09.2026", async ({ page }) => {
  const items = await acts(page);
  test.skip(!items, "набора region-acts нет в сборке");
  await page.goto("regions/ru-kgd/");
  const box = page.locator(".pd-acts");
  await expect(box.locator("h2")).toHaveText("Официальные документы региона");
  const item = box.locator('.pd-act-item[data-eo="3901202609100002"]');
  await expect(item).toHaveCount(1);
  await expect(item).toContainText("от 09.09.2026 № 678");
  await expect(item.locator("a")).toHaveAttribute("href", "http://publication.pravo.gov.ru/document/3901202609100002");
  const kinds = await box.locator(".pd-act-item__kind").allTextContents();
  expect(kinds[0]).toMatch(/Маршрутизация|Как устроена/);
  const count = (id) => items.filter((a) => a.region_id === id).length;
  for (const r of items.filter((a) => a.kind === "reimbursement" && count(a.region_id) <= 25).slice(0, 1)) {
    const base = `regions/${r.region_id.toLowerCase()}/`;
    await page.goto(count(r.region_id) > 5 ? `${base}documents/` : base);
    await expect(page.locator(`.pd-act-item[data-eo="${r.id}"] .pd-act-item__draft`)).toContainText("межрегиональное соглашение");
  }
});

test("официальные документы: у Москвы честная фраза об отсутствии", async ({ page }) => {
  const items = await acts(page);
  test.skip(!items, "набора region-acts нет в сборке");
  test.skip(items.some((a) => a.region_id === "RU-MOW"), "у Москвы акты нашлись");
  await page.goto("regions/ru-mow/");
  await expect(page.locator(".pd-acts")).toContainText("На портале официальной публикации актов региона о паллиативной помощи не найдено");
  await checkA11y(page);
});

test("официальные документы читаются без JS @nojs", async ({ page }) => {
  const items = await acts(page);
  test.skip(!items, "набора region-acts нет в сборке");
  await page.goto("regions/ru-kgd/");
  await page.locator(".pd-acts summary").click();
  await expect(page.locator(".pd-act-item").first()).toBeVisible();
});

test("/data/ показывает снимок портала и число документов", async ({ page }) => {
  const items = await acts(page);
  test.skip(!items, "набора region-acts нет в сборке");
  await page.goto("data/");
  const sec = page.locator('section[aria-labelledby="pd-d-acts"]');
  await expect(sec).toContainText(String(items.length));
  await expect(sec).toContainText(/Снимок портала от \d{2}\.\d{2}\.\d{4}/);
});

test("все документы региона: ссылка с карточки и все акты по страницам", async ({ page }) => {
  test.setTimeout(120000);
  const items = await acts(page);
  test.skip(!items, "набора region-acts нет в сборке");
  const by = {};
  for (const a of items) (by[a.region_id] ||= []).push(a);
  const [region, list] = Object.entries(by).sort((a, b) => b[1].length - a[1].length)[0];
  test.skip(list.length <= 5, "у всех регионов мало документов");
  await page.goto(`regions/${region.toLowerCase()}/`);
  await expect(page.locator(".pd-acts__box .pd-act-item")).toHaveCount(5);
  await page.locator(".pd-acts summary").click();
  await page.locator(".pd-acts__more a").click();
  const seen = new Set();
  for (;;) {
    await expect(page.locator("h1")).toHaveCount(1);
    for (const eo of await page.locator(".pd-act-item").evaluateAll((els) => els.map((e) => e.dataset.eo))) seen.add(eo);
    await checkA11y(page);
    const next = page.getByRole("link", { name: "Следующие документы" });
    if (!(await next.count())) break;
    await next.click();
  }
  expect([...seen].sort()).toEqual(list.map((a) => a.id).sort());
});
