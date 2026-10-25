// Borrow and reserve, shared by the dashboard, catalog and item pages.
// Each sends one request, shows a toast, and then calls onDone() so the page can redraw.
// Whether the action is allowed was already decided by Python (item.actions);
// if anything changed meanwhile, the server says no and we show its message.

import { api } from "./api.js";
import { busy, formatDate, toast, toastError } from "./ui.js";

export function borrowItem(item, button, onDone) {
  const restore = busy(button, "Borrowing…");
  api.post("/api/loans", { item_id: item.item_id })
    .then((loan) => toast(`Borrowed "${item.title}"`, `Due back ${formatDate(loan.due_date)}.`))
    .catch((error) => toastError(error, "Couldn't borrow this"))
    .finally(() => { restore(); onDone(); });
}

export function reserveItem(item, button, onDone) {
  const restore = busy(button, "Joining…");
  api.post("/api/reservations", { item_id: item.item_id })
    .then(() => api.get(`/api/items/${encodeURIComponent(item.item_id)}`))
    .then((fresh) => {
      const position = fresh.actions && fresh.actions.queue_position;
      toast(`You're on the waitlist for "${item.title}"`,
        position ? `Number ${position} in line. We'll let you know when a copy is held for you.`
                 : "We'll let you know when a copy is held for you.");
    })
    .catch((error) => toastError(error, "Couldn't join the waitlist"))
    .finally(() => { restore(); onDone(); });
}

/** Handlers in the shape bookButton() expects. */
export function bookHandlers(onDone) {
  return {
    borrow: (item, button) => borrowItem(item, button, onDone),
    reserve: (item, button) => reserveItem(item, button, onDone),
  };
}
