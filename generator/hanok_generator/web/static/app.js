// Design screen: form state, request composition, preview and build status.
// The server resolves and lays out every request; this module computes no geometry.
import { drawElevation, drawNesting, tooltip } from "./preview.js";
import { setupPackages, showHistory, showPackage } from "./packages.js";
import { SIDE, TYPE, describeBuildFailure, describeError, fmt, josa, pair, presetText } from "./messages.js";

const STORE_KEY = "hanok-web.form.v1";
const ERROR_BOXES = ["type", "size", "lattice", "preset", "picture", "stock", "request", "nest"];
const INPUT_IDS = ["size-w", "size-h", "lat-v", "lat-h", "pic-w", "pic-h", "pic-m", "stock-l", "stock-w", "stock-t", "preset"];
const ACTIVE = ["submitting", "queued", "running"];
const STATUS = {
  checking: ["st-wait", "◌ 확인 중"],
  ready: ["st-pre", "◐ 사전 확인 통과 · 도면 검사 전"],
  error: ["st-fail", "✕ 입력 오류"],
  layout: ["st-fail", "✕ 원판 배치 오류"],
  offline: ["st-fail", "✕ 서버에 연결할 수 없음"],
};
const state = {
  meta: null, form: null, note: "",
  preview: null, previewOk: false, previewKey: null, seq: 0, timer: 0, slow: 0, controller: null,
  build: null, tip: null, lastBuilt: null,
};
const $ = (id) => document.getElementById(id);
const text = (value) => (value === undefined || value === null ? "" : String(value));

// ---- Request composition: pure functions, also run under node by tests/test_web.py ----

export function number(value) {
  // Integral input stays an integer (463, not 463.0) so the request matches the example JSON.
  const raw = text(value).trim();
  return /^[+-]?(\d+(\.\d*)?|\.\d+)$/.test(raw) ? Number(raw) : raw;
}

export function key(value) {
  return JSON.stringify(value, (_, v) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
      : v);
}

const presetInfo = (meta, id) => meta.presets.find((p) => p.id === id);

export function formFromRequest(request, meta) {
  const preset = typeof request.preset === "string" ? request.preset : meta.default_preset;
  const basis = "inner_mm" in request ? "inner" : "outer";
  const size = Array.isArray(request[`${basis}_mm`]) ? request[`${basis}_mm`] : [];
  const lattice = Array.isArray(request.lattice_per_leaf) ? request.lattice_per_leaf : [];
  const picture = "picture" in request ? request.picture : presetInfo(meta, preset)?.picture ?? null;
  const stock = Array.isArray(request.stock_mm) ? request.stock_mm : meta.stock_mm;
  const a3 = meta.picture_sizes.A3;
  return {
    type: request.type === "single" ? "single" : "double",
    hinge: request.hinge_side === "right" ? "right" : "left",
    basis,
    size: [text(size[0]), text(size[1])],
    lattice: [text(lattice[0]), text(lattice[1])],
    preset,
    picture: {
      on: picture !== null && picture !== undefined,
      w: text(picture?.size_mm?.[0] ?? a3[0]),
      h: text(picture?.size_mm?.[1] ?? a3[1]),
      margin: text(picture?.margin_mm ?? meta.picture_margin_mm),
    },
    stock: [text(stock[0]), text(stock[1]), text(stock[2])],
  };
}

export function compose(form, meta) {
  // The shape of the hand-written examples: optional keys only when they differ from
  // the defaults, so the same design gives the same package_id as the CLI.
  const request = { type: form.type };
  if (form.type === "single") request.hinge_side = form.hinge;
  request[form.basis === "inner" ? "inner_mm" : "outer_mm"] = form.size.map(number);
  request.lattice_per_leaf = form.lattice.map(number);
  if (form.preset !== meta.default_preset) request.preset = form.preset;
  const picture = form.picture.on
    ? { size_mm: [number(form.picture.w), number(form.picture.h)], margin_mm: number(form.picture.margin) }
    : null;
  if (key(picture) !== key(presetInfo(meta, form.preset)?.picture ?? null)) request.picture = picture;
  const stock = form.stock.map(number);
  if (key(stock) !== key(meta.stock_mm)) request.stock_mm = stock;
  return request;
}

