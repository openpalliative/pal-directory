import { issueText, issueUrl } from "../../lib/issue-url.js";

class PdReport extends HTMLElement {
  connectedCallback() {
    const select = this.querySelector("select");
    const link = this.querySelector(".pd-report__link");
    const copy = this.querySelector("op-copy");
    const hint = this.querySelector(".pd-report__hint");
    const base = { region: this.dataset.region, regionName: this.dataset.name, dataVersion: this.dataset.version };
    const update = () => {
      const option = select?.selectedOptions[0];
      const args = { ...base, line: option?.value || "", number: option?.value ? option.text : "" };
      link.href = issueUrl(args);
      copy?.setAttribute("text", issueText(args));
      const live = copy?.querySelector("[aria-live]");
      if (live) live.textContent = "";
    };
    if (select) {
      for (const li of document.querySelectorAll("li[data-line][data-number]")) {
        if (!li.querySelector("a.pd-line__num")) continue;
        select.add(new Option(li.dataset.number, li.dataset.line));
      }
      select.closest(".pd-report__pick").hidden = select.options.length < 2;
      select.addEventListener("change", update);
    }
    if (hint) hint.hidden = false;
    update();
  }
}

if (!customElements.get("pd-report")) customElements.define("pd-report", PdReport);
