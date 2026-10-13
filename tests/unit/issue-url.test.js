import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { issueUrl, issueText, ISSUE_BASE } from "../../lib/issue-url.js";

const args = { region: "RU-KGD", regionName: "Калининградская область", line: "ru-kgd-rzn-84012535202",
  number: "8 (4012) 53-52-02", dataVersion: "2026.10.11" };

test("ссылка на issue: только разрешённые ключи и кириллица закодирована", () => {
  const url = new URL(issueUrl(args));
  assert.equal(url.origin + url.pathname, ISSUE_BASE);
  assert.deepEqual([...url.searchParams.keys()], ["template", "title", "region", "line", "data_version"]);
  assert.equal(url.searchParams.get("title"), "Номер: Калининградская область, 8 (4012) 53-52-02");
  assert.equal(url.searchParams.get("template"), "wrong-number.yml");
  assert.ok(!/[а-яё ]/i.test(issueUrl(args)));
  assert.ok(issueUrl(args).length < 2000);
});

test("без номера: только регион", () => {
  const url = new URL(issueUrl({ region: "RU-KGD", regionName: "Калининградская область", dataVersion: "2026.10.11" }));
  assert.deepEqual([...url.searchParams.keys()], ["template", "title", "region", "data_version"]);
  assert.equal(url.searchParams.get("title"), "Номер: Калининградская область");
});

test("текст ошибки без лишних полей", () => {
  const text = issueText(args);
  assert.deepEqual(text.split("\n").map((s) => s.split(":")[0]), [
    "Ошибка в номере, раздел «Куда звонить» openpalliative", "Регион", "Номер", "Версия данных", "Что не так",
    "Где вы видели правильный номер",
  ]);
  assert.ok(!/@|ФИО/.test(text));
});

test("ссылка из сборки совпадает со ссылкой из браузера", () => {
  const py = execFileSync("uv", ["run", "--quiet", "python", "-c",
    "import site_hooks as h, sys; print(h.issue_url(*sys.argv[1:]))",
    args.region, args.regionName, args.line, args.number, args.dataVersion], { encoding: "utf8" }).trim();
  assert.equal(py, issueUrl(args));
});
