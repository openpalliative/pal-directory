import { todayIso, ruDate, parseIsoDate, toIsoDate } from "../../ui/js/format.js";

const until = document.querySelectorAll("[data-print-until]");
if (until.length) {
  const d = parseIsoDate(todayIso());
  d.setUTCDate(d.getUTCDate() + 90);
  for (const el of until) el.textContent = ruDate(toIsoDate(d));
}
