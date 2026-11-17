"use strict";
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

async function getJSON(u) {
  const r = await fetch(u);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
async function postJSON(u, body) {
  const r = await fetch(u, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

// ---------- tabs ----------
$$(".tabs button").forEach((b) => {
  b.onclick = () => {
    $$(".tabs button").forEach((x) => x.classList.remove("active"));
    $$(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#tab-" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "params") loadParams();
    if (b.dataset.tab === "camera" && typeof pollCamera === "function") pollCamera();
  };
});

// ---------- status ----------
function setCard(id, cm, lv) {
  const el = $("#c-" + id);
  if (!el) return;
  el.className = "card dir " + lv;
  if (cm !== null) el.querySelector(".cm").textContent = Math.round(cm);
  const l = el.querySelector(".lv");
  l.textContent = lv;
  l.className = "lv " + lv;
}

async function pollStatus() {
  try {
    const s = await getJSON("/api/status");
    $("#conn").textContent = "已连接";
    $("#conn").className = "pill ok";
    const d = s.dirs || {};
    if (d.front) setCard("front", d.front.cm, d.front.level);
    if (d.left) setCard("left", d.left.cm, d.left.level);
    if (d.right) setCard("right", d.right.cm, d.right.level);
    setCard("ground", null, s.ground || "CLEAR");
    const w = s.worst || {};
    $("#worst").textContent = (w.dir || "--") + " / " + (w.level || "--");
    $("#amode").textContent = s.audio_mode || "--";
    const cl = $("#cam-level"), cr = $("#cam-ratio");
    if (cl) cl.textContent = s.ground || "--";
    if (cr) cr.textContent = (s.cam_ratio != null ? s.cam_ratio.toFixed(4) : "--");
    renderNav(s.nav);
    const src = s.sources || {};
    for (const k of ["ultra", "lidar", "camera"]) {
      const e = $("#src-" + k);
      if (e) e.className = "dot " + (src[k] ? "on" : "off");
    }
  } catch (e) {
    $("#conn").textContent = "断开";
    $("#conn").className = "pill bad";
  }
}
// ---------- feasible direction / detour ----------
const NAV_LABEL = {
  front: "正前", front_left: "左前", front_right: "右前",
  left: "左", right: "右",
};
const NAV_RECO = {
  forward: "✅ 前方畅通，可直行",
  bear_left: "↖ 请左前方绕行",
  bear_right: "↗ 请右前方绕行",
  turn_left: "⬅ 请向左转",
  turn_right: "➡ 请向右转",
  stop: "🛑 请停下，前方无法通行",
};
function renderNav(nav) {
  const reco = $("#nav-reco"), box = $("#nav-zones");
  if (!reco || !box) return;
  if (!nav) { reco.textContent = "雷达无数据"; box.innerHTML = ""; return; }
  reco.textContent = NAV_RECO[nav.action] || nav.action || "--";
  reco.className = "navreco " + (nav.front_blocked ? "blocked" : "ok");
  const order = ["left", "front_left", "front", "front_right", "right"];
  box.innerHTML = order.map((k) => {
    const z = (nav.zones || {})[k] || {};
    const cls = z.clear ? "nz ok" : "nz bad";
    return `<div class="${cls}"><b>${NAV_LABEL[k]}</b>` +
           `<span>${z.cm != null ? Math.round(z.cm) : "--"}</span></div>`;
  }).join("");
}

// ---------- polar scan (calibration) ----------
const cv = $("#polar");
const cx = cv.getContext("2d");
const CX = 210, CY = 210, RMAX = 195, MAXCM = 400;
const DIRCOL = { front: "#2ea043", left: "#2f81f7", right: "#db6d28" };

function toXY(deg, cm) {
  const r = Math.min(cm, MAXCM) / MAXCM * RMAX;
  const a = (deg - 90) * Math.PI / 180; // 0°朝上
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)];
}

async function pollScan() {
  if (!$("#tab-calib").classList.contains("active")) return;
  let s;
  try { s = await getJSON("/api/scan"); } catch (e) { return; }
  cx.clearRect(0, 0, 420, 420);
  // 网格
  cx.strokeStyle = "#22272e"; cx.fillStyle = "#6e7681"; cx.font = "11px sans-serif";
  for (let i = 1; i <= 4; i++) {
    cx.beginPath(); cx.arc(CX, CY, RMAX * i / 4, 0, 2 * Math.PI); cx.stroke();
    cx.fillText((MAXCM * i / 4) + "cm", CX + 2, CY - RMAX * i / 4 + 12);
  }
  cx.beginPath(); cx.moveTo(CX, CY - RMAX); cx.lineTo(CX, CY + RMAX);
  cx.moveTo(CX - RMAX, CY); cx.lineTo(CX + RMAX, CY); cx.stroke();
  cx.fillText("0°(上)", CX + 4, CY - RMAX + 2);
  // 扇区
  const half = (s.half || 25) * Math.PI / 180;
  const centers = s.centers || {};
  for (const dir in centers) {
    const c = (centers[dir] - 90) * Math.PI / 180;
    cx.beginPath(); cx.moveTo(CX, CY);
    cx.arc(CX, CY, RMAX, c - half, c + half);
    cx.closePath();
    cx.fillStyle = DIRCOL[dir] + "33"; cx.fill();
    const [lx, ly] = toXY(centers[dir], MAXCM * 0.9);
    cx.fillStyle = DIRCOL[dir]; cx.fillText(dir, lx - 10, ly);
  }
  // 点云
  cx.fillStyle = "#e6edf3";
  (s.points || []).forEach(([deg, cm]) => {
    const [x, y] = toXY(deg, cm);
    cx.fillRect(x - 1, y - 1, 2.4, 2.4);
  });
  $("#conn").className = "pill " + (s.alive ? "ok" : "bad");
}

async function calib(dir) {
  const r = await postJSON("/api/calibrate", { dir });
  $("#calib-msg").textContent = r.error
    ? "失败: " + r.error
    : dir + " 已设为 " + JSON.stringify(r.changed);
  syncAngleInputs();
}
async function applyAngles() {
  const p = {
    LIDAR_FRONT_ANGLE_DEG: +$("#ang-front").value,
    LIDAR_LEFT_ANGLE_DEG: +$("#ang-left").value,
    LIDAR_RIGHT_ANGLE_DEG: +$("#ang-right").value,
    LIDAR_SECTOR_HALF_DEG: +$("#ang-half").value,
  };
  const r = await postJSON("/api/params", { params: p });
  $("#calib-msg").textContent = "已应用: " + JSON.stringify(r.changed);
}
async function syncAngleInputs() {
  const p = (await getJSON("/api/params")).params;
  $("#ang-front").value = p.LIDAR_FRONT_ANGLE_DEG;
  $("#ang-left").value = p.LIDAR_LEFT_ANGLE_DEG;
  $("#ang-right").value = p.LIDAR_RIGHT_ANGLE_DEG;
  $("#ang-half").value = p.LIDAR_SECTOR_HALF_DEG;
}
// ---------- params ----------
const GROUPS = [
  ["ULTRA_", "超声波"], ["LIDAR_", "激光雷达"], ["CAM_", "摄像头"],
  ["LEVEL_", "危险分级"], ["TTS_", "语音(TTS)"], ["TONE_", "纯音"],
  ["AUDIO_", "音频"], ["WEB_", "Web"], ["LOOP", "主循环"], ["USE_", "开关"],
  ["", "其它"],
];
let PARAMS = {}, DEFAULTS = {}, RESTART = [];

function groupOf(key) {
  for (const [pre, name] of GROUPS)
    if (pre === "" || key.startsWith(pre)) return name;
  return "其它";
}
function inputFor(key, val) {
  const isObj = typeof val === "object" && val !== null;
  const v = isObj ? JSON.stringify(val, null, 0) : String(val);
  const restart = RESTART.includes(key) ? " restart" : "";
  const tag = isObj
    ? `<textarea data-k="${key}" rows="3">${v}</textarea>`
    : `<input data-k="${key}" value="${escapeHtml(v)}">`;
  return `<div class="pitem${restart}"><label class="k">${key}</label>${tag}</div>`;
}
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

async function loadParams() {
  const r = await getJSON("/api/params");
  PARAMS = r.params; DEFAULTS = r.defaults; RESTART = r.restart_required || [];
  const byGroup = {};
  Object.keys(PARAMS).sort().forEach((k) => {
    const g = groupOf(k);
    (byGroup[g] = byGroup[g] || []).push(k);
  });
  let html = "";
  GROUPS.forEach(([, name]) => {
    if (!byGroup[name]) return;
    html += `<div class="pgroup"><h3>${name}</h3><div class="body">`;
    byGroup[name].forEach((k) => (html += inputFor(k, PARAMS[k])));
    html += `</div></div>`;
  });
  $("#params-groups").innerHTML = html;
  $("#params-groups").querySelectorAll("[data-k]").forEach((el) => {
    el.addEventListener("input", () =>
      el.closest(".pitem").classList.add("changed"));
  });
  syncAngleInputs();
  buildAudioGrid();
  syncSwitches();
  if (typeof buildThresholds === "function") buildThresholds();
}

async function saveParams() {
  const upd = {};
  $("#params-groups").querySelectorAll(".pitem.changed [data-k]").forEach((el) => {
    upd[el.dataset.k] = el.value;
  });
  if (!Object.keys(upd).length) { $("#params-msg").textContent = "无改动"; return; }
  const r = await postJSON("/api/params", { params: upd });
  let msg = "已保存 " + Object.keys(r.changed).length + " 项";
  if (r.restart_required && r.restart_required.length)
    msg += " ⟳需重启: " + r.restart_required.join(", ");
  $("#params-msg").textContent = msg;
  loadParams();
}
async function resetParams() {
  if (!confirm("恢复所有参数为默认值?")) return;
  await postJSON("/api/reset", {});
  $("#params-msg").textContent = "已恢复默认";
  loadParams();
}
async function restartSvc() {
  if (!confirm("重启导盲杖服务? 会短暂中断感知。")) return;
  await postJSON("/api/restart", {});
  $("#params-msg").textContent = "重启中… 稍后刷新页面";
}

// ---------- audio test ----------
function buildAudioGrid() {
  const keys = Object.keys(PARAMS.TTS_PHRASES || {});
  $("#audio-grid").innerHTML = keys.map((k) =>
    `<button onclick="testAudio('${k}')"><b>${k}</b><br>${PARAMS.TTS_PHRASES[k]}</button>`
  ).join("");
}
async function testAudio(key) { await postJSON("/api/audio_test", { key }); }

// ---------- 播报开关面板 ----------
async function setMute(on) {
  await postJSON("/api/params", { params: { AUDIO_MUTE: on } });
  if (PARAMS) PARAMS.AUDIO_MUTE = on;
}
async function setEnable(grp, on) {
  const cur = Object.assign({}, PARAMS.SPEECH_ENABLE || {});
  cur[grp] = on;
  await postJSON("/api/params", { params: { SPEECH_ENABLE: cur } });
  if (PARAMS) PARAMS.SPEECH_ENABLE = cur;
}
function syncSwitches() {
  const m = $("#sw-mute");
  if (m) m.checked = !!PARAMS.AUDIO_MUTE;
  const en = PARAMS.SPEECH_ENABLE || {};
  $$('#tab-audio .sw input[data-grp]').forEach((el) => {
    el.checked = en[el.dataset.grp] !== false;
  });
}
(function initSwitches() {
  const m = $("#sw-mute");
  if (m) m.addEventListener("change", () => setMute(m.checked));
  $$('#tab-audio .sw input[data-grp]').forEach((el) => {
    el.addEventListener("change", () => setEnable(el.dataset.grp, el.checked));
  });
})();

// ---------- vision (识别前方) ----------
async function visionDescribe() {
  const btn = $("#vision-btn"), out = $("#vision-result");
  if (!btn) return;
  btn.disabled = true;
  out.textContent = "识别中…";
  try {
    const r = await postJSON("/api/vision", {});
    if (r.text) out.textContent = "🗣 " + r.text;
    else out.textContent = "未识别: " + (r.error || "无结果");
  } catch (e) {
    out.textContent = "请求失败";
  } finally {
    btn.disabled = false;
  }
}

// ---------- threshold sliders ----------
const TH_DIST = [
  ["LEVEL_DANGER_CM", "危险 DANGER", 10, 150, 1],
  ["LEVEL_WARN_CM", "警告 WARN", 20, 250, 1],
  ["LEVEL_CAUTION_CM", "注意 CAUTION", 40, 350, 1],
  ["NAV_CLEAR_CM", "可通行阈值 NAV_CLEAR", 50, 400, 5],
];
const TH_CAM = [
  ["CAM_EDGE_RATIO_WARN", "提示阈值(边缘密度)", 0.01, 0.2, 0.002],
  ["CAM_EDGE_RATIO_DANGER", "危险阈值(边缘密度)", 0.02, 0.35, 0.002],
  ["CAM_MIN_BLOB_AREA", "最小障碍块(像素)", 100, 5000, 50],
];

function buildSliders(containerSel, defs) {
  const box = $(containerSel);
  if (!box) return;
  box.innerHTML = defs.map(([k, label, min, max, step]) => `
    <div class="throw">
      <label>${label}</label>
      <input type="range" data-k="${k}" min="${min}" max="${max}" step="${step}"
             value="${PARAMS[k]}">
      <span class="val" id="v-${k}">${PARAMS[k]}</span>
    </div>`).join("");
  box.querySelectorAll("input[type=range]").forEach((el) => {
    el.addEventListener("input", () => {
      $("#v-" + el.dataset.k).textContent = el.value;
      scheduleThSave(el.dataset.k, el.value);
    });
  });
}
let thTimer = null, thPend = {};
function scheduleThSave(k, v) {
  thPend[k] = v;
  clearTimeout(thTimer);
  thTimer = setTimeout(async () => {
    const p = thPend; thPend = {};
    await postJSON("/api/params", { params: p });
    for (const kk in p) if (PARAMS[kk] !== undefined) PARAMS[kk] = +p[kk];
  }, 250);
}
function buildThresholds() {
  buildSliders("#th-dist", TH_DIST);
  buildSliders("#th-cam", TH_CAM);
}

// ---------- camera view ----------
let camView = "normal";
$$('input[name="camview"]').forEach((r) => {
  r.addEventListener("change", () => { if (r.checked) camView = r.value; });
});
function pollCamera() {
  if (!$("#tab-camera").classList.contains("active")) return;
  const img = $("#cam-img");
  img.src = "/api/camera.jpg?view=" + camView + "&t=" + Date.now();
}

// ---------- boot ----------
(async () => { await loadParams(); buildThresholds(); })();
setInterval(pollStatus, 400);
setInterval(pollScan, 300);
setInterval(pollCamera, 200);
pollStatus();


