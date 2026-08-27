// E100 visibility dashboard -- vanilla JS, no build step, no CDN libraries.
// Fetches data/runs.json (written by `e100-visibility export-web`) and
// renders a date-filtered trend chart + a per-run detail table.

(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  // Fixed per-provider colors (not assigned by array index) so a given
  // provider keeps the same line color across charts/runs regardless of
  // which other providers are present. Keys must match the exact
  // `provider` string in run.aggregate.per_provider[].provider. An
  // unlisted (future) provider falls back to --text-secondary instead of
  // breaking the render -- see providerSeriesFor.
  const PROVIDER_COLORS = {
    openai: "--provider-openai",
    gemini: "--provider-gemini",
    perplexity: "--provider-perplexity",
    claude: "--provider-claude",
    grok: "--provider-grok",
    copilot: "--provider-copilot",
    google_ai_overview: "--provider-google_ai_overview",
    google_ai_mode: "--provider-google_ai_mode",
  };

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

  // Matches the fetch_error message every provider adapter raises when its
  // api_key_env isn't set (see ProviderError in each *_provider.py) -- an
  // expected "not wired up yet" state, not a real failure, so the UI shows
  // it as neutral rather than alarming.
  const MISSING_API_KEY_PATTERN = /environment variable .+ is not set/;

  function ruPlural(n, one, few, many) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
    return many;
  }

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

    return names.map((name) => {
      const points = runs.map((run) => {
        const stats =
          name === "overall" ? run.aggregate.overall : run.aggregate.per_provider.find((p) => p.provider === name);
        return { x: new Date(run.timestamp), y: stats ? stats[metricKey] : null };
      });
      const color =
        name === "overall"
          ? "var(--chart-overall)"
          : PROVIDER_COLORS[name]
            ? `var(${PROVIDER_COLORS[name]})`
            : "var(--text-secondary)";
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

  // ---------- breakdown charts (by provider / by query / by competitor) ----------

  // Fixed, reproducible illustrative numbers -- NOT random, NOT derived
  // from any real run -- shown only while isDemo is true (see
  // renderBreakdownCharts) so stakeholders can see the intended shape of
  // these charts before any provider API key is wired up. Every one of
  // these charts is preceded by a visible "ДЕМО" banner; the moment a run
  // has at least one successful observation, this data is never touched
  // again -- real numbers take over immediately, however sparse.
  const DEMO_PROVIDER_BREAKDOWN = [
    { label: "claude", pct: 60 },
    { label: "perplexity", pct: 52 },
    { label: "openai", pct: 45 },
    { label: "gemini", pct: 38 },
  ];

  const DEMO_QUERY_BREAKDOWN = [
    { label: "Jakie są najlepsze karty paliwowe dla firm w Polsce?", pct: 72 },
    { label: "Ranking kart paliwowych dla firm 2026", pct: 68 },
    { label: "Porównanie kart paliwowych dostępnych na polskim rynku", pct: 64 },
    { label: "Jakie firmy oferują karty paliwowe dla biznesu w Polsce?", pct: 58 },
    { label: "Opinie o kartach paliwowych dla firm – co wybrać?", pct: 55 },
    { label: "Najlepsze rozwiązania płatnicze dla flot samochodowych w Polsce", pct: 50 },
    { label: "Karta paliwowa dla dużej floty samochodów dostawczych", pct: 47 },
    { label: "Polecane karty flotowe dla małej firmy transportowej", pct: 44 },
    { label: "Najlepsza karta paliwowa dla przewoźników międzynarodowych (tankowanie w całej Europie)", pct: 41 },
    { label: "Karty paliwowe umożliwiające tankowanie na wielu sieciach stacji", pct: 38 },
    { label: "Jak wybrać kartę paliwową dla floty pojazdów?", pct: 35 },
    { label: "Karta flotowa z rabatem na paliwo dla firm transportowych", pct: 32 },
    { label: "Jak zarządzać wydatkami na paliwo w firmie – jakie narzędzia/karty pomagają?", pct: 29 },
    { label: "Karty paliwowe z aplikacją mobilną i raportowaniem wydatków", pct: 26 },
    { label: "Ile kosztuje karta paliwowa dla firmy i jakie są opłaty?", pct: 23 },
    { label: "Karta paliwowa dla firmy jednoosobowej vs dla dużej floty – różnice", pct: 20 },
    { label: "Karta paliwowa dla jednoosobowej działalności gospodarczej – co polecacie?", pct: 17 },
    { label: "Karty paliwowe bez limitu kredytowego dla firm", pct: 14 },
  ];

  const DEMO_COMPETITOR_BREAKDOWN = [
    { label: "E100", pct: 30, isE100: true },
    { label: "DKV", pct: 27, isE100: false },
    { label: "Shell", pct: 20, isE100: false },
    { label: "UTA", pct: 14, isE100: false },
    { label: "Orlen", pct: 9, isE100: false },
  ];

  const DEMO_BANNER_TEXT = "ДЕМО — так будет выглядеть после подключения API";

  function providerColorVar(name) {
    return PROVIDER_COLORS[name] ? `var(${PROVIDER_COLORS[name]})` : "var(--text-secondary)";
  }

  function computeProviderBreakdown(agg) {
    return agg.per_provider
      .filter((p) => p.successful_queries > 0)
      .map((p) => ({ label: p.provider, pct: p.share_of_voice_pct, color: providerColorVar(p.provider) }));
  }

  function computeQueryBreakdown(run) {
    const byQuery = new Map();
    run.observations.forEach((o) => {
      if (o.fetch_error) return; // not a successful observation for this metric
      if (!byQuery.has(o.query)) byQuery.set(o.query, { total: 0, mentioned: 0 });
      const entry = byQuery.get(o.query);
      entry.total += 1;
      if (o.mentioned) entry.mentioned += 1;
    });
    const items = [];
    byQuery.forEach((v, query) => {
      if (v.total === 0) return;
      items.push({ label: query, pct: (v.mentioned / v.total) * 100 });
    });
    items.sort((a, b) => b.pct - a.pct);
    return items;
  }

  function computeCompetitorBreakdown(agg) {
    const e100Count = agg.overall.mentioned_count;
    const total = e100Count + agg.top_competitors.reduce((sum, c) => sum + c.frequency, 0);
    if (total <= 0) return [];
    const items = [{ label: "E100", pct: (e100Count / total) * 100, isE100: true }];
    agg.top_competitors.forEach((c) => {
      items.push({ label: c.name, pct: (c.frequency / total) * 100, isE100: false });
    });
    return items;
  }

  function renderDemoBanner(container) {
    const banner = document.createElement("div");
    banner.className = "demo-banner";
    banner.textContent = DEMO_BANNER_TEXT;
    container.appendChild(banner);
  }

  function renderBarList(container, bars, { isDemo = false } = {}) {
    container.innerHTML = "";
    if (isDemo) renderDemoBanner(container);

    if (bars.length === 0) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Недостаточно данных для графика.";
      container.appendChild(empty);
      return;
    }

    const width = 640;
    const rowH = 34;
    const margin = { top: 6, left: 8, right: 8 };
    const trackW = width - margin.left - margin.right;
    const height = margin.top + bars.length * rowH;

    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");

    bars.forEach((bar, i) => {
      const rowY = margin.top + i * rowH;

      const labelText = document.createElementNS(SVG_NS, "text");
      labelText.setAttribute("x", margin.left);
      labelText.setAttribute("y", rowY + 10);
      labelText.setAttribute("font-size", "11");
      labelText.setAttribute("fill", "var(--text)");
      const truncated = bar.label.length > 70 ? `${bar.label.slice(0, 68)}…` : bar.label;
      labelText.textContent = truncated;
      if (truncated !== bar.label) {
        const title = document.createElementNS(SVG_NS, "title");
        title.textContent = bar.label;
        labelText.appendChild(title);
      }
      svg.appendChild(labelText);

      const barY = rowY + 16;
      const barH = 12;
      const track = document.createElementNS(SVG_NS, "rect");
      track.setAttribute("x", margin.left);
      track.setAttribute("y", barY);
      track.setAttribute("width", trackW);
      track.setAttribute("height", barH);
      track.setAttribute("rx", 3);
      track.setAttribute("fill", "var(--border)");
      svg.appendChild(track);

      const pct = Math.max(0, Math.min(100, bar.pct));
      const fillW = (pct / 100) * trackW;
      const fill = document.createElementNS(SVG_NS, "rect");
      fill.setAttribute("x", margin.left);
      fill.setAttribute("y", barY);
      fill.setAttribute("width", fillW);
      fill.setAttribute("height", barH);
      fill.setAttribute("rx", 3);
      fill.setAttribute("fill", bar.color || "var(--accent)");
      svg.appendChild(fill);

      const valueText = document.createElementNS(SVG_NS, "text");
      valueText.setAttribute("y", barY + barH - 2);
      valueText.setAttribute("font-size", "10");
      valueText.setAttribute("font-weight", "600");
      const insideLabel = pct >= 85;
      if (insideLabel) {
        valueText.setAttribute("x", margin.left + fillW - 4);
        valueText.setAttribute("text-anchor", "end");
        valueText.setAttribute("fill", "#ffffff");
      } else {
        valueText.setAttribute("x", margin.left + fillW + 4);
        valueText.setAttribute("text-anchor", "start");
        valueText.setAttribute("fill", "var(--text)");
      }
      valueText.textContent = `${pct.toFixed(0)}%`;
      svg.appendChild(valueText);
    });

    container.appendChild(svg);
  }

  function renderDonut(container, segments, { isDemo = false } = {}) {
    container.innerHTML = "";
    if (isDemo) renderDemoBanner(container);

    if (segments.length === 0) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Недостаточно данных для графика.";
      container.appendChild(empty);
      return;
    }

    const size = 320;
    const cx = size / 2;
    const cy = size / 2;
    const r = 90;
    const strokeW = 36;
    const circumference = 2 * Math.PI * r;

    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("role", "img");

    const ring = document.createElementNS(SVG_NS, "g");
    ring.setAttribute("transform", `rotate(-90 ${cx} ${cy})`);

    let cumulative = 0;
    const labels = [];
    segments.forEach((seg) => {
      const segLen = (seg.pct / 100) * circumference;
      const circle = document.createElementNS(SVG_NS, "circle");
      circle.setAttribute("cx", cx);
      circle.setAttribute("cy", cy);
      circle.setAttribute("r", r);
      circle.setAttribute("fill", "none");
      circle.setAttribute("stroke", seg.color);
      circle.setAttribute("stroke-width", strokeW);
      circle.setAttribute("stroke-dasharray", `${segLen} ${circumference - segLen}`);
      circle.setAttribute("stroke-dashoffset", `${-cumulative}`);
      ring.appendChild(circle);

      const midAngleDeg = ((cumulative + segLen / 2) / circumference) * 360 - 90;
      const labelR = r + strokeW / 2 + 16;
      const rad = (midAngleDeg * Math.PI) / 180;
      labels.push({
        x: cx + labelR * Math.cos(rad),
        y: cy + labelR * Math.sin(rad),
        text: `${seg.label} ${seg.pct.toFixed(0)}%`,
        color: seg.color,
        angleDeg: midAngleDeg,
      });

      cumulative += segLen;
    });

    svg.appendChild(ring);

    labels.forEach((l) => {
      const normalized = ((l.angleDeg % 360) + 360) % 360;
      const text = document.createElementNS(SVG_NS, "text");
      text.setAttribute("x", l.x);
      text.setAttribute("y", l.y);
      text.setAttribute("font-size", "11");
      text.setAttribute("font-weight", "600");
      text.setAttribute("fill", l.color);
      text.setAttribute("text-anchor", normalized > 90 && normalized < 270 ? "end" : "start");
      text.setAttribute("dominant-baseline", "middle");
      text.textContent = l.text;
      svg.appendChild(text);
    });

    container.appendChild(svg);
  }

  function renderBreakdownCharts(run) {
    const isDemo = run.aggregate.overall.successful_queries === 0;

    if (isDemo) {
      renderBarList($("chart-by-provider"), DEMO_PROVIDER_BREAKDOWN.map((p) => ({ ...p, color: providerColorVar(p.label) })), { isDemo: true });
      renderBarList($("chart-by-query"), DEMO_QUERY_BREAKDOWN.map((q) => ({ ...q, color: "var(--accent)" })), { isDemo: true });
      renderDonut(
        $("chart-competitors-share"),
        DEMO_COMPETITOR_BREAKDOWN.map((c) => ({ ...c, color: c.isE100 ? "var(--accent)" : "var(--text-secondary)" })),
        { isDemo: true }
      );
      return;
    }

    const agg = run.aggregate;
    renderBarList($("chart-by-provider"), computeProviderBreakdown(agg));
    renderBarList(
      $("chart-by-query"),
      computeQueryBreakdown(run).map((q) => ({ ...q, color: "var(--accent)" }))
    );
    renderDonut(
      $("chart-competitors-share"),
      computeCompetitorBreakdown(agg).map((c) => ({ ...c, color: c.isE100 ? "var(--accent)" : "var(--text-secondary)" }))
    );
  }

  // ---------- run detail ----------

  function renderErrorGroups(container, agg) {
    const groups = new Map();
    agg.errors.forEach((e) => {
      if (!groups.has(e.provider)) groups.set(e.provider, []);
      groups.get(e.provider).push(e);
    });

    groups.forEach((entries, provider) => {
      const allMissingKey = entries.every((e) => MISSING_API_KEY_PATTERN.test(e.message));
      const stats = agg.per_provider.find((p) => p.provider === provider);
      const totalForProvider = stats ? stats.total_queries : entries.length;

      const li = document.createElement("li");
      const details = document.createElement("details");
      const summary = document.createElement("summary");

      if (allMissingKey) {
        summary.innerHTML = `<strong>${escapeHtml(provider)}</strong> <span class="badge neutral">API не подключён</span>`;
      } else {
        const errorWord = ruPlural(entries.length, "ошибка", "ошибки", "ошибок");
        const queryWord = ruPlural(totalForProvider, "запрос", "запроса", "запросов");
        const badgeText = `${entries.length} ${errorWord} из ${totalForProvider} ${queryWord}`;
        summary.innerHTML = `<strong>${escapeHtml(provider)}</strong> <span class="badge error">${badgeText}</span> <span class="muted">${escapeHtml(entries[0].message)}</span>`;
      }

      const nested = document.createElement("ul");
      nested.className = "plain-list nested-error-log";
      entries.forEach((e) => {
        const nestedLi = document.createElement("li");
        nestedLi.textContent = `${e.query}: ${e.message}`;
        nested.appendChild(nestedLi);
      });

      details.appendChild(summary);
      details.appendChild(nested);
      li.appendChild(details);
      container.appendChild(li);
    });
  }

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
    $("chart-by-provider").innerHTML = "";
    $("chart-by-query").innerHTML = "";
    $("chart-competitors-share").innerHTML = "";

    if (!run) {
      heading.textContent = "Выбранный прогон";
      return;
    }

    heading.textContent = `Прогон #${run.run_id} — ${fmtDate(run.timestamp)}`;
    const agg = run.aggregate;
    renderBreakdownCharts(run);

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

    renderErrorGroups(errorsList, agg);

    run.observations.forEach((o) => {
      const tr = document.createElement("tr");
      if (o.fetch_error) {
        const isMissingKey = MISSING_API_KEY_PATTERN.test(o.fetch_error);
        const badgeClass = isMissingKey ? "badge neutral" : "badge error";
        const badgeText = isMissingKey ? "API не подключён" : "ошибка";
        tr.innerHTML = `
          <td class="wrap">${escapeHtml(o.query)}</td>
          <td>${escapeHtml(o.provider)}</td>
          <td colspan="6"><span class="${badgeClass}" title="${escapeHtml(o.fetch_error)}">${badgeText}</span></td>
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

  // ---------- trigger run ----------

  const TRIGGER_RUN_LOCKOUT_MS = 60000;
  const TRIGGER_RUN_DEFAULT_LABEL = "Запустить прогон";

  async function handleTriggerRun() {
    const button = $("trigger-run-button");
    const status = $("trigger-run-status");

    button.disabled = true;
    button.textContent = "Запускаем…";
    status.textContent = "";
    status.classList.remove("error-text");

    let response;
    try {
      response = await fetch("/api/trigger-run", { method: "POST" });
    } catch {
      status.textContent = "Не удалось запустить: сетевая ошибка.";
      status.classList.add("error-text");
      button.disabled = false;
      button.textContent = TRIGGER_RUN_DEFAULT_LABEL;
      return;
    }

    let data = null;
    try {
      data = await response.json();
    } catch {
      // fall through with data == null -- handled below via the generic
      // HTTP-status message, never surfacing a raw/unparseable body
    }

    if (response.ok && data && data.ok) {
      status.textContent = "Прогон запущен — обновите дашборд через 3-5 минут.";
      button.textContent = "Запущено";
      setTimeout(() => {
        button.disabled = false;
        button.textContent = TRIGGER_RUN_DEFAULT_LABEL;
      }, TRIGGER_RUN_LOCKOUT_MS);
      return;
    }

    const message = (data && data.error) || `HTTP ${response.status}`;
    status.textContent = `Не удалось запустить: ${message}`;
    status.classList.add("error-text");
    button.disabled = false;
    button.textContent = TRIGGER_RUN_DEFAULT_LABEL;
  }

  // ---------- queries editor ----------

  // sha is required by GitHub's Contents API to prove we're overwriting
  // the version we last read, not silently clobbering someone else's
  // concurrent edit -- see the 409 handling in handleQueriesSave.
  const queriesEditorState = { sha: null, loaded: false };

  async function loadQueriesEditor() {
    const textarea = $("queries-textarea");
    const status = $("queries-status");
    status.textContent = "";
    status.classList.remove("error-text");

    let response;
    try {
      response = await fetch("/api/queries", { method: "GET" });
    } catch {
      status.textContent = "Не удалось загрузить: сетевая ошибка.";
      status.classList.add("error-text");
      return;
    }

    let data = null;
    try {
      data = await response.json();
    } catch {
      // handled below via the generic HTTP-status message
    }

    if (response.ok && data && typeof data.content === "string" && typeof data.sha === "string") {
      textarea.value = data.content;
      queriesEditorState.sha = data.sha;
      queriesEditorState.loaded = true;
    } else {
      const message = (data && data.error) || `HTTP ${response.status}`;
      status.textContent = `Не удалось загрузить: ${message}`;
      status.classList.add("error-text");
    }
  }

  async function handleQueriesSave() {
    const textarea = $("queries-textarea");
    const button = $("queries-save-button");
    const status = $("queries-status");

    if (!queriesEditorState.sha) {
      status.textContent = "Сначала дождитесь загрузки текущего содержимого файла.";
      status.classList.add("error-text");
      return;
    }

    button.disabled = true;
    button.textContent = "Сохраняем…";
    status.textContent = "";
    status.classList.remove("error-text");

    let response;
    try {
      response = await fetch("/api/queries", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: textarea.value, sha: queriesEditorState.sha }),
      });
    } catch {
      status.textContent = "Не удалось сохранить: сетевая ошибка.";
      status.classList.add("error-text");
      button.disabled = false;
      button.textContent = "Сохранить";
      return;
    }

    let data = null;
    try {
      data = await response.json();
    } catch {
      // handled below via the generic HTTP-status message
    }

    button.disabled = false;
    button.textContent = "Сохранить";

    if (response.ok && data && data.ok) {
      if (data.sha) queriesEditorState.sha = data.sha;
      status.textContent = "Сохранено — изменения попадут в дашборд после следующего прогона.";
      return;
    }

    // Textarea content is deliberately left untouched on any failure
    // (including a 409 conflict) so the user's edits aren't lost.
    const message = (data && data.error) || `HTTP ${response.status}`;
    status.textContent = `Не удалось сохранить: ${message}`;
    status.classList.add("error-text");
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
    $("trigger-run-button").addEventListener("click", handleTriggerRun);
    $("queries-save-button").addEventListener("click", handleQueriesSave);
    $("queries-editor").addEventListener("toggle", () => {
      if ($("queries-editor").open && !queriesEditorState.loaded) {
        loadQueriesEditor();
      }
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
