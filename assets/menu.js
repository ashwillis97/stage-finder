(function () {
  var M = {"main": [["/", "Search all shows"], ["/new/", "New this week"], ["/email-alerts/", "Email alerts"]], "types": [["/pantomime/", "Pantomime 2026"], ["/christmas-shows/", "Christmas shows 2026"], ["/west-end-shows/", "West End shows"], ["/categories/comedy/", "Comedy"], ["/categories/musicals/", "Musicals"], ["/categories/tribute-acts/", "Tribute acts"], ["/categories/classical/", "Classical and orchestral"], ["/categories/family/", "Family and kids shows"], ["/categories/concerts/", "Concerts and live music"]], "cities": [["/cities/birmingham/", "Birmingham"], ["/cities/london/", "London"], ["/cities/glasgow/", "Glasgow"], ["/cities/nottingham/", "Nottingham"], ["/cities/manchester/", "Manchester"], ["/cities/bristol/", "Bristol"], ["/cities/shrewsbury/", "Shrewsbury"], ["/cities/liverpool/", "Liverpool"], ["/cities/edinburgh/", "Edinburgh"], ["/cities/leicester/", "Leicester"], ["/cities/belfast/", "Belfast"], ["/cities/wolverhampton/", "Wolverhampton"], ["/cities/york/", "York"], ["/cities/sheffield/", "Sheffield"], ["/cities/scunthorpe/", "Scunthorpe"], ["/cities/bournemouth/", "Bournemouth"], ["/cities/bath/", "Bath"], ["/cities/norwich/", "Norwich"], ["/cities/brighton/", "Brighton"], ["/cities/leeds/", "Leeds"], ["/cities/oxford/", "Oxford"], ["/cities/stoke-on-trent/", "Stoke-on-Trent"], ["/cities/cardiff/", "Cardiff"], ["/cities/hull/", "Hull"], ["/cities/cambridge/", "Cambridge"], ["/cities/coventry/", "Coventry"], ["/cities/blackburn/", "Blackburn"], ["/cities/northampton/", "Northampton"], ["/cities/dunfermline/", "Dunfermline"], ["/cities/bury/", "Bury"]], "more": [["/venues/", "All venues"], ["/#sgTitle", "Add a venue or show"]]};
  if (!M) return;
  var top = document.querySelector(".top");
  if (!top) return;
  var brand = top.querySelector(".brand");
  var color = brand ? getComputedStyle(brand).color : "#1f1a16";
  var css = document.createElement("style");
  css.textContent =
    ".mbtn{display:none;position:absolute;right:12px;top:50%;transform:translateY(-50%);width:44px;height:44px;border:0;background:none;color:inherit;cursor:pointer;padding:0;align-items:center;justify-content:center}" +
    ".mbtn svg{width:26px;height:26px}" +
    ".mbtn:focus:not(:focus-visible){outline:none}" +
    ".mpanel{position:fixed;inset:0;z-index:1000;background:#faf6ef;color:#1f1a16;overflow-y:auto;font-family:'Outfit',Arial,sans-serif;padding:0 20px 40px;display:none}" +
    ".mpanel.open{display:block}" +
    ".mhead{display:flex;align-items:center;justify-content:space-between;padding:max(14px,env(safe-area-inset-top,0px)) 0 8px}" +
    ".mhead b{font-weight:800;font-size:24px;letter-spacing:-.02em}" +
    ".mhead b span{color:#c4411d}" +
    ".mclose{width:44px;height:44px;border:0;background:none;cursor:pointer;color:#1f1a16;display:flex;align-items:center;justify-content:center;margin-right:-10px}" +
    ".mpanel h2{margin:26px 0 8px;padding-top:14px;border-top:1.5px solid #1f1a16;font-size:14px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#6a5f54}" +
    ".mpanel ul{list-style:none;margin:0;padding:0}" +
    ".mpanel li a{display:block;padding:11px 0;font-size:20px;font-weight:600;color:#1f1a16;text-decoration:none;border-bottom:1px solid rgba(31,26,22,.12)}" +
    ".mpanel .mcities{display:flex;flex-wrap:wrap;gap:4px 22px}" +
    ".mpanel .mcities a{display:inline-block;padding:9px 0;font-size:17px;font-weight:500;color:#1f1a16;text-decoration:none}" +
    ".mpanel a:hover,.mpanel a:focus-visible{color:#a8391a}" +
    ".mpanel .mall{display:inline-block;margin-top:8px;font-size:16px;font-weight:600;color:#a8391a;text-decoration:underline;text-underline-offset:3px}" +
    "@media(max-width:760px){.mbtn{display:flex}.top{position:relative}.top:not(.hashero){padding-right:52px}.top a.home{display:none}}" +
    "@media(min-width:761px){.mpanel{display:none!important}}";
  document.head.appendChild(css);
  var btn = document.createElement("button");
  btn.type = "button"; btn.className = "mbtn"; btn.setAttribute("aria-label", "Open menu"); btn.setAttribute("aria-expanded", "false"); btn.setAttribute("aria-controls", "mpanel");
  btn.style.color = color;
  btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
  top.appendChild(btn);
  if (top.querySelector(".hero")) { top.classList.add("hashero"); btn.style.top = "max(6px, env(safe-area-inset-top, 0px))"; btn.style.transform = "none"; }
  function list(items) { return "<ul>" + items.map(function (i) { return '<li><a href="' + i[0] + '">' + i[1] + "</a></li>"; }).join("") + "</ul>"; }
  var p = document.createElement("div");
  p.id = "mpanel"; p.className = "mpanel"; p.setAttribute("role", "dialog"); p.setAttribute("aria-modal", "true"); p.setAttribute("aria-label", "Menu");
  p.innerHTML =
    '<div class="mhead"><b>Find a <span>Show</span></b><button type="button" class="mclose" aria-label="Close menu"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg></button></div>' +
    list(M.main) +
    "<h2>Types of show</h2>" + list(M.types) +
    "<h2>Locations</h2>" + '<div class="mcities">' + M.cities.map(function (c) { return '<a href="' + c[0] + '">' + c[1] + "</a>"; }).join("") + '</div><a class="mall" href="/cities/">All locations</a>' +
    "<h2>More</h2>" + list(M.more);
  document.body.appendChild(p);
  var close = p.querySelector(".mclose");
  function open() { p.classList.add("open"); btn.setAttribute("aria-expanded", "true"); document.documentElement.style.overflow = "hidden"; close.focus(); }
  function shut() { p.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); document.documentElement.style.overflow = ""; btn.focus(); }
  btn.addEventListener("click", open);
  close.addEventListener("click", shut);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && p.classList.contains("open")) shut(); });
  p.addEventListener("click", function (e) { var a = e.target.closest && e.target.closest("a"); if (a && a.getAttribute("href").charAt(0) === "#") shut(); });
})();
