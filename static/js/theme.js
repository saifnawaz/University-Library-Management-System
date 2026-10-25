// Runs in <head> before the page draws, so there is no flash of the wrong theme.
// Uses the saved choice if there is one, otherwise the system setting.
(function () {
  var saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) { /* storage blocked */ }
  var dark = saved ? saved === "dark"
                   : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();
