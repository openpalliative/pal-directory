import { getRegion, setRegion } from "../../ui/js/region-store.js";

class PdRemember extends HTMLElement {
  connectedCallback() {
    if (this.dataset.mode === "card") this.card();
    else this.home();
  }

  card() {
    const id = this.dataset.region;
    const on = this.querySelector(".pd-remember__on");
    const off = this.querySelector(".pd-remember__off");
    const render = () => {
      const saved = getRegion() === id;
      on.hidden = !saved;
      off.hidden = saved;
    };
    setRegion(id);
    this.querySelector("[data-forget]").addEventListener("click", () => {
      setRegion(null);
      render();
      this.querySelector("[data-remember]").focus();
    });
    this.querySelector("[data-remember]").addEventListener("click", () => {
      setRegion(id);
      render();
      this.querySelector("[data-forget]").focus();
    });
    render();
    this.hidden = false;
  }

  home() {
    const link = this.querySelector("[data-region-link]");
    const render = () => {
      const id = getRegion();
      const source = id && document.querySelector(`[data-pd-regions] > li[data-region="${id}"] a`);
      if (!source) {
        this.hidden = true;
        return;
      }
      link.href = source.href;
      link.textContent = source.textContent.trim();
      this.hidden = false;
    };
    this.querySelector("[data-forget]").addEventListener("click", () => {
      setRegion(null);
      render();
      document.getElementById("pd-q")?.focus();
    });
    document.addEventListener("op-region-change", render);
    render();
  }
}

if (!customElements.get("pd-remember")) customElements.define("pd-remember", PdRemember);
