const state = {
  events: [],
  policies: [],
  backends: [],
  assignments: [],
  integrations: null,
  selectedEventId: null,
  selectedAssignmentId: null,
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
};

const post = (path, payload = {}) =>
  api(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });

const byId = (id) => document.getElementById(id);

function tags(tags) {
  return tags.map((tag) => `<span class="pill muted-pill">${tag}</span>`).join(" ");
}

function linkOrDash(url, label) {
  return url ? `<a href="${url}" target="_blank" rel="noreferrer">${label}</a>` : "-";
}

function renderHealth(health) {
  byId("health").innerHTML = `
    <strong>${health.service}</strong><br />
    <span>${health.ok ? "healthy" : "unhealthy"}</span><br />
    <span>${health.chatassign_home}</span>
  `;
}

function renderEvents() {
  byId("events").innerHTML = state.events
    .map((event) => {
      const selected = event.event_id === state.selectedEventId ? " selected" : "";
      return `
        <button class="item${selected}" data-event="${event.event_id}">
          <h4>${event.title}</h4>
          <div class="meta">${event.event_id} · ${event.source}/${event.kind} · ${event.occurred_at}</div>
          <div>${tags(event.tags)}</div>
          <div class="meta">${event.excerpt}</div>
        </button>
      `;
    })
    .join("");
  document.querySelectorAll("[data-event]").forEach((node) => {
    node.addEventListener("click", () => {
      state.selectedEventId = node.dataset.event;
      const assignment = state.assignments.find((item) => item.source_event.event_id === state.selectedEventId);
      state.selectedAssignmentId = assignment?.assignment_id || null;
      renderAll();
    });
  });
}

function selectedEvent() {
  return state.events.find((event) => event.event_id === state.selectedEventId) || state.events[0];
}

function selectedAssignment() {
  return state.assignments.find((assignment) => assignment.assignment_id === state.selectedAssignmentId);
}

function renderReview() {
  const event = selectedEvent();
  if (!state.selectedEventId && event) state.selectedEventId = event.event_id;
  const assignment = selectedAssignment() || state.assignments.find((item) => item.source_event.event_id === event?.event_id);
  byId("selected-event-pill").textContent = event ? event.event_id : "No event";

  if (!event) {
    byId("review-content").className = "empty";
    byId("review-content").textContent = "No candidate events.";
    return;
  }

  const review = assignment?.review || {
    actionable: event.source === "voice" && event.tags.includes("thought"),
    reason: "Ready to create an assignment and run reviewer stub.",
    proposed_task: { title: event.title, brief: "Create an assignment from this event.", acceptance: [] },
    risks: ["Assignment has not been persisted yet."],
    questions: ["Create an assignment now?"],
  };

  byId("review-content").className = "review-block";
  byId("review-content").innerHTML = `
    <div class="item">
      <h4>${event.title}</h4>
      <div class="meta">${event.event_id} · source=${event.source} · kind=${event.kind}</div>
      <div>${tags(event.tags)}</div>
      <p>${event.excerpt}</p>
    </div>
    <div class="item">
      <h4>Reviewer Output</h4>
      <p><strong>Actionable:</strong> ${review.actionable}</p>
      <p>${review.reason}</p>
      <p><strong>Proposed task:</strong> ${review.proposed_task?.brief || "-"}</p>
      <p><strong>Risks</strong></p>
      <ul>${(review.risks || []).map((risk) => `<li>${risk}</li>`).join("")}</ul>
      <p><strong>Questions</strong></p>
      <ul>${(review.questions || []).map((question) => `<li>${question}</li>`).join("")}</ul>
    </div>
  `;
}

function renderPolicies() {
  byId("policies").innerHTML = state.policies
    .map(
      (policy) => `
      <div class="item">
        <h4>${policy.name}</h4>
        <div class="meta">${policy.policy_id}</div>
        <p>${policy.rule}</p>
        <p><strong>Mode:</strong> ${policy.mode}</p>
        <div>${policy.available_modes.map((mode) => `<span class="pill muted-pill">${mode}</span>`).join(" ")}</div>
      </div>
    `,
    )
    .join("");
}

function renderBackends() {
  byId("backends").innerHTML = state.backends
    .map(
      (backend) => `
      <div class="item">
        <h4>${backend.name}</h4>
        <div class="meta">${backend.backend_id} · ${backend.status}</div>
        <p><strong>Capabilities:</strong> ${Object.entries(backend.capabilities)
          .filter((entry) => entry[1])
          .map((entry) => entry[0])
          .join(", ")}</p>
        <p><strong>Executors:</strong> ${backend.executors.map((executor) => executor.label).join(", ")}</p>
      </div>
    `,
    )
    .join("");
}

