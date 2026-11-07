"use strict";
// Fictional identities and states. No export from any private owner or database.
window.DEMO_DATA = {
  workflows: [
    {
      id: "synthetic-etf-01",
      name: "studyA",
      sub: "subtitleA",
      status: "blocked",
      label: "blockedLabel",
      progress: 4,
      steps: [
        ["question", "complete", "quant-research", "authorizedScope"],
        ["snapshot", "complete", "market-data", "snapshotVerified"],
        ["backtest", "complete", "backtest-runtime", "integrityVerified"],
        ["pit", "blocked", "quant-research", "pitMissing"],
        ["review", "waiting", "quant-research", "reviewRequired"],
        ["handoff", "waiting", "quant-research", "notVerified"],
      ],
    },
    {
      id: "synthetic-cost-02",
      name: "studyB",
      sub: "subtitleB",
      status: "running",
      label: "runningLabel",
      progress: 3,
      steps: [
        ["question", "complete", "quant-research", "authorizedScope"],
        ["snapshot", "complete", "market-data", "snapshotVerified"],
        ["pit", "complete", "quant-research", "snapshotVerified"],
        ["backtest", "running", "backtest-runtime", "notVerified"],
        ["review", "waiting", "quant-research", "reviewRequired"],
        ["handoff", "waiting", "quant-research", "notVerified"],
      ],
    },
    {
      id: "synthetic-plan-03",
      name: "studyC",
      sub: "subtitleC",
      status: "approval",
      label: "approvalLabel",
      progress: 1,
      steps: [
        ["question", "complete", "quant-research", "authorizedScope"],
        ["snapshot", "blocked", "task-orchestrator", "approvalRequired"],
        ["pit", "waiting", "quant-research", "notVerified"],
        ["backtest", "waiting", "backtest-runtime", "notVerified"],
        ["review", "waiting", "quant-research", "reviewRequired"],
        ["handoff", "waiting", "quant-research", "notVerified"],
      ],
    },
  ],
  events: [
    ["event4", "event4sub", "time4"],
    ["event3", "event3sub", "time3"],
    ["event2", "event2sub", "time2"],
    ["event1", "event1sub", "time1"],
  ],
  skills: [
    ["pit-data-review", "data-owner", "syn-a14c82e", "skillRead"],
    ["backtest-audit", "runtime-owner", "syn-b63f90a", "skillBacktest"],
    ["research-handoff", "research-owner", "syn-c92d17b", "skillReview"],
  ],
};
