(function () {
  var root = document.documentElement;
  root.classList.add("js");

  // переключатели: вид (возраст/темы), возраст, фильтр тем по вердикту
  function pick(group, attr, value) {
    document.querySelectorAll(group).forEach(function (el) {
      el.hidden = el.getAttribute(attr) !== value;
    });
  }
  function select(buttons, active, aria) {
    buttons.forEach(function (b) { b.setAttribute(aria, b === active ? "true" : "false"); });
  }
  var views = document.querySelectorAll(".view");
  views.forEach(function (b) {
    b.addEventListener("click", function () {
      select(views, b, "aria-selected");
      pick(".view-panel", "data-view", b.dataset.view);
    });
  });
  var ages = document.querySelectorAll(".chip[data-age]");
  ages.forEach(function (b) {
    b.addEventListener("click", function () {
      select(ages, b, "aria-selected");
      pick(".cmp__panel", "data-age", b.dataset.age);
    });
  });
  var filters = document.querySelectorAll(".chip[data-v]");
  filters.forEach(function (b) {
    b.addEventListener("click", function () {
      select(filters, b, "aria-pressed");
      document.querySelectorAll(".topic").forEach(function (t) {
        t.hidden = b.dataset.v !== "all" && t.dataset.v !== b.dataset.v;
      });
    });
  });
  if (views[0]) views[0].click();
  if (ages[0]) ages[0].click();

  // якоря на свёрнутые разделы раскрывают их
  function openTarget(id) {
    var el = id && document.getElementById(id);
    if (!el) return false;
    if (el.tagName === "DETAILS") el.open = true;
    el.scrollIntoView();
    return true;
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (a && openTarget(decodeURIComponent(a.getAttribute("href").slice(1)))) e.preventDefault();
  });
  window.addEventListener("hashchange", function () { openTarget(decodeURIComponent(location.hash.slice(1))); });
  openTarget(decodeURIComponent(location.hash.slice(1)));

  var btn = document.getElementById("toggle-all");
  if (btn) btn.addEventListener("click", function () {
    var open = btn.textContent === "Раскрыть всё";
    document.querySelectorAll(".sec").forEach(function (d) { d.open = open; });
    btn.textContent = open ? "Свернуть всё" : "Раскрыть всё";
  });
})();
