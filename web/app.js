// E100 visibility dashboard -- vanilla JS, no build step, no CDN libraries.
// Fetches data/runs.json (written by `e100-visibility export-web`) and
// renders a date-filtered trend chart + a per-run detail table.

(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const CHART_COLORS = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5", "--chart-6"];

  const state = {
    runs: [], // sorted ascending by timestamp
    filteredRuns: [],
    selectedRunId: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function fmtPct(value) {
    return value === null || value === undefined ? "—" : `${value.toFixed(1)}%`;
  }

  function fmtPos(value) {
    return value === null || value === undefined ? "—" : value.toFixed(1);
  }

  function fmtDate(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toISOString().slice(0, 10);
  }

  function sentimentClass(sentiment) {
    if (sentiment === "positive") return "sentiment-positive";
    if (sentiment === "negative") return "sentiment-negative";
    return "sentiment-neutral";
  }

  const SENTIMENT_RU = { positive: "позитивная", neutral: "нейтральная", negative: "негативная" };

  // ---------- data loading ----------

  async function loadRuns() {
    const response = await fetch("data/runs.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const runs = await response.json();
    runs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    return runs;
  }

  // ---------- filtering ----------

  function applyDateFilter() {
    const fromValue = $("date-from").value;
    const toValue = $("date-to").value;
    const from = fromValue ? new Date(fromValue + "T00:00:00Z") : null;
    const to = toValue ? new Date(toValue + "T23:59:59Z") : null;

    state.filteredRuns = state.runs.filter((run) => {
      const t = new Date(run.timestamp);
      if (from && t < from) return false;
      if (to && t > to) return false;
      return true;
    });

    populateRunSelect();
    renderCharts();
    renderSelectedRun();
  }

  function populateRunSelect() {
    const select = $("run-select");
    select.innerHTML = "";

    if (state.filteredRuns.length === 0) {
      state.selectedRunId = null;
      const option = document.createElement("option");
      option.textContent = "нет прогонов в этом диапазоне";
      select.appendChild(option);
      select.disabled = true;
      return;
    }
    select.disabled = false;

    // newest first in the dropdown
    for (let i = state.filteredRuns.length - 1; i >= 0; i--) {
      const run = state.filteredRuns[i];
      const option = document.createElement("option");
      option.value = String(run.run_id);
      option.textContent = `#${run.run_id} — ${fmtDate(run.timestamp)}`;
      select.appendChild(option);
    }

    const stillInRange = state.filteredRuns.some((r) => r.run_id === state.selectedRunId);
    if (!stillInRange) {
      state.selectedRunId = state.filteredRuns[state.filteredRuns.length - 1].run_id;
    }
    select.value = String(state.selectedRunId);
  }

  // ---------- chart ----------

  function providerSeriesFor(runs, metricKey) {
    const providerNames = new Set();
    runs.forEach((run) => {
      run.aggregate.per_provider.forEach((p) => providerNames.add(p.provider));
    });
    const sortedProviders = Array.from(providerNames).sort();
    const names = [...sortedProviders, "overall"];

    return names.map((name, index) => {
      const points = runs.map((run) => {
        const stats =
          name === "overall" ? run.aggregate.overall : run.aggregate.per_provider.find((p) => p.provider === name);
        return { x: new Date(run.timestamp), y: stats ? stats[metricKey] : null };
      });
      const color = name === "overall" ? "var(--chart-overall)" : `var(${CHART_COLORS[index % CHART_COLORS.length]})`;
      return { name, points, color, bold: name === "overall" };
    });
  }

  function buildSegments(points) {
    const segments = [];
    let current = [];
    for (const point of points) {
      if (point.y === null || point.y === undefined) {
        if (current.length) segments.push(current);
        current = [];
      } else {
        current.push(point);
      }
    }
    if (current.length) segments.push(current);
    return segments;
  }

  function renderLineChart(container, series, { invertY = false } = {}) {
    container.innerHTML = "";

    const allPoints = series.flatMap((s) => s.points).filter((p) => p.y !== null && p.y !== undefined);
    if (allPoints.length === 0) {
      return false;
    }

    const width = 620;
    const height = 260;
    const margin = { top: 12, right: 12, bottom: 28, left: 40 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const xs = allPoints.map((p) => p.x.getTime());
    const ys = allPoints.map((p) => p.y);
    let xMin = Math.min(...xs);
    let xMax = Math.max(...xs);
    if (xMin === xMax) {
      xMin -= 1;
      xMax += 1;
    }
    let yMin = Math.min(...ys);
    let yMax = Math.max(...ys);
    const yPad = (yMax - yMin) * 0.15 || 1;
    yMin -= yPad;
    yMax += yPad;
    if (!invertY) yMin = Math.max(0, yMin);

    const sx = (t) => margin.left + ((t - xMin) / (xMax - xMin)) * innerW;
    const sy = (v) => {
      const ratio = (v - yMin) / (yMax - yMin);
      return invertY ? margin.top + ratio * innerH : margin.top + (1 - ratio) * innerH;
    };

    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");

    const axisColor = "var(--border)";
    const textColor = "var(--text-secondary)";

    // axes
    const xAxis = document.createElementNS(SVG_NS, "line");
    xAxis.setAttribute("x1", margin.left);
    xAxis.setAttribute("x2", width - margin.right);
    xAxis.setAttribute("y1", height - margin.bottom);
    xAxis.setAttribute("y2", height - margin.bottom);
    xAxis.setAttribute("stroke", axisColor);
    svg.appendChild(xAxis);

    const yAxis = document.createElementNS(SVG_NS, "line");
    yAxis.setAttribute("x1", margin.left);
    yAxis.setAttribute("x2", margin.left);
    yAxis.setAttribute("y1", margin.top);
    yAxis.setAttribute("y2", height - margin.bottom);
    yAxis.setAttribute("stroke", axisColor);
    svg.appendChild(yAxis);

    // y ticks: min/mid/max of the actual data domain
    [yMin + yPad, (yMin + yMax) / 2, yMax - yPad].forEach((value) => {
      const y = sy(value);
      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", margin.left - 6);
      label.setAttribute("y", y + 3);
      label.setAttribute("text-anchor", "end");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", textColor);
      label.textContent = value.toFixed(1);
      svg.appendChild(label);
    });

    // x ticks: first and last date in range (+ middle if room)
    const xTickTimes = xMax - xMin > 0 ? [xMin, (xMin + xMax) / 2, xMax] : [xMin];
    xTickTimes.forEach((t) => {
      const x = sx(t);
      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", x);
      label.setAttribute("y", height - margin.bottom + 16);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", textColor);
      label.textContent = new Date(t).toISOString().slice(0, 10);
      svg.appendChild(label);
    });

    series.forEach((s) => {
      buildSegments(s.points).forEach((segment) => {
        if (segment.length === 1) {
          const circle = document.createElementNS(SVG_NS, "circle");
          circle.setAttribute("cx", sx(segment[0].x.getTime()));
          circle.setAttribute("cy", sy(segment[0].y));
          circle.setAttribute("r", 3);
          circle.setAttribute("fill", s.color);
          svg.appendChild(circle);
          return;
        }
        const d = segment
          .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p.x.getTime()).toFixed(1)} ${sy(p.y).toFixed(1)}`)
          .join(" ");
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", d);
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", s.color);
        path.setAttribute("stroke-width", s.bold ? 2.5 : 1.75);
        path.setAttribute("stroke-linejoin", "round");
        svg.appendChild(path);

        segment.forEach((p) => {
          const circle = document.createElementNS(SVG_NS, "circle");
          circle.setAttribute("cx", sx(p.x.getTime()));
          circle.setAttribute("cy", sy(p.y));
          circle.setAttribute("r", 2.5);
          circle.setAttribute("fill", s.color);
          svg.appendChild(circle);
        });
      });
    });

    container.appendChild(svg);

    const legend = document.createElement("div");
    legend.className = "legend";
    series.forEach((s) => {
      const item = document.createElement("span");
      item.className = "legend-item";
      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      swatch.style.background = s.color;
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(s.name === "overall" ? "все провайдеры (среднее)" : s.name));
      legend.appendChild(item);
    });
    container.appendChild(legend);

    return true;
  }

  function renderCharts() {
    const runs = state.filteredRuns;
    const sovSeries = providerSeriesFor(runs, "share_of_voice_pct");
    const posSeries = providerSeriesFor(runs, "avg_position");

    const sovOk = renderLineChart($("chart-sov"), sovSeries, { invertY: false });
    const posOk = renderLineChart($("chart-position"), posSeries, { invertY: true });

    $("chart-empty").hidden = sovOk || posOk;
  }

  // ---------- run detail ----------

  function renderSelectedRun() {
    const run = state.filteredRuns.find((r) => r.run_id === state.selectedRunId);
    const heading = $("run-heading");
    const summary = $("run-summary");
    const competitorsBody = document.querySelector("#competitors-table tbody");
    const absentList = $("absent-queries-list");
    const recommendationsList = $("recommendations-list");
    const errorsList = $("errors-list");
    const observationsBody = document.querySelector("#observations-table tbody");

    summary.innerHTML = "";
    competitorsBody.innerHTML = "";
    absentList.innerHTML = "";
    recommendationsList.innerHTML = "";
    errorsList.innerHTML = "";
    observationsBody.innerHTML = "";

    if (!run) {
      heading.textContent = "Выбранный прогон";
      return;
    }

    heading.textContent = `Прогон #${run.run_id} — ${fmtDate(run.timestamp)}`;
    const agg = run.aggregate;

    const tiles = [
      ["Share of Voice (среднее)", fmtPct(agg.overall.share_of_voice_pct)],
      ["Средняя позиция (среднее)", fmtPos(agg.overall.avg_position)],
      ["Успешных запросов", `${agg.overall.successful_queries} / ${agg.overall.total_queries}`],
      ["Упоминаний E100", String(agg.overall.mentioned_count)],
    ];
    tiles.forEach(([label, value]) => {
      const tile = document.createElement("div");
      tile.className = "stat-tile";
      tile.innerHTML = `<div class="value">${value}</div><div class="label">${label}</div>`;
      summary.appendChild(tile);
    });

    agg.top_competitors.forEach((c, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${i + 1}</td><td>${escapeHtml(c.name)}</td><td>${c.frequency}</td><td>${fmtPos(c.avg_position)}</td>`;
      competitorsBody.appendChild(tr);
    });

    agg.absent_queries.forEach((q) => {
      const li = document.createElement("li");
      li.textContent = q;
      absentList.appendChild(li);
    });

    agg.recommendations.forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      recommendationsList.appendChild(li);
    });

    agg.errors.forEach((e) => {
      const li = document.createElement("li");
      li.textContent = `[${e.provider}] ${e.query}: ${e.message}`;
      errorsList.appendChild(li);
    });

    run.observations.forEach((o) => {
      const tr = document.createElement("tr");
      if (o.fetch_error) {
        tr.innerHTML = `
          <td class="wrap">${escapeHtml(o.query)}</td>
          <td>${escapeHtml(o.provider)}</td>
          <td colspan="6"><span class="badge error">ошибка</span> ${escapeHtml(o.fetch_error)}</td>
        `;
      } else {
        const mentionedBadge = o.mentioned
          ? '<span class="badge yes">Да</span>'
          : '<span class="badge no">Нет</span>';
        const position = o.mentioned ? `${o.position} из ${o.total_brands}` : "—";
        const sourceLink = o.has_source_link ? "есть" : "нет";
        tr.innerHTML = `
          <td class="wrap">${escapeHtml(o.query)}</td>
          <td>${escapeHtml(o.provider)}</td>
          <td>${mentionedBadge}</td>
          <td>${position}</td>
          <td class="wrap">${escapeHtml(o.context || "")}</td>
          <td class="${sentimentClass(o.sentiment)}">${SENTIMENT_RU[o.sentiment] || o.sentiment || "—"}</td>
          <td class="wrap">${o.competitors_above.length ? escapeHtml(o.competitors_above.join(", ")) : "—"}</td>
          <td>${sourceLink}</td>
        `;
      }
      observationsBody.appendChild(tr);
    });
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }

  // ---------- boot ----------

  function setDateInputBounds(runs) {
    const from = $("date-from");
    const to = $("date-to");
    const first = fmtDate(runs[0].timestamp);
    const last = fmtDate(runs[runs.length - 1].timestamp);
    from.min = first;
    from.max = last;
    to.min = first;
    to.max = last;
    from.value = first;
    to.value = last;
  }

  async function init() {
    let runs;
    try {
      runs = await loadRuns();
    } catch (err) {
      $("load-error").hidden = false;
      $("load-error-detail").textContent = String(err.message || err);
      $("market-label").textContent = "";
      return;
    }

    if (runs.length === 0) {
      $("empty-state").hidden = false;
      $("market-label").textContent = "";
      return;
    }

    state.runs = runs;
    const latest = runs[runs.length - 1];
    $("market-label").textContent = `Рынок: ${latest.market.label} (${latest.market.language}/${latest.market.country}) — ${runs.length} прогон(ов) в истории`;

    $("dashboard").hidden = false;
    setDateInputBounds(runs);

    $("date-from").addEventListener("change", applyDateFilter);
    $("date-to").addEventListener("change", applyDateFilter);
    $("run-select").addEventListener("change", (e) => {
      state.selectedRunId = Number(e.target.value);
      renderSelectedRun();
    });

    applyDateFilter();

    const rangeSummary = $("range-summary");
    // keep the "N of M runs in range" note in sync
    const updateRangeSummary = () => {
      rangeSummary.textContent = `${state.filteredRuns.length} из ${state.runs.length} прогонов в диапазоне`;
    };
    $("date-from").addEventListener("change", updateRangeSummary);
    $("date-to").addEventListener("change", updateRangeSummary);
    updateRangeSummary();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
