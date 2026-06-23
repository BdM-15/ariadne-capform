/**
 * Insights entity drill-down + intensity scatter tooltips (extends clew_charts.js).
 * Chart/chip click opens Agency or Competitor profile tab — does not mutate facet form.
 */
(function () {
  var DRILL_MAP = {
    agency: { lens: "agency", scope: "agency" },
    sub_agency: { lens: "agency", scope: "sub_agency" },
    awarding_office: { lens: "agency", scope: "office" },
    recipient: { lens: "competitor", scope: "recipient" },
  };

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
      chart.setOption({
        tooltip: { formatter: intensityTooltip },
      });
    });
  }

  function formParams(form) {
    var params = new URLSearchParams();
    if (!form) return params;
    new FormData(form).forEach(function (value, key) {
      if (value != null && String(value).length) params.append(key, String(value));
    });
    return params;
  }

  function entityKindForField(field) {
    var map = DRILL_MAP[field];
    return map ? map.lens : "agency";
  }

  function entityScopeForField(field, meta) {
    if (meta && meta.entityScope) return meta.entityScope;
    var map = DRILL_MAP[field];
    return map ? map.scope : field;
  }

  function navigateEntityDrill(field, value, meta) {
    var form = document.getElementById("insights-radar-form");
    if (!form || !value) return;
    if (window.closeInsightsAwardDrawer) window.closeInsightsAwardDrawer();
    var map = DRILL_MAP[field];
    if (!map && !(meta && meta.drillLens)) return;

    var lens = (meta && meta.drillLens) || (map && map.lens) || "overview";
    var scope = entityScopeForField(field, meta);
    var kind = lens === "competitor" ? "competitor" : "agency";

    var params = formParams(form);
    params.set("run", "1");
    params.set("lens", lens);
    params.set("entity_kind", kind);
    params.set("entity_value", value);
    params.set("entity_scope", scope);

    var lensInput = document.getElementById("insights-active-lens");
    if (lensInput) lensInput.value = lens;

    if (window.htmx) {
      window.htmx.ajax("GET", "/partials/insights/slice?" + params.toString(), {
        target: "#insights-slice-panel",
        swap: "outerHTML",
      });
    }
  }

  function drillFromChart(host, params) {
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
    }
    if (!value && params.name) value = params.name;
    if (!value) return;
    navigateEntityDrill(field, value, meta);
  }

  function bindDrillChips() {
    document.querySelectorAll(".insights-drill-chip").forEach(function (btn) {
      if (btn.dataset.drillBound) return;
      btn.dataset.drillBound = "1";
      btn.addEventListener("click", function () {
        navigateEntityDrill(
          btn.getAttribute("data-drill-field"),
          btn.getAttribute("data-drill-value"),
          null
        );
      });
    });
    document.querySelectorAll(".insights-hone-chip").forEach(function (btn) {
      if (btn.dataset.drillBound) return;
      btn.dataset.drillBound = "1";
      btn.addEventListener("click", function () {
        navigateEntityDrill(
          btn.getAttribute("data-hone-field"),
          btn.getAttribute("data-hone-value"),
          null
        );
      });
    });
  }

  function bindChartDrill() {
    if (!window.echarts) return;
    document.querySelectorAll(".clew-echarts-host").forEach(function (host) {
      var chart = window.echarts.getInstanceByDom(host);
      if (!chart || host.dataset.drillBound) return;
      host.dataset.drillBound = "1";
      chart.on("click", function (params) {
        drillFromChart(host, params);
      });
    });
  }

  window.initInsightsHone = function () {
    bindDrillChips();
    patchIntensityCharts();
    bindChartDrill();
  };

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "insights-slice-panel" || (t.closest && t.closest("#insights-slice-panel"))) {
      var lensInput = document.getElementById("insights-active-lens");
      var panel = document.getElementById("insights-slice-panel");
      if (lensInput && panel && panel.dataset.activeLens) {
        lensInput.value = panel.dataset.activeLens;
      }
      if (window.initClewCharts) window.initClewCharts();
      window.initInsightsHone();
    }
  });
})();