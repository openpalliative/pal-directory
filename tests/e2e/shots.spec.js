import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { test } from "../../opsite/tests/fixtures.js";

const dir = join(process.cwd(), "_reports", "shots", "pal-directory");
const widths = [360, 390, 768, 1024, 1440];
const themes = ["light", "dark"];
const pages = [
  ["home", ""], ["kgd", "regions/ru-kgd/"], ["irk", "regions/ru-irk/"], ["mow", "regions/ru-mow/"],
  ["chu", "regions/ru-chu/"], ["federal", "federal/"], ["route", "routes/ru-kgd/"], ["data", "data/"],
  ["regions", "regions/"], ["routes", "routes/"], ["404", "404.html"],
];

test.describe.configure({ mode: "parallel" });

for (const [name, path] of pages) {
  test(`скриншоты ${name} @shots`, async ({ browser }) => {
    test.setTimeout(180000);
    mkdirSync(dir, { recursive: true });
    for (const theme of themes) {
      for (const size of ["m", "xl"]) {
        for (const width of size === "xl" ? [360] : widths) {
          const context = await browser.newContext({ viewport: { width, height: 800 }, colorScheme: theme, locale: "ru-RU" });
          if (size === "xl") await context.addInitScript(() => localStorage.setItem("op:prefs", JSON.stringify({ size: "xl" })));
          const page = await context.newPage();
          await page.goto(path);
          await page.evaluate(() => document.fonts.ready);
          await page.screenshot({ path: join(dir, `${name}-${width}-${theme}${size === "xl" ? "-a++" : ""}.png`), fullPage: true });
          await context.close();
        }
      }
    }
  });
}

for (const [name, path] of [["kgd", "regions/ru-kgd/"], ["irk", "regions/ru-irk/"], ["federal", "federal/"]]) {
  test(`печать ${name} @shots`, async ({ page }) => {
    mkdirSync(dir, { recursive: true });
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    await page.pdf({ path: join(dir, `${name}-print-a4.pdf`), format: "A4", preferCSSPageSize: true });
    await page.emulateMedia({ media: "print", colorScheme: "light" });
    await page.setViewportSize({ width: 794, height: 1123 });
    await page.screenshot({ path: join(dir, `${name}-print-a4.png`), fullPage: true });
  });
}
