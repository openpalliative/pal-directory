import { test, expect } from "../../opsite/tests/fixtures.js";

const cases = [
  ["", "#region=%3Cscript%3Ealert(1)%3C%2Fscript%3E"],
  ["", "#region=<img src=x onerror=alert(1)>"],
  ["", "#back=../../x"],
  ["", "#back=%2F%2Fevil.example"],
  ["regions/ru-kgd/", "#back=../../x"],
  ["federal/", "#region=RU-KGD&back=<script>"],
];

for (const [path, hash] of cases) {
  test(`чужой адрес не исполняется и не уводит: ${path || "/"}${hash}`, async ({ page }, info) => {
    test.skip(info.project.name === "nojs");
    let dialogs = 0;
    page.on("dialog", (d) => { dialogs += 1; d.dismiss(); });
    await page.goto(path + hash);
    await page.waitForLoadState("load");
    await page.waitForTimeout(200);
    expect(new URL(page.url()).pathname).toBe(`/pal-directory/${path}`);
    expect(dialogs).toBe(0);
    await expect(page.locator(".pd-back")).toBeHidden();
    await expect(page.locator("img[src=x], main script:not([type])")).toHaveCount(0);
  });
}

test("испорченный регион в localStorage не ломает страницы", async ({ page }, info) => {
  test.skip(info.project.name === "nojs");
  await page.addInitScript(() => localStorage.setItem("op:region", '"]x'));
  for (const path of ["", "regions/ru-irk/", "federal/"]) {
    await page.goto(path);
    await page.waitForLoadState("load");
    expect(new URL(page.url()).pathname).toBe(`/pal-directory/${path}`);
  }
  await page.goto("");
  await expect(page.locator(".pd-remember--home")).toBeHidden();
});
