(function () {
  var ENDPOINT = "";
  if (!ENDPOINT) return;
  function send(e) {
    var a = e.target && e.target.closest && e.target.closest("a[data-v]");
    if (!a) return;
    try { navigator.sendBeacon(ENDPOINT, JSON.stringify({ v: a.getAttribute("data-v"), s: a.getAttribute("data-s"), k: a.getAttribute("data-k"), p: location.pathname })); } catch (x) {}
  }
  document.addEventListener("click", send, true);
  document.addEventListener("auxclick", send, true);
})();
