let token = "",
  me = null,
  currentPolicy = null;
const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => {
  const x = document.createElement(tag);
  if (text !== undefined) x.textContent = text;
  if (cls) x.className = cls;
  return x;
};
async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    path === "/admin/policy" ? 60000 : 6000,
  );
  try {
    const res = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await res.json();
    if (!res.ok)
      throw Error(
        typeof data.detail === "string"
          ? data.detail
          : "Please check the input and try again.",
      );
    return data;
  } catch (e) {
    if (e.name === "AbortError")
      throw Error("The request is taking too long. Please try again.");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
function tab(name) {
  document
    .querySelectorAll(".pane")
    .forEach((p) => p.classList.toggle("hidden", p.id !== name));
  document
    .querySelectorAll(".tab")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
}
document
  .querySelectorAll(".tab")
  .forEach((b) => (b.onclick = () => tab(b.dataset.tab)));
document.querySelectorAll(".sample").forEach(
  (b) =>
    (b.onclick = () => {
      $("question").value = b.textContent;
      tab("ask");
      $("question").focus();
    }),
);
async function loadPolicy() {
  currentPolicy = await api("/policy");
  $("version").textContent = `Policy v${currentPolicy.version}`;
  $("source-title").textContent = currentPolicy.document;
  $("source-sections").replaceChildren();
  currentPolicy.sections.forEach((s) => {
    const d = el("div", undefined, "source-section");
    d.append(el("h3", s.title), el("p", s.text));
    $("source-sections").append(d);
  });
}
$("login").onclick = async () => {
  $("login").disabled = true;
  try {
    token = "";
    const data = await api("/auth/demo-token", {
      username: $("username").value,
      password: $("password").value,
    });
    token = data.access_token;
    me = await api("/me");
    $("session").textContent = `Signed in as ${me.subject} · ${me.role}`;
    $("company-label").textContent = me.company_name.toUpperCase();
    await loadPolicy();
    $("result").replaceChildren(
      el("p", "Your company policy is ready. Ask a question above.", "muted"),
    );
    $("policy-json").value = "";
  } catch (e) {
    token = "";
    me = null;
    currentPolicy = null;
    $("session").textContent = e.message;
    $("version").textContent = "—";
    $("source-sections").replaceChildren();
    $("result").replaceChildren();
  } finally {
    $("login").disabled = false;
  }
};
$("question-form").onsubmit = async (e) => {
  e.preventDefault();
  if (!token) {
    $("session").textContent = "Please sign in first.";
    return;
  }
  $("submit").disabled = true;
  $("result").replaceChildren(
    el("p", "Checking your current policy…", "muted"),
  );
  try {
    const data = await api("/questions", {
      question: $("question").value,
      retrieval: $("method").value,
    });
    if (data.provider !== "fake" && data.llm_calls > 0) {
      const name = data.provider === "groq" ? "Groq" : "Gemini";
      $("provider").textContent = data.status === "try_again" ? `${name} request failed` : `${name} responded`;
      document.querySelector(".dot").style.background = data.status === "try_again" ? "#b27a22" : "#258160";
    }
    const top = el("div", undefined, "result-top");
    top.append(
      el(
        "span",
        {
          answered: data.answer_style === "policy_excerpt" ? "Policy excerpt" : "Your answer",
          not_covered: "Not covered",
          try_again: "Please try again",
        }[data.status],
        `status ${data.status === "answered" ? "" : "warning"}`,
      ),
      el(
        "span",
        `${me.company_name} · v${data.version ?? "—"}`,
        "result-company",
      ),
    );
    $("result").replaceChildren(top, el("p", data.answer, "answer"));
    if (data.citations.length)
      $("result").append(el("p", "CHECK THE EVIDENCE", "evidence-title"));
    data.citations.forEach((c, i) => {
      const d = el("div", undefined, "citation");
      const heading = el("div", undefined, "citation-heading");
      heading.append(
        el("span", String(i + 1), "citation-number"),
        el("span", c.section),
      );
      d.append(
        heading,
        el("p", c.quote),
        el("small", `${c.document} · Version ${c.version} · § ${c.section_id}`),
      );
      $("result").append(d);
    });
    const metrics = el("div", undefined, "metrics");
    [
      `${data.latency_ms.toFixed(0)} ms total`,
      `${data.retrieval_ms.toFixed(0)} ms retrieval`,
      `${data.llm_calls} / 2 LLM calls`,
      `${data.citations.length} / 3 cited chunks`,
      data.provider === "fake"
        ? "FAKE LLM · offline test mode"
        : `${data.provider === "groq" ? "Groq" : "Gemini"} · real LLM`,
    ].forEach((t) => metrics.append(el("span", t)));
    if (data.status === "try_again" && data.request_id) {
      metrics.append(el("span", `Support reference: ${data.request_id.slice(0, 12)}`));
    }
    $("result").append(metrics);
  } catch (e) {
    $("result").replaceChildren(el("p", e.message, "muted"));
  } finally {
    $("submit").disabled = false;
  }
};
$("load-policy").onclick = async () => {
  try {
    await loadPolicy();
    const draft = structuredClone(currentPolicy);
    draft.version += 1;
    $("policy-json").value = JSON.stringify(draft, null, 2);
  } catch (e) {
    $("publish-message").textContent = e.message;
  }
};
$("publish-policy").onclick = async () => {
  $("publish-policy").disabled = true;
  try {
    const result = await api(
      "/admin/policy",
      JSON.parse($("policy-json").value),
    );
    $("publish-message").textContent =
      `Version ${result.version} is active for ${me.company_name}. New questions now use this version.`;
    await loadPolicy();
  } catch (e) {
    $("publish-message").textContent =
      e instanceof SyntaxError
        ? "The JSON is invalid. Check its syntax and retry."
        : e.message;
  } finally {
    $("publish-policy").disabled = false;
  }
};
api("/health")
  .then((h) => {
    $("provider").textContent =
      h.provider === "fake"
        ? "Fake LLM · offline tests"
        : h.real_llm_configured
          ? `${h.provider === "groq" ? "Groq" : "Gemini"} key set`
          : "API key needed";
  })
  .catch(() => {
    $("provider").textContent = "Service unavailable";
  });
