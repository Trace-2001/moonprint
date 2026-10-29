/* 月印 Moonprint · 前端逻辑 */

const $ = (id) => document.getElementById(id);
const CAL_LABEL = { lunar: "阴历", solar: "阳历" };

const state = {
  people: [],
  jobId: null,
  timer: null,
  previewToken: 0,
};

/* ---------------- 工具 ---------------- */

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function maxDay(cal) {
  return cal === "solar" ? 31 : 30;
}

function validPerson(p) {
  const y = Number(p.year), m = Number(p.month), d = Number(p.day);
  if (!(y >= 1900 && y <= 2100)) return false;
  if (!(m >= 1 && m <= 12)) return false;
  return d >= 1 && d <= maxDay(p.calendar);
}

function collectPeople() {
  return state.people
    .map((p) => ({
      name: String(p.name || "").trim(),
      calendar: p.calendar || "lunar",
      year: Number(p.year),
      month: Number(p.month),
      day: Number(p.day),
    }))
    .filter(validPerson);
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({ ok: false, error: "响应解析失败" }));
  if (!data.ok) throw new Error(data.error || "请求失败");
  return data;
}

/* ---------------- 名单编辑 ---------------- */

function newPerson() {
  return { name: "", calendar: "lunar", year: "", month: "", day: "" };
}

function renderPeople() {
  const box = $("people");
  box.innerHTML = "";
  const only = state.people.length <= 1;

  state.people.forEach((p, i) => {
    const row = document.createElement("div");
    row.className = "person";
    row.innerHTML = `
      <input class="nm"  placeholder="名字" value="${esc(p.name)}"  data-i="${i}" data-k="name">
      <select class="cal" data-i="${i}" data-k="calendar">
        <option value="lunar"${p.calendar === "lunar" ? " selected" : ""}>阴历</option>
        <option value="solar"${p.calendar === "solar" ? " selected" : ""}>阳历</option>
      </select>
      <input class="num" placeholder="年" value="${esc(p.year)}"  data-i="${i}" data-k="year">
      <input class="num" placeholder="月" value="${esc(p.month)}" data-i="${i}" data-k="month">
      <input class="num" placeholder="日" value="${esc(p.day)}"   data-i="${i}" data-k="day">
      <button class="del" data-i="${i}" title="删除这一行"${only ? " disabled" : ""}>&times;</button>
    `;
    box.appendChild(row);
  });

  box.querySelectorAll("input").forEach((inp) => {
    inp.addEventListener("input", (e) => {
      const { i, k } = e.target.dataset;
      state.people[+i][k] = e.target.value;
      validateRow(e.target);
      refreshCount();
      schedulePreview();
    });
  });

  box.querySelectorAll("select.cal").forEach((sel) => {
    sel.addEventListener("change", (e) => {
      const { i, k } = e.target.dataset;
      state.people[+i][k] = e.target.value;
      const row = e.target.closest(".person");
      const dayIn = row.querySelector("input.num:last-of-type");
      if (dayIn) {
        dayIn.max = maxDay(e.target.value);
        validateRow(dayIn);
      }
      schedulePreview();
    });
  });

  box.querySelectorAll(".del").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      if (state.people.length <= 1) return;
      state.people.splice(+e.currentTarget.dataset.i, 1);
      renderPeople();
      refreshCount();
      schedulePreview();
    });
  });

  refreshCount();
}

function validateRow(inp) {
  const i = +inp.dataset.i;
  const p = state.people[i];
  const filled = p.year !== "" && p.month !== "" && p.day !== "";
  inp.classList.toggle("bad", filled && !validPerson(p));
}

function refreshCount() {
  const n = collectPeople().length;
  $("countHint").textContent = n ? `已填好 ${n} 人` : "填写完整的生日后会自动计算月相";
}

/* ---------------- 实时天文预览 ---------------- */

let previewTimer = null;

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 350);
}

function renderEmptyHint(msg) {
  document.querySelector("#infoTable tbody").innerHTML =
    `<tr><td colspan="7" class="hint">${esc(msg)}</td></tr>`;
}

