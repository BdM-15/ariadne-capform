/**
 * Insights — ECharts drill + graph expand. Profile buttons use HTMX (insights_drill_profile_btn).
 */
(function () {
  var SLICE_TARGET = "#insights-stage-content";
  var intensityDrillLock = false;

  function formParams(form) {
    var params = new URLSearchParams();
    if (!form) return params;
    new FormData(form).forEach(function (value, key) {
      if (value != null && String(value).length) params.append(key, String(value));
    });
    return params;
  }

  function sliceDrillValues(field, value, meta) {
    var form = document.getElementById("insights-radar-form");
    value = (value || "").trim();
    if (!form || !value) return null;
    if (window.closeInsightsAwardDrawer) window.closeInsightsAwardDrawer();

    var map = {
      agency: { lens: "agency", kind: "agency", scope: "agency" },
      sub_agency: { lens: "agency", kind: "agency", scope: "sub_agency" },
      awarding_office: { lens: "agency", kind: "agency", scope: "office" },
      funding_office: { lens: "agency", kind: "agency", scope: "office" },
      recipient: { lens: "competitor", kind: "competitor", scope: "recipient" },
    };
    var row = map[field] || {};
    var lens = (meta && meta.drillLens) || row.lens || "overview";
    var scope = (meta && meta.entityScope) || row.scope || field;
    var kind = lens === "competitor" ? "competitor" : "agency";

    var lensInput = document.getElementById("insights-active-lens");
    if (lensInput) lensInput.value = lens;
    syncEntityState(kind, scope, value);
    if (window.persistInsightsSession) window.persistInsightsSession();
    return {
      run: "1",
      lens: lens,
      entity_kind: kind,
      entity_value: value,
      entity_scope: scope,
    };
  }

  function syncEntityState(kind, scope, value) {
    var root = document.getElementById("insights-entity-state");
    if (!root) return;
    var kindInput = root.querySelector('input[name="entity_kind"]');
    var valueInput = root.querySelector('input[name="entity_value"]');
    var scopeInput = root.querySelector('input[name="entity_scope"]');
    if (kindInput) kindInput.value = kind || "";
    if (valueInput) valueInput.value = value || "";
    if (scopeInput) scopeInput.value = scope || "";
  }

  function requestSliceDrill(field, value, meta) {
    if (intensityDrillLock) return;
    var values = sliceDrillValues(field, value, meta);
    if (!values || !window.postInsightsSlice) return;
    intensityDrillLock = true;
    window.postInsightsSlice(values, "Opening Agency profile…").catch(function () {
      if (window.showInsightsSliceLoading) window.showInsightsSliceLoading("Run slice first, then click a dot.");
    }).finally(function () {
      if (window.releaseIntensityDrillLock) window.releaseIntensityDrillLock();
    });
  }

  window.releaseIntensityDrillLock = function () {
    intensityDrillLock = false;
  };

  function intensityOfficeValue(params) {
    var d = params.data || {};
    return String(d.office || d.agency || params.name || "").trim();
  }

  function openIntensityOffice(host, params) {
    var raw = host.getAttribute("data-chart-option");
    if (!raw) return;
    var option;
    try {
      option = JSON.parse(raw);
    } catch (_) {
      return;
    }
    var meta = option._intel || option._clew || {};
    var value = intensityOfficeValue(params);
    if (!value) return;
    requestSliceDrill(meta.honeField || "awarding_office", value, meta);
  }

  window.openIntensityOfficeFromChart = function (host, params) {
    openIntensityOffice(host, params || {});
  };

  function intensityScatterData(chart) {
    var opt = chart.getOption();
    var series = opt.series && opt.series[0];
    return series && series.data ? series.data : [];
  }

  function nearestIntensityIndex(chart, offsetX, offsetY) {
    var data = intensityScatterData(chart);
    if (!data.length) return -1;
    var nearest = -1;
    var minDist = Infinity;
    data.forEach(function (item, idx) {
      var value = item.value;
      if (!value || value.length < 2) return;
      var pixel = chart.convertToPixel({ seriesIndex: 0 }, value);
      if (!pixel || pixel.length < 2) return;
      var dx = pixel[0] - offsetX;
      var dy = pixel[1] - offsetY;
      var dist = dx * dx + dy * dy;
      var radius = (item.symbolSize || 12) / 2 + 10;
      if (dist > radius * radius) return;
      if (dist < minDist) {
        minDist = dist;
        nearest = idx;
      }
    });
    return nearest;
  }

  function bindIntensityZrClick(host, chart) {
    var zr = chart.getZr();
    if (!zr) return;
    if (host._intensityZrClick) zr.off("click", host._intensityZrClick);
    host._intensityZrClick = function (ev) {
      if (ev && ev.event) ev.event.stopPropagation();
      var idx = nearestIntensityIndex(chart, ev.offsetX, ev.offsetY);
      if (idx < 0) return;
      var data = intensityScatterData(chart)[idx];
      if (!data) return;
      openIntensityOffice(host, { data: data, dataIndex: idx });
    };
    zr.on("click", host._intensityZrClick);
  }

  window.bindIntensityChart = function (host, chart) {
    if (!host || !chart || chart.isDisposed()) return;
    if (host._intensityBoundChart === chart) return;
    host._intensityBoundChart = chart;
    chart.off("click");
    bindIntensityZrClick(host, chart);
    host.style.cursor = "pointer";
  };

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
    if (meta.mode === "agency_intensity") {
      openIntensityOffice(host, params);
      return;
    }
    if (meta.mode === "relations_graph" || meta.mode === "expose_graph") {
      if (ev && ev.shiftKey && params.data && params.data.id) {
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
      if (params.data.office) value = params.data.office;
      else if (params.data.label && typeof params.data.label === "string") value = params.data.label;
      else if (field === "agency" && params.data.agency) value = params.data.agency;
    }
    if (!value && params.name) value = params.name;
    if (!value) return;
    requestSliceDrill(field, value, meta);
  }

  function bindChartDrill() {
    if (!window.echarts) return;
    document.querySelectorAll(".clew-echarts-host").forEach(function (host) {
      if (host.getAttribute("data-chart-key") === "intensity") return;
      var chart = window.echarts.getInstanceByDom(host);
      if (!chart) return;
      if (host._insightsDrillChart === chart) return;
      host._insightsDrillChart = chart;
      chart.off("click");
      chart.on("click", function (params) {
        var ev = params.event && (params.event.event || params.event);
        drillFromChart(host, params, ev);
      });
    });
  }

  window.rebindOfficesScatter = function () {
    document.querySelectorAll('.clew-echarts-host[data-chart-key="intensity"]').forEach(function (host) {
      var chart = window.echarts.getInstanceByDom(host);
      if (!chart || !window.bindIntensityChart) return;
      host._intensityBoundChart = null;
      window.bindIntensityChart(host, chart);
    });
  };

  window.initInsightsHone = function () {
    bindChartDrill();
    window.rebindOfficesScatter();
  };

  document.body.addEventListener("htmx:afterSettle", function (evt) {
    var target = evt.detail && evt.detail.target;
    if (!target || !target.querySelector) return;
    if (!target.querySelector('[data-chart-key="intensity"]')) return;
    window.setTimeout(function () {
      window.rebindOfficesScatter();
    }, 50);
  });

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    if (window.releaseIntensityDrillLock) window.releaseIntensityDrillLock();
    var target = evt.detail && evt.detail.target;
    if (!target || target.id !== "insights-stage-content") return;
    var lens = target.dataset && target.dataset.activeLens;
    if (lens === "agency") {
      target.querySelectorAll(".insights-lens-tab").forEach(function (tab) {
        if (tab.textContent && tab.textContent.trim() === "Agency" && tab.scrollIntoView) {
          tab.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
      });
      var body = target.querySelector("#insights-lens-body");
      if (body && body.scrollIntoView) body.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    window.initInsightsHone();
  });
  if (document.readyState !== "loading") window.initInsightsHone();
})();