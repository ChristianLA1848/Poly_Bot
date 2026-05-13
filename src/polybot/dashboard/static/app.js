const statusValue = document.querySelector("#status-value");
const statusPill = document.querySelector("#bot-status");
const pnlValue = document.querySelector("#pnl-value");
const btcPrice = document.querySelector("#btc-price");
const targetPrice = document.querySelector("#target-price");
const targetDelta = document.querySelector("#target-delta");
const strategyReasonCode = document.querySelector("#strategy-reason-code");
const strategyEdge = document.querySelector("#strategy-edge");
const strategyConfidence = document.querySelector("#strategy-confidence");
const decisionsList = document.querySelector("#decisions");
const eventsList = document.querySelector("#events");
const decisionCount = document.querySelector("#decision-count");
const eventCount = document.querySelector("#event-count");
const marketState = document.querySelector("#market-state");
const marketMessage = document.querySelector("#market-message");
const marketSlug = document.querySelector("#market-slug");
const marketQuestion = document.querySelector("#market-question");
const marketEndTime = document.querySelector("#market-end-time");
const marketAcceptingOrders = document.querySelector("#market-accepting-orders");
const marketOrderRules = document.querySelector("#market-order-rules");
const startBotButton = document.querySelector("#start-bot");
const stopBotButton = document.querySelector("#stop-bot");
const settingsForm = document.querySelector("#settings-form");
const settingsStatus = document.querySelector("#settings-status");

let currentSettings = {};

function formatCurrency(value, signed = false) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(Number(value));
}

function setRuntimeStatus(status) {
  statusValue.textContent = status;
  statusPill.textContent = status;
}

function setControlBusy(isBusy) {
  startBotButton.disabled = isBusy;
  stopBotButton.disabled = isBusy;
}

async function errorDetail(response, fallback) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail) && payload.detail.length > 0) {
      return payload.detail
        .map((item) => item.msg || item.message || JSON.stringify(item))
        .join("; ");
    }
  } catch {
    return fallback;
  }

  return fallback;
}

function getNested(source, path) {
  return path.split(".").reduce((value, key) => value?.[key], source);
}

function setNested(target, path, value) {
  const parts = path.split(".");
  let cursor = target;

  for (const part of parts.slice(0, -1)) {
    cursor[part] = cursor[part] || {};
    cursor = cursor[part];
  }

  cursor[parts.at(-1)] = value;
}

function cloneSettings(settings) {
  return JSON.parse(JSON.stringify(settings || {}));
}

function populateSettingsForm(settings) {
  currentSettings = cloneSettings(settings);

  for (const field of settingsForm.elements) {
    if (!field.name) {
      continue;
    }

    const value = getNested(settings, field.name);
    if (value !== null && value !== undefined) {
      field.value = value;
    }
  }
}

function settingsFromForm() {
  const settings = cloneSettings(currentSettings);

  for (const field of settingsForm.elements) {
    if (!field.name || field.value === "") {
      continue;
    }

    const value = field.type === "number" ? Number(field.value) : field.value;
    setNested(settings, field.name, value);
  }

  return settings;
}

function renderSettings(settings) {
  if (settings && Object.keys(settings).length > 0) {
    populateSettingsForm(settings);
  }
}

function renderEmpty(list, message) {
  list.innerHTML = "";
  const item = document.createElement("li");
  item.className = "empty";
  item.textContent = message;
  list.appendChild(item);
}

function createRow(title, body, timestamp) {
  const item = document.createElement("li");
  item.className = "row";

  const content = document.createElement("div");
  const heading = document.createElement("strong");
  const detail = document.createElement("p");
  const time = document.createElement("time");

  heading.textContent = title;
  detail.textContent = body;
  time.textContent = timestamp;

  content.append(heading, detail);
  item.append(content, time);
  return item;
}

function renderDecisions(decisions) {
  decisionCount.textContent = decisions.length;
  decisionsList.innerHTML = "";

  if (decisions.length === 0) {
    renderEmpty(decisionsList, "No decisions recorded yet.");
    return;
  }

  for (const decision of decisions) {
    decisionsList.appendChild(
      createRow(
        decision.action || "UNKNOWN",
        decision.reason || "No reason provided",
        decision.created_at || "",
      ),
    );
  }
}

function renderStrategyMetrics(decisions) {
  const latestDecision = (decisions || [])[0] || {};
  strategyReasonCode.textContent = latestDecision.reason_code || "-";
  strategyEdge.textContent =
    latestDecision.edge === null || latestDecision.edge === undefined
      ? "-"
      : Number(latestDecision.edge).toFixed(4);
  strategyConfidence.textContent =
    latestDecision.confidence === null || latestDecision.confidence === undefined
      ? "-"
      : `${(Number(latestDecision.confidence) * 100).toFixed(1)}%`;
}

