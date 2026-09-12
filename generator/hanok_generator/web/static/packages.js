// History and package screens: read-only views of published packages, and the drawing viewer.
import { BASIS, DRAWINGS, PENDING_KO, SIDE, TARGETS, brief, bytes, pair, packageTitle, when } from "./messages.js";

const $ = (id) => document.getElementById(id);
const MAIN_FILES = ["window.dxf", "parts_manifest.csv", "pocket_manifest.csv", "dogbone_manifest.csv",
  "hardware_reference_manifest.csv", "README.txt", "design_request.json", "validation_report.json"];
const viewer = { list: [], index: 0, scale: 1, x: 0, y: 0, drag: null };
let deps = null; // { api, h, code, meta, loadRequest, fresh }
let current = null; // the package shown on the package screen

export function setupPackages(injected) {
  deps = injected;
  $("hist-refresh").addEventListener("click", showHistory);
  $("pkg-use").addEventListener("click", () => {
    if (current) deps.loadRequest(current.request, `패키지 ${current.package_id.slice(0, 8)}의 입력을 불러왔습니다.`);
  });
  $("pkg-verify").addEventListener("click", () => current && verify(current.package_id));
  $("pkg-toggle").addEventListener("click", () => {
    const open = $("pkg-toggle").getAttribute("aria-expanded") !== "true";
    $("pkg-toggle").setAttribute("aria-expanded", String(open));
    $("pkg-toggle").textContent = open ? "검사 전체 접기" : "검사 전체 보기";
    $("pkg-all-wrap").hidden = !open;
  });
  setupViewer();
}

// ---- History ----

export async function showHistory() {
  $("hist-note").textContent = "불러오는 중입니다.";
  let reply;
  try {
    reply = await deps.api("GET", "/api/packages");
  } catch {
    $("hist-note").textContent = "서버에 연결할 수 없습니다.";
    return;
  }
  const { packages, latest } = reply.body;
  $("hist-note").textContent = packages.length ? `패키지 ${packages.length}개 · 최신순 · 출력 폴더 ${deps.meta.output}` : "";
  $("hist-empty").hidden = packages.length > 0;
  $("hist-table").hidden = packages.length === 0;
  $("hist-rows").replaceChildren(...packages.map((s) => historyRow(s, latest)));
}

function historyRow(s, latest) {
  const { h, code } = deps;
  const id = code(s.package_id.slice(0, 8));
  if (s.error) {
    return h("tr", {}, h("td", { class: "num" }, when(s.created).short), h("td", { colspan: "5" }, s.error), h("td", {}, id), h("td"));
  }
  const load = h("button", { type: "button", class: "linkish" }, "불러오기");
  load.addEventListener("click", async () => {
    const { status, body } = await deps.api("GET", `/api/packages/${s.package_id}`);
    if (status === 200) deps.loadRequest(body.request, `패키지 ${s.package_id.slice(0, 8)}의 입력을 불러왔습니다.`);
  });
  return h("tr", {},
    h("td", { class: "num" }, when(s.created).short),
    h("td", {}, s.type === "single" ? `단문 · ${SIDE[s.hinge_side]} 경첩` : "양문"),
    h("td", { class: "num" }, `${BASIS[s.size.basis]} ${pair(s.size.requested_mm)}`),
    h("td", { class: "num" }, s.lattice_per_leaf.join("+")),
    h("td", {}, code(s.preset)),
    h("td", { class: "num" }, `${s.parts} · ${s.pockets}`),
    h("td", {}, id, s.package_id === latest ? h("span", { class: "tag" }, "최신") : null),
    h("td", { class: "act" }, h("a", { href: `#/packages/${s.package_id}` }, "열기"), load));
}

// ---- One package ----

export async function showPackage(id) {
  const { h, code } = deps;
  current = null;
  $("view-package").dataset.id = id;
  $("pkg-body").hidden = true;
  $("pkg-message").hidden = true;
  $("pkg-title").textContent = "패키지를 불러오는 중입니다.";
  let reply;
  try {
    reply = await deps.api("GET", `/api/packages/${id}`);
  } catch {
    reply = { status: 0, body: null };
  }
  if ($("view-package").dataset.id !== id) return; // the user moved on meanwhile
  if (reply.status !== 200) {
    $("pkg-title").textContent = reply.status === 404 ? "없는 패키지입니다" : "패키지를 열 수 없습니다";
    $("pkg-message").textContent = reply.status === 404
      ? "출력 폴더에 이 package_id가 없습니다. 기록 화면에서 다시 고르세요."
      : reply.body?.message ?? "서버에 연결할 수 없습니다.";
    $("pkg-message").hidden = false;
    return;
  }
  const d = reply.body;
  current = d;
  const passed = d.checks.passed === d.checks.total;
  $("pkg-title").textContent = packageTitle(d, deps.meta.picture_sizes);
  $("pkg-badges").replaceChildren(...[
    h("span", { class: `st ${passed ? "st-pass" : "st-fail"}` }, `${passed ? "✓" : "✕"} 검사 ${d.checks.passed}/${d.checks.total} ${passed ? "통과" : "실패"}`),
    h("span", { class: "st st-wait", id: "pkg-integrity" }, "◌ 무결성 확인 중"),
    h("span", { class: "st st-pend" }, "! 제작 확인 전 · PENDING"),
    deps.fresh() === id ? h("span", { class: "st st-pre" }, "방금 생성") : null,
  ].filter(Boolean));
  $("pkg-ids").replaceChildren(...[
    h("span", {}, "패키지 ", h("code", { title: d.package_id }, `${d.package_id.slice(0, 8)}…`)),
    h("span", {}, "revision ", code(d.revision)),
    h("span", {}, `생성 ${when(d.created).long}`),
    d.latest ? h("span", { class: "tag" }, "최신") : null,
  ].filter(Boolean));
  $("pkg-pending").replaceChildren(...d.validation.pending.map((item) => h("li", {}, PENDING_KO[item] ?? item)));
  renderDrawings(d);
  renderFiles(d);
  renderChecks(d);
  $("pkg-request").textContent = JSON.stringify(d.request, null, 2);
  $("pkg-normalized").textContent = JSON.stringify(d.normalized_request, null, 2);
  $("pkg-body").hidden = false;
  verify(id);
}

