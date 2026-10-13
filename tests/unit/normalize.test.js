import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalize, matchRegion as matchObjects } from "../../opsite/ui/js/region-match.js";

const matchRegion = (q, list) => matchObjects(q, list).map((r) => r.id);

function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows;
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
}

const regions = parseCsv(readFileSync(new URL("../../data/regions.csv", import.meta.url), "utf8"))
  .filter((r) => r.id && !r.excluded)
  .map((r) => ({ id: r.id, name: r.name, capital: r.capital, aliases: r.aliases.split(";").filter(Boolean) }));

const first = (q) => matchRegion(q, regions)[0];

test("в списке 83 региона", () => {
  assert.equal(regions.length, 83);
});

test("normalize убирает ё, регистр и знаки", () => {
  assert.equal(normalize("  Орёл-на-Оке "), "орел на оке");
  assert.equal(normalize("Санкт-Петербург"), "санкт петербург");
});

test("находит по названию, столице и сокращению", () => {
  const cases = [
    ["Орёл", "RU-ORL"], ["орел", "RU-ORL"], ["спб", "RU-SPE"], ["питер", "RU-SPE"], ["СПб", "RU-SPE"],
    ["мск", "RU-MOW"], ["подмосковье", "RU-MOS"], ["якутия", "RU-SA"], ["югра", "RU-KHM"], ["хмао", "RU-KHM"],
    ["кузбасс", "RU-KEM"], ["иркутск", "RU-IRK"], ["калин", "RU-KGD"], ["Казань", "RU-TA"],
    ["нижний новгород", "RU-NIZ"], ["москва", "RU-MOW"],
  ];
  for (const [q, id] of cases) assert.equal(first(q), id, q);
});

test("Москва не находит Московскую область первой и наоборот", () => {
  assert.deepEqual(matchRegion("москва", regions), ["RU-MOW"]);
  assert.equal(first("московская"), "RU-MOS");
});

test("в списке нет территорий из стоп-листа платформы", () => {
  const text = readFileSync(new URL("../../opsite/lint/territories.yaml", import.meta.url), "utf8");
  const patterns = [...text.matchAll(/^\s+- (.+)$/gm)].map((m) => new RegExp(m[1].trim()));
  assert.ok(patterns.length > 5);
  for (const r of regions) {
    const hay = [r.id, r.name, r.capital, ...r.aliases].join(" ");
    for (const rx of patterns) assert.ok(!rx.test(hay), `${r.id}: ${rx}`);
  }
});

test("пустой запрос ничего не находит", () => {
  assert.deepEqual(matchRegion("   ", regions), []);
  assert.deepEqual(matchRegion("абвгд", regions), []);
});

test("совпадение внутри слова не показывается, если есть совпадение по началу слова", () => {
  assert.deepEqual(matchRegion("мск", regions), ["RU-MOW"]);
  assert.ok(matchRegion("ромск", regions).includes("RU-KOS"));
});