// ---- DOM helpers ----

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value === null || value === undefined) continue;
    if (name === "class") el.className = value;
    else el.setAttribute(name, value === true ? "" : String(value));
  }
  el.append(...children.filter((c) => c !== null && c !== undefined && c !== false));
  return el;
}
const code = (value) => h("code", {}, value);
const radio = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value;
function check(name, value) {
  const el = document.querySelector(`input[name="${name}"][value="${value}"]`);
  if (el) el.checked = true;
}

async function api(method, path, body, signal) {
  const init = { method, signal, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  const data = await response.json().catch(() => null);
  setOffline(false);
  return { status: response.status, body: data };
}

function setOffline(on) {
  $("offline").hidden = !on;
  if (on) setStatus("offline");
}

function setStatus(kind) {
  const [cls, label] = STATUS[kind];
  for (const el of [$("status"), $("dock-status")]) {
    el.classList.remove(...Object.values(STATUS).map(([c]) => c));
    el.classList.add(cls);
    el.textContent = label;
  }
}

// ---- Form ----

function readForm() {
  return {
    type: radio("type") ?? "double",
    hinge: radio("hinge") ?? "left",
    basis: radio("basis") ?? "outer",
    size: [$("size-w").value, $("size-h").value],
    lattice: [$("lat-v").value, $("lat-h").value],
    preset: $("preset").value,
    picture: { on: radio("picture") === "on", w: $("pic-w").value, h: $("pic-h").value, margin: $("pic-m").value },
    stock: [$("stock-l").value, $("stock-w").value, $("stock-t").value],
  };
}

function writeForm(form) {
  check("type", form.type);
  check("hinge", form.hinge);
  check("basis", form.basis);
  check("picture", form.picture.on ? "on" : "off");
  [$("size-w").value, $("size-h").value] = form.size;
  [$("lat-v").value, $("lat-h").value] = form.lattice;
  $("preset").value = form.preset;
  [$("pic-w").value, $("pic-h").value, $("pic-m").value] = [form.picture.w, form.picture.h, form.picture.margin];
  [$("stock-l").value, $("stock-w").value, $("stock-t").value] = form.stock;
}

function save() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(state.form));
  } catch {
    // Storage can be unavailable; the draft simply is not kept.
  }
}

function restore() {
  try {
    const form = JSON.parse(localStorage.getItem(STORE_KEY) ?? "null");
    const strings = (list, n) => Array.isArray(list) && list.length === n && list.every((v) => typeof v === "string");
    if (form && typeof form.type === "string" && typeof form.preset === "string" && strings(form.size, 2)
        && strings(form.lattice, 2) && strings(form.stock, 3) && form.picture && typeof form.picture.on === "boolean") {
      return form;
    }
  } catch {
    // A broken draft falls back to the example.
  }
  return null;
}

function setForm(form) {
  state.form = form;
  state.note = "";
  writeForm(form);
  state.form = readForm();
  save();
  refreshForm();
  runPreview();
}

function onFormInput(event) {
  const target = event.target;
  if (target.name === "basis" && target.value !== state.form.basis) convertBasis(target.value);
  if (target.name === "type" && target.value !== state.form.type) keepPresetValid(target.value);
  const next = readForm();
  if (key(next) === key(state.form)) return; // radios fire both input and change
  state.form = next;
  showNote("");
  save();
  refreshForm();
  schedulePreview();
}

function convertBasis(to) {
  // Keep the same window (D5): take the other basis from the server's last answer for
  // this exact input, else shift by the frame members the server reported in meta.
  const form = state.form;
  const p = state.preview;
  let values = null;
  if (p?.size && state.previewKey === key(compose(form, state.meta))) {
    values = to === "inner" ? p.size.inner_mm : p.size.outer_mm;
  } else {
    const sizes = form.size.map(number);
    const shift = (to === "inner" ? -2 : 2) * state.meta.frame_member_mm;
    if (sizes.every((v) => typeof v === "number")) values = sizes.map((v) => v + shift);
  }
  if (values) [$("size-w").value, $("size-h").value] = values.map((v) => String(Math.round(v * 1e6) / 1e6));
}

