"use strict";
(() => {
  let lang = "en";
  try {
    lang = localStorage.getItem("research-workbench-language") || "en";
  } catch (_) {}
  if (!window.liveLocales[lang]) lang = "en";
  const $ = (id) => document.getElementById(id),
    t = (k) =>
      window.liveLocales[lang][k] ||
      window.liveLocales[lang][String(k).toLowerCase()] ||
      k;
  const node = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  };
  let token="", authenticationRequired=false, authEpoch=0;
  let workflows = [],
    total = 0,
    selected = null,
    stepId = null,
    view = null,
    events = [],
    metrics = null,
    busy = false,
    last = null,
    healthy = false,
    detailError = false;
  const unknown = (v) =>
    v === null || v === undefined || v === ""
      ? t("unknown")
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v);
  const time = (v) => {
    if (!v) return t("unknown");
    const d = new Date(typeof v === "number" ? v * 1000 : v);
    return Number.isNaN(d.getTime())
      ? t("unknown")
      : new Intl.DateTimeFormat(lang, {
          dateStyle: "medium",
          timeStyle: "medium",
          timeZone: "UTC",
        }).format(d) + " UTC";
  };
  const value = (v) =>
    typeof v === "boolean" ? t(v ? "yes" : "no") : unknown(v);
  const badge = (s) => {
    s = String(s || "unknown").toLowerCase();
    return node(
      "span",
      t(s || "unknown"),
      "live-badge " +
        (s === "verified" || s === "succeeded"
          ? "good"
          : s === "missing" || s === "blocked" || s === "failed"
            ? "warn"
            : ""),
    );
  };
  const facts = (pairs) => {
    const dl = node("dl", undefined, "live-facts");
    pairs.forEach(([k, v]) => {
      dl.append(node("dt", t(k)), node("dd", v));
    });
    return dl;
  };
  const panel = (title) => {
    const e = node("section", undefined, "live-panel");
    e.append(node("h2", title));
    return e;
  };
  async function get(path) {
    const epoch = authEpoch;
    const r = await fetch(path, {
      cache: "no-store",
      headers: { Accept: "application/json", ...(token?{Authorization:"Bearer "+token}:{}) },
      signal: AbortSignal.timeout(8000),
    });
    if (r.status===401 && epoch === authEpoch) authenticationRequired=true;
    if (!r.ok) throw Error("HTTP " + r.status);
    return r.json();
  }
  function renderStatic() {
    document.documentElement.lang = lang;
    document.title = t("workbench");
    document
      .querySelectorAll("[data-i18n]")
      .forEach((e) => (e.textContent = t(e.dataset.i18n)));
    $("language").value = lang;
  }
  function renderList() {
    const statuses = [...new Set(workflows.map((w) => w.status))].sort();
    const old = $("status").value;
    const allOption = node("option", t("all"));
    allOption.value = "";
    $("status").replaceChildren(allOption);
    statuses.forEach((s) => {
      const o = node("option", t(s));
      o.value = s;
      $("status").append(o);
    });
    $("status").value = old;
    const q = $("search").value.toLocaleLowerCase(lang),
      filter = $("status").value,
      items = workflows.filter(
        (w) =>
          (!filter || w.status === filter) &&
          `${w.title} ${w.workflow_id}`.toLocaleLowerCase(lang).includes(q),
      );
    $("workflows").replaceChildren();
    items.forEach((w) => {
      const b = node("button", undefined, "live-workflow");
      b.type = "button";
      b.setAttribute("aria-pressed", String(w.workflow_id === selected));
      b.append(
        node("strong", w.title || w.workflow_id),
        node("small", w.workflow_id),
        badge(w.status),
      );
      b.onclick = () => {
        selected = w.workflow_id;
        stepId = null;
        view = null;
        events = [];
        render();
        poll();
      };
      $("workflows").append(b);
    });
    if (!items.length)
      $("workflows").append(
        node("p", t(workflows.length ? "noMatch" : "empty"), "live-muted"),
      );
    $("more").hidden = workflows.length >= total;
  }
  function renderMetrics() {
    $("metrics").replaceChildren();
    [
      ["workflows", metrics?.workflow_count],
      ["steps", metrics?.step_count],
      ["calls", metrics?.owner_calls],
      ["observedTokens", metrics?.observed_tokens],
      ["unknownUsage", metrics?.usage_unknown_count],
      ["errors", metrics?.owner_errors],
      ["interventions", metrics?.operator_interventions],
      ["cost", metrics?.model_cost_usd],
    ].forEach(([k, v]) => {
      const e = node("div", undefined, "live-metric");
      e.append(node("strong", unknown(v)), node("span", t(k)));
      $("metrics").append(e);
    });
  }
  function renderDetail() {
    const root = $("detail");
    root.replaceChildren();
    if (!view) {
      root.append(
        node("p", t(detailError ? "unavailable" : "select"), "live-muted"),
      );
      return;
    }
    if (detailError)
      root.append(node("p", t("unavailable"), "live-health outage"));
    const p = panel(view.title || view.workflow_id);
    p.append(
      badge(view.status),
      facts([
        ["plan", unknown(view.plan_sha256)],
        ["approved", value(view.approved)],
        ["research", value(view.research_validated)],
        ["promotion", value(view.promotion_authorized)],
        ["created", time(view.created_at)],
        ["updated", time(view.updated_at)],
        ["freshness", view.freshness ? t(view.freshness) : t("unknown")],
      ]),
    );
    root.append(p);
    const steps = Array.isArray(view.steps) ? view.steps : [],
      graph = panel(t("dependencies")),
      layers = node("div", undefined, "live-graph");
    let remaining = [...steps],
      done = new Set(),
      i = 0;
    while (remaining.length) {
      let layer = remaining.filter((s) =>
        (s.depends_on || []).every((d) => done.has(d)),
      );
      const invalid = !layer.length;
      if (invalid) layer = remaining;
      const col = node("div", undefined, "live-layer");
      col.append(
        node("small", invalid ? t("invalidGraph") : `${t("layer")} ${++i}`),
      );
      layer.forEach((s) => {
        const b = node("button", undefined, "live-step");
        b.type = "button";
        b.setAttribute(
          "aria-pressed",
          String(s.id === (stepId || steps[0]?.id)),
        );
        b.append(
          node("strong", s.id),
          badge(s.status),
          node(
            "small",
            `${t("depends")}: ${(s.depends_on || []).join(", ") || t("none")}`,
          ),
        );
        b.onclick = () => {
          stepId = s.id;
          renderDetail();
        };
        col.append(b);
      });
      layers.append(col);
      layer.forEach((s) => done.add(s.id));
      remaining = remaining.filter((s) => !done.has(s.id));
      if (invalid) break;
    }
    graph.append(layers);
    root.append(graph);
    const s = steps.find((s) => s.id === stepId) || steps[0];
    if (s) {
      const info = panel(s.id);
      info.append(
        facts([
          ["owner", unknown(s.owner_id)],
          ["revision", unknown(s.owner_revision)],
          ["updated", time(s.updated_at)],
          ["observed", time(s.observed_at)],
          ["evidenceState", unknown(s.evidence_status)],
          ["error", unknown(s.error_code)],
          ...Object.entries(s.metrics || {}).map(([k, v]) => [k, value(v)]),
        ]),
      );
      if (s.execution) {
        info.append(facts([
          ["session", unknown(s.execution.session_id)],
          ["turn", value(s.execution.turn)],
          ["observedTokens", value(s.execution.observed_tokens)],
          ["cumulativeTokens", value(s.execution.cumulative_tokens)],
        ]));
      }
      root.append(info);
      const evidence = panel(t("evidence")),
        grid = node("div", undefined, "live-evidence");
      [
        "input_integrity",
        "historical_pit",
        "execution_semantics",
        "independent_review",
        "economic_conclusion",
        "promotion",
      ].forEach((k) => {
        const c = s.evidence?.checks?.[k] || {},
          e = node("div", undefined, "live-check");
        e.append(
          node("strong", t(k === "promotion" ? "promotionCheck" : k)),
          badge(c.status),
          node("p", `${t("source")}: ${unknown(c.source)}`),
          node("p", `${t("digest")}: ${unknown(c.evidence_sha256)}`),
        );
        grid.append(e);
      });
      evidence.append(grid);
      root.append(evidence);
      const recovery = panel(t("recovery"));
      recovery.append(
        facts([
          ["code", unknown(s.recovery?.code)],
          ["operator", value(s.recovery?.requires_operator)],
        ]),
        node("h3", t("actions")),
      );
      const ul = node("ul");
      (s.recovery?.actions || []).forEach((a) => ul.append(node("li", t(a))));
      if (!ul.children.length) ul.append(node("li", t("unknown")));
      recovery.append(ul);
      root.append(recovery);
    }
    const ep = panel(t("events")),
      list = node("ol", undefined, "live-events");
    events
      .slice(-20)
      .reverse()
      .forEach((e) =>
        list.append(
          node(
            "li",
            `${time(e.created)} · ${e.type} · ${e.step_id || "—"} · #${e.seq}`,
          ),
        ),
      );
    if (!events.length) ep.append(node("p", t("noEvents"), "live-muted"));
    ep.append(list);
    root.append(ep);
  }
  function render() {
    renderStatic();
    $("login").hidden=!authenticationRequired&&!token;
    $("health").textContent = healthy
      ? `${t("connected")} ${time(last)}`
      : t("outage");
    $("health").classList.toggle("outage", !healthy);
    $("setup").hidden = healthy;
    renderMetrics();
    renderList();
    renderDetail();
  }
  async function poll(more = false) {
    if (busy) return;
    const epoch = authEpoch;
    busy = true;
    $("refresh").disabled = true;
    try {
      const offsets = more
        ? [workflows.length]
        : Array.from(
            { length: Math.max(1, Math.ceil(workflows.length / 100)) },
            (_, i) => i * 100,
          );
      const [pages, m] = await Promise.all([
        Promise.all(
          offsets.map((offset) =>
            get(`/v1/workflows?limit=100&offset=${offset}`),
          ),
        ),
        get("/v1/metrics"),
      ]);
      if (epoch !== authEpoch) return;
      const list = pages[0];
      list.workflows = pages.flatMap((p) => p.workflows);
      if (
        list.schema !== "quant.workflow_list.v1" ||
        !Array.isArray(list.workflows) ||
        m.schema !== "quant.orchestrator_metrics.v1"
      )
        throw Error("Invalid API");
      workflows = more ? [...workflows, ...list.workflows] : list.workflows;
      total = list.pagination?.total ?? workflows.length;
      metrics = m;
      if (!workflows.some((w) => w.workflow_id === selected)) {
        selected = null;
        view = null;
        events = [];
        stepId = null;
      }
      healthy = true;
      authenticationRequired=false;
      last = Date.now() / 1000;
      if (!selected && workflows.length) selected = workflows[0].workflow_id;
      if (selected) {
        const id = selected;
        try {
          const [v, e] = await Promise.all([
            get(`/v1/workflows/${encodeURIComponent(id)}`),
            get(`/v1/workflows/${encodeURIComponent(id)}/events?tail=100`),
          ]);
          if (epoch === authEpoch && id === selected) {
            view = v;
            events = Array.isArray(e.events) ? e.events : [];
            detailError = false;
          }
        } catch (_) {
          if (epoch === authEpoch) detailError = true;
        }
      }
    } catch (_) {
      if (epoch === authEpoch) healthy = false;
    } finally {
      if (epoch === authEpoch) {
        busy = false;
        $("refresh").disabled = false;
        render();
      }
    }
  }
  $("connect").onclick = () => {authEpoch++;busy=false;token=$("token").value.trim(); $("token").value=""; poll();};
  $("disconnect").onclick = () => {authEpoch++;busy=false;token=""; $("token").value="";workflows=[];total=0;metrics=null;view=null;events=[];selected=null;healthy=false;authenticationRequired=true;render();poll();};
  $("refresh").onclick = () => poll();
  $("more").onclick = () => poll(true);
  $("search").oninput = renderList;
  $("status").onchange = renderList;
  $("language").onchange = (e) => {
    lang = e.target.value;
    try {
      localStorage.setItem("research-workbench-language", lang);
    } catch (_) {}
    render();
  };
  render();
  poll();
  setInterval(() => poll(), 5000);
})();
