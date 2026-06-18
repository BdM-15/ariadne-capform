/**
 * Clew ECharts — dark ink/neon theme, HTMX-safe re-init.
 */
(function () {
  var instances = [];

  function stripSankeyLabel(name) {
    if (!name || typeof name !== "string") return name;
    var idx = name.indexOf("::");
    return idx >= 0 ? name.slice(idx + 2) : name;
  }

  function formatMillions(value) {
    var n = Number(value);
    if (!isFinite(n)) return value;
    return "$" + n.toFixed(2) + "M";
  }

  function polishOption(option) {
    if (!option || !option.series) return option;
    option.series.forEach(function (series) {
      if (series.type === "sankey" && series.data) {
        series.label = series.label || {};
        series.label.formatter = function (params) {
          return stripSankeyLabel(params.name);
        };
      }
    });
    if (option._clew && option._clew.tooltipTemplate === "year_value_actions") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        var p = params[0];
        if (!p || !p.data) return "";
        var acts = p.data.actions != null ? p.data.actions : "—";
        return (
          "FY " +
          p.axisValue +
          "<br/>" +
          formatMillions(p.data.value) +
          " obligated<br/>" +
          acts +
          " actions"
        );
      };
    } else if (option.tooltip && option.tooltip.trigger === "item") {
      option.tooltip.formatter = function (params) {
        if (params.data && params.data.value != null) {
          return stripSankeyLabel(params.name) + "<br/>" + formatMillions(params.data.value);
        }
        return stripSankeyLabel(params.name);
      };
    } else if (option.tooltip && option.tooltip.trigger === "axis") {
      option.tooltip.formatter = function (params) {
        var p = params[0];
        if (!p) return "";
        return p.name + "<br/>" + formatMillions(p.value);
      };
    }
    return option;
  }

  function disposeAll() {
    instances.forEach(function (chart) {
      if (chart && !chart.isDisposed()) chart.dispose();
    });
    instances = [];
  }

  function mount(host) {
    var raw = host.getAttribute("data-chart-option");
    if (!raw || !window.echarts) return;
    var option;
    try {
      option = JSON.parse(raw);
    } catch (e) {
      console.warn("Clew chart JSON parse failed", e);
      return;
    }
    var existing = window.echarts.getInstanceByDom(host);
    if (existing) existing.dispose();
    var chart = window.echarts.init(host, null, { renderer: "canvas" });
    chart.setOption(polishOption(option), { notMerge: true });
    instances.push(chart);
  }

  function resizeAll() {
    instances.forEach(function (chart) {
      if (chart && !chart.isDisposed()) chart.resize();
    });
  }

  window.initClewCharts = function () {
    if (!window.echarts) return;
    disposeAll();
    document.querySelectorAll(".clew-echarts-host").forEach(mount);
    resizeAll();
  };

  window.addEventListener("resize", resizeAll);

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "clew-results-panel" || (t.closest && t.closest("#clew-results-panel"))) {
      window.initClewCharts();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    if (document.querySelector(".clew-echarts-host")) window.initClewCharts();
  });
})();