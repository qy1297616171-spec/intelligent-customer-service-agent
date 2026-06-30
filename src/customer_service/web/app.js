const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const messages = $("#messages");
const questionInput = $("#question");
const sendButton = $("#send-button");
const tenantId = "demo-company";
let customerId = "customer-2846";
let rounds = 0;
let latestDocuments = [];
let currentConversationId = null;
let editingDocumentId = null;
let allSessions = [];
let activeSessionFilter = "all";
let allTickets = [];
let allCustomers = [];
let editingCustomerId = null;
const welcomeMarkup = messages.innerHTML;

async function loadModelStatus() {
  try {
    const response = await fetch("/model-status");
    const status = await response.json();
    $("#model-label").textContent = status.configured
      ? `${status.model} 模型`
      : "本地证据直答模式";
  } catch (error) {
    $("#model-label").textContent = "模型状态未知";
  }
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function showToast(text) {
  const toast = $("#toast");
  toast.textContent = text;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2300);
}

function switchPage(page) {
  const widePage = page !== "chat";
  $("#app-shell").classList.toggle("knowledge-mode", widePage);
  $("#chat-page").classList.toggle("active", page === "chat");
  $("#knowledge-page").classList.toggle("active", page === "knowledge");
  $("#analytics-page").classList.toggle("active", page === "analytics");
  $("#tickets-page").classList.toggle("active", page === "tickets");
  $("#customers-page").classList.toggle("active", page === "customers");
  $("#audit-page").classList.toggle("active", page === "audit");
  $$(".global-item[data-page]").forEach((item) => item.classList.toggle("active", item.dataset.page === page));
  if (page === "knowledge") loadDocuments();
  if (page === "analytics") loadAnalytics();
  if (page === "tickets") loadTickets();
  if (page === "customers") loadCustomers();
  if (page === "audit") loadAuditLogs();
}

$$('[data-page]').forEach((item) => item.addEventListener("click", () => switchPage(item.dataset.page)));
$$('.muted-action').forEach((item) => item.addEventListener("click", () => showToast("该模块已预留，将在后续版本开放")));
$("#go-knowledge").addEventListener("click", () => switchPage("knowledge"));

function appendMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = role === "assistant"
    ? `<div class="message-avatar">AI</div><div class="message-body"><div class="message-name">星选商城智能客服 <span>机器人</span></div><div class="bubble">${content}</div><time>刚刚</time></div>`
    : `<div class="message-body"><div class="message-name">王女士 · 金卡会员</div><div class="bubble"><p>${escapeHtml(content)}</p></div><time>刚刚</time></div>`;
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function updateSources(citations) {
  $("#source-count").textContent = citations.length;
  $("#source-list").innerHTML = citations.length ? citations.map((item) => `
    <article class="source-card">
      <header><strong>${escapeHtml(item.title)}</strong><em>${Math.round(item.score * 100)}% 匹配</em></header>
      <p>${escapeHtml(item.source)}</p>
    </article>`).join("") : '<div class="source-empty"><span>⌕</span><p>当前回答没有可引用的企业知识</p></div>';
}

async function askQuestion(question) {
  if (!currentConversationId) await createConversation(false);
  appendMessage("user", question);
  questionInput.value = "";
  sendButton.disabled = true;
  const loading = appendMessage("assistant", '<span class="typing"><i></i><i></i><i></i></span>');
  try {
    const response = await fetch("/api/v1/conversations/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: tenantId, customer_id: customerId, conversation_id: currentConversationId, question }),
    });
    if (!response.ok) throw new Error("请求失败");
    const data = await response.json();
    currentConversationId = data.conversation_id;
    const citations = data.citations.map((item) => `
      <div class="citation-link"><strong>知识来源</strong> · ${escapeHtml(item.title)} / ${escapeHtml(item.source)}</div>`).join("");
    loading.querySelector(".bubble").innerHTML = `
      <p>${escapeHtml(data.answer)}</p>
      <div class="answer-meta">
        <span class="meta-pill ${data.grounded ? "" : "warning"}">${data.answer_type === "business_fact" ? "✓ 电商系统实时数据" : (data.grounded ? "✓ 已通过知识校验" : "! 依据不足，建议转人工")}</span>
        <span class="meta-pill">${data.cache_hit ? "缓存快速回答" : "实时检索回答"}</span>
        <span class="meta-pill">${data.latency_ms} 毫秒</span>
      </div>${citations}`;
    rounds += 1;
    $("#round-count").textContent = rounds;
    $("#avg-latency").textContent = `${data.latency_ms}ms`;
    updateSources(data.citations);
    await loadConversations(false);
  } catch (error) {
    loading.querySelector(".bubble").innerHTML = '<p>客服服务暂时不可用，请稍后重试或转接人工客服。</p><div class="answer-meta"><span class="meta-pill warning">连接异常</span></div>';
  } finally {
    sendButton.disabled = false;
    questionInput.focus();
  }
}