function keepPresetValid(type) {
  const info = presetInfo(state.meta, $("preset").value);
  state.note = "";
  if (info && !info.types.includes(type)) {
    const fallback = state.meta.default_preset;
    $("preset").value = fallback;
    state.note = `${josa(TYPE[type], "은", "는")} ${info.id} 프리셋을 쓸 수 없어 ${josa(fallback, "으로", "로")} 바꿨습니다.`;
  }
}

function step(id, delta) {
  const input = $(id);
  const [low, high] = state.meta.limits.lattice;
  const current = Number.parseInt(input.value, 10);
  input.value = String(Math.min(high, Math.max(low, (Number.isFinite(current) ? current : 0) + delta)));
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function refreshForm() {
  const f = state.form;
  const meta = state.meta;
  $("hinge-row").hidden = f.type !== "single";
  for (const option of $("preset").options) option.disabled = !presetInfo(meta, option.value)?.types.includes(f.type);
  for (const id of ["pic-w", "pic-h", "pic-m"]) $(id).disabled = !f.picture.on;
  for (const chip of $("pic-chips").children) {
    const [w, hgt] = meta.picture_sizes[chip.dataset.size];
    chip.disabled = !f.picture.on;
    chip.setAttribute("aria-pressed", String(f.picture.on && number(f.picture.w) === w && number(f.picture.h) === hgt));
  }
  const basis = f.basis === "inner" ? "내경" : "외경";
  $("size-w").setAttribute("aria-label", `${basis} 가로 mm`);
  $("size-h").setAttribute("aria-label", `${basis} 세로 mm`);
  // One-line values shown on collapsed groups (narrow screens) and the stock fold.
  $("cur-type").textContent = f.type === "single" ? `단문 · ${SIDE[f.hinge]} 경첩` : "양문";
  $("cur-size").textContent = `${basis} ${f.size.join(" × ")}`;
  $("cur-lattice").textContent = `${f.lattice[0]} + ${f.lattice[1]}`;
  $("cur-preset").textContent = f.preset;
  $("cur-picture").textContent = f.picture.on ? `${f.picture.w} × ${f.picture.h} · 여유 ${f.picture.margin}` : "없음";
  const thickness = number(f.stock[2]);
  $("cur-stock").textContent = `${f.stock.join(" × ")}${typeof thickness === "number" ? ` · 홈 깊이 ${fmt(thickness / 2)}` : ""}`;
  $("hint-type").textContent = state.note || (f.type === "single"
    ? `${SIDE[f.hinge]} 선대에 경첩을, 반대쪽 선대에 손잡이와 걸쇠를 답니다.`
    : "좌우 창짝의 바깥쪽 선대에 경첩을 답니다.");
  $("hint-type").classList.toggle("note", Boolean(state.note));
  $("hint-preset").textContent = presetText(presetInfo(meta, f.preset));
  renderHints();
  renderBuild();
  updateBuild();
}

function renderHints() {
  const f = state.form;
  const size = state.preview?.size;
  $("hint-size").textContent = f.basis === "inner"
    ? `내경은 고정틀 안쪽 치수(안목)입니다.${size ? ` 외경 ${pair(size.outer_mm)} mm = 내경 + 2 × ${fmt(size.frame_member_mm)}` : ""}`
    : `외경은 완성된 바깥 치수입니다.${size ? ` 내경(고정틀 안목) ${pair(size.inner_mm)} mm` : ""}`;
  const d = state.previewOk ? state.preview.derived : null;
  const bars = d && d.lattice_per_leaf.some(Boolean);
  $("hint-lattice").textContent = !d ? "" : bars ? `빈칸 ${pair(d.lattice_cell)} mm · 교차 ${d.crossings_total}곳` : "창살 없음 · 개구부 전체가 한 칸입니다.";
  $("hint-picture").textContent = d && f.picture.on
    ? `그림 기준영역 ${pair(d.picture_region)} mm · 고정틀 뒤 별도 뒤판에 붙입니다.`
    : "그림은 창짝이 아니라 고정틀 뒤 별도 뒤판에 붙입니다.";
}

// ---- Preview ----

function schedulePreview() {
  clearTimeout(state.timer);
  state.timer = setTimeout(runPreview, 150);
}

async function runPreview() {
  clearTimeout(state.timer);
  const request = compose(state.form, state.meta);
  const requestKey = key(request);
  const seq = ++state.seq;
  state.controller?.abort();
  state.controller = new AbortController();
  clearTimeout(state.slow);
  state.slow = setTimeout(() => seq === state.seq && setStatus("checking"), 200);
  try {
    const { status, body } = await api("POST", "/api/preview", request, state.controller.signal);
    if (seq !== state.seq) return;
    Object.assign(state, { preview: body, previewOk: status === 200, previewKey: requestKey });
    render();
  } catch (error) {
    if (error.name !== "AbortError" && seq === state.seq) setOffline(true);
  } finally {
    if (seq === state.seq) clearTimeout(state.slow);
  }
}

function render() {
  const p = state.preview;
  const ok = state.previewOk;
  clearErrors();
  if (p?.assembly) drawElevation($("panel-elev"), p, { basis: state.form.basis, tip: state.tip });
  else if (!$("panel-elev").querySelector("svg")) $("panel-elev").replaceChildren(h("p", { class: "empty" }, "입력 오류를 고치면 정면도를 그립니다."));
  $("panel-elev").classList.toggle("stale", !p?.assembly);
  if (ok) drawNesting($("panel-nest"), p, { tip: state.tip });
  else if (!$("panel-nest").querySelector("svg")) $("panel-nest").replaceChildren(h("p", { class: "empty" }, "입력 오류를 고치면 원판 배치를 그립니다."));
  $("panel-nest").classList.toggle("stale", !ok);
  $("stale-note").hidden = Boolean(p?.assembly) || !$("panel-elev").querySelector("svg");
  if (!ok) showError(p);
  renderHints();
  renderSummary();
  setStatus(ok ? "ready" : p?.stage === "nesting" ? "layout" : "error");
  renderBuild();
  updateBuild();
}

function clearErrors() {
  for (const name of ERROR_BOXES) {
    $(`err-${name}`).hidden = true;
    $(`err-${name}`).replaceChildren();
  }
  for (const id of INPUT_IDS) $(id).removeAttribute("aria-invalid");
}

function showError(body) {
  const info = describeError(body, { meta: state.meta });
  const box = $(`err-${info.where}`) ?? $("err-request");
  box.replaceChildren(`✕ ${info.text} `, code(info.rule));
  box.hidden = false;
  box.closest("details")?.setAttribute("open", "");
  for (const id of info.inputs) $(id)?.setAttribute("aria-invalid", "true");
  if (body?.stage === "nesting") {
    $("err-nest").replaceChildren(`✕ ${info.text} `, code(info.rule));
    $("err-nest").hidden = false;
  }
}

function packageLinks(id) {
  return h("span", { class: "links" },
    h("a", { href: `#/packages/${id}` }, "패키지 열기"), " · ",
    h("a", { href: `/files/${id}.zip` }, "ZIP 받기"));
}

function renderSummary() {
  const p = state.previewOk ? state.preview : null;
  $("kv").replaceChildren();
  $("meters").replaceChildren();
  $("same").hidden = true;
  if (!p) return;
  const d = p.derived;
  const basis = state.form.basis;
  const rows = [
    [`외경${basis === "outer" ? " (입력)" : ""}`, pair(p.size.outer_mm)],
    [`내경${basis === "inner" ? " (입력)" : ""}`, pair(p.size.inner_mm)],
    ["창짝", `${p.assembly.leaves.length} × ${pair(d.leaf_width_height)}`],
    ["개구부", pair(d.leaf_opening)],
    ["빈칸", pair(d.lattice_cell)],
    ["부품 · 홈", `${d.totals.parts} · ${d.totals.pockets}`],
    ["도그본 · 결합쌍", `${d.totals.reliefs} · ${d.totals.joint_pairs}`],
  ];
  $("kv").append(...rows.flatMap(([term, value]) => [h("dt", {}, term), h("dd", {}, value)]));
  const n = p.nesting;
  $("meters").append(...[["원판 가로 사용", 0], ["원판 세로 사용", 1]].map(([label, i]) => {
    const bar = h("b");
    bar.style.width = `${Math.min(100, (100 * n.used_mm[i]) / n.usable_mm[i])}%`;
    return h("div", { class: "meter" }, `${label} ${fmt(n.used_mm[i])} / ${fmt(n.usable_mm[i])} mm`, h("div", { class: "bar" }, bar));
  }));
  if (p.same_revision.length) {
    const id = p.same_revision[0];
    $("same").replaceChildren("같은 설계(revision 일치) 패키지가 이미 있습니다. ", code(id.slice(0, 8)), " ", packageLinks(id));
    $("same").hidden = false;
  }
}

// ---- Build ----

function updateBuild() {
  const busy = ACTIVE.includes(state.build?.state);
  const current = key(compose(state.form, state.meta));
  const checked = state.previewKey === current;
  const ready = state.previewOk && checked;
  for (const button of [$("build"), $("dock-build")]) button.disabled = busy || !ready;
  $("build-note").textContent = busy
    ? "생성이 끝나면 다시 누를 수 있습니다."
    : ready
      ? "DXF를 저장해 다시 읽고 도면 검사를 모두 통과한 패키지만 저장합니다. 보통 2초 안팎입니다."
      : checked && state.preview ? "입력 오류를 고치면 생성할 수 있습니다." : "사전 확인을 기다리는 중입니다.";
}

async function startBuild() {
  if ($("build").disabled) return;
  const request = compose(state.form, state.meta);
  state.build = { state: "submitting", request, key: key(request) };
  renderBuild();
  updateBuild();
  try {
    const { status, body } = await api("POST", "/api/builds", request);
    if (status === 202) {
      Object.assign(state.build, body);
      setTimeout(poll, 400);
    } else {
      Object.assign(state.build, { state: "rejected", error: body, status });
    }
  } catch {
    Object.assign(state.build, { state: "rejected", error: null, status: 0 });
    setOffline(true);
  }
  renderBuild();
  updateBuild();
}

async function poll() {
  const build = state.build;
  if (!build?.build_id || !ACTIVE.includes(build.state)) return;
  try {
    const { status, body } = await api("GET", `/api/builds/${build.build_id}`);
    if (state.build !== build) return;
    if (status === 200) Object.assign(build, body);
    else build.state = "lost";
  } catch {
    setOffline(true);
  }
  renderBuild();
  updateBuild();
  if (ACTIVE.includes(build.state)) {
    setTimeout(poll, 500);
  } else if (build.state === "passed") {
    state.lastBuilt = build.result.package_id;
    // A build ends on its package screen, unless the user has already gone elsewhere.
    if (currentView() === "design") location.hash = `#/packages/${state.lastBuilt}`;
  }
}

function renderBuild() {
  const card = $("build-card");
  const b = state.build;
  card.hidden = !b;
  if (!b) return;
  const items = [];
  let tone = "";
  if (b.state === "submitting") {
    items.push(h("p", {}, "생성을 요청하는 중입니다."));
  } else if (b.state === "queued") {
    items.push(h("p", {}, h("b", {}, "대기 중"), ` · ${b.position > 1 ? `앞에 ${b.position - 1}개` : "다음 차례"}`));
  } else if (b.state === "running") {
    items.push(h("p", {}, h("b", {}, "생성 중"), ` · ${fmt(b.elapsed_s, 1)}초`),
      h("p", { class: "small" }, "DXF 저장 → 다시 읽어 검사 → 도면 5장 → 봉인"));
  } else if (b.state === "passed") {
    tone = "pass";
    const r = b.result;
    items.push(h("p", {}, h("b", {}, `✓ 검사 ${r.checks}/${r.checks} 통과`), ` · ${fmt(b.elapsed_s, 1)}초`),
      h("p", {}, "패키지 ", code(r.package_id.slice(0, 8)), " ", packageLinks(r.package_id)),
      h("p", { class: "small" }, "명목 CAD 검증까지 끝났습니다. 제작 전 확인 항목은 패키지에 PENDING으로 남습니다."));
  } else if (b.state === "failed") {
    tone = "fail";
    const cell = state.previewOk && state.previewKey === b.key ? state.preview.derived.lattice_cell : null;
    const out = describeBuildFailure(b.error, { cell, relief: state.meta.relief_radius_mm, request: b.request });
    items.push(h("p", {}, h("b", {}, `✕ ${out.title}`), b.elapsed_s ? ` · ${fmt(b.elapsed_s, 1)}초` : ""));
    for (const item of out.items) items.push(h("p", {}, `${item.text} `, code(item.rule)));
    const folder = state.meta.output.split(/[\\/]/).pop();
    items.push(h("p", { class: "small" }, b.error?.failure_report ? `작업 기록 ${folder}/${b.error.failure_report} · ` : "",
      "입력은 그대로 남아 있습니다."));
  } else if (b.state === "rejected") {
    tone = "fail";
    const reason = b.status === 429 || !b.error ? describeError(b.error ?? { rule_id: "build.queue_full" }, {}).text
      : describeError(b.error, { meta: state.meta }).text;
    items.push(h("p", {}, h("b", {}, "✕ 생성을 시작하지 못했습니다")), h("p", {}, b.status === 0 ? "서버에 연결할 수 없습니다." : reason));
  } else if (b.state === "lost") {
    items.push(h("p", {}, "서버가 다시 시작되어 이 생성의 진행 기록이 사라졌습니다. 완료된 패키지는 출력 폴더에 남아 있습니다."));
  }
  if (b.key !== key(compose(state.form, state.meta))) {
    items.push(h("p", { class: "chip" }, ACTIVE.includes(b.state) ? "제출한 순간의 입력으로 생성합니다" : "지금 입력과 다른 설계의 결과입니다"));
  }
  card.className = `buildcard ${tone}`;
  card.replaceChildren(...items);
}

// ---- Screens, notes and JSON files ----

const VIEWS = ["design", "packages", "package"];
const REQUEST_KEYS = ["schema_version", "type", "hinge_side", "outer_mm", "inner_mm", "lattice_per_leaf", "preset", "picture", "stock_mm"];

function currentView() {
  return VIEWS.find((name) => !$(`view-${name}`).hidden) ?? "design";
}

function route() {
  const match = /^#\/packages\/([0-9a-f]{64})$/.exec(location.hash);
  const view = match ? "package" : location.hash === "#/packages" ? "packages" : "design";
  for (const name of VIEWS) $(`view-${name}`).hidden = name !== view;
  $("dock").hidden = view !== "design";
  for (const [id, on] of [["nav-design", view === "design"], ["nav-packages", view !== "design"]]) {
    if (on) $(id).setAttribute("aria-current", "page");
    else $(id).removeAttribute("aria-current");
  }
  document.title = { design: "한옥 창호 생성기", packages: "기록 · 한옥 창호 생성기", package: "패키지 · 한옥 창호 생성기" }[view];
  if (view === "packages") showHistory();
  else if (view === "package") showPackage(match[1]);
  else if (state.preview) render(); // panels drawn while hidden had no width
  if (view !== "design") window.scrollTo(0, 0);
}

function showNote(message) {
  $("note-request").textContent = message;
  $("note-request").hidden = !message;
}

function loadRequest(request, message) {
  setForm(formFromRequest(request, state.meta));
  showNote(message);
  location.hash = "#/design";
}

async function importJson(file) {
  if (!file) return;
  if (file.size > 64 * 1024) {
    showNote("입력 JSON은 64 KiB 이하여야 합니다.");
    return;
  }
  let data;
  try {
    data = JSON.parse(await file.text());
  } catch {
    showNote(`${josa(file.name, "은", "는")} 올바른 JSON이 아닙니다.`);
    return;
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    showNote("입력 JSON은 객체여야 합니다.");
    return;
  }
  // The server checks the values; the form only has to be able to hold them.
  const notes = [`${josa(file.name, "을", "를")} 불러왔습니다.`];
  const ignored = Object.keys(data).filter((k) => !REQUEST_KEYS.includes(k));
  if (ignored.length) notes.push(`알 수 없는 항목 ${ignored.join(", ")}은(는) 무시했습니다.`);
  if ("outer_mm" in data && "inner_mm" in data) notes.push("외경과 내경이 함께 있어 내경을 썼습니다.");
  setForm(formFromRequest(data, state.meta));
  showNote(notes.join(" "));
}

function exportJson() {
  const request = compose(state.form, state.meta);
  const basis = "inner_mm" in request ? "inner" : "outer";
  const name = `hanok_${request.type}_${basis}_${request[`${basis}_mm`].join("x")}_${request.lattice_per_leaf.join("x")}.json`;
  const url = URL.createObjectURL(new Blob([`${JSON.stringify(request, null, 2)}\n`], { type: "application/json" }));
  const link = h("a", { href: url, download: name.replace(/[^\w.-]+/g, "_") });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---- Tabs and start ----

function selectTab(name, focus = false) {
  for (const tab of ["elev", "nest"]) {
    const on = tab === name;
    $(`tab-${tab}`).setAttribute("aria-selected", String(on));
    $(`tab-${tab}`).tabIndex = on ? 0 : -1;
    $(`panel-${tab}`).hidden = !on;
    $(`legend-${tab}`).hidden = !on;
    if (on && focus) $(`tab-${tab}`).focus();
  }
  state.tip?.hide();
  // A hidden panel has no width, so draw it again once its size is known.
  if (name === "nest" && state.previewOk) drawNesting($("panel-nest"), state.preview, { tip: state.tip });
  if (name === "elev" && state.preview?.assembly) {
    drawElevation($("panel-elev"), state.preview, { basis: state.form.basis, tip: state.tip });
  }
}

function bind() {
  const form = $("form");
  form.addEventListener("input", onFormInput);
  form.addEventListener("change", onFormInput);
  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("click", (event) => {
    const stepper = event.target.closest("[data-step]");
    if (stepper) step(stepper.dataset.step, Number(stepper.dataset.delta));
    const chip = event.target.closest("[data-size]");
    if (chip) {
      [$("pic-w").value, $("pic-h").value] = state.meta.picture_sizes[chip.dataset.size].map(String);
      $("pic-w").dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
  for (const id of ["lat-v", "lat-h"]) {
    $(id).addEventListener("keydown", (event) => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      step(id, event.key === "ArrowUp" ? 1 : -1);
    });
  }
  $("reset").addEventListener("click", () => setForm(formFromRequest(state.meta.example, state.meta)));
  $("import").addEventListener("click", () => $("import-file").click());
  $("import-file").addEventListener("change", async (event) => {
    await importJson(event.target.files[0]);
    event.target.value = "";
  });
  $("export").addEventListener("click", exportJson);
  for (const button of [$("build"), $("dock-build")]) button.addEventListener("click", startBuild);
  $("tab-elev").addEventListener("click", () => selectTab("elev"));
  $("tab-nest").addEventListener("click", () => selectTab("nest"));
  $("pv-tabs").addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    selectTab($("tab-elev").getAttribute("aria-selected") === "true" ? "nest" : "elev", true);
  });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      startBuild();
    }
  });
}

async function start() {
  state.tip = tooltip($("preview-pane"), $("tip"));
  try {
    const { status, body } = await api("GET", "/api/meta");
    if (status !== 200) throw new Error(`meta ${status}`);
    state.meta = body;
  } catch {
    setOffline(true);
    return;
  }
  const meta = state.meta;
  $("engine").textContent = `엔진 ${meta.engine_version} · 이 컴퓨터에서만`;
  $("preset").replaceChildren(...meta.presets.map((p) => h("option", { value: p.id }, p.id)));
  $("pic-chips").replaceChildren(...Object.entries(meta.picture_sizes).map(([name, size]) =>
    h("button", { type: "button", "data-size": name, "aria-pressed": "false", title: `${pair(size)} mm` }, name)));
  if (matchMedia("(max-width: 980px)").matches) {
    for (const group of document.querySelectorAll("details.fg")) group.open = false;
  }
  bind();
  setForm(restore() ?? formFromRequest(meta.example, meta));
  setupPackages({ api, h, code, meta, loadRequest, fresh: () => state.lastBuilt });
  window.addEventListener("hashchange", route);
  route();
}

if (typeof document !== "undefined") start();
