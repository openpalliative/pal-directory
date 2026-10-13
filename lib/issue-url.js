export const ISSUE_BASE = "https://github.com/openpalliative/pal-directory/issues/new";

export function issueTitle({ regionName, number }) {
  return number ? `Номер: ${regionName}, ${number}` : `Номер: ${regionName}`;
}

export function issueUrl({ region, regionName, line = "", number = "", dataVersion = "" }) {
  const params = [
    ["template", "wrong-number.yml"],
    ["title", issueTitle({ regionName, number })],
    ["region", region],
    ["line", line],
    ["data_version", dataVersion],
  ];
  const query = params
    .filter(([, v]) => v)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join("&");
  return `${ISSUE_BASE}?${query}`;
}

export function issueText({ region, regionName, line = "", number = "", dataVersion = "" }) {
  const rows = [
    "Ошибка в номере, раздел «Куда звонить» openpalliative",
    `Регион: ${regionName} (${region})`,
  ];
  if (number) rows.push(`Номер: ${number}${line ? ` (${line})` : ""}`);
  if (dataVersion) rows.push(`Версия данных: ${dataVersion}`);
  rows.push("Что не так:", "Где вы видели правильный номер:");
  return rows.join("\n");
}