$("#ask-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (question) askQuestion(question);
});

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("#ask-form").requestSubmit();
  }
});
questionInput.addEventListener("input", () => {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 100)}px`;
});
messages.addEventListener("click", (event) => {
  const button = event.target.closest("[data-question]");
  if (button) askQuestion(button.dataset.question);
});

async function createConversation(notify = true) {
  const response = await fetch("/api/v1/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, customer_id: customerId, customer_name: "王女士" }),
  });
  if (!response.ok) throw new Error("创建会话失败");
  const session = await response.json();
  currentConversationId = session.id;
  rounds = 0;
  $("#round-count").textContent = "0";
  $("#avg-latency").textContent = "--";
  updateSources([]);
  messages.innerHTML = welcomeMarkup;
  await loadConversations(false);
  questionInput.focus();
  if (notify) showToast("已创建新的客服会话");
  return session;
}

function sessionTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "刚刚" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function renderSessions(sessions) {
  allSessions = sessions;
  const pendingSessions = sessions.filter((session) => session.status === "handoff");
  $("#session-count").textContent = sessions.length;
  $("#pending-count").textContent = pendingSessions.length;
  const visibleSessions = activeSessionFilter === "pending" ? pendingSessions : sessions;
  $("#session-list").innerHTML = visibleSessions.length ? `<p class="group-title">${activeSessionFilter === "pending" ? "待处理会话" : "最近会话"}</p>${visibleSessions.map((session) => `
    <button class="session-item ${session.id === currentConversationId ? "active" : ""}" data-session-id="${session.id}">
      <span class="channel-avatar green">王</span>
      <span class="session-copy"><strong>${escapeHtml(session.customer_name)} · 金卡会员</strong><small>${escapeHtml(session.preview)}</small></span>
      <span class="session-meta"><time>${sessionTime(session.updated_at)}</time>${session.status === "open" ? '<i class="online-dot"></i>' : ""}</span>
    </button>`).join("")}` : `<p class="session-loading">${activeSessionFilter === "pending" ? "当前没有待处理会话" : "暂无会话"}</p>`;
}

$$('[data-session-filter]').forEach((button) => button.addEventListener("click", () => {
  activeSessionFilter = button.dataset.sessionFilter;
  $$('[data-session-filter]').forEach((item) => item.classList.toggle("active", item === button));
  renderSessions(allSessions);
}));

async function loadConversations(loadActive = true) {
  try {
    const response = await fetch(`/api/v1/conversations?tenant_id=${tenantId}&customer_id=${customerId}`);
    const sessions = await response.json();
    if (!sessions.length) {
      await createConversation(false);
      return;
    }
    if (!currentConversationId) currentConversationId = sessions[0].id;
    renderSessions(sessions);
    if (loadActive) await loadConversationMessages(currentConversationId);
  } catch (error) {
    $("#session-list").innerHTML = '<p class="session-loading">会话加载失败</p>';
  }
}

async function loadConversationMessages(conversationId) {
  const response = await fetch(`/api/v1/conversations/${conversationId}/messages?tenant_id=${tenantId}`);
  if (!response.ok) throw new Error("消息加载失败");
  const history = await response.json();
  rounds = history.filter((item) => item.role === "user").length;
  $("#round-count").textContent = rounds;
  updateSources(history.at(-1)?.citations || []);
  if (!history.length) {
    messages.innerHTML = welcomeMarkup;
    return;
  }
  messages.innerHTML = '<div class="date-divider"><span>历史消息</span></div>';
  history.forEach((item) => {
    if (item.role === "user") {
      appendMessage("user", item.content);
      return;
    }
    const citations = item.citations.map((citation) => `<div class="citation-link"><strong>知识来源</strong> · ${escapeHtml(citation.title)} / ${escapeHtml(citation.source)}</div>`).join("");
    appendMessage("assistant", `<p>${escapeHtml(item.content)}</p>${citations}`);
  });
}

$("#new-chat").addEventListener("click", () => createConversation().catch(() => showToast("创建会话失败")));

$("#session-search").addEventListener("input", (event) => {
  const keyword = event.target.value.trim().toLowerCase();
  $$(".session-item").forEach((item) => item.hidden = !item.textContent.toLowerCase().includes(keyword));
});
$("#session-list").addEventListener("click", async (event) => {
  const item = event.target.closest("[data-session-id]");
  if (!item) return;
  currentConversationId = item.dataset.sessionId;
  $$(".session-item").forEach((entry) => entry.classList.toggle("active", entry === item));
  try { await loadConversationMessages(currentConversationId); } catch (error) { showToast("历史消息加载失败"); }
});
$("#transfer-button").addEventListener("click", async () => {
  try {
    if (!currentConversationId) await createConversation(false);
    const response = await fetch("/api/v1/handoffs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: tenantId, customer_id: customerId, conversation_id: currentConversationId, reason: "客户申请转接人工客服" }),
    });
    if (!response.ok) throw new Error("转接失败");
    const ticket = await response.json();
    showToast(`工单 ${ticket.ticket_no} 已进入${ticket.queue}`);
    await loadConversations(false);
  } catch (error) {
    showToast("转人工失败，请稍后重试");
  }
});

async function loadCustomerOrder() {
  try {
    const response = await fetch(`/api/v1/commerce/customers/${customerId}/orders?tenant_id=${tenantId}`);
    if (!response.ok) throw new Error("订单加载失败");
    const orders = await response.json();
    if (!orders.length) throw new Error("暂无订单");
    const order = orders[0];
    const product = order.lines[0];
    const latest = order.logistics[0];
    $("#order-status").textContent = order.status_label;
    $("#order-card").classList.remove("loading");
    $("#order-card").innerHTML = `
      <div class="order-number"><span>${escapeHtml(order.order_no)}</span><em>${escapeHtml(order.status_label)}</em></div>
      <div class="product-row"><div class="product-thumb">耳机</div><div><strong>${escapeHtml(product.product_name)}</strong><small>${escapeHtml(product.specification)} · ×${product.quantity}</small></div><b>¥${order.total_amount.toFixed(2)}</b></div>
      <div class="logistics-row"><i></i><div><strong>${escapeHtml(latest.description)}</strong><small>${escapeHtml(latest.occurred_at)} · ${escapeHtml(order.carrier)}</small></div></div>
      <button class="order-query-button" data-question="我的订单物流到哪了？">查询完整物流</button>`;
    $("#order-card [data-question]").addEventListener("click", (event) => askQuestion(event.currentTarget.dataset.question));
  } catch (error) {
    $("#order-status").textContent = "未连接";
    $("#order-card").textContent = "暂时无法读取订单信息";
  }
}

function renderTrend(daily) {
  const maxValue = Math.max(1, ...daily.map((item) => Math.max(item.messages, item.conversations)));
  $("#trend-chart").innerHTML = daily.map((item) => `
    <div class="trend-column">
      <div class="bars"><i style="height:${Math.max(4, item.messages / maxValue * 130)}px" title="${item.messages} 条消息"></i><b style="height:${Math.max(4, item.conversations / maxValue * 130)}px" title="${item.conversations} 个会话"></b></div>
      <span>${item.date}</span>
    </div>`).join("");
}

function renderAnswerTypes(types) {
  const items = [
    ["订单/物流直答", types.business_fact, "green-type"],
    ["知识库回答", types.knowledge, "blue-type"],
    ["证据不足拒答", types.refusal, "amber-type"],
  ];
  const total = Math.max(1, items.reduce((sum, item) => sum + item[1], 0));
  $("#answer-types").innerHTML = items.map(([label, value, className]) => `
    <div class="type-row"><div><i class="${className}"></i><span>${label}</span><strong>${value}</strong></div><div class="type-progress"><b class="${className}" style="width:${value / total * 100}%"></b></div></div>`).join("");
}

async function loadAnalytics() {
  try {
    const response = await fetch(`/api/v1/analytics/overview?tenant_id=${tenantId}`);
    if (!response.ok) throw new Error("统计加载失败");
    const data = await response.json();
    $("#analytics-conversations").textContent = data.metrics.conversations;
    $("#analytics-resolution").textContent = `${data.metrics.resolution_rate}%`;
    $("#analytics-handoffs").textContent = data.metrics.handoffs;
    $("#analytics-pending").textContent = `${data.metrics.pending} 个待处理`;
    $("#analytics-knowledge").textContent = data.metrics.knowledge;
    renderTrend(data.daily);
    renderAnswerTypes(data.answer_types);
    $("#analytics-tickets").innerHTML = data.recent_handoffs.length ? data.recent_handoffs.map((ticket) => `
      <tr><td>${escapeHtml(ticket.ticket_no)}</td><td>${escapeHtml(ticket.customer_id)}</td><td>${escapeHtml(ticket.queue)}</td><td><span class="priority-${ticket.priority}">${ticket.priority === "high" ? "高" : "普通"}</span></td><td><span class="ticket-status">排队中</span></td><td>${sessionTime(ticket.created_at)}</td></tr>`).join("") : '<tr><td colspan="6" class="analytics-empty">暂无转人工工单</td></tr>';
  } catch (error) {
    showToast("数据分析加载失败");
  }
}

$("#refresh-analytics").addEventListener("click", loadAnalytics);

const ticketStatusLabels = {
  queued: "排队中",
  processing: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

function renderTickets() {
  const keyword = $("#ticket-search").value.trim().toLowerCase();
  const status = $("#ticket-status-filter").value;
  const visible = allTickets.filter((ticket) =>
    (status === "all" || ticket.status === status)
    && `${ticket.ticket_no} ${ticket.customer_id} ${ticket.reason}`.toLowerCase().includes(keyword)
  );
  $("#ticket-queued").textContent = allTickets.filter((item) => item.status === "queued").length;
  $("#ticket-processing").textContent = allTickets.filter((item) => item.status === "processing").length;
  $("#ticket-resolved").textContent = allTickets.filter((item) => item.status === "resolved").length;
  $("#ticket-high").textContent = allTickets.filter((item) => item.priority === "high" && !["resolved", "closed"].includes(item.status)).length;
  $("#ticket-list").innerHTML = visible.length ? visible.map((ticket) => {
    const nextAction = ticket.status === "queued" ? ["受理", "processing"] : ticket.status === "processing" ? ["标记解决", "resolved"] : ticket.status === "resolved" ? ["关闭", "closed"] : null;
    return `<tr>
      <td><strong>${escapeHtml(ticket.ticket_no)}</strong></td><td>${escapeHtml(ticket.customer_id)}</td><td class="ticket-reason">${escapeHtml(ticket.reason)}</td><td>${escapeHtml(ticket.queue)}</td>
      <td><span class="priority-${ticket.priority}">${ticket.priority === "high" ? "高" : "普通"}</span></td><td><span class="work-status status-${ticket.status}">${ticketStatusLabels[ticket.status]}</span></td><td>${sessionTime(ticket.created_at)}</td>
      <td><div class="ticket-actions">${nextAction ? `<button data-ticket-id="${ticket.id}" data-next-status="${nextAction[1]}">${nextAction[0]}</button>` : ""}<button data-open-conversation="${ticket.conversation_id}">查看会话</button></div></td>
    </tr>`;
  }).join("") : '<tr><td colspan="8" class="table-empty">没有符合条件的工单</td></tr>';
}

async function loadTickets() {
  try {
    const response = await fetch(`/api/v1/handoffs?tenant_id=${tenantId}`);
    if (!response.ok) throw new Error("工单加载失败");
    allTickets = await response.json();
    renderTickets();
  } catch (error) {
    $("#ticket-list").innerHTML = '<tr><td colspan="8" class="table-empty">工单加载失败</td></tr>';
  }
}

$("#refresh-tickets").addEventListener("click", loadTickets);
$("#ticket-search").addEventListener("input", renderTickets);
$("#ticket-status-filter").addEventListener("change", renderTickets);
$("#ticket-list").addEventListener("click", async (event) => {
  const action = event.target.closest("[data-ticket-id]");
  const conversationButton = event.target.closest("[data-open-conversation]");
  if (conversationButton) {
    currentConversationId = conversationButton.dataset.openConversation;
    switchPage("chat");
    try { await loadConversationMessages(currentConversationId); } catch (error) { showToast("关联会话加载失败"); }
    return;
  }
  if (!action) return;
  try {
    const response = await fetch(`/api/v1/handoffs/${action.dataset.ticketId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: tenantId, status: action.dataset.nextStatus }),
    });
    if (!response.ok) throw new Error("更新失败");
    showToast(`工单已更新为${ticketStatusLabels[action.dataset.nextStatus]}`);
    await Promise.all([loadTickets(), loadConversations(false)]);
  } catch (error) {
    showToast("工单状态更新失败");
  }
});

