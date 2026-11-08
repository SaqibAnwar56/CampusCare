(function () {
  "use strict";
  const el = id => document.getElementById(id);
  const status = { Submitted: "#94a3b8", "Under Review": "#f59e0b", Assigned: "#6366f1", "In Progress": "#2563eb",
                   Resolved: "#16a34a", Closed: "#334155", Rejected: "#dc2626" };
  const prio = { Low: "#94a3b8", Medium: "#3b82f6", High: "#f97316", Critical: "#dc2626" };
  const bar = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } };
  fetch("/admin/api/stats", { headers: { Accept: "application/json" } }).then(r => r.json()).then(d => {
    if (el("chartStatus")) new Chart(el("chartStatus"), { type: "doughnut",
      data: { labels: Object.keys(d.by_status), datasets: [{ data: Object.values(d.by_status), backgroundColor: Object.keys(d.by_status).map(k => status[k]), borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom" } } } });
    if (el("chartCategory")) new Chart(el("chartCategory"), { type: "bar",
      data: { labels: Object.keys(d.by_category), datasets: [{ label: "Requests", data: Object.values(d.by_category), backgroundColor: "#2563eb", borderRadius: 6 }] }, options: bar });
    if (el("chartPriority")) new Chart(el("chartPriority"), { type: "bar",
      data: { labels: Object.keys(d.by_priority), datasets: [{ label: "Open requests", data: Object.values(d.by_priority), backgroundColor: Object.keys(d.by_priority).map(k => prio[k]), borderRadius: 6 }] }, options: bar });
    if (el("chartTrend")) new Chart(el("chartTrend"), { type: "line",
      data: { labels: d.trend.map(t => t.label), datasets: [{ label: "New requests", data: d.trend.map(t => t.count), borderColor: "#2563eb", backgroundColor: "rgba(37,99,235,.12)", fill: true, tension: .35 }] }, options: bar });
  });
})();
