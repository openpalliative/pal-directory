import { test, expect } from "../../opsite/tests/fixtures.js";

test("карточка запоминает регион, главная показывает, забыть убирает", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.goto("regions/ru-kgd/");
  await expect(page.locator(".pd-remember__on")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("op:region"))).toBe("RU-KGD");
  await page.goto("");
  const home = page.locator(".pd-remember--home");
  await expect(home).toContainText("Ваш регион: Калининградская область");
  await expect(home.locator("a")).toHaveAttribute("href", /regions\/ru-kgd\/$/);
  await home.getByRole("button", { name: "забыть" }).click();
  await expect(home).toBeHidden();
  expect(await page.evaluate(() => localStorage.getItem("op:region"))).toBeNull();
});

test("на карточке можно забыть и запомнить снова", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.goto("regions/ru-irk/");
  await page.getByRole("button", { name: "забыть" }).click();
  await expect(page.locator(".pd-remember__off")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("op:region"))).toBeNull();
  await page.getByRole("button", { name: "запомнить снова" }).click();
  expect(await page.evaluate(() => localStorage.getItem("op:region"))).toBe("RU-IRK");
});
