// Login page: send the user id and password, then go to the right home page.
// In demo mode, also offer demo accounts (listed by Python) and a data reset.

import { api, ApiError } from "./api.js";
import { h, busy, homeFor, themeToggle, toast, toastError } from "./ui.js";

const form = document.getElementById("login-form");
const userIdInput = document.getElementById("user-id");
const passwordInput = document.getElementById("password");
const submit = document.getElementById("submit");
const errorBox = document.getElementById("form-error");

document.getElementById("theme-slot").append(themeToggle());

// There is no self-service reset; say how it works instead of a dead link.
document.getElementById("forgot").addEventListener("click", (event) => {
  event.preventDefault();
  toast("Forgot your password?", "Ask at the circulation desk and a librarian will reset it for you.");
});

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

// Already signed in? Skip the form. (/api/session answers 200 either way, so no console error.)
api.get("/api/session").then(({ user }) => {
  if (user) window.location.replace(homeFor(user));
  else userIdInput.focus();
}).catch(() => userIdInput.focus());

// ---------- demo mode ----------

/** One row per demo account; clicking it fills the form. */
function demoAccount(account, all) {
  const button = h("button", { class: "demo-account", type: "button", "data-role": account.role,
                               "aria-pressed": "false" },
    h("span", { class: "role" }, account.role),
    h("span", { class: "who" }, `${account.user_id} · ${account.name}`),
    h("span", { class: "what" }, account.summary));
  button.addEventListener("click", () => {
    userIdInput.value = account.user_id;
    passwordInput.value = account.password;
    errorBox.hidden = true;
    all().forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    submit.focus();
  });
  return button;
}

/** "Reset demo data": the first click asks, a second click within a few seconds resets. */
function resetButton() {
  const button = h("button", { class: "btn btn-quiet btn-small", type: "button" }, "Reset demo data");
  let armed = null;
  button.addEventListener("click", async () => {
    if (!armed) {
      button.textContent = "Click again to reset";
      armed = setTimeout(() => { armed = null; button.textContent = "Reset demo data"; }, 4000);
      return;
    }
    clearTimeout(armed);
    armed = null;
    button.textContent = "Reset demo data";
    const restore = busy(button, "Resetting…");
    try {
      await api.post("/api/demo/reset");
      toast("Demo data reset", "Every account, loan and fine is back to how it started.");
      await showDemoPanel();
    } catch (error) {
      toastError(error, "Couldn't reset the demo data");
    } finally {
      restore();
    }
  });
  return button;
}

/** Show the panel if the server is in demo mode; with demo mode off the endpoint doesn't exist. */
async function showDemoPanel() {
  let accounts;
  try {
    accounts = await api.get("/api/demo/accounts");
  } catch {
    return; // not in demo mode (404), or unreachable: the normal form still works
  }
  if (!accounts.length) return;
  const rows = [];
  rows.push(...accounts.map((a) => demoAccount(a, () => rows)));
  document.getElementById("demo-slot").replaceChildren(
    h("section", { class: "demo-panel", "aria-labelledby": "demo-title" },
      h("div", {},
        h("h3", { id: "demo-title" }, "Try a demo account"),
        h("p", { class: "small muted" }, "Pick a role to fill in the form, then sign in.")),
      h("div", { class: "demo-accounts" }, rows),
      h("div", { class: "demo-reset" },
        h("span", {}, "Anyone can change the demo data."),
        resetButton())));
}

showDemoPanel();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;

  // Convenience check only; the server checks the same thing.
  if (!userIdInput.value.trim() || !passwordInput.value) {
    showError("Enter your user ID and password.");
    return;
  }

  submit.disabled = true;
  submit.textContent = "Signing in…";
  try {
    const user = await api.post("/api/login", {
      user_id: userIdInput.value.trim(),
      password: passwordInput.value,
    });
    window.location.replace(homeFor(user));
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    passwordInput.value = "";
    passwordInput.focus();
    submit.disabled = false;
    submit.textContent = "Sign in";
  }
});
