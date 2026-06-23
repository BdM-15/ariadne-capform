/**
 * Insights entity drill-down, relations graph expand (DR browse +), intensity tooltips.
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
    new FormData(state).forEach(function (value, key) {
      if (value != null && String(value).length) params.append(key, String(value));
    });
    return params;
  }

  function openLensesCard() {
    var card = document.getElementById("insights-lenses-card");
    if (card) card.open = true;
  }

  function sliceLoadingEl() {
    return document.getElementById("insights-slice-loading");
  }

  function sliceLoadingMessage(lens, kind) {
    if (kind === "competitor" || lens === "competitor") {
      return "Loading competitor profile… PG + multi-hop relations graph may take 30–90s.";
    }
    if (kind === "agency" || lens === "agency") {
      return "Loading agency profile… PG query may take 30–90s.";
    }
    if (lens === "trace") {
      return "Loading Trace lens… relations graph + Sankeys may take 30–90s.";
    }
    if (lens === "competition") {
      return "Loading Competition lens…";
    }
    return "Loading lens results…";
  }

  function setSliceLoading(active, message, chip) {
    var banner = sliceLoadingEl();
    var panel = document.getElementById("insights-slice-panel");
    if (banner) {
      banner.textContent = message || "Loading…";
      banner.classList.toggle("is-loading", !!active);
    }
    if (panel) panel.classList.toggle("is-loading", !!active);
    if (chip) chip.classList.toggle("is-loading", !!active);
  }

  window.showInsightsSliceLoading = function (message) {
    setSliceLoading(true, message || "Loading…");
  };

  window.clearInsightsSliceLoading = function () {
    setSliceLoading(false, "");
    document.querySelectorAll(".insights-drill-chip.is-loading").forEach(function (el) {
      el.classList.remove("is-loading");
    });
  };

  function navigateEntityDrill(field, value, meta, chip) {
    var form = document.getElementById("insights-radar-form");
    value = (value || "").trim();
    if (!form || !value) return;
    if (window.closeInsightsAwardDrawer) window.closeInsightsAwardDrawer();
    var map = DRILL_MAP[field];
    if (!map && !(meta && meta.drillLens)) return;

    var lens = (meta && meta.drillLens) || (map && map.lens) || "overview";
    var scope = (meta && meta.entityScope) || (map && map.scope) || field;
    var kind = lens === "competitor" ? "competitor" : "agency";

    var params = formParams(form);
    params.set("run", "1");
    params.set("lens", lens);
    params.set("entity_kind", kind);
    params.set("entity_value", value);
    params.set("entity_scope", scope);

    var lensInput = document.getElementById("insights-active-lens");
    if (lensInput) lensInput.value = lens;
    openLensesCard();
    if (window.persistInsightsSession) window.persistInsightsSession();
    setSliceLoading(true, sliceLoadingMessage(lens, kind), chip);

    if (window.htmx) {
      window.htmx.ajax("GET", "/partials/insights/slice?" + params.toString(), {
        target: "#insights-slice-panel",
        swap: "outerHTML",
      });
    }
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

    chart.setOption({
      series: [{ data: nodes, links: links }],
    });
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

  function drillRelationsNode(params) {
    var kind = params.data.kind || "";
    var label = params.data.name || params.name || "";
    if (kind === "prime" || kind === "sub") {
      navigateEntityDrill("recipient", label, { drillLens: "competitor", entityScope: "recipient" });
    } else if (kind === "agency") {
      navigateEntityDrill("agency", label, { drillLens: "agency", entityScope: "agency" });
    } else if (kind === "person") {
      return;
    }
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
        drillRelationsNode(params);
      }
      return;
    }
    if (meta.mode === "relationship_heatmap" && params.data && meta.recipients) {
      var yi = params.data[1];
      var recipient = meta.recipients[yi];
      if (recipient) {
        navigateEntityDrill("recipient", recipient, {
          drillLens: "competitor",
          entityScope: "recipient",
        });
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
    navigateEntityDrill(field, value, meta);
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

  if (!document.body.dataset.insightsDrillDelegated) {
    document.body.dataset.insightsDrillDelegated = "1";
    document.body.addEventListener("click", function (event) {
      var chip = event.target.closest(".insights-drill-chip, .insights-hone-chip");
      if (!chip) return;
      if (chip.hasAttribute("hx-get")) return;
      event.preventDefault();
      event.stopPropagation();
      navigateEntityDrill(
        chip.getAttribute("data-drill-field") || chip.getAttribute("data-hone-field"),
        chip.getAttribute("data-drill-value") || chip.getAttribute("data-hone-value"),
        null,
        chip
      );
    });
  }

  document.body.addEventListener("htmx:beforeRequest", function (e) {
    var cfg = e.detail && e.detail.requestConfig;
    var elt = e.detail && e.detail.elt;
    var target = cfg && cfg.target;
    if (target !== "#insights-slice-panel" && target !== "insights-slice-panel") return;
    var banner = sliceLoadingEl();
    if (!banner || banner.classList.contains("htmx-request") || banner.classList.contains("is-loading")) {
      return;
    }
    var msg = "Loading lens results…";
    if (elt && elt.getAttribute && elt.getAttribute("role") === "tab") {
      msg = "Switching to " + (elt.textContent || "lens").trim() + "… PG may take 30–90s.";
    } else {
      var lensInput = document.getElementById("insights-active-lens");
      var lens = lensInput && lensInput.value ? lensInput.value : "overview";
      msg = sliceLoadingMessage(lens);
    }
    setSliceLoading(true, msg);
  });

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "insights-slice-panel" || (t.closest && t.closest("#insights-slice-panel"))) {
      if (window.clearInsightsSliceLoading) window.clearInsightsSliceLoading();
      var lensInput = document.getElementById("insights-active-lens");
      var panel = document.getElementById("insights-slice-panel");
      if (lensInput && panel && panel.dataset.activeLens) {
        lensInput.value = panel.dataset.activeLens;
      }
      if (window.initInsightsPage) window.initInsightsPage();
      else {
        if (window.initClewCharts) window.initClewCharts();
        window.initInsightsHone();
      }
    }
    if (t.id === "insights-lens-tabs") {
      if (window.initInsightsPage) window.initInsightsPage();
    }
  });

  document.body.addEventListener("htmx:responseError", function (e) {
    var cfg = e.detail && e.detail.requestConfig;
    var target = cfg && cfg.target;
    if (target === "#insights-slice-panel" || target === "insights-slice-panel") {
      if (window.clearInsightsSliceLoading) window.clearInsightsSliceLoading();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    window.initInsightsHone();
  });
  if (document.readyState !== "loading") window.initInsightsHone();
})();