function renderDrawings(d) {
  const { h } = deps;
  // Small server-made copies on the page; the viewer loads the full drawing.
  const drawings = DRAWINGS.filter(([name]) => d.files.some((f) => f.path === name))
    .map(([name, title]) => ({ src: `/files/${d.package_id}/${name}`, thumb: `/thumbs/${d.package_id}/${name}`, title, size: d.drawings?.[name] }));
  $("pkg-thumbs").replaceChildren(...drawings.map((drawing, i) => {
    const img = h("img", { src: drawing.thumb, alt: `${drawing.title} 도면`, loading: "lazy", decoding: "async" });
    const button = h("button", { type: "button", class: "thumb", "aria-label": `${drawing.title} 크게 보기` },
      img, h("span", { class: "cap" }, h("b", {}, drawing.title), h("span", {}, drawing.size ? `${drawing.size[0]} × ${drawing.size[1]} px` : "")));
    button.addEventListener("click", () => openViewer(drawings, i));
    return button;
  }));
}

function renderFiles(d) {
  const { h, code } = deps;
  const row = (f) => h("li", {}, h("a", { href: `/files/${d.package_id}/${f.path}` }, code(f.path)), h("span", {}, bytes(f.bytes)));
  const total = d.files.reduce((sum, f) => sum + f.bytes, 0) + d.manifest_bytes;
  const main = MAIN_FILES.map((name) => d.files.find((f) => f.path === name)).filter(Boolean);
  const rest = [...d.files.filter((f) => !MAIN_FILES.includes(f.path)), { path: "package_manifest.json", bytes: d.manifest_bytes }];
  $("pkg-files").replaceChildren(
    h("li", { class: "dl-zip" }, h("a", { href: `/files/${d.package_id}.zip` }, h("b", {}, "전체 ZIP")),
      h("span", {}, `파일 ${d.files.length + 1}개 · ${bytes(total)}`)),
    ...main.map(row),
    h("li", { class: "more" }, h("details", {}, h("summary", {}, `나머지 파일 ${rest.length}개 (도면 PNG, 부품표 원본, 소스)`),
      h("ul", { class: "dl" }, ...rest.map(row)))));
}

function renderChecks(d) {
  const { h, code } = deps;
  const groups = new Map();
  for (const check of d.validation.checks) {
    const target = check.targets?.[0] ?? "other";
    const group = groups.get(target) ?? { total: 0, passed: 0 };
    group.total += 1;
    group.passed += check.status === "PASS" ? 1 : 0;
    groups.set(target, group);
  }
  const pill = (passed, total) => h("span", { class: `st ${passed === total ? "st-pass" : "st-fail"}` },
    `${passed === total ? "✓" : "✕"} ${passed}/${total} 통과`);
  $("h-checks").textContent = `검사 ${d.validation.checks.length}개 · 대상별`;
  $("pkg-groups").replaceChildren(...[...groups].map(([target, g]) => h("tr", {},
    h("td", {}, TARGETS[target] ?? target), h("td", {}, code(target)), h("td", { class: "num" }, String(g.total)),
    h("td", {}, pill(g.passed, g.total)))));
  $("pkg-all").replaceChildren(...d.validation.checks.map((c) => h("tr", {},
    h("td", {}, code(c.rule_id), h("div", { class: "small" }, c.message ?? "")),
    h("td", { class: "num" }, brief(c.expected)), h("td", { class: "num" }, brief(c.actual)),
    h("td", {}, h("span", { class: `st ${c.status === "PASS" ? "st-pass" : "st-fail"}` }, c.status)))));
  $("pkg-toggle").setAttribute("aria-expanded", "false");
  $("pkg-toggle").textContent = "검사 전체 보기";
  $("pkg-all-wrap").hidden = true;
}

async function verify(id) {
  const badge = $("pkg-integrity");
  if (!badge) return;
  badge.className = "st st-wait";
  badge.textContent = "◌ 무결성 확인 중";
  let reply;
  try {
    reply = await deps.api("GET", `/api/packages/${id}/verify`);
  } catch {
    reply = { status: 0, body: null };
  }
  if ($("view-package").dataset.id !== id) return;
  const ok = reply.status === 200 && reply.body?.status === "PASS";
  badge.className = `st ${ok ? "st-pass" : "st-fail"}`;
  badge.textContent = ok ? `✓ 무결성 확인 · 파일 ${reply.body.files}` : `✕ 무결성 불일치${reply.body?.message ? ` · ${reply.body.message}` : ""}`;
}

// ---- Drawing viewer: pan by dragging, zoom with the wheel, buttons or keys ----

function setupViewer() {
  const stage = $("viewer-stage");
  const img = $("viewer-img");
  img.addEventListener("load", fit);
  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoom(event.deltaY < 0 ? 1.2 : 1 / 1.2, event.clientX, event.clientY);
  }, { passive: false });
  stage.addEventListener("pointerdown", (event) => {
    viewer.drag = { x: event.clientX - viewer.x, y: event.clientY - viewer.y };
    stage.setPointerCapture(event.pointerId);
    stage.classList.add("grabbing");
  });
  stage.addEventListener("pointermove", (event) => {
    if (!viewer.drag) return;
    viewer.x = event.clientX - viewer.drag.x;
    viewer.y = event.clientY - viewer.drag.y;
    apply();
  });
  const release = () => {
    viewer.drag = null;
    stage.classList.remove("grabbing");
  };
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);
  stage.addEventListener("dblclick", (event) => (viewer.scale < 0.999 ? zoomTo(1, event.clientX, event.clientY) : fit()));
  $("viewer-bar").addEventListener("click", (event) => {
    const action = event.target.closest("[data-zoom]")?.dataset.zoom;
    if (action === "in") zoom(1.25);
    else if (action === "out") zoom(0.8);
    else if (action === "fit") fit();
    else if (action === "actual") zoomTo(1);
  });
  $("viewer-prev").addEventListener("click", () => show(viewer.index - 1));
  $("viewer-next").addEventListener("click", () => show(viewer.index + 1));
  $("viewer-close").addEventListener("click", () => $("viewer").close());
  $("viewer").addEventListener("keydown", (event) => {
    const pan = { ArrowLeft: [80, 0], ArrowRight: [-80, 0], ArrowUp: [0, 80], ArrowDown: [0, -80] }[event.key];
    if (pan) {
      viewer.x += pan[0];
      viewer.y += pan[1];
      apply();
    } else if (event.key === "+" || event.key === "=") zoom(1.25);
    else if (event.key === "-") zoom(0.8);
    else if (event.key === "0") fit();
    else if (event.key === "1") zoomTo(1);
    else if (event.key === "[") show(viewer.index - 1);
    else if (event.key === "]") show(viewer.index + 1);
    else return;
    event.preventDefault();
  });
}

export function openViewer(list, index) {
  viewer.list = list;
  $("viewer").showModal();
  show(index);
}

function show(index) {
  const count = viewer.list.length;
  viewer.index = ((index % count) + count) % count;
  const item = viewer.list[viewer.index];
  $("viewer-title").textContent = `${item.title} · ${viewer.index + 1}/${count}`;
  $("viewer-open").href = item.src;
  $("viewer-img").alt = `${item.title} 도면`;
  $("viewer-img").src = item.src;
  if ($("viewer-img").complete) fit();
}

function fit() {
  const img = $("viewer-img");
  const box = $("viewer-stage").getBoundingClientRect();
  if (!img.naturalWidth || !box.width) return;
  viewer.scale = Math.min(box.width / img.naturalWidth, box.height / img.naturalHeight);
  viewer.x = (box.width - img.naturalWidth * viewer.scale) / 2;
  viewer.y = (box.height - img.naturalHeight * viewer.scale) / 2;
  apply();
}

function zoomTo(scale, clientX, clientY) {
  zoom(scale / viewer.scale, clientX, clientY);
}

function zoom(factor, clientX, clientY) {
  const box = $("viewer-stage").getBoundingClientRect();
  const px = (clientX ?? box.left + box.width / 2) - box.left;
  const py = (clientY ?? box.top + box.height / 2) - box.top;
  const next = Math.min(4, Math.max(0.02, viewer.scale * factor));
  // Keep the image point under the cursor fixed while the scale changes.
  viewer.x = px - ((px - viewer.x) * next) / viewer.scale;
  viewer.y = py - ((py - viewer.y) * next) / viewer.scale;
  viewer.scale = next;
  apply();
}

function apply() {
  $("viewer-img").style.transform = `translate(${viewer.x}px, ${viewer.y}px) scale(${viewer.scale})`;
  $("viewer-zoom").textContent = `${Math.round(viewer.scale * 100)}%`;
}
