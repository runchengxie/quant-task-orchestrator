"use strict";
(() => {
  let language;
  try {
    language = localStorage.getItem("quant-demo-locale") || "en";
  } catch {
    language = "en";
  }
  if (!window.LOCALES[language]) language = "en";
  let data = structuredClone(window.DEMO_DATA);
  let selected = data.workflows[0].id;
  let stepIndex = 3;
  let filter = "all";
  let search = "";
  let toastTimer;
  const $ = (selector) => document.querySelector(selector);
  const t = (key) =>
    window.LOCALES[language][key] ?? window.LOCALES.en[key] ?? key;
  const escape = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[character],
    );
  const e = (key) => escape(t(key));
  function toast(key) {
    $("#toast").textContent = t(key);
    $("#toast").classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(
      () => $("#toast").classList.remove("visible"),
      4000,
    );
  }
  function workflow() {
    return data.workflows.find((item) => item.id === selected);
  }
  function badge(status, label) {
    return `<span class="pill ${status === "approval" ? "blocked" : status}">${e(label)}</span>`;
  }
  function renderRows() {
    const rows = data.workflows.filter(
      (item) =>
        (filter !== "attention" ||
          ["blocked", "failed", "approval", "review"].includes(item.status)) &&
        `${t(item.name)} ${item.id}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    );
    $("#workflow-list").innerHTML = rows.length
      ? rows
          .map(
            (item) =>
              `<button class="workflow-row ${item.id === selected ? "selected" : ""}" data-workflow="${escape(item.id)}" aria-pressed="${item.id === selected}"><span class="workflow-name"><span class="workflow-symbol">${item.status === "running" ? "⌁" : "◇"}</span><span><strong>${e(item.name)}</strong><small>${e(item.sub)}</small></span></span><span class="row-owner"><span>quant-research</span><small>${e("ownerPair")}</small></span><span>${badge(item.status, item.label)}</span><span class="row-progress"><span class="track"><span style="width:${(item.progress / 6) * 100}%"></span></span>${item.progress}/6</span><span class="arrow">›</span></button>`,
          )
          .join("")
      : `<p class="empty">${e("empty")}</p>`;
    document.querySelectorAll("[data-workflow]").forEach((button) =>
      button.addEventListener("click", () => {
        selected = button.dataset.workflow;
        stepIndex = workflow().steps.findIndex((step) =>
          ["blocked", "failed", "running"].includes(step[1]),
        );
        if (stepIndex < 0) stepIndex = 0;
        render();
      }),
    );
  }
  function renderMap() {
    const item = workflow();
    $("#map-title").textContent = t(item.name);
    $("#graph").innerHTML = item.steps
      .map(
        (step, index) =>
          `<button class="node ${step[1]} ${stepIndex === index ? "selected" : ""}" data-step="${index}" aria-pressed="${stepIndex === index}"><span class="node-top"><span class="mono">0${index + 1}</span><span class="node-state">${{ complete: "✓", failed: "×", blocked: "!", running: "◉", waiting: "○" }[step[1]]}</span></span><strong>${e(step[0])}</strong><small>${escape(step[2])}</small></button>`,
      )
      .join("");
    document.querySelectorAll("[data-step]").forEach((button) =>
      button.addEventListener("click", () => {
        stepIndex = Number(button.dataset.step);
        renderMap();
        renderInspector();
      }),
    );
  }
  function renderInspector() {
    const item = workflow();
    const step = item.steps[stepIndex];
    const stateLabel = {
      failed: "failed",
      complete: "complete",
      blocked: "blocked",
      running: "executing",
      waiting: "waiting",
    }[step[1]];
    let note =
      step[1] === "waiting"
        ? "waitingNote"
        : step[1] === "running"
          ? "computeNote"
          : "doneNote";
    if (step[1] === "failed") note = "failedNote";
    if (step[3] === "pitMissing") note = "pitBlock";
    if (step[3] === "approvalRequired") note = "approvalBlock";
    const definition = (key, value, mono = false) =>
      `<div class="definition"><span>${e(key)}</span><strong class="${mono ? "mono" : ""}">${escape(value)}</strong></div>`;
    $("#step-detail").innerHTML =
      `<div class="inspector-label">${e("stepInspector")} <span class="mono">/ 0${stepIndex + 1}</span></div><h2>${e(step[0])}</h2>${badge(step[1], stateLabel)}${definition("domainOwner", step[2], true)}<details class="technical-details"><summary>${e("advancedDetails")}</summary>${definition("assignment", `demo-${item.id.slice(-2)}-0${stepIndex + 1}`, true)}${definition("evidence", t(step[3]))}${definition("sourceRevision", "synthetic · a14c82e", true)}${definition("budget", `900 ${t("seconds")}`)}</details><div class="evidence-box"><strong>${e(item.status === "complete" ? "workflowComplete" : "workflowOpen")}</strong><p>${e(note)}</p></div><button class="inspector-action" id="step-action">${e(step[3] === "approvalRequired" ? "approveDemo" : step[1] === "running" ? "completeDemo" : "inspectManifest")}</button>`;
    $("#step-action").addEventListener("click", () => {
      if (step[3] === "approvalRequired") {
        item.status = "running";
        item.label = "runningLabel";
        item.progress = 2;
        step[1] = "running";
        step[3] = "notVerified";
        data.events.unshift(["event5", "event5sub", "time4"]);
        render();
        toast("approvalToast");
      } else if (step[1] === "running") {
        step[1] = "complete";
        step[3] =
          step[0] === "backtest" ? "integrityVerified" : "snapshotVerified";
        item.progress += 1;
        item.status = "review";
        item.label = "reviewLabel";
        const next = item.steps.findIndex(
          (candidate) => candidate[1] === "waiting",
        );
        if (next >= 0) {
          item.steps[next][1] = "blocked";
          item.steps[next][3] = "reviewRequired";
          stepIndex = next;
        }
        data.events.unshift(["event6", "event6sub", "time4"]);
        render();
        toast("completeToast");
      } else toast("manifestToast");
    });
  }
  function render() {
    document.documentElement.lang = language;
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll("[data-placeholder]").forEach((node) => {
      node.placeholder = t(node.dataset.placeholder);
      node.setAttribute("aria-label", t(node.dataset.placeholder));
    });
    $("#language").textContent = language === "en" ? "中文" : "English";
    $("#language").setAttribute(
      "aria-label",
      language === "en" ? "切换到中文" : "Switch to English",
    );
    const item = workflow();
    const done = item.steps.filter((step) => step[1] === "complete").length;
    const state = ["complete", "failed"].includes(item.status) ? item.status : item.status === "running" ? "running" : "blocked";
    const progress = t("progressSummary").replace("{done}", done).replace("{total}", item.steps.length);
    $("#workflow-summary").innerHTML = `<div class="summary-title"><div><div class="eyebrow">${e("selectedWorkflow")}</div><h2>${e(item.name)}</h2></div>${badge(item.status, item.label)}</div><div class="summary-progress"><strong>${escape(progress)}</strong><span class="track"><span style="width:${done / item.steps.length * 100}%"></span></span></div><div class="summary-copy"><div><h3>${e("currentSituation")}</h3><p>${e(state + "Summary")}</p></div><div class="next-step"><h3>${e("nextStep")}</h3><p>${e(state + "Next")}</p></div></div>`;
    renderRows();
    renderMap();
    renderInspector();
    $("#events").innerHTML = data.events
      .slice(0, 4)
      .map(
        (event) =>
          `<div class="event"><span class="event-marker"></span><div><strong>${e(event[0])}</strong><small>${e(event[1])}</small></div><time class="mono">${e(event[2])}</time></div>`,
      )
      .join("");
    $("#skill-list").innerHTML = data.skills
      .map(
        (skill) =>
          `<div class="skill"><strong>⌘ &nbsp;${escape(skill[0])}</strong><span class="mono">${escape(skill[1])} / ${escape(skill[2])}</span><span>◇ ${e(skill[3])}</span></div>`,
      )
      .join("");
  }
  $("#language").addEventListener("click", () => {
    language = language === "en" ? "zh-CN" : "en";
    try {
      localStorage.setItem("quant-demo-locale", language);
    } catch {}
    render();
  });
  $("#search").addEventListener("input", (event) => {
    search = event.target.value;
    renderRows();
  });
  document.querySelectorAll("[data-filter]").forEach((button) =>
    button.addEventListener("click", () => {
      filter = button.dataset.filter;
      document
        .querySelectorAll("[data-filter]")
        .forEach((tab) => tab.classList.toggle("active", tab === button));
      renderRows();
    }),
  );
  $("#replay").addEventListener("click", () => {
    data = structuredClone(window.DEMO_DATA);
    selected = data.workflows[0].id;
    stepIndex = 3;
    filter = "all";
    search = "";
    $("#search").value = "";
    document
      .querySelectorAll("[data-filter]")
      .forEach((tab) =>
        tab.classList.toggle("active", tab.dataset.filter === "all"),
      );
    render();
    toast("replayToast");
  });
  document.querySelectorAll(".nav-item").forEach((link) =>
    link.addEventListener("click", () => {
      if (link.getAttribute("href") !== "#workflows") $("#advanced-details").open = true;
      document
        .querySelectorAll(".nav-item")
        .forEach((item) => item.classList.toggle("active", item === link));
    }),
  );
  render();
})();
