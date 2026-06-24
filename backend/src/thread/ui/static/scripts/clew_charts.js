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

  function formatMoneyFromMillions(m) {
    var n = Number(m);
    if (!isFinite(n)) return "—";
    var sign = n < 0 ? "-" : "";
    var a = Math.abs(n);
    if (a >= 1e6) return sign + "$" + (a / 1e6).toFixed(1) + "T";
    if (a >= 1e3) return sign + "$" + (a / 1e3).toFixed(1) + "B";
    if (a >= 1) return sign + "$" + a.toFixed(1) + "M";
    if (a > 0) return sign + "$" + Math.round(a * 1e3) + "K";
    return sign + "$0";
  }

  function formatCount(n) {
    var v = Number(n);
    if (!isFinite(v)) return "—";
    var sign = v < 0 ? "-" : "";
    var a = Math.abs(v);
    if (a >= 1e6) return sign + (a / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return sign + (a / 1e3).toFixed(1) + "k";
    return sign + String(Math.round(v));
  }

  function moneyAxisLabel(value) {
    return formatMoneyFromMillions(value).replace(/^\$/, "");
  }

  window.clewChartFormat = {
    moneyFromMillions: formatMoneyFromMillions,
    count: formatCount,
  };

  function applyAxisFormatters(option) {
    if (!option) return option;
    var intel = option._intel || option._clew || {};
    var mode = intel.mode;

    if (mode === "agency_intensity" && option.xAxis && option.yAxis) {
      option.xAxis.axisLabel = option.xAxis.axisLabel || {};
      option.yAxis.axisLabel = option.yAxis.axisLabel || {};
      if (intel.logScale) {
        option.xAxis.axisLabel.formatter = function (v) {
          return formatCount(Math.round(v));
        };
        option.yAxis.axisLabel.formatter = moneyAxisLabel;
      } else {
        option.xAxis.axisLabel.formatter = formatCount;
        option.yAxis.axisLabel.formatter = moneyAxisLabel;
      }
    }

    if (
      intel.tooltipTemplate === "expiring_timeline" ||
      intel.tooltipTemplate === "motion_fy_trend"
    ) {
      if (Array.isArray(option.yAxis)) {
        option.yAxis[0].axisLabel = option.yAxis[0].axisLabel || {};
        option.yAxis[0].axisLabel.formatter = moneyAxisLabel;
        option.yAxis[1].axisLabel = option.yAxis[1].axisLabel || {};
        option.yAxis[1].axisLabel.formatter = formatCount;
      }
    }

    if (
      mode === "hbar" ||
      mode === "motion_expiring_channels" ||
      mode === "motion_parent_shadow" ||
      mode === "sub_flow" ||
      mode === "pricing_buckets"
    ) {
      if (option.xAxis && option.xAxis.type === "value") {
        option.xAxis.axisLabel = option.xAxis.axisLabel || {};
        option.xAxis.axisLabel.formatter = moneyAxisLabel;
      }
      if (option.yAxis && option.yAxis.type === "value" && option.yAxis.name === "$M") {
        option.yAxis.axisLabel = option.yAxis.axisLabel || {};
        option.yAxis.axisLabel.formatter = moneyAxisLabel;
      }
    }
    return option;
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
        var acts = p.data.actions != null ? formatCount(p.data.actions) : "—";
        return (
          "FY " +
          p.axisValue +
          "<br/>" +
          formatMoneyFromMillions(p.data.value) +
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
            var n =
              p.data.contracts != null
                ? p.data.contracts
                : p.data.actions != null
                  ? p.data.actions
                  : null;
            var count = n != null ? formatCount(n) : "—";
            lines.push(formatMoneyFromMillions(p.data.value) + " expiring · " + count + " contracts");
          } else if (p.seriesName === "Contracts" || p.seriesName === "Actions") {
            lines.push(formatCount(p.value) + " contracts (month total line)");
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
            var acts = p.data.actions != null ? formatCount(p.data.actions) : "—";
            lines.push(formatMoneyFromMillions(p.data.value) + " obligated · " + acts + " actions");
          } else if (p.seriesName === "Actions") {
            lines.push(formatCount(p.value) + " actions (FY total line)");
          }
        });
        return lines.join("<br/>");
      };
    } else if (intelMeta.tooltipTemplate === "motion_channel_pct") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        var d = params.data || {};
        var acts = d.actions != null ? formatCount(d.actions) : "—";
        return (
          (params.seriesName || "Lane") +
          "<br/>" +
          Number(d.value || 0).toFixed(1) +
          "% of slice · " +
          formatMoneyFromMillions(d.millions) +
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
        var lines = [
          period + (totalM != null ? " · " + formatMoneyFromMillions(totalM) + " total" : ""),
        ];
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
                formatMoneyFromMillions(d.millions)
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
        var acts = d.actions != null ? " · " + formatCount(d.actions) + " actions" : "";
        return p.name + "<br/>" + pct + formatMoneyFromMillions(d.millions || d.value) + acts;
      };
    } else if (intelMeta.tooltipTemplate === "intensity" || intelMeta.mode === "agency_intensity") {
      option.tooltip = option.tooltip || {};
      option.tooltip.formatter = function (params) {
        var d = params.data || {};
        var title = d.office || d.agency || params.name || "—";
        if (title && typeof title === "object") title = params.name || "—";
        var lines = ["<strong>" + title + "</strong>"];
        lines.push("<span style='color:#94a3b8'>Awarding office (contract actions)</span>");
        if (d.funding_office_count > 1) {
          lines.push(
            d.funding_office_count + " funding offices — trace customers on Agency tab"
          );
        } else if (d.funding_office_count === 1) {
          lines.push("1 funding office — trace on Agency tab");
        }
        if (d.parent_agency) lines.push("Agency: " + d.parent_agency);
        if (d.parent_sub) lines.push("Component: " + d.parent_sub);
        var acts =
          d.actions != null
            ? formatCount(d.actions) + " prime actions"
            : d.value && d.value[0] != null
              ? formatCount(Math.round(d.value[0])) + " actions (axis)"
              : "—";
        var millions =
          d.millions != null
            ? formatMoneyFromMillions(d.millions) + " obligated"
            : d.value && d.value[1] != null
              ? formatMoneyFromMillions(d.value[1]) + " (axis)"
              : "—";
        lines.push(acts);
        lines.push(millions);
        if (d.share_pct != null) lines.push(d.share_pct + "% of slice TAM");
        var quad = {
          hot: "<span style='color:#00ff9c'>Hot — qualify this office first</span>",
          high_value: "High $ — larger awards, fewer actions",
          high_volume: "High volume — many contract actions",
          watch: "Watch — below median on both axes",
        };
        if (d.quadrant && quad[d.quadrant]) lines.push(quad[d.quadrant]);
        else if (d.hot) lines.push(quad.hot);
        if (intelMeta.logScale) {
          lines.push("<span style='color:#64748b;font-size:10px'>Log axes — compare relative intensity</span>");
        }
        if (intelMeta.officeTotal && intelMeta.officeShown) {
          lines.push(
            "<span style='color:#64748b;font-size:10px'>Showing top " +
              intelMeta.officeShown +
              " of " +
              intelMeta.officeTotal +
              " offices</span>"
          );
        }
        lines.push(
          "<span style='color:#94a3b8;font-size:10px'>Click dot → Agency profile</span>"
        );
        return lines.join("<br/>");
      };
    } else if (option.tooltip && option.tooltip.trigger === "item" && intelMeta.mode !== "agency_intensity") {
      option.tooltip.formatter = function (params) {
        if (params.data && params.data.value != null) {
          return stripSankeyLabel(params.name) + "<br/>" + formatMoneyFromMillions(params.data.value);
        }
        return stripSankeyLabel(params.name);
      };
    } else if (option.tooltip && option.tooltip.trigger === "axis") {
      option.tooltip.formatter = function (params) {
        var p = params[0];
        if (!p) return "";
        return p.name + "<br/>" + formatMoneyFromMillions(p.value);
      };
    }
    return applyAxisFormatters(option);
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
    if (host.getAttribute("data-chart-key") === "intensity") {
      host._intensityBoundChart = null;
      if (window.bindIntensityChart) window.bindIntensityChart(host, chart);
    }
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