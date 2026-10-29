// Chat panels: "Ask the librarian" for members and the staff assistant for librarians.
// Python decides everything (who may ask, topic, rate limit, what data the LLM sees);
// this only sends the question and draws the answer.

import { api, ApiError } from "./api.js";
import { h, busy, toastError } from "./ui.js";

const KEEP = 4; // exchanges kept on screen

export const MEMBER_ASSISTANT = {
  title: "Ask the librarian",
  endpoint: "/api/chat",
  answerer: "Librarian",
  placeholder: "Is Clean Code available?",
  suggestions: ["What's due soon?", "Do I owe any fines?", "What should I read next?"],
  note: "Answers come only from the library catalog and your own account. Library questions only.",
};

export const STAFF_ASSISTANT = {
  title: "Staff assistant",
  endpoint: "/api/staff/chat",
  answerer: "Assistant",
  placeholder: "Which members have overdue theses?",
  suggestions: ["Who is more than 7 days overdue?", "How many theses are on loan?",
    "Which books have a waitlist?"],
  note: "Answers come only from the library's own records: loans, fines, waitlists, members " +
    "and the catalog. It can't change anything; use Issue & return or Members for that.",
};

/** One question and its answer (or "Thinking…" while waiting). */
function exchange(question, answerer) {
  const answer = h("p", { class: "chat-answer pending" }, "Thinking…");
  const el = h("div", { class: "chat-exchange" },
    h("p", { class: "chat-question" }, h("span", { class: "chat-who" }, "You"), question),
    h("div", {}, h("span", { class: "chat-who" }, answerer), answer));
  return {
    el,
    show(text, kind = "answer") {
      answer.className = `chat-answer ${kind}`;
      answer.textContent = text; // text only: the reply is never treated as HTML
    },
  };
}

/** A chat panel (MEMBER_ASSISTANT or STAFF_ASSISTANT). Build it once and keep it between refreshes. */
export function assistantPanel({ title, endpoint, answerer, placeholder, suggestions: starters, note }) {
  const input = h("input", { class: "input", id: "ask-input", type: "text", maxlength: "500",
    autocomplete: "off", placeholder });
  const send = h("button", { class: "btn btn-light", type: "submit" }, "Ask");
  const log = h("div", { class: "chat-log", "aria-live": "polite" });
  const suggestions = h("div", { class: "chat-suggestions" },
    starters.map((text) => h("button", { class: "btn btn-quiet btn-small", type: "button",
      onclick: () => ask(text) }, text)));
  const newChat = h("button", { class: "btn btn-quiet btn-small", type: "button", hidden: true,
    onclick: startOver }, "New chat");
  let asked = false; // a question sent before the saved conversation arrived wins

  function addExchange(question) {
    const item = exchange(question, answerer);
    log.append(item.el);
    while (log.children.length > KEEP) log.firstElementChild.remove();
    suggestions.hidden = true;
    newChat.hidden = false;
    return item;
  }

  // The session remembers the last few questions (Python keeps them); show them again after a reload.
  api.get("/api/chat/history").then((turns) => {
    if (asked) return;
    for (const turn of turns) addExchange(turn.question).show(turn.answer);
    scrollToEnd(log);
  }).catch(() => {}); // nothing to show; asking still works

  async function startOver() {
    const restore = busy(newChat, "Clearing…");
    try {
      await api.del("/api/chat/history");
      log.replaceChildren();
      suggestions.hidden = false;
      newChat.hidden = true;
    } catch (error) {
      toastError(error, "Couldn't start a new chat");
    } finally {
      restore();
      input.focus();
    }
  }

  async function ask(text) {
    const question = text.trim();
    if (!question) { input.focus(); return; } // convenience only; Python checks too
    asked = true;
    const item = addExchange(question);
    scrollToEnd(log);
    input.value = "";
    const restore = busy(send, "Asking…");
    try {
      const reply = await api.post(endpoint, { question });
      item.show(reply.answer, reply.kind);
    } catch (error) {
      const message = error instanceof ApiError
        ? [error.message, error.nextStep].filter(Boolean).join(" ")
        : "Something went wrong. Please try again.";
      item.show(message, "error");
    } finally {
      scrollToEnd(log);
      restore();
      input.focus();
    }
  }

  const form = h("form", { class: "row", onsubmit: (e) => { e.preventDefault(); ask(input.value); } },
    h("label", { class: "visually-hidden", for: "ask-input" }, "Your question"), input, send);
  return h("section", { class: "dark-panel assistant", id: "ask", "aria-labelledby": "ask-title" },
    h("div", { class: "chat-head" }, h("h2", { id: "ask-title" }, title), newChat),
    log, suggestions, form,
    h("p", { class: "muted small chat-note" }, note));
}

/** Show the newest exchange (only matters when the log scrolls, in the docked sidebar). */
function scrollToEnd(log) {
  log.scrollTop = log.scrollHeight;
}

/**
 * The page layout with an assistant: the content, then the panel. CSS docks the panel to
 * the right edge on wide screens and keeps it at the bottom on narrow ones.
 */
export function withAssistant(panel, ...content) {
  // Moving the kept panel into the new layout resets its scroll; go back to the newest answer.
  requestAnimationFrame(() => scrollToEnd(panel.querySelector(".chat-log")));
  return h("div", { class: "with-assistant" }, h("div", { class: "page-flow" }, ...content), panel);
}
