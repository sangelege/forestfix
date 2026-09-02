const state = {
  tasks: [],
  selectedTask: null,
  selectedCandidate: null,
  providers: [],
};

const $ = (selector) => document.querySelector(selector);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return payload;
}

function statusClass(status) {
  if (["accepted", "ready", "applied", "completed", "ok"].includes(status)) return "ok";
  if (["generating", "verifying", "baseline_ready", "created"].includes(status)) return "warn";
  if (["failed", "rejected", "error"].includes(status)) return "bad";
  return "neutral";
}

function statusLabel(status) {
  return status || "unknown";
}

function badge(status) {
  const node = el("span", `badge ${statusClass(status)}`, statusLabel(status));
  return node;
}

function splitValues(value, fallback = []) {
  const text = (value || "").trim();
  if (!text) return fallback;
  return text.split(",").map((part) => part.trim()).filter(Boolean);
}

async function loadRuntime() {
  const data = await api("/providers");
  state.providers = data.providers;
  const badgeNode = $("#execution-badge");
  if (data.execution.docker_available) {
    badgeNode.textContent = "Docker ready";
    badgeNode.className = "badge ok";
  } else if (data.execution.unsafe_local_enabled) {
    badgeNode.textContent = "Local trusted";
    badgeNode.className = "badge warn";
  } else {
    badgeNode.textContent = "No executor";
    badgeNode.className = "badge bad";
  }
  renderProviderChecks();
}

function renderProviderChecks() {
  const container = $("#provider-checks");
  container.replaceChildren();
  for (const provider of state.providers) {
    const label = el("label");
    const input = el("input");
    input.type = "checkbox";
    input.value = provider.name;
    input.checked = provider.available;
    input.disabled = !provider.available;
    label.append(input, document.createTextNode(provider.name));
    if (!provider.available) {
      label.title = "Provider executable not found";
      label.style.opacity = "0.5";
    }
    container.append(label);
  }
}

async function loadTasks(selectTaskId = null) {
  const data = await api("/task-list");
  state.tasks = data.tasks;
  renderTaskList();
  const nextId = selectTaskId || state.selectedTask || (state.tasks[0] && state.tasks[0].task_id);
  if (nextId) {
    selectTask(nextId);
  } else {
    $("#empty-state").classList.remove("hidden");
    $("#task-detail").classList.add("hidden");
  }
}

function renderTaskList() {
  const list = $("#task-list");
  list.replaceChildren();
  for (const task of state.tasks) {
    const item = el("button", "task-item");
    if (task.task_id === state.selectedTask) item.classList.add("selected");
    const top = el("div", "task-item-title");
    top.append(el("strong", "", task.task_id), badge(task.status));
    item.append(top, el("small", "", task.spec.repo_path || ""));
    item.addEventListener("click", () => selectTask(task.task_id));
    list.append(item);
  }
}

async function selectTask(taskId) {
  state.selectedTask = taskId;
  state.selectedCandidate = null;
  renderTaskList();
  $("#empty-state").classList.add("hidden");
  $("#task-detail").classList.remove("hidden");
  const task = await api(`/tasks/${taskId}`);
  $("#detail-task-id").textContent = task.task_id;
  const status = $("#detail-status");
  status.textContent = task.status;
  status.className = `badge ${statusClass(task.status)}`;
  $("#spec-json").textContent = JSON.stringify(task.spec, null, 2);
  $("#baseline-json").textContent = task.baseline
    ? JSON.stringify(task.baseline, null, 2)
    : "No baseline has been recorded.";
  $("#candidate-list").replaceChildren();
  $("#candidate-detail").classList.add("hidden");
  renderCandidates(task.candidates || []);
}

function renderCandidates(candidates) {
  const list = $("#candidate-list");
  list.replaceChildren();
  if (!candidates.length) {
    list.append(el("div", "run-status", "No candidates yet."));
    return;
  }
  for (const candidate of candidates) {
    const item = el("button", "candidate-item");
    const top = el("div", "candidate-item-top");
    top.append(el("strong", "", candidate.candidate_id), badge(candidate.status));
    item.append(top, el("p", "", `${candidate.provider} · ${candidate.summary || "no summary"}`));
    item.addEventListener("click", () => showCandidate(candidate.candidate_id));
    list.append(item);
  }
}

async function showCandidate(candidateId) {
  const candidate = await api(`/candidates/${candidateId}`);
  state.selectedCandidate = candidateId;
  $("#candidate-detail").classList.remove("hidden");
  $("#candidate-id").textContent = candidate.candidate_id;
  $("#candidate-patch").textContent = candidate.patch || "No patch generated.";
  $("#candidate-report").textContent = JSON.stringify(candidate.report || {}, null, 2);
  $("#apply-candidate").disabled = candidate.status !== "accepted";
}

async function runBaseline() {
  const taskId = state.selectedTask;
  if (!taskId) return;
  setRunStatus("正在复现基线...", "warn");
  try {
    const baseline = await api(`/tasks/${taskId}/baseline`, {
      method: "POST",
      body: JSON.stringify({
        execution_mode: $("#execution-mode").value,
        container_image: $("#container-image").value || null,
      }),
    });
    setRunStatus(`基线复现：${baseline.reproduced ? "成功" : "失败"}`, baseline.reproduced ? "ok" : "bad");
    await selectTask(taskId);
  } catch (error) {
    setRunStatus(error.message, "bad");
  }
}

