(function () {
  "use strict";
  const sb = document.getElementById("sidebar"), btn = document.getElementById("menuBtn");
  if (sb && btn) btn.addEventListener("click", () => sb.classList.toggle("open"));

  document.querySelectorAll("form[data-confirm]").forEach(f =>
    f.addEventListener("submit", e => { if (!window.confirm(f.dataset.confirm)) e.preventDefault(); }));

  document.querySelectorAll("[data-counter]").forEach(el => {
    const out = document.querySelector(el.dataset.counter);
    const upd = () => { if (out) out.textContent = el.value.length + " / " + el.maxLength; };
    el.addEventListener("input", upd); upd();
  });

  // Image preview + client-side pre-check (the server re-validates everything)
  const img = document.getElementById("image");
  if (img) img.addEventListener("change", () => {
    const err = document.getElementById("imageClientError"), prev = document.getElementById("imagePreview");
    err.textContent = ""; prev.classList.add("d-none");
    const f = img.files[0]; if (!f) return;
    if (!/\.(png|jpe?g)$/i.test(f.name)) { err.textContent = "Only PNG or JPG images are allowed."; img.value = ""; return; }
    if (f.size > 2 * 1024 * 1024) { err.textContent = "Image must be smaller than 2 MB."; img.value = ""; return; }
    prev.src = URL.createObjectURL(f); prev.classList.remove("d-none");
  });

  // Live duplicate hint on the request form (server enforces the same rule on submit)
  const form = document.getElementById("requestForm");
  if (form) {
    const box = document.getElementById("liveDup");
    let timer;
    const esc = s => s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const check = () => {
      const b = form.building.value, l = form.location.value.trim(), c = form.category.value;
      if (!b || l.length < 3 || !c) { box.classList.add("d-none"); return; }
      fetch("/api/duplicates?" + new URLSearchParams({ building: b, location: l, category: c }),
            { headers: { "Accept": "application/json" } })
        .then(r => r.ok ? r.json() : []).then(list => {
          if (!list.length) { box.classList.add("d-none"); return; }
          box.innerHTML = "<strong><i class='bi bi-exclamation-triangle'></i> Similar open request" + (list.length > 1 ? "s" : "") +
            " already reported here:</strong><ul class='mb-0 mt-1'>" +
            list.map(x => "<li><a href='" + x.url + "'>" + esc(x.reference_id) + "</a> — " + esc(x.title) + " (" + esc(x.status) + ")</li>").join("") + "</ul>";
          box.classList.remove("d-none");
        }).catch(() => {});
    };
    ["building", "location", "category"].forEach(n => form[n].addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(check, 400); }));
  }
})();