function renderIntegrations() {
  const data = state.integrations || {};
  const resolver = data.resolver || {};
  byId("resolver-pill").textContent = resolver.enabled ? "resolver on" : "resolver off";
  byId("integrations").innerHTML = `
    <div class="item">
      <h4>ChatEvent</h4>
      <p>${data.chatevent?.status || "-"} · ${data.chatevent?.profile || "-"}</p>
      <div class="meta">${data.chatevent?.candidate_source || ""}</div>
    </div>
    <div class="item">
      <h4>ChatBoard Backend</h4>
      <p>${data.chatboard?.status || "-"} · ${data.chatboard?.profile || "-"}</p>
      <div class="meta">${data.chatboard?.adapter || ""}</div>
    </div>
    <div class="item">
      <h4>User Channel</h4>
      <p>${data.user_channel?.status || "-"} · ${data.user_channel?.profile || "-"}</p>
      <div class="meta">Adapter/profile reference only; core does not hardcode Zulip.</div>
    </div>
    <div class="item">
      <h4>Local-to-Public Resolver</h4>
      <p>${resolver.enabled ? "Enabled" : "Configured but inactive"} · ${resolver.kind || "-"}</p>
      <div class="meta">Local root: ${resolver.local_root || "-"}</div>
      <div class="meta">Public base configured: ${resolver.public_base_url_configured ? "yes" : "no"}</div>
      <div class="meta">${resolver.note || ""}</div>
    </div>
  `;
}

