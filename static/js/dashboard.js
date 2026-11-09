/* dashboard.js - draws the mock test score chart (Chart.js is loaded from a CDN) */
(function () {
  "use strict";
  var dataElement = document.getElementById("chart-data");
  var canvas = document.getElementById("scoreChart");
  if (!dataElement || !canvas || !window.Chart) { return; }

  var data = JSON.parse(dataElement.textContent);
  new window.Chart(canvas, {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [{
        label: "Score (%)", data: data.scores, fill: true, tension: 0.3,
        borderColor: "#0b4f9c", backgroundColor: "rgba(11, 79, 156, 0.12)", pointRadius: 4
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { min: 0, max: 100, title: { display: true, text: "Score (%)" } } },
      plugins: { legend: { display: false } }
    }
  });
})();