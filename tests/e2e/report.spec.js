import { test, expect } from "../../opsite/tests/fixtures.js";
import { issueUrl, issueText } from "../../lib/issue-url.js";

test("ссылка на ошибку собрана сборкой и меняется при выборе номера", async ({ page, context, browserName }, info) => {
  const meta = await (await page.request.get("data/v1/region-lines.json")).json();
  await page.goto("regions/ru-kgd/");
  const link = page.locator(".pd-report__link");
  const base = { region: "RU-KGD", regionName: "Калининградская область", dataVersion: meta.version };
  await expect(link).toHaveAttribute("href", issueUrl(base));
  if (info.project.name === "nojs") return;
  const select = page.getByLabel("Какой номер");
  const options = select.locator("option");
  if (meta.items.every((l) => l.origin === "synthetic")) {
    await expect(page.locator(".pd-report__pick")).toBeHidden();
    return;
  }
  expect(await options.count()).toBeGreaterThan(1);
  const value = await options.nth(1).getAttribute("value");
  const number = (await options.nth(1).textContent()).trim();
  await select.selectOption(value);
  const args = { ...base, line: value, number };
  await expect(link).toHaveAttribute("href", issueUrl(args));
  await expect(page.locator(".pd-report__copy")).toHaveAttribute("text", issueText(args));
  if (browserName !== "chromium") return;
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "Скопировать текст ошибки" }).click();
  await expect(page.locator(".pd-report__live")).toHaveText("Скопировано");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(issueText(args));
});
