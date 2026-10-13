import { test, expect } from "../../opsite/tests/fixtures.js";

test.use({ viewport: { width: 360, height: 640 } });

test("поиск: якутия открывает карточку", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.goto("");
  const input = page.getByLabel("Ваш регион");
  await expect(input).toBeInViewport();
  await input.fill("якутия");
  await expect(page.locator("#pd-q-count")).toHaveText("Найдено регионов: 1");
  await page.locator("#pd-q-results a").first().click();
  await expect(page).toHaveURL(/regions\/ru-sa\/$/);
  await expect(page.locator("h1")).toHaveText("Республика Саха (Якутия)");
});

test("поиск: калин и Enter", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.goto("");
  await page.getByLabel("Ваш регион").fill("калин");
  await expect(page.locator("#pd-q-results a")).toHaveText(["Калининградская область"]);
  await page.getByLabel("Ваш регион").press("Enter");
  await expect(page).toHaveURL(/regions\/ru-kgd\/$/);
});

test("поиск: пусто показывает текст и ссылку на федеральные номера", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.goto("");
  await page.getByLabel("Ваш регион").fill("атлантида");
  await expect(page.locator(".pd-search__empty")).toBeVisible();
  await expect(page.locator(".pd-search__empty a")).toHaveAttribute("href", "federal/");
  await expect(page.locator("#pd-q-results")).toBeHidden();
});

test("#region= на главной ведёт в карточку", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.goto("#region=RU-IRK&back=who-to-call");
  await expect(page).toHaveURL(/regions\/ru-irk\/$/);
  await expect(page.locator(".pd-back")).toContainText("Вернуться: Не знаю, куда звонить");
  await expect(page.locator(".pd-back a")).toHaveAttribute("href", "/s/who-to-call/");
});

test("чужой регион в #region= отбрасывается", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.goto("#region=RU-XXX");
  await expect(page.locator("h1")).toHaveText("Куда звонить");
  expect(new URL(page.url()).hash).toBe("");
});
