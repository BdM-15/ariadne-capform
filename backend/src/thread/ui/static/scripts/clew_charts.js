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
    var intelMeta = option._intel || option._clew || {};
    if (intelMeta.tooltipTemplate === "year_value_actions") {
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
    } else if (intelMeta.tooltipTemplate === "expiring_timeline") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        if (!params || !params.length) return "";
        var lines = [params[0].axisValue];
        params.forEach(function (p) {
          if (p.seriesName === "$ expiring" && p.data) {
            var acts = p.data.actions != null ? p.data.actions : "—";
            lines.push(formatMillions(p.data.value) + " expiring · " + acts + " actions");
          } else if (p.seriesName === "Actions") {
            lines.push(p.value + " actions (month total line)");
          }
        });
        return lines.join("<br/>");
      };
    } else if (intelMeta.tooltipTemplate === "motion_fy_trend") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        if (!params || !params.length) return "";
        var lines = [params[0].axisValue];
        params.forEach(function (p) {
          if (p.seriesName === "$ obligated" && p.data) {
            var acts = p.data.actions != null ? p.data.actions : "—";
            lines.push(formatMillions(p.data.value) + " obligated · " + acts + " actions");
          } else if (p.seriesName === "Actions") {
            lines.push(p.value + " actions (FY total line)");
          }
        });
        return lines.join("<br/>");
      };
    } else if (intelMeta.tooltipTemplate === "motion_channel_pct") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        var d = params.data || {};
        var acts = d.actions != null ? d.actions : "—";
        return (
          (params.seriesName || "Lane") +
          "<br/>" +
          Number(d.value || 0).toFixed(1) +
          "% of slice · " +
          formatMillions(d.millions) +
          "<br/>" +
          acts +
          " actions"
        );
      };
    } else if (intelMeta.tooltipTemplate === "motion_q4_mix") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        if (!params || !params.length) return "";
        var period = params[0].axisValue || "";
        var totalM =
          period.indexOf("Q4") >= 0
            ? intelMeta.q4_total_millions
            : intelMeta.rest_total_millions;
        var lines = [period + (totalM != null ? " · " + formatMillions(totalM) + " total" : "")];
        params
          .filter(function (p) {
            return p.value > 0;
          })
          .sort(function (a, b) {
            return b.value - a.value;
          })
          .forEach(function (p) {
            var d = p.data || {};
            lines.push(
              (p.seriesName || "") +
                ": " +
                Number(p.value).toFixed(1) +
                "% · " +
                formatMillions(d.millions)
            );
          });
        return lines.join("<br/>");
      };
    } else if (intelMeta.tooltipTemplate === "motion_channel_value") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        var p = params[0];
        if (!p || !p.data) return "";
        var d = p.data;
        var pct = d.pct != null ? Number(d.pct).toFixed(1) + "% · " : "";
        var acts = d.actions != null ? " · " + d.actions + " actions" : "";
        return p.name + "<br/>" + pct + formatMillions(d.millions || d.value) + acts;
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
    if (!option || !option.series) return;
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

  function scheduleChartInit() {
    window.requestAnimationFrame(function () {
      window.initClewCharts();
    });
  }

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (
      t.id === "clew-results-panel" ||
      t.id === "insights-stage-content" ||
      (t.closest && (t.closest("#clew-results-panel") || t.closest("#insights-stage-content")))
    ) {
      scheduleChartInit();
    }
  });

  document.body.addEventListener("htmx:afterSettle", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (
      t.id === "insights-stage-content" ||
      (t.closest && t.closest("#insights-stage-content"))
    ) {
      scheduleChartInit();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    if (document.querySelector(".clew-echarts-host")) window.initClewCharts();
  });

  function showClewError(message) {
    var panel = document.getElementById("clew-results-panel");
    if (!panel) return;
    panel.innerHTML =
      '<div class="p-4 space-y-2">' +
      '<p class="text-neon-amber text-xs font-semibold">Clew analysis failed.</p>' +
      '<p class="text-[11px] text-slate-500 font-mono">' +
      message +
      "</p></div>";
  }

  document.body.addEventListener("htmx:beforeRequest", function (e) {
    var target = e.detail && e.detail.target;
    if (!target || target.id !== "clew-results-panel") return;
    target.innerHTML =
      '<div class="clew-results-loading p-6 text-center space-y-2">' +
      '<p class="text-neon-cyan text-sm font-semibold">Running trace…</p>' +
      '<p class="text-[11px] text-slate-500 font-mono">PG bulk query on ~4M awards — may take 5–15s. Live MCP adds a few seconds.</p>' +
      "</div>";
  });

  document.body.addEventListener("htmx:responseError", function (e) {
    var target = e.detail && e.detail.target;
    if (!target || target.id !== "clew-results-panel") return;
    var status = e.detail.xhr && e.detail.xhr.status;
    showClewError(
      "Server error" + (status ? " (HTTP " + status + ")" : "") + ". Check terminal log.",
    );
  });

  document.body.addEventListener("htmx:sendError", function (e) {
    var target = e.detail && e.detail.target;
    if (!target || target.id !== "clew-results-panel") return;
    showClewError("Network error — is python app.py running?");
  });
})();