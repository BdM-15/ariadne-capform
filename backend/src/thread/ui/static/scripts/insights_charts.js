/**
 * Insights hone + intensity scatter tooltips (extends clew_charts.js).
 */
(function () {
  function intensityTooltip(params) {
    var d = params.data || {};
    var agency = d.agency || params.name || "—";
    var acts = d.value && d.value[0] != null ? d.value[0] : "—";
    var millions = d.value && d.value[1] != null ? d.value[1] : "—";
    var hot = d.hot ? "<br/><span style='color:#00ff9c'>Above the line</span>" : "";
    return agency + "<br/>" + acts + " actions<br/>$" + Number(millions).toFixed(2) + "M" + hot;
  }

  function patchIntensityCharts() {
    if (!window.echarts) return;
    document.querySelectorAll('.insights-echarts-hero[data-chart-key="intensity"]').forEach(function (host) {
      var chart = window.echarts.getInstanceByDom(host);
      if (!chart) return;
      var opt = chart.getOption();
      if (!opt || !opt.series || !opt.series[0]) return;
      chart.setOption({
        tooltip: { formatter: intensityTooltip },
      });
    });
  }

  function honeFromChart(host, params) {
    var raw = host.getAttribute("data-chart-option");
    if (!raw) return;
    var option;
    try {
      option = JSON.parse(raw);
    } catch (_) {
      return;
    }
    var meta = option._intel || option._clew || {};
    var field = meta.honeField;
    if (!field) return;
    var value = null;
    if (params.data) {
      if (field === "agency" && params.data.agency) value = params.data.agency;
      else if (params.data.label) value = params.data.label;
      else if (params.name) value = params.name;
    }
    if (!value) return;
    applyHone(field, value);
  }

  function applyHone(field, value) {
    var form = document.getElementById("insights-radar-form");
    if (!form) return;
    var input = form.querySelector('[name="' + field + '"]');
    if (!input) return;
    input.value = value;
    var lens = document.getElementById("insights-active-lens");
    if (lens) lens.value = "overview";
    if (window.htmx) window.htmx.trigger(form, "submit");
  }

  function bindHoneChips() {
    document.querySelectorAll(".insights-hone-chip").forEach(function (btn) {
      if (btn.dataset.honeBound) return;
      btn.dataset.honeBound = "1";
      btn.addEventListener("click", function () {
        applyHone(btn.getAttribute("data-hone-field"), btn.getAttribute("data-hone-value"));
      });
    });
  }

  function bindChartHone() {
    if (!window.echarts) return;
    document.querySelectorAll(".clew-echarts-host").forEach(function (host) {
      var chart = window.echarts.getInstanceByDom(host);
      if (!chart || host.dataset.honeBound) return;
      host.dataset.honeBound = "1";
      chart.on("click", function (params) {
        honeFromChart(host, params);
      });
    });
  }

  window.initInsightsHone = function () {
    bindHoneChips();
    patchIntensityCharts();
    bindChartHone();
  };

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "insights-slice-panel" || (t.closest && t.closest("#insights-slice-panel"))) {
      if (window.initClewCharts) window.initClewCharts();
      window.initInsightsHone();
    }
  });
})();