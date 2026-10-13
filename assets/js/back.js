import { watchParams } from "../../ui/js/xparams.js";

const regionLink = (id) => document.querySelector(`[data-pd-regions] > li[data-region="${id}"] a`);

class PdBack extends HTMLElement {
  connectedCallback() {
    let titles = {};
    try {
      titles = JSON.parse(this.dataset.situations || "{}");
    } catch {}
    const onList = document.querySelector("[data-pd-regions]") !== null;
    watchParams(["region", "back"], (params) => {
      const link = params.region && onList ? regionLink(params.region) : null;
      if (link) {
        location.replace(link.href + (params.back ? `#back=${encodeURIComponent(params.back)}` : ""));
        return;
      }
      if (params.back) {
        this.querySelector("a").href = this.dataset.hub + params.back + "/";
        this.querySelector("[data-back-label]").textContent = `Вернуться: ${titles[params.back]}`;
        this.hidden = false;
      }
    }, { back: (v) => Object.hasOwn(titles, v) });
  }
}

if (!customElements.get("pd-back")) customElements.define("pd-back", PdBack);
