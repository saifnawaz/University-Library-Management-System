// Pieces shared by the librarian pages.

import { h, formatDate, formatMoney, plural, emptyState } from "./ui.js";

/** Overdue loans as a table. The fine column is what each loan adds when it comes back
 *  (not yet charged), so it is labelled that way and never mixed up with current fines. */
export function overdueTable(loans, { limit = null } = {}) {
  if (!loans.length) return emptyState("Nothing overdue", "Every loan is within its due date.");
  const rows = limit ? loans.slice(0, limit) : loans;
  return h("div", { class: "table-wrap" },
    h("table", { class: "table" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Member"), h("th", {}, "Item"), h("th", {}, "Late by"),
        h("th", { class: "num" }, "Adds on return"))),
      h("tbody", {}, rows.map((loan) => h("tr", {},
        h("td", {},
          h("a", { href: `/staff/desk?member=${encodeURIComponent(loan.member_id)}` }, loan.member_name),
          h("div", { class: "sub" }, loan.member_role)),
        h("td", {}, loan.item_title, h("div", { class: "sub" }, `Due ${formatDate(loan.due_date)}`)),
        h("td", { class: "late nowrap" }, plural(loan.days_overdue, "day")),
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
