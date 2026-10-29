// My loans: what's out, fines (with payment), and history.
// Current fine, total fine and "what blocks borrowing" all come from Python.

import { api } from "./api.js";
import {
  h, boot, startPage, cover, dueText, busy, toastError, blockedNotice, paymentToast,
  accruingText, formatDate, formatMoney, plural, loadingState, emptyState, errorState,
} from "./ui.js";

const main = document.getElementById("main");

function loanRow(loan) {
  const soon = loan.overdue || loan.days_left <= 3;
  return h("div", { class: "row-card" },
    cover(loan.item_type_key, loan.item_title, { size: "small" }),
    h("div", { class: "grow" },
      h("div", { class: "title" },
        h("a", { href: `/catalog/${encodeURIComponent(loan.item_id)}` }, loan.item_title)),
      h("div", { class: "sub" }, `${loan.item_author} · due ${formatDate(loan.due_date)}`)),
    h("div", { class: "side" },
      h("span", { class: `status ${soon ? "tone-warn" : "tone-muted"}` }, dueText(loan)),
      loan.overdue ? h("span", { class: "muted" }, accruingText(loan)) : null));
}

/** One fines section: the two figures, a pay form when something is payable, the rules in one line. */
function finesSection(me) {
  const figures = h("div", { class: "figures" },
    h("div", { class: "figure" },
      h("div", { class: `stat-value ${me.current_fine > 0 ? "tone-warn" : ""}` }, formatMoney(me.current_fine)),
      h("div", { class: "stat-label" }, h("strong", {}, "Current fine"), h("br"), "Charged, payable now")),
    h("div", { class: "figure" },
      h("div", { class: "stat-value" }, formatMoney(me.total_fine)),
      h("div", { class: "stat-label" }, h("strong", {}, "Total fine"), h("br"),
        me.accruing_fine > 0
          ? `Includes ${formatMoney(me.accruing_fine)} added when overdue items come back`
          : "Nothing more is building up")));

  let payment = null;
  if (me.current_fine > 0) {
    const amount = h("input", { class: "input", id: "pay-amount", type: "number", min: "1",
      step: "any", value: String(me.current_fine), inputmode: "decimal" });
    const pay = h("button", { class: "btn btn-primary", type: "submit" }, "Pay current fine");
    payment = h("form", { class: "inline-form", novalidate: true },
      h("div", { class: "field" }, h("label", { for: "pay-amount" }, "Amount (Rs)"), amount), pay);
    payment.addEventListener("submit", async (event) => {
      event.preventDefault();
      const restore = busy(pay, "Paying…");
      try {
        const updated = await api.post("/api/fines/pay", { amount: amount.value });
        paymentToast(updated);  // says what still blocks borrowing, if anything
        load();                 // redraws the notice, figures and buttons
      } catch (error) {
        restore();
        toastError(error, "Couldn't take the payment");
      }
    });
  }

  const rules = [
    `Up to ${plural(me.borrow_limit, "item")} for ${me.loan_days} days`,
    `late returns ${me.fine_policy}`,
    me.has_research_access ? "you can borrow theses" : null,
  ].filter(Boolean).join(" · ");

  return h("section", { class: "section" },
    h("h2", {}, "Fines"), figures, payment, h("p", { class: "rule-line" }, rules));
}

function historyTable(history) {
  if (!history.length) return emptyState("No past loans yet", "Items you return will be listed here.");
  return h("div", { class: "table-wrap" },
    h("table", { class: "table" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Item"), h("th", {}, "Borrowed"), h("th", {}, "Returned"),
        h("th", {}, "Late by"), h("th", { class: "num" }, "Fine charged"))),
      h("tbody", {}, history.map((loan) => h("tr", {},
        h("td", {}, loan.item_title, h("div", { class: "sub" }, loan.item_author)),
        h("td", { class: "nowrap" }, formatDate(loan.issue_date)),
        h("td", { class: "nowrap" }, formatDate(loan.return_date)),
        h("td", { class: loan.days_overdue ? "late nowrap" : "nowrap" },
          loan.days_overdue ? plural(loan.days_overdue, "day") : "On time"),
        h("td", { class: "num" }, loan.fine ? formatMoney(loan.fine) : "—"))))));
}

async function load() {
  try {
    const [me, loans] = await Promise.all([api.get("/api/me"), api.get("/api/me/loans")]);
    main.replaceChildren(
      h("div", { class: "page-head" },
        h("div", {}, h("p", { class: "eyebrow" }, "My loans"), h("h1", {}, "Loans and fines"))),
      blockedNotice(me),
      h("div", { class: "columns" },
        h("section", { class: "section" },
          h("div", { class: "section-head" },
            h("h2", {}, "On your desk"),
            h("span", { class: "muted small" }, `${loans.current.length} of ${me.borrow_limit}`)),
          loans.current.length
            ? h("div", { class: "stack" }, loans.current.map(loanRow))
            : emptyState("Nothing on loan", "Find something to read in the catalog.",
                h("a", { class: "btn btn-outline", href: "/catalog" }, "Browse the catalog"))),
        finesSection(me)),
      h("section", { class: "section" }, h("h2", {}, "History"), historyTable(loans.history)));
  } catch (error) {
    main.replaceChildren(errorState(error, load));
  }
}

boot(main, async () => {
  await startPage("member");
  main.replaceChildren(loadingState("rows", 4));
  load();
});
