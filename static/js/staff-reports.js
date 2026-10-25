// Reports: collection and membership numbers, every overdue loan, and what's popular.

import { api } from "./api.js";
import { overdueTable, shelfChart } from "./staff-common.js";
import { h, boot, startPage, stat, formatMoney, loadingState, errorState } from "./ui.js";

const main = document.getElementById("main");

function countTable(title, counts) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return h("section", { class: "section" },
    h("h2", {}, title),
    h("div", { class: "table-wrap" },
      h("table", { class: "table", style: { minWidth: "0" } },
        h("tbody", {}, rows.map(([label, n]) =>
          h("tr", {}, h("td", {}, label), h("td", { class: "num" }, String(n))))))));
}

async function load() {
  try {
    const [stats, overdue] = await Promise.all([
      api.get("/api/reports/stats"),
      api.get("/api/reports/overdue"),
    ]);
    main.replaceChildren(
      h("div", { class: "page-head" },
        h("div", {}, h("p", { class: "eyebrow" }, "Reports"), h("h1", {}, "The collection at a glance"))),
      h("div", { class: "stats" },
        stat(String(stats.titles), "Titles in the catalog"),
        stat(h("span", {}, String(stats.copies_on_loan), h("small", {}, ` / ${stats.copies}`)), "Printed copies on loan"),
        stat(String(stats.overdue_loans), "Overdue loans", stats.overdue_loans ? "warn" : ""),
        stat(formatMoney(stats.unpaid_fines), "Fines pending")),
      h("div", { class: "columns" },
        countTable("Titles by type", stats.titles_by_type),
        countTable("Members by role", stats.members_by_role)),
      h("section", { class: "section" }, h("h2", {}, "All overdue loans"), overdueTable(overdue)),
      h("section", { class: "section" },
        h("h2", {}, "Most borrowed, all time"), shelfChart(stats.most_borrowed)));
  } catch (error) {
    main.replaceChildren(errorState(error, load));
  }
}

boot(main, async () => {
  await startPage("staff");
  main.replaceChildren(loadingState("rows", 3));
  load();
});