function updateCustomerSidebar(customer) {
  $("#profile-avatar").textContent = customer.name.slice(0, 1);
  $("#profile-name").textContent = customer.name;
  $("#profile-membership").textContent = customer.membership;
  $("#profile-id").textContent = customer.id;
  $("#profile-source").textContent = customer.source;
  $("#profile-orders").textContent = `${customer.total_orders} 笔`;
  $("#profile-spent").textContent = `¥ ${customer.total_spent.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`;
  $("#profile-tags").innerHTML = customer.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
}

async function loadActiveCustomer() {
  try {
    const response = await fetch(`/api/v1/customers/${customerId}?tenant_id=${tenantId}`);
    if (!response.ok) return;
    updateCustomerSidebar(await response.json());
  } catch (error) { /* Keep the fallback profile. */ }
}

function renderCustomers() {
  const keyword = $("#customer-search").value.trim().toLowerCase();
  const membership = $("#customer-level-filter").value;
  const visible = allCustomers.filter((customer) =>
    (membership === "all" || customer.membership === membership)
    && `${customer.name} ${customer.id} ${customer.phone}`.toLowerCase().includes(keyword)
  );
  $("#customer-total").textContent = allCustomers.length;
  $("#customer-vip").textContent = allCustomers.filter((item) => ["金卡会员", "黑金会员"].includes(item.membership)).length;
  $("#customer-orders").textContent = allCustomers.reduce((sum, item) => sum + item.total_orders, 0);
  $("#customer-spent").textContent = `¥${allCustomers.reduce((sum, item) => sum + item.total_spent, 0).toLocaleString("zh-CN")}`;
  $("#customer-list").innerHTML = visible.length ? visible.map((customer) => `
    <tr><td><div class="customer-cell"><span>${escapeHtml(customer.name.slice(0, 1))}</span><div><strong>${escapeHtml(customer.name)}</strong><small>${escapeHtml(customer.id)} · ${escapeHtml(customer.phone)}</small></div></div></td>
    <td><span class="member-badge member-${customer.membership}">${escapeHtml(customer.membership)}</span></td><td>${escapeHtml(customer.source)}<small class="cell-sub">${escapeHtml(customer.region)}</small></td><td>${customer.total_orders}</td><td>¥${customer.total_spent.toLocaleString("zh-CN")}</td>
    <td><div class="customer-tags">${customer.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div></td><td><span class="customer-status status-${customer.status}">${customer.status === "active" ? "正常" : customer.status === "inactive" ? "停用" : "黑名单"}</span></td>
    <td><div class="ticket-actions"><button data-view-customer="${customer.id}">查看</button><button data-edit-customer="${customer.id}">编辑</button></div></td></tr>`).join("") : '<tr><td colspan="8" class="table-empty">没有符合条件的客户</td></tr>';
}

