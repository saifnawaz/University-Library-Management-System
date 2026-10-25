// Pieces shared by the librarian pages.

import { h, formatMoney, plural, emptyState } from "./ui.js";

/** Overdue loans as a table: Member · role, item, days late, fine so far. */
export function overdueTable(loans, { limit = null } = {}) {
  if (!loans.length) return emptyState("Nothing overdue", "Every loan is within its due date.");
  const rows = limit ? loans.slice(0, limit) : loans;
  return h("div", { class: "table-wrap" },
    h("table", { class: "table" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Member"), h("th", {}, "Item"), h("th", {}, "Days late"), h("th", { class: "num" }, "Fine"))),
      h("tbody", {}, rows.map((loan) => h("tr", {},
        h("td", {},
          h("a", { href: `/staff/desk?member=${encodeURIComponent(loan.member_id)}` }, loan.member_name),
          ` · ${loan.member_role}`),
        h("td", {}, loan.item_title),
        h("td", { class: "late" }, String(loan.days_overdue)),
        h("td", { class: "num" }, formatMoney(loan.fine)))))));
}

/** "Most borrowed" as a row of book blocks; block height shows how often. */
export function shelfChart(ranking) {
  if (!ranking.length) return emptyState("No loans in this period", "Popular items will show here.");
  const most = Math.max(...ranking.map((r) => r.times));
  return h("div", { class: "shelf-chart", role: "list", "aria-label": "Most borrowed items" },
    ranking.map((r) => h("div", { class: "bar-item", role: "listitem" },
      h("div", { class: "bar-slot" },
        h("div", { class: "bar", dataset: { type: r.type },
                   style: { "--bar-height": `${Math.round(48 + 92 * (r.times / most))}px` } })),
      h("div", { class: "bar-label" }, r.title),
      h("div", { class: "bar-count" }, plural(r.times, "loan")))));
}