async function runGenerate() {
  const taskId = state.selectedTask;
  if (!taskId) return;
  const providers = [...document.querySelectorAll("#provider-checks input:checked")].map(
    (input) => input.value
  );
  if (!providers.length) {
    setRunStatus("至少选择一个 Provider。", "bad");
    return;
  }
  setRunStatus("生成候选并运行验证，可能需要数分钟...", "warn");
  try {
    const data = await api(`/tasks/${taskId}/generate`, {
      method: "POST",
      body: JSON.stringify({
        providers,
        execution_mode: $("#execution-mode").value,
        container_image: $("#container-image").value || null,
      }),
    });
    const accepted = data.candidates.filter((candidate) => candidate.status === "accepted").length;
    setRunStatus(`完成：${data.candidates.length} 个候选，${accepted} 个通过。`, accepted ? "ok" : "warn");
    await selectTask(taskId);
  } catch (error) {
    setRunStatus(error.message, "bad");
  }
}

async function runManualVerification() {
  const taskId = state.selectedTask;
  if (!taskId) return;
  const candidateId = $("#manual-candidate-id").value.trim() || "manual-candidate";
  const patch = $("#manual-patch").value;
  if (!patch.trim()) {
    setRunStatus("补丁内容不能为空。", "bad");
    return;
  }
  setRunStatus("正在验证手动补丁...", "warn");
  try {
    await api(`/tasks/${taskId}/verify`, {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        patch,
        execution_mode: $("#execution-mode").value,
        container_image: $("#container-image").value || null,
      }),
    });
    setRunStatus("手动补丁验证完成。", "ok");
    await selectTask(taskId);
    const candidates = await api(`/tasks/${taskId}/candidates`);
    const candidate = candidates.candidates.find((item) => item.candidate_id === candidateId);
    if (candidate) {
      await showCandidate(candidateId);
    }
  } catch (error) {
    setRunStatus(error.message, "bad");
  }
}

function setRunStatus(message, kind = "neutral") {
  const node = $("#run-status");
  node.textContent = message;
  node.className = `run-status ${kind}`;
}

function openDialog() {
  $("#task-dialog").showModal();
}

function closeDialog() {
  $("#task-dialog").close();
}

async function createTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const acceptanceLines = data.get("acceptance_commands")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => splitValues(line));
  const payload = {
    task_id: data.get("task_id"),
    repo_path: data.get("repo_path"),
    base_commit: data.get("base_commit"),
    reproduction_command: splitValues(data.get("reproduction_command")),
    acceptance_commands: acceptanceLines,
    allowed_paths: splitValues(data.get("allowed_paths")),
    denied_paths: splitValues(data.get("denied_paths")),
    candidate_count: Number(data.get("candidate_count")),
    timeout_seconds: Number(data.get("timeout_seconds")),
    network_access: data.get("network_access") === "on",
  };
  try {
    await api("/tasks", { method: "POST", body: JSON.stringify(payload) });
    closeDialog();
    form.reset();
    await loadTasks(payload.task_id);
  } catch (error) {
    alert(error.message);
  }
}

async function createDemoTask() {
  try {
    const task = await api("/demo-task", { method: "POST" });
    await loadTasks(task.task_id);
  } catch (error) {
    alert(error.message);
  }
}

async function fillDemoPatch() {
  try {
    const data = await api("/demo-patch");
    $("#manual-patch").value = data.patch;
  } catch (error) {
    setRunStatus(error.message, "bad");
  }
}

async function applyCandidate() {
  const candidateId = state.selectedCandidate;
  if (!candidateId) return;
  try {
    const result = await api(`/candidates/${candidateId}/apply`, { method: "POST" });
    setRunStatus(`已应用到 ${result.branch}`, "ok");
    await selectTask(state.selectedTask);
    await showCandidate(candidateId);
  } catch (error) {
    setRunStatus(error.message, "bad");
  }
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((node) => node.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((node) => node.classList.remove("active"));
      tab.classList.add("active");
      $(`#tab-${tab.dataset.tab}`).classList.add("active");
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  $("#new-task").addEventListener("click", openDialog);
  $("#demo-task").addEventListener("click", createDemoTask);
  $("#close-dialog").addEventListener("click", closeDialog);
  $("#cancel-dialog").addEventListener("click", closeDialog);
  $("#refresh-tasks").addEventListener("click", () => loadTasks());
  $("#task-form").addEventListener("submit", createTask);
  $("#run-baseline").addEventListener("click", runBaseline);
  $("#run-generate").addEventListener("click", runGenerate);
  $("#fill-demo-patch").addEventListener("click", fillDemoPatch);
  $("#verify-manual").addEventListener("click", runManualVerification);
  $("#apply-candidate").addEventListener("click", applyCandidate);
  setupTabs();
  loadRuntime().then(() => loadTasks());
});