async function loadCustomers() {
  try {
    const response = await fetch(`/api/v1/customers?tenant_id=${tenantId}`);
    if (!response.ok) throw new Error("客户加载失败");
    allCustomers = await response.json();
    renderCustomers();
  } catch (error) {
    $("#customer-list").innerHTML = '<tr><td colspan="8" class="table-empty">客户加载失败</td></tr>';
  }
}

function openCustomerModal(customer) {
  editingCustomerId = customer.id;
  $("#customer-modal-title").textContent = `编辑客户 · ${customer.name}`;
  $("#customer-membership").value = customer.membership;
  $("#customer-tags").value = customer.tags.join(", ");
  $("#customer-status").value = customer.status;
  $("#customer-modal").classList.add("open");
  $("#customer-modal").setAttribute("aria-hidden", "false");
}
function closeCustomerModal() {
  $("#customer-modal").classList.remove("open");
  $("#customer-modal").setAttribute("aria-hidden", "true");
  editingCustomerId = null;
}
$$('[data-close-customer]').forEach((item) => item.addEventListener("click", closeCustomerModal));
$("#refresh-customers").addEventListener("click", loadCustomers);
$("#customer-search").addEventListener("input", renderCustomers);
$("#customer-level-filter").addEventListener("change", renderCustomers);
$("#customer-list").addEventListener("click", async (event) => {
  const edit = event.target.closest("[data-edit-customer]");
  const view = event.target.closest("[data-view-customer]");
  if (edit) openCustomerModal(allCustomers.find((item) => item.id === edit.dataset.editCustomer));
  if (view) {
    const customer = allCustomers.find((item) => item.id === view.dataset.viewCustomer);
    customerId = customer.id;
    updateCustomerSidebar(customer);
    switchPage("chat");
    currentConversationId = null;
    await Promise.all([loadConversations(), loadCustomerOrder()]);
    showToast(`已切换到客户 ${customer.name}`);
  }
});
$("#customer-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!editingCustomerId) return;
  const tags = $("#customer-tags").value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
  const response = await fetch(`/api/v1/customers/${editingCustomerId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, membership: $("#customer-membership").value, tags, status: $("#customer-status").value }),
  });
  if (response.ok) {
    const updated = await response.json();
    if (updated.id === customerId) updateCustomerSidebar(updated);
    closeCustomerModal();
    await loadCustomers();
    showToast("客户资料已更新");
  } else {
    showToast("客户资料更新失败");
  }
});

async function loadIdentity() {
  try {
    const response = await fetch("/api/v1/auth/me");
    if (!response.ok) return;
    const identity = await response.json();
    $("#current-user").textContent = identity.display_name.slice(0, 1);
    $("#current-user").title = `${identity.display_name} · ${identity.role} / 点击退出`;
    $("#current-user").dataset.authenticated = "true";
  } catch (error) { /* Authentication can be disabled in development. */ }
}
$("#current-user").addEventListener("click", async () => {
  if (!$("#current-user").dataset.authenticated) return;
  if (!window.confirm("确定退出当前企业账号吗？")) return;
  await fetch("/api/v1/auth/logout", { method: "POST" });
  location.href = "/login";
});

async function loadAuditLogs() {
  try {
    const response = await fetch(`/api/v1/audit-logs?tenant_id=${tenantId}&limit=100`);
    if (!response.ok) throw new Error("无权访问审计日志");
    const logs = await response.json();
    $("#audit-list").innerHTML = logs.length ? logs.map((log) => `<tr><td>${new Date(log.created_at).toLocaleString("zh-CN")}</td><td>${escapeHtml(log.user_id)}</td><td><span class="audit-action">${escapeHtml(log.action)}</span></td><td>${escapeHtml(log.resource)}</td><td><span class="customer-status status-active">${log.result === "success" ? "成功" : "失败"}</span></td><td>${escapeHtml(log.ip_address)}</td></tr>`).join("") : '<tr><td colspan="6" class="table-empty">暂无审计日志</td></tr>';
  } catch (error) {
    $("#audit-list").innerHTML = '<tr><td colspan="6" class="table-empty">仅企业管理员可查看审计日志</td></tr>';
  }
}
$("#refresh-audit").addEventListener("click", loadAuditLogs);

function openModal(document = null) {
  editingDocumentId = document?.id || null;
  $("#modal-title").textContent = document ? "编辑企业知识" : "新建企业知识";
  $("#doc-title").value = document?.title || "";
  $("#doc-content").value = document?.content || "";
  $("#doc-source").value = document?.source || "";
  $("#knowledge-modal").classList.add("open");
  $("#knowledge-modal").setAttribute("aria-hidden", "false");
  $("#doc-title").focus();
}
function closeModal() {
  $("#knowledge-modal").classList.remove("open");
  $("#knowledge-modal").setAttribute("aria-hidden", "true");
  editingDocumentId = null;
}
$("#open-create").addEventListener("click", () => openModal());
$$('[data-close-modal]').forEach((item) => item.addEventListener("click", closeModal));
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });

function renderDocuments(documents) {
  $("#metric-total").textContent = documents.length;
  $("#metric-published").textContent = documents.length;
  $("#document-list").innerHTML = documents.length ? documents.map((item) => `
    <tr>
      <td>${escapeHtml(item.title)}</td>
      <td>${escapeHtml(item.source || "手工录入")}</td>
      <td><span class="status-published">已发布</span></td>
      <td>${escapeHtml(item.content)}</td>
      <td><div class="table-actions"><button class="table-action" data-use-question="${escapeHtml(item.title)}">去提问</button><button class="table-action" data-edit-document="${item.id}">编辑</button><button class="table-action danger" data-delete-document="${item.id}">删除</button></div></td>
    </tr>`).join("") : '<tr><td colspan="5" class="table-empty">暂无知识，请新建第一条企业知识。</td></tr>';
  $$('[data-use-question]').forEach((button) => button.addEventListener("click", () => {
    switchPage("chat");
    questionInput.value = button.dataset.useQuestion;
    questionInput.focus();
  }));
  $$('[data-edit-document]').forEach((button) => button.addEventListener("click", () => {
    openModal(latestDocuments.find((item) => item.id === button.dataset.editDocument));
  }));
  $$('[data-delete-document]').forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm("确定删除这条知识吗？删除后将不再用于客服回答。")) return;
    const response = await fetch(`/api/v1/knowledge/documents/${button.dataset.deleteDocument}?tenant_id=${tenantId}`, { method: "DELETE" });
    if (response.ok) { showToast("知识已删除"); await loadDocuments(); } else { showToast("删除失败"); }
  }));
}

async function loadDocuments() {
  try {
    const response = await fetch(`/api/v1/knowledge/documents?tenant_id=${tenantId}`);
    if (!response.ok) throw new Error("加载失败");
    latestDocuments = await response.json();
    renderDocuments(latestDocuments);
  } catch (error) {
    $("#document-list").innerHTML = '<tr><td colspan="5" class="table-empty">知识库加载失败，请确认服务状态。</td></tr>';
  }
}

$("#knowledge-search").addEventListener("input", (event) => {
  const keyword = event.target.value.trim().toLowerCase();
  renderDocuments(latestDocuments.filter((item) => `${item.title} ${item.content} ${item.source}`.toLowerCase().includes(keyword)));
});
$("#refresh-documents").addEventListener("click", loadDocuments);

$("#knowledge-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#save-document");
  button.disabled = true;
  button.textContent = "正在保存…";
  try {
    const wasEditing = Boolean(editingDocumentId);
    const response = await fetch(wasEditing ? `/api/v1/knowledge/documents/${editingDocumentId}` : "/api/v1/knowledge/documents", {
      method: wasEditing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_id: tenantId,
        title: $("#doc-title").value.trim(),
        content: $("#doc-content").value.trim(),
        source: $("#doc-source").value.trim() || "手工录入",
      }),
    });
    if (!response.ok) throw new Error("保存失败");
    event.target.reset();
    closeModal();
    showToast(wasEditing ? "知识已更新" : "知识已保存并发布");
    await loadDocuments();
  } catch (error) {
    showToast("保存失败，请检查填写内容");
  } finally {
    button.disabled = false;
    button.textContent = "保存并发布";
  }
});

loadModelStatus();
loadCustomerOrder();
loadConversations();
loadActiveCustomer();
loadIdentity();
