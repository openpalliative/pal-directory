import { matchRegion } from "../../ui/js/region-match.js";

const LIMIT = 8;

class PdRegionSearch extends HTMLElement {
  connectedCallback() {
    const input = this.querySelector("input");
    const count = this.querySelector(".pd-search__count");
    const empty = this.querySelector(".pd-search__empty");
    const results = this.querySelector(".pd-search__results");
    const regions = [...document.querySelectorAll("[data-pd-regions] > li[data-region]")].map((li) => {
      const link = li.querySelector("a");
      return {
        id: li.dataset.region,
        name: link.textContent.trim(),
        capital: li.dataset.capital || "",
        aliases: (li.dataset.aliases || "").split(";").filter(Boolean),
        href: link.href,
      };
    });
    let found = [];
    const apply = () => {
      const q = input.value.trim();
      found = q ? matchRegion(q, regions) : [];
      results.replaceChildren(...found.slice(0, LIMIT).map((r) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = r.href;
        a.textContent = r.name;
        li.append(a);
        return li;
      }));
      results.hidden = found.length === 0;
      empty.hidden = !q || found.length > 0;
      if (!q) count.textContent = "";
      else if (!found.length) count.textContent = "Ничего не найдено";
      else if (found.length > LIMIT) count.textContent = `Найдено регионов: ${found.length}. Уточните название или выберите в списке ниже`;
      else count.textContent = `Найдено регионов: ${found.length}`;
    };
    input.addEventListener("input", apply);
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (found.length === 1) location.assign(found[0].href);
    });
    this.hidden = false;
    if (input.value) apply();
  }
}

if (!customElements.get("pd-region-search")) customElements.define("pd-region-search", PdRegionSearch);
