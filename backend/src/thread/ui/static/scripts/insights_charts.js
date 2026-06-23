/**
 * Insights — ECharts drill + graph expand. Profile buttons use HTMX (insights_drill_profile_btn).
 */
(function () {
  var SLICE_TARGET = "#insights-stage-content";

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
      chart.setOption({ tooltip: { formatter: intensityTooltip } });
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

  function entityParams() {
    var state = document.getElementById("insights-entity-state");
    var params = new URLSearchParams();
    if (!state) return params;
    if (state.tagName === "FORM") {
      new FormData(state).forEach(function (value, key) {
        if (value != null && String(value).length) params.append(key, String(value));
      });
      return params;
    }
    state.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (field) {
      if (field.name && field.value != null && String(field.value).length) {
        params.append(field.name, String(field.value));
      }
    });
    return params;
  }

  function sliceDrillParams(field, value, meta) {
    var form = document.getElementById("insights-radar-form");
    value = (value || "").trim();
    if (!form || !value) return null;
    if (window.closeInsightsAwardDrawer) window.closeInsightsAwardDrawer();

    var map = {
      agency: { lens: "agency", kind: "agency", scope: "agency" },
      sub_agency: { lens: "agency", kind: "agency", scope: "sub_agency" },
      awarding_office: { lens: "agency", kind: "agency", scope: "office" },
      recipient: { lens: "competitor", kind: "competitor", scope: "recipient" },
    };
    var row = map[field] || {};
    var lens = (meta && meta.drillLens) || row.lens || "overview";
    var scope = (meta && meta.entityScope) || row.scope || field;
    var kind = lens === "competitor" ? "competitor" : "agency";

    var params = formParams(form);
    params.set("run", "1");
    params.set("lens", lens);
    params.set("entity_kind", kind);
    params.set("entity_value", value);
    params.set("entity_scope", scope);

    var lensInput = document.getElementById("insights-active-lens");
    if (lensInput) lensInput.value = lens;
    if (window.persistInsightsSession) window.persistInsightsSession();
    return params;
  }

  function requestSliceDrill(field, value, meta) {
    var params = sliceDrillParams(field, value, meta);
    if (!params || !window.htmx) return;
    if (window.showInsightsSliceLoading) window.showInsightsSliceLoading("Opening profile…");
    window.htmx.ajax("GET", "/partials/insights/slice?" + params.toString(), {
      target: SLICE_TARGET,
      swap: "outerHTML",
      indicator: "#insights-slice-loading",
    });
  }

  function mergeGraphSeries(chart, expansion) {
    if (!chart || !expansion) return;
    var opt = chart.getOption();
    var series = (opt.series && opt.series[0]) || {};
    var nodes = series.data ? series.data.slice() : [];
    var links = series.links ? series.links.slice() : [];
    var nodeIds = {};
    nodes.forEach(function (n) {
      nodeIds[n.id] = true;
    });
    var linkKeys = {};
    links.forEach(function (l) {
      linkKeys[l.source + "→" + l.target] = true;
    });

    (expansion.nodes || []).forEach(function (n) {
      if (!nodeIds[n.id]) {
        nodeIds[n.id] = true;
        nodes.push({
          id: n.id,
          name: (n.label || n.id).slice(0, 32),
          kind: n.kind,
          hop: n.hop,
          value: n.millions_total || 0,
          symbolSize: 18,
        });
      }
    });

    var edgeColors = {
      obligation: "#00f0ff",
      teaming: "#00ff9c",
      teaming_network: "#86efac",
      vehicle_member: "#fbbf24",
      co_occurrence: "#ff2bd6",
      person_affiliation: "#f472b6",
    };
    (expansion.edges || []).forEach(function (e) {
      var key = e.source + "→" + e.target;
      if (linkKeys[key]) return;
      linkKeys[key] = true;
      links.push({
        source: e.source,
        target: e.target,
        value: Math.max(e.millions || 0.01, 0.01),
        lineStyle: {
          color: edgeColors[e.kind] || "#94a3b8",
          width: Math.max(1, Math.min(6, Math.sqrt(e.millions || 0))),
        },
        kind: e.kind,
      });
    });

    chart.setOption({ series: [{ data: nodes, links: links }] });
  }

  function expandGraphNode(host, nodeId) {
    var form = document.getElementById("insights-radar-form");
    if (!form || !nodeId) return;
    var params = formParams(form);
    entityParams().forEach(function (value, key) {
      params.append(key, value);
    });
    params.set("node_id", nodeId);
    params.set("batch", "3");
    fetch("/api/insights/graph-expand?" + params.toString())
      .then(function (res) {
        return res.json();
      })
      .then(function (payload) {
        if (payload.error || !payload.expansion) return;
        var chart = window.echarts.getInstanceByDom(host);
        mergeGraphSeries(chart, payload.expansion);
      })
      .catch(function () {});
  }

  function drillFromChart(host, params, ev) {
    var raw = host.getAttribute("data-chart-option");
    if (!raw) return;
    var option;
    try {
      option = JSON.parse(raw);
    } catch (_) {
      return;
    }
    var meta = option._intel || option._clew || {};
    var shiftExpand = ev && ev.shiftKey;

    if (meta.mode === "relations_graph" || meta.mode === "expose_graph") {
      if (shiftExpand && params.data && params.data.id) {
        expandGraphNode(host, params.data.id);
        return;
      }
      if (params.data) {
        var kind = params.data.kind || "";
        var label = params.data.name || params.name || "";
        if (kind === "prime" || kind === "sub") {
          requestSliceDrill("recipient", label, { drillLens: "competitor", entityScope: "recipient" });
        } else if (kind === "agency") {
          requestSliceDrill("agency", label, { drillLens: "agency", entityScope: "agency" });
        }
      }
      return;
    }
    if (meta.mode === "relationship_heatmap" && params.data && meta.recipients) {
      var yi = params.data[1];
      var recipient = meta.recipients[yi];
      if (recipient) {
        requestSliceDrill("recipient", recipient, { drillLens: "competitor", entityScope: "recipient" });
      }
      return;
    }
    var field = meta.honeField || meta.drillField;
    if (!field) return;
    var value = null;
    if (params.data) {
      if (field === "agency" && params.data.agency) value = params.data.agency;
      else if (params.data.label) value = params.data.label;
    }
    if (!value && params.name) value = params.name;
    if (!value) return;
    requestSliceDrill(field, value, meta);
  }

  function bindChartDrill() {
    if (!window.echarts) return;
    document.querySelectorAll(".clew-echarts-host").forEach(function (host) {
      var chart = window.echarts.getInstanceByDom(host);
      if (!chart || host.dataset.drillBound) return;
      host.dataset.drillBound = "1";
      chart.on("click", function (params) {
        var ev = params.event && params.event.event;
        drillFromChart(host, params, ev);
      });
    });
  }

  window.initInsightsHone = function () {
    patchIntensityCharts();
    bindChartDrill();
  };

  document.addEventListener("DOMContentLoaded", function () {
    window.initInsightsHone();
  });
  if (document.readyState !== "loading") window.initInsightsHone();
})();