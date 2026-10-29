// Reservations: the member's place in each waitlist, cancelling, and notifications.

import { api } from "./api.js";
import {
  h, boot, startPage, cover, busy, toast, toastError, formatDate,
  loadingState, emptyState, errorState,
} from "./ui.js";

const main = document.getElementById("main");

function reservationRow(r) {
  const cancel = h("button", { class: "btn btn-quiet btn-small", type: "button" }, "Cancel");
  cancel.addEventListener("click", async () => {
    const restore = busy(cancel, "Cancelling…");
    try {
      await api.del(`/api/reservations/${encodeURIComponent(r.item_id)}`);
      toast(`Cancelled your reservation`, `You're no longer waiting for "${r.item_title}".`);
      load();
    } catch (error) {
      restore();
      toastError(error, "Couldn't cancel this");
    }
  });
  return h("div", { class: "row-card" },
    cover(r.item_type_key, r.item_title, { size: "small" }),
    h("div", { class: "grow" },
      h("div", { class: "title" },
        h("a", { href: `/catalog/${encodeURIComponent(r.item_id)}` }, r.item_title)),
      h("div", { class: "sub" }, `${r.item_author} · reserved ${formatDate(r.created_at)}`)),
    h("div", { class: "side" },
      r.ready
        ? h("span", { class: "status tone-good" }, `Ready to collect until ${formatDate(r.held_until)} · held at the desk`)
        : h("span", { class: "status tone-muted" }, `Number ${r.position} in line`),
      cancel));
}

async function load() {
  try {
    const [reservations, notifications] = await Promise.all([
      api.get("/api/me/reservations"),
      api.get("/api/me/notifications"),
    ]);
    const newestFirst = [...notifications].reverse();
    main.replaceChildren(
      h("div", { class: "page-head" },
        h("div", {}, h("p", { class: "eyebrow" }, "Reservations"), h("h1", {}, "Your waitlist")),
        h("a", { class: "btn btn-quiet", href: "/catalog" }, "Find something to reserve")),
      h("div", { class: "columns" },
        h("section", { class: "section" },
          h("h2", {}, "Waiting for"),
          reservations.length
            ? h("div", { class: "stack" }, reservations.map(reservationRow))
            : emptyState("You're not waiting for anything",
                "When every copy of an item is out, use Join waitlist in the catalog.")),
        h("section", { class: "section" },
          h("h2", {}, "Notifications"),
          newestFirst.length
            ? h("div", { class: "stack" }, newestFirst.map((m) =>
                h("div", { class: "row-card" }, h("div", { class: "grow" }, m))))
            : emptyState("No notifications", "We'll tell you here when a reserved item is held for you."))));
  } catch (error) {
    main.replaceChildren(errorState(error, load));
  }
}

boot(main, async () => {
  await startPage("member");
  main.replaceChildren(loadingState("rows", 3));
  load();
});