function renderAssignments() {
  byId("assignment-count").textContent = String(state.assignments.length);
  if (!state.assignments.length) {
    byId("assignments").innerHTML = '<div class="empty">No assignments yet.</div>';
    byId("assignment-detail").innerHTML = '<div class="empty">Create an assignment to inspect timeline, draft, watch, and links.</div>';
    return;
  }
  byId("assignments").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Assignment</th>
          <th>Status</th>
          <th>Source Event</th>
          <th>Policy</th>
          <th>Watch</th>
          <th>Links</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        ${state.assignments
          .map((assignment) => {
            const selected = assignment.assignment_id === state.selectedAssignmentId ? " class=\"selected-row\"" : "";
            const links = assignment.links || {};
            return `
              <tr${selected} data-assignment="${assignment.assignment_id}">
                <td><strong>${assignment.assignment_id}</strong><br /><span class="meta">${assignment.title}</span></td>
                <td class="status">${assignment.state || assignment.status}</td>
                <td>${assignment.source_event.event_id}<br /><span class="meta">${assignment.source_event.source}/${assignment.source_event.kind}</span></td>
                <td>${assignment.policy_id}</td>
                <td>${assignment.watch?.state || "-"}<br /><span class="meta">${assignment.watch?.interval_seconds || "-"}s / ttl ${assignment.watch?.ttl_seconds || "-"}</span></td>
                <td>${linkOrDash(links.assignment_url, "assignment")} ${linkOrDash(links.task_url, "task")} ${linkOrDash(links.prd_url, "PRD")} ${linkOrDash(links.run_url, "run")}</td>
                <td>
                  <div class="button-row">
                    <button data-reply="${assignment.assignment_id}">Reply</button>
                    <button data-confirm="${assignment.assignment_id}">Confirm</button>
                    <button data-progress="${assignment.assignment_id}">Progress</button>
                    <button id="mark-done" data-done="${assignment.assignment_id}">Complete</button>
                  </div>
                </td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
  document.querySelectorAll("[data-assignment]").forEach((node) => {
    node.addEventListener("click", () => {
      state.selectedAssignmentId = node.dataset.assignment;
      renderAll();
    });
  });
  document.querySelectorAll("[data-reply]").forEach((node) => {
    node.addEventListener("click", async () => {
      await post(`/api/assignments/${node.dataset.reply}/reply`, {
        content: "Prioritize service-backed ChatAssign ingestion, keep Event payload metadata-only, and wait for confirmation before ChatBoard creation.",
      });
      await load();
    });
  });
  document.querySelectorAll("[data-confirm]").forEach((node) => {
    node.addEventListener("click", async () => {
      await post(`/api/assignments/${node.dataset.confirm}/confirm`, { content: "Confirmed. Create the ChatBoard task and start the safe mock run." });
      await load();
    });
  });
  document.querySelectorAll("[data-progress]").forEach((node) => {
    node.addEventListener("click", async () => {
      await post(`/api/assignments/${node.dataset.progress}/progress`, { content: "What is the current progress on this assignment?" });
      await load();
    });
  });
  document.querySelectorAll("[data-done]").forEach((node) => {
    node.addEventListener("click", async () => {
      await post(`/api/assignments/${node.dataset.done}/complete`, { status: "completed" });
      await load();
    });
  });
  renderAssignmentDetail();
}

function renderAssignmentDetail() {
  const assignment = selectedAssignment() || state.assignments[0];
  if (!assignment) return;
  state.selectedAssignmentId = assignment.assignment_id;
  const links = assignment.links || {};
  const draft = assignment.draft || {};
  const watch = assignment.watch || {};
  const timeline = assignment.timeline || [];
  byId("assignment-detail").innerHTML = `
    <div class="detail-grid">
      <div class="item">
        <h4>Draft / Confirmation</h4>
        <p><strong>State:</strong> ${assignment.state || assignment.status}</p>
        <p><strong>Draft v${draft.version || 1}:</strong> ${draft.summary || "-"}</p>
        <p><strong>Confirmation required:</strong> ${draft.confirmation_required !== false}</p>
      </div>
      <div class="item">
        <h4>Thread Watch</h4>
        <p><strong>${watch.watch_id || "-"}</strong> · ${watch.state || "-"}</p>
        <p>${assignment.zulip_thread?.stream || "-"} / ${assignment.zulip_thread?.topic || "-"}</p>
        <div class="meta">${watch.filter_boundary || watch.contract || ""}</div>
      </div>
      <div class="item">
        <h4>Link Panel</h4>
        <p>${linkOrDash(links.assignment_url, "Assignment")} ${linkOrDash(links.thread_url, "Thread")}</p>
        <p>${linkOrDash(links.task_url, "Task")} ${linkOrDash(links.prd_url, "PRD")} ${linkOrDash(links.run_url, "Run")}</p>
      </div>
    </div>
    <div class="timeline">
      ${timeline
        .map(
          (item) => `
            <div class="timeline-row">
              <span class="timeline-dot"></span>
              <div>
                <div><strong>${item.title}</strong> <span class="meta">${item.kind} · ${item.at}</span></div>
                <div class="meta">${item.detail || ""}</div>
              </div>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderAll() {
  renderEvents();
  renderReview();
  renderPolicies();
  renderBackends();
  renderIntegrations();
  renderAssignments();
}

async function load() {
  const [health, events, policies, backends, assignments, integrations] = await Promise.all([
    api("/api/health"),
    api("/api/events/candidates"),
    api("/api/policies"),
    api("/api/backends"),
    api("/api/assignments"),
    api("/api/integrations"),
  ]);
  state.events = events.events;
  state.policies = policies.policies;
  state.backends = backends.backends;
  state.assignments = assignments.assignments;
  state.integrations = integrations;
  if (!state.selectedEventId && state.events[0]) state.selectedEventId = state.events[0].event_id;
  renderHealth(health);
  renderAll();
}

document.querySelectorAll(".nav").forEach((node) => {
  node.addEventListener("click", () => {
    document.querySelectorAll(".nav").forEach((item) => item.classList.remove("active"));
    node.classList.add("active");
    const titles = {
      inbox: ["Inbox", "Candidate ChatEvent items ready for policy review."],
      review: ["Review", "Reviewer output, task proposal, risks, and questions."],
      policies: ["Policies", "Policy modes and default routing rules."],
      routing: ["Routing / Backends", "ChatBoard backend and executor capability view."],
      assignments: ["Assignments / Runs", "Lifecycle, provenance, run/session refs, and paths."],
      integrations: ["Integrations", "ChatEvent, ChatBoard, user-channel, and resolver status."],
    };
    byId("view-title").textContent = titles[node.dataset.view][0];
    byId("view-subtitle").textContent = titles[node.dataset.view][1];
  });
});

byId("refresh").addEventListener("click", load);

byId("create-assignment").addEventListener("click", async () => {
  const event = selectedEvent();
  if (!event) return;
  const assignment = await post("/api/assignments", {
    event_id: event.event_id,
    policy_id: "voice-thought",
    backend_id: "local-chatboard-mock",
    executor: "codex",
  });
  state.selectedAssignmentId = assignment.assignment_id;
  await load();
});

byId("rerun-review").addEventListener("click", async () => {
  const assignment = selectedAssignment();
  if (!assignment) return;
  await post(`/api/assignments/${assignment.assignment_id}/review`);
  await load();
});

byId("mark-waiting").addEventListener("click", async () => {
  const assignment = selectedAssignment();
  if (!assignment) return;
  await post(`/api/assignments/${assignment.assignment_id}/status`, { status: "waiting_for_user" });
  await load();
});

byId("reject-assignment").addEventListener("click", async () => {
  const assignment = selectedAssignment();
  if (!assignment) return;
  await post(`/api/assignments/${assignment.assignment_id}/status`, { status: "rejected" });
  await load();
});

load().catch((error) => {
  byId("health").textContent = error.message;
});