async function runPreview() {
  const people = collectPeople();
  if (!people.length) {
    renderEmptyHint("填写完整的生日后，这里会显示对应的公历日期、阴历日期与月相");
    refreshCount();
    return;
  }
  const token = ++state.previewToken;
  try {
    const data = await api("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ people, hour: +$("hour").value }),
    });
    if (token !== state.previewToken) return;
    renderInfoTable(data.people);
    refreshCount();
  } catch (err) {
    if (token !== state.previewToken) return;
    renderEmptyHint(err.message);
  }
}

function renderInfoTable(people) {
  const tbody = document.querySelector("#infoTable tbody");
  tbody.innerHTML = people.map((d) => `
    <tr>
      <td class="nm">${esc(d.name)}</td>
      <td><span class="cal">${esc(CAL_LABEL[d.calendar] || d.calendar)}</span></td>
      <td>${esc(d.gregorian)}</td>
      <td>${esc(d.lunar)}</td>
      <td>${esc(d.phase_name)}</td>
      <td>${d.lit_percent}%</td>
      <td>朝${esc(d.lit_side)}</td>
    </tr>
  `).join("");
}

/* ---------------- 渲染任务 ---------------- */

function setBusy(busy) {
  $("generate").disabled = busy;
  $("progress").hidden = !busy;
  if (busy) $("error").hidden = true;
}

function setProgress(pct, msg) {
  $("barFill").style.width = `${Math.round((pct || 0) * 100)}%`;
  $("progressText").textContent = msg || "";
}

async function generate() {
  const people = collectPeople();
  if (!people.length) {
    $("error").textContent = "请至少填写一个完整的生日（年 1900–2100，月 1–12，日 1–30/31）";
    $("error").hidden = false;
    return;
  }

  setBusy(true);
  setProgress(0, "提交任务…");

  try {
    const data = await api("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        people,
        quality: $("quality").value,
        cols: $("cols").value ? +$("cols").value : null,
        hour: +$("hour").value,
        filename: $("fname").value,
        add_logo: $("addLogo").checked,
        logo: $("logo").value,
      }),
    });
    state.jobId = data.job_id;
    startPolling();
  } catch (err) {
    setBusy(false);
    $("error").textContent = err.message;
    $("error").hidden = false;
  }
}

function startPolling() {
  stopPolling();
  state.timer = setInterval(poll, 600);
}

function stopPolling() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

async function poll() {
  if (!state.jobId) return stopPolling();
  try {
    const j = await api(`/api/job/${state.jobId}`);
    setProgress(j.progress, j.message);

    if (j.status === "done") {
      stopPolling();
      setBusy(false);
      showResult(j);
    } else if (j.status === "error") {
      stopPolling();
      setBusy(false);
      $("error").textContent = j.error || "渲染失败";
      $("error").hidden = false;
    } else if (j.status === "expired") {
      stopPolling();
      setBusy(false);
      $("error").textContent = "任务已过期，请重新生成";
      $("error").hidden = false;
    }
  } catch (err) {
    stopPolling();
    setBusy(false);
    $("error").textContent = err.message;
    $("error").hidden = false;
  }
}

function showResult(job) {
  $("result").hidden = false;
  $("previewImg").src = `/api/job/${state.jobId}/image?t=${Date.now()}`;
  $("fnameTag").textContent = job.filename || "";
  if (job.people) renderInfoTable(job.people);
  // 下载用隐藏 <a download>，不跳转页面，下载后可直接继续改名单/再生成
  $("download").onclick = () => {
    const a = document.createElement("a");
    a.href = `/api/job/${state.jobId}/download`;
    a.download = job.filename || "月相图.png";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };
  setTimeout(() => $("result").scrollIntoView({ behavior: "smooth", block: "start" }), 120);
}

/* ---------------- 启动 ---------------- */

async function init() {
  $("add").addEventListener("click", () => {
    if (state.people.length >= 12) return;
    state.people.push(newPerson());
    renderPeople();
  });

  $("generate").addEventListener("click", generate);
  $("hour").addEventListener("change", schedulePreview);

  // 可选落款：勾选后显示 logo 样式选择，默认不勾选
  $("addLogo").addEventListener("change", () => {
    $("logoRow").hidden = !$("addLogo").checked;
  });

  // 空白启动，不预填任何个人信息
  state.people = [newPerson(), newPerson()];
  renderPeople();
  refreshCount();
}

document.addEventListener("DOMContentLoaded", init);
