// Librarian form for adding an item. It only collects fields and shows the ones that
// matter for the chosen type; ItemFactory in Python validates everything and builds the item.

import { api, ApiError } from "./api.js";
import { h, busy, toast } from "./ui.js";

const TYPES = [
  ["book", "Book"], ["reference", "Reference book"], ["ebook", "E-book"],
  ["magazine", "Magazine"], ["thesis", "Thesis"],
];

// The one extra field each type has (same names ItemFactory reads).
const EXTRA_FIELD = {
  book: ["isbn", "ISBN", "e.g. 9780132350884"],
  reference: ["isbn", "ISBN", "e.g. 9780199688975"],
  ebook: ["file_format", "File format", "PDF or EPUB"],
  magazine: ["issue_number", "Issue", "e.g. Vol. 69 No. 9"],
  thesis: ["supervisor", "Supervisor", "e.g. Dr. Sana Javed"],
};

function field(id, label, input, { wide = false, hint = null } = {}) {
  input.id = id;
  return h("div", { class: `field ${wide ? "wide" : ""}` },
    h("label", { for: id }, label), input, hint ? h("span", { class: "hint" }, hint) : null);
}

export function itemForm({ onAdded, onCancel }) {
  const typeSelect = h("select", { class: "input", name: "type" },
    TYPES.map(([key, label]) => h("option", { value: key }, label)));
  const input = (name, props = {}) => h("input", { class: "input", name, ...props });

  const copiesField = field("f-copies", "Copies", input("total_copies", { type: "number", min: "1", value: "1" }));
  const extraInput = input("extra");
  const extraField = field("f-extra", "", extraInput);
  const error = h("div", { class: "form-error", role: "alert", hidden: true });

  function showTypeFields() {
    const [name, label, placeholder] = EXTRA_FIELD[typeSelect.value];
    extraInput.name = name;
    extraInput.placeholder = placeholder;
    extraField.querySelector("label").textContent = label;
    copiesField.hidden = typeSelect.value === "ebook"; // e-books have unlimited copies
  }
  typeSelect.addEventListener("change", showTypeFields);

  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Add to catalog");
  const form = h("form", { class: "panel", novalidate: true, "aria-labelledby": "add-title" },
    h("h2", { id: "add-title" }, "Add an item"),
    error,
    h("div", { class: "form-grid" },
      field("f-type", "Type", typeSelect),
      field("f-id", "Item ID", input("item_id", { placeholder: "e.g. B007", autocomplete: "off" })),
      field("f-title", "Title", input("title"), { wide: true }),
      field("f-author", "Author", input("author"), { hint: "Publisher or editor for magazines" }),
      field("f-year", "Year", input("year", { type: "number", min: "1000" })),
      field("f-subject", "Subject", input("subject", { placeholder: "e.g. Databases" })),
      copiesField,
      extraField,
      field("f-desc", "Description", h("textarea", { class: "input", name: "description", rows: "3" }),
        { wide: true, hint: "A sentence or two. Used for search and recommendations." })),
    h("div", { class: "row" },
      submit,
      h("button", { class: "btn btn-quiet", type: "button", onclick: onCancel }, "Cancel")));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const data = Object.fromEntries(
      [...new FormData(form).entries()].map(([k, v]) => [k, String(v).trim()]));
    if (typeSelect.value === "ebook") delete data.total_copies;

    const restore = busy(submit, "Adding…");
    try {
      const item = await api.post("/api/items", data);
      toast(`Added "${item.title}"`, `${item.item_type} · ${item.status_text}`);
      onAdded(item);
    } catch (e) {
      error.textContent = e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
      error.hidden = false;
      restore();
    }
  });

  showTypeFields();
  setTimeout(() => form.querySelector("#f-id").focus(), 0);
  return form;
}
