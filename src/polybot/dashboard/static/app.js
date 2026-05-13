const statusValue = document.querySelector("#status-value");
const statusPill = document.querySelector("#bot-status");
const pnlValue = document.querySelector("#pnl-value");
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

function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    signDisplay: "exceptZero",
  }).format(Number(value || 0));
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

async function refreshSnapshot() {
  const response = await fetch("/api/snapshot");
  if (!response.ok) {
    throw new Error(`Snapshot request failed: ${response.status}`);
  }

  const snapshot = await response.json();
  const status = snapshot.bot_status || "ready";
  statusValue.textContent = status;
  statusPill.textContent = status;
  pnlValue.textContent = formatCurrency(snapshot.today_pnl);
  renderMarketStatus(snapshot.market_status);
  renderDecisions(snapshot.recent_decisions || []);
  renderEvents(snapshot.recent_events || []);
}

refreshSnapshot().catch(() => {
  statusValue.textContent = "offline";
  statusPill.textContent = "offline";
});

setInterval(() => {
  refreshSnapshot().catch(() => {
    statusValue.textContent = "offline";
    statusPill.textContent = "offline";
  });
}, 5000);
