import { test, expect, pdfPages } from "../../opsite/tests/fixtures.js";

test.skip(({ browserName }) => browserName !== "chromium", "PDF собирает только Chromium");

async function printText(page) {
  await page.emulateMedia({ media: "print" });
  return page.evaluate(() => document.body.innerText.replace(/\s+/g, " "));
}

test("печать: каждая карточка не больше 2 листов A4", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  test.setTimeout(240000);
  const regions = (await (await page.request.get("data/v1/regions.json")).json()).items;
  expect(regions.length).toBe(83);
  const over = [];
  for (const r of regions) {
    await page.goto(`regions/${r.slug}/`);
    const n = await pdfPages(page);
    if (n > 2) over.push(`${r.id}: ${n}`);
  }
  expect(over).toEqual([]);
});

test("печать: Калининград, Иркутск и федеральные номера на 1 листе", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  for (const path of ["regions/ru-kgd/", "regions/ru-irk/", "federal/"]) {
    await page.goto(path);
    expect(await pdfPages(page), path).toBe(1);
  }
});

test("печать: на листе дата таблицы, отметка о проверке и срок сверки", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.goto("regions/ru-irk/");
  await page.emulateMedia({ media: "print" });
  const footer = page.locator(".pd-sheet-footer");
  await expect(footer).toBeVisible();
  await expect(footer).toContainText(/Таблица Росздравнадзора от \d{2}\.\d{2}\.\d{4}, звонком не проверено/);
  await expect(footer).toContainText(/Сверьте до \d{2}\.\d{2}\.\d{4}/);
  await expect(page.locator(".pd-report")).toBeHidden();
  const status = page.locator(".pd-line .op-status--unverified").first();
  if (await page.locator(".pd-line").count()) await expect(status).toBeVisible();
});

test("печать Калининграда: горячая линия, адрес перечня, без «ниже»", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  await page.goto("regions/ru-kgd/");
  const text = await printText(page);
  expect(text).toContain("8-800-700-84-36, сторонняя линия, не проверено");
  expect(text).toContain("Адрес перечня: https://openpalliative.github.io/pal-directory/routes/ru-kgd/");
  expect(text).not.toMatch(/ниже|на этой странице/i);
});