function renderEvents(events) {
  eventCount.textContent = events.length;
  eventsList.innerHTML = "";

  if (events.length === 0) {
    renderEmpty(eventsList, "No events recorded yet.");
    return;
  }

  for (const event of events) {
    eventsList.appendChild(
      createRow(event.level || "info", event.message || "", event.created_at || ""),
    );
  }
}

function renderMarketStatus(status) {
  const market = status || {};
  marketState.textContent = market.state || "unknown";
  marketMessage.textContent = market.message || "No market checked yet.";
  marketSlug.textContent = market.slug || "-";
  marketQuestion.textContent = market.question || "-";
  marketEndTime.textContent = market.end_time || "-";
  marketAcceptingOrders.textContent =
    typeof market.accepting_orders === "boolean" ? String(market.accepting_orders) : "-";
  marketOrderRules.textContent =
    market.tick_size && market.min_size ? `${market.tick_size} / ${market.min_size}` : "-";
}

function renderFeedStatus(feed) {
  btcPrice.textContent = formatCurrency(feed?.btc_price);
  targetPrice.textContent = formatCurrency(feed?.target_price);

  const deltaParts = [];
  if (feed?.delta_pct !== null && feed?.delta_pct !== undefined) {
    deltaParts.push(
      `${new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 3,
        minimumFractionDigits: 3,
        signDisplay: "exceptZero",
      }).format(Number(feed.delta_pct))}%`,
    );
  }
  if (feed?.delta !== null && feed?.delta !== undefined) {
    deltaParts.push(formatCurrency(feed.delta, true));
  }
  targetDelta.textContent = deltaParts.length > 0 ? deltaParts.join(" / ") : "-";
}

async function refreshSnapshot() {
  const response = await fetch("/api/snapshot");
  if (!response.ok) {
    throw new Error(`Snapshot request failed: ${response.status}`);
  }

  const snapshot = await response.json();
  const status = snapshot.runtime_status?.state || snapshot.bot_status || "ready";
  setRuntimeStatus(status);
  pnlValue.textContent = formatCurrency(snapshot.today_pnl, true);
  renderFeedStatus(snapshot.feed_status);
  renderMarketStatus(snapshot.market_status);
  renderSettings(snapshot.settings);
  const recentDecisions = snapshot.recent_decisions || [];
  renderStrategyMetrics(recentDecisions);
  renderDecisions(recentDecisions);
  renderEvents(snapshot.recent_events || []);
}

async function loadSettings() {
  const response = await fetch("/api/settings");
  if (!response.ok) {
    return;
  }

  renderSettings(await response.json());
}

for (const tab of document.querySelectorAll("[data-tab-target]")) {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tabTarget;
    document.querySelectorAll("[data-tab-target]").forEach((item) => {
      const isActive = item === tab;
      item.classList.toggle("is-active", isActive);
      item.setAttribute("aria-selected", String(isActive));
    });
    document
      .querySelectorAll("[data-tab-panel]")
      .forEach((panel) => panel.classList.toggle("is-active", panel.dataset.tabPanel === target));
  });
}

startBotButton.addEventListener("click", async () => {
  setControlBusy(true);

  try {
    const response = await fetch("/api/bot/start", { method: "POST" });
    if (!response.ok) {
      throw new Error(await errorDetail(response, `Start request failed: ${response.status}`));
    }
    await refreshSnapshot();
  } catch (error) {
    statusValue.textContent = error.message;
    statusPill.textContent = "error";
  } finally {
    setControlBusy(false);
  }
});

stopBotButton.addEventListener("click", async () => {
  setControlBusy(true);

  try {
    const response = await fetch("/api/bot/stop", { method: "POST" });
    if (!response.ok) {
      throw new Error(await errorDetail(response, `Stop request failed: ${response.status}`));
    }
    await refreshSnapshot();
  } catch (error) {
    statusValue.textContent = error.message;
    statusPill.textContent = "error";
  } finally {
    setControlBusy(false);
  }
});

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  settingsStatus.textContent = "Saving...";

  try {
    const response = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settingsFromForm()),
    });
    if (!response.ok) {
      throw new Error(await errorDetail(response, `Settings request failed: ${response.status}`));
    }

    renderSettings(await response.json());
    settingsStatus.textContent = "Saved for next start.";
  } catch (error) {
    settingsStatus.textContent = error.message;
  }
});

loadSettings().catch(() => {
  settingsStatus.textContent = "Settings unavailable.";
});

refreshSnapshot().catch(() => {
  setRuntimeStatus("offline");
});

setInterval(() => {
  refreshSnapshot().catch(() => {
    setRuntimeStatus("offline");
  });
}, 5000);
