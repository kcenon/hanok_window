// Korean wording for the page. Values in messages come from the server's `details`,
// and the rule id stays visible so every message traces back to an engine rule.

export const KIND = { F01: "고정틀 선대", F02: "고정틀 가로대", S01: "창짝 선대", S02: "창짝 가로대", L01: "세로 창살", L02: "가로 창살",
  B01: "뒤틀 선대", B02: "뒤틀 가로대" };
export const GROUP = { FIXED: "고정틀", LEFT_LEAF: "왼쪽 창짝", RIGHT_LEAF: "오른쪽 창짝", LEAF_1: "창짝" };
export const TYPE = { double: "양문", single: "단문" };
export const SIDE = { left: "왼쪽", right: "오른쪽" };
export const BASIS = { outer: "외경", inner: "내경", artwork: "화판" };

export function fmt(value, digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);
  const text = value.toFixed(digits).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  return text === "-0" ? "0" : text.replace("-", "−");
}

export function pair(values, digits = 2) {
  return Array.isArray(values) ? values.map((v) => fmt(v, digits)).join(" × ") : String(values ?? "");
}

// A Korean particle depends on whether the word before it ends in a final consonant;
// digits are read as Sino-Korean numbers (1 일, 2 이, 3 삼 …).
const DIGIT_FINAL = { 0: "ㅇ", 1: "ㄹ", 2: "", 3: "ㅁ", 4: "", 5: "", 6: "ㄱ", 7: "ㄹ", 8: "ㄹ", 9: "" };
export function josa(word, withFinal, withoutFinal) {
  const last = String(word).trim().slice(-1);
  const code = last.charCodeAt(0);
  let final = "";
  if (code >= 0xac00 && code <= 0xd7a3) {
    const index = (code - 0xac00) % 28;
    final = index === 8 ? "ㄹ" : index ? "x" : "";
  } else if (last in DIGIT_FINAL) {
    final = DIGIT_FINAL[last];
  } else if (/[lmnr]/i.test(last)) {
    final = "x";
  }
  if (withFinal === "으로") return word + (final && final !== "ㄹ" ? "으로" : "로");
  return word + (final ? withFinal : withoutFinal);
}

const FIELD_LABELS = {
  outer_mm: "외경", "outer_mm[0]": "외경 가로", "outer_mm[1]": "외경 세로",
  inner_mm: "내경", "inner_mm[0]": "내경 가로", "inner_mm[1]": "내경 세로",
  lattice_per_leaf: "창살 수", "lattice_per_leaf[0]": "세로 창살 수", "lattice_per_leaf[1]": "가로 창살 수",
  "picture.size_mm": "그림 크기", "picture.size_mm[0]": "그림 가로", "picture.size_mm[1]": "그림 세로",
  "picture.margin_mm": "그림 여유", stock_mm: "원판", "stock_mm[0]": "원판 길이", "stock_mm[1]": "원판 폭",
  "stock_mm[2]": "원판 두께",
  artwork: "화판", "artwork.size_mm": "화판 크기", "artwork.size_mm[0]": "화판 가로",
  "artwork.size_mm[1]": "화판 세로", "artwork.thickness_mm": "화판 두께", "artwork.cover_mm": "덮는 폭",
  "artwork.fit_mm": "끼움 여유", "artwork.spacer_mm": "스페이서",
};
// Request field -> input element ids on the design screen.
const FIELD_INPUTS = {
  outer_mm: ["size-w", "size-h"], "outer_mm[0]": ["size-w"], "outer_mm[1]": ["size-h"],
  inner_mm: ["size-w", "size-h"], "inner_mm[0]": ["size-w"], "inner_mm[1]": ["size-h"],
  lattice_per_leaf: ["lat-v", "lat-h"], "lattice_per_leaf[0]": ["lat-v"], "lattice_per_leaf[1]": ["lat-h"],
  "picture.size_mm": ["pic-w", "pic-h"], "picture.size_mm[0]": ["pic-w"], "picture.size_mm[1]": ["pic-h"],
  "picture.margin_mm": ["pic-m"], stock_mm: ["stock-l", "stock-w", "stock-t"], "stock_mm[0]": ["stock-l"],
  "stock_mm[1]": ["stock-w"], "stock_mm[2]": ["stock-t"], preset: ["preset"],
  artwork: ["size-w", "size-h"], "artwork.size_mm": ["size-w", "size-h"], "artwork.size_mm[0]": ["size-w"],
  "artwork.size_mm[1]": ["size-h"], "artwork.thickness_mm": ["art-t"], "artwork.cover_mm": ["art-c"],
  "artwork.fit_mm": ["art-f"], "artwork.spacer_mm": ["art-s"],
};

export const fieldLabel = (field) => FIELD_LABELS[field] ?? field ?? "입력";

const RULES = {
  "input.object": () => ({ text: "입력은 JSON 객체여야 합니다." }),
  "input.json": () => ({ text: "JSON 형식이 올바르지 않습니다." }),
  "input.too_large": () => ({ text: "입력 JSON은 64 KiB 이하여야 합니다." }),
  "input.unknown_fields": (d) => ({ text: `알 수 없는 입력 항목이 있습니다: ${(d.fields ?? []).join(", ")}.` }),
  "input.schema_version": () => ({ text: "지원하는 입력 스키마 버전은 1입니다." }),
  "input.type": () => ({ text: "창 형식은 양문 또는 단문입니다." }),
  "input.hinge_side": () => ({ text: "단문은 경첩 쪽(왼쪽·오른쪽)이 필요하고, 양문은 경첩 쪽을 따로 정하지 않습니다." }),
  "input.size_basis": () => ({ text: "크기는 외경·내경·화판 중 하나로만 입력합니다.", inputs: ["size-w", "size-h"] }),
  "input.artwork": () => ({ text: "화판은 크기와 두께·덮는 폭·끼움 여유·스페이서로 지정합니다.", inputs: ["size-w", "size-h"] }),
  "input.artwork_picture": () => ({ text: "액자형은 화판이 그림 자리를 대신하므로 그림을 함께 지정할 수 없습니다." }),
  "input.preset_artwork": () => ({
    text: "R3 프리셋은 A3 그림을 후면 지지판에 두는 규칙이라 액자형과 함께 쓸 수 없습니다. standard_v1이나 standard_4x8_v1을 쓰세요.",
    inputs: ["preset"],
  }),
  "artwork.covers_inner": (d) => ({
    text: `화판 ${pair(d.artwork)} mm가 내경 ${pair(d.inner)} mm를 각 변 ${fmt(d.cover)} mm씩 덮지 못합니다. `
      + `화판을 ${pair(d.required)} mm로 맞추세요.`,
    inputs: ["size-w", "size-h"],
  }),
  "artwork.cover_hides_edge": (d, ctx) => ({
    text: `고정틀이 덮는 폭 ${fmt(d.cover)} mm가 끼움 여유 ${fmt(d.fit)} mm보다 크지 않아, 화판이 여유만큼 밀리면 가장자리가 보입니다. `
      + advise(artworkAdvice(ctx.suggestion), "덮는 폭을 늘리거나 끼움 여유를 줄이세요."),
    inputs: ["art-c", "art-f"],
  }),
  "artwork.back_member_width": (d, ctx) => ({
    text: `고정틀 폭에서 덮는 폭과 끼움 여유를 뺀 뒤틀 폭이 ${fmt(d.back_member_width)} mm로, 창살 폭 ${fmt(d.minimum)} mm보다 좁습니다. `
      + advise(artworkAdvice(ctx.suggestion), `덮는 폭을 ${fmt(d.cover_at_most)} mm 이하로 줄이세요.`),
    inputs: ["art-c", "art-f"],
  }),
  "artwork.depth_within_stock": (d, ctx) => ({
    text: `스페이서 ${fmt(d.spacer)} mm와 화판 두께 ${fmt(d.thickness)} mm를 더한 ${fmt(d.required)} mm가 원판 두께 ${fmt(d.available)} mm보다 깊습니다. `
      + advise([...artworkAdvice(ctx.suggestion), ...stockAdvice(ctx.suggestion)], "화판이나 스페이서를 줄이세요."),
    inputs: ["art-t", "art-s"],
  }),
  "input.vector": (d) => ({ text: `${josa(fieldLabel(d.field), "은", "는")} 값 ${d.required}개로 입력합니다.` }),
  "input.number": (d) => ({
    text: String(d.field ?? "").startsWith("lattice")
      ? "창살 수는 0 이상의 정수로 입력하세요."
      : `${josa(fieldLabel(d.field), "에", "에")} 숫자를 입력하세요.`,
  }),
  "input.range": (d) => ({
    text: d.derived_from
      ? `내경에서 계산한 외경 ${pair(d.actual)} mm가 최대 ${fmt(d.maximum)} mm를 넘습니다. 내경을 줄이세요.`
      : `${josa(fieldLabel(d.field), "은", "는")} ${fmt(d.minimum)}–${fmt(d.maximum)} 사이여야 합니다. 지금 ${fmt(d.actual)}입니다.`,
  }),
  "input.preset": () => ({ text: "지원하지 않는 프리셋입니다.", inputs: ["preset"] }),
  "input.preset_type": () => ({ text: "R3 프리셋은 양문 전용입니다. 단문은 standard_v1을 쓰세요.", inputs: ["preset"] }),
  "input.picture": () => ({ text: "그림은 크기와 여유로 지정합니다." }),
  "input.stock_thickness": () => ({ text: "원판 두께는 5–60 mm입니다.", inputs: ["stock-t"] }),
  "opening.positive_size": (d, ctx) => ({
    text: `창이 작아 창짝 안쪽 개구부가 남지 않습니다(가로 ${fmt(d.width)} mm, 세로 ${fmt(d.height)} mm). `
      + advise(sizeAdvice(ctx.suggestion), "창을 키우세요."),
    inputs: [d.width <= 0 && "size-w", d.height <= 0 && "size-h"],
  }),
  "lattice.positive_gap": (d, ctx) => {
    // details.horizontal is the gap between vertical bars; details.vertical between horizontal bars.
    const [nv, nh] = ctx.request?.lattice_per_leaf ?? [];
    const hint = ctx.suggestion ?? {};
    const size = hint.outer_mm ?? hint.inner_mm ?? {};
    const label = hint.inner_mm ? "내경" : "외경";
    const parts = [];
    const inputs = [];
    if (d.horizontal <= 0) {
      const fewer = hint.vertical_per_leaf != null ? `세로 창살을 ${hint.vertical_per_leaf}개 이하로 줄이거나` : "세로 창살을 줄이거나";
      const wider = size.width_at_least != null ? `${label} 가로를 ${fmt(size.width_at_least)} mm 이상으로 늘리세요.` : "창 가로를 늘리세요.";
      parts.push(`세로 창살 ${nv}개를 넣으면 창살 사이 가로 빈칸이 ${fmt(d.horizontal)} mm가 됩니다. ${fewer} ${wider}`);
      inputs.push("lat-v");
    }
    if (d.vertical <= 0) {
      const fewer = hint.horizontal_per_leaf != null ? `가로 창살을 ${hint.horizontal_per_leaf}개 이하로 줄이거나` : "가로 창살을 줄이거나";
      const taller = size.height_at_least != null ? `${label} 세로를 ${fmt(size.height_at_least)} mm 이상으로 늘리세요.` : "창 세로를 늘리세요.";
      parts.push(`가로 창살 ${nh}개를 넣으면 창살 사이 세로 빈칸이 ${fmt(d.vertical)} mm가 됩니다. ${fewer} ${taller}`);
      inputs.push("lat-h");
    }
    return { text: parts.join(" "), inputs };
  },
  "leaf.aspect_ratio": (d, ctx) => ({
    text: `창짝 높이/폭이 ${fmt(d.measured)}로 ${fmt(d.minimum)}보다 작습니다. `
      + advise(sizeAdvice(ctx.suggestion), "창 가로를 줄이거나 세로를 늘리세요."),
    inputs: ["size-w", "size-h"],
  }),
  "hardware.reference_spacing": (d, ctx) => ({
    text: `창짝 높이 ${fmt(d.leaf_height)} mm에서는 경첩 두 개가 겹칩니다. `
      + advise(sizeAdvice(ctx.suggestion), `창짝 높이가 ${fmt(d.required_greater_than)} mm보다 커지도록 창 세로를 늘리세요.`),
    inputs: ["size-h"],
  }),
  "picture.fits_width": (d, ctx) => ({
    text: `그림 가로와 양쪽 여유를 합친 ${fmt(d.required)} mm가 그림 기준영역 가로 ${fmt(d.available)} mm보다 큽니다. `
      + advise([...pictureAdvice(ctx.suggestion), ...sizeAdvice(ctx.suggestion)], "그림이나 여유를 줄이거나 창을 키우세요."),
    inputs: ["pic-w", "pic-m"],
  }),
  "picture.fits_height": (d, ctx) => ({
    text: `그림 세로와 위아래 여유를 합친 ${fmt(d.required)} mm가 그림 기준영역 세로 ${fmt(d.available)} mm보다 큽니다. `
      + advise([...pictureAdvice(ctx.suggestion), ...sizeAdvice(ctx.suggestion)], "그림이나 여유를 줄이거나 창을 키우세요."),
    inputs: ["pic-h", "pic-m"],
  }),
  "nesting.part_fits_stock": (d, ctx) => {
    const kind = KIND[String(d.part_id).split("-")[0]] ?? "부품";
    const long = d.part?.[0] > d.usable?.[0];
    const problem = long
      ? `${kind} ${d.part_id}의 길이 ${fmt(d.part[0])} mm가 원판에서 쓸 수 있는 길이 ${fmt(d.usable[0])} mm보다 깁니다. `
      : `${kind} ${d.part_id}의 폭 ${fmt(d.part?.[1])} mm가 원판에서 쓸 수 있는 폭 ${fmt(d.usable?.[1])} mm보다 넓습니다. `;
    const options = [...stockAdvice(ctx.suggestion), ...sizeAdvice(ctx.suggestion)];
    return { text: problem + advise(options, long ? "원판 길이를 늘리거나 창을 줄이세요." : "원판 폭을 늘리세요."),
             inputs: [long ? "stock-l" : "stock-w"] };
  },
  "nesting.board_width": (d, ctx) => ({
    text: `부품을 원판 한 장에 모두 놓을 수 없습니다. 배치 높이 ${fmt(d.top)} mm가 한도 ${fmt(d.limit)} mm(원판 폭 − 가장자리 여유)를 넘습니다. `
      + advise([...stockAdvice(ctx.suggestion), "창살을 줄이"], "원판 폭을 늘리거나 창살을 줄이세요."),
    inputs: ["stock-w"],
  }),
  "build.queue_full": () => ({ text: "생성 대기열이 가득 찼습니다. 진행 중인 생성이 끝난 뒤 다시 누르세요." }),
};

// The server's `suggestion` names the request field to change and a bound the engine accepts, e.g.
// {"outer_mm": {"width_at_most": 473}}. Each option is a verb stem; advise() joins them as choices.
const BOUNDS = [
  ["width_at_least", "가로", "이상으로 늘리"], ["width_at_most", "가로", "이하로 줄이"],
  ["height_at_least", "세로", "이상으로 늘리"], ["height_at_most", "세로", "이하로 줄이"],
];

function sizeAdvice(suggestion) {
  // A frame-type request is answered in its own field, so suggestion.artwork holds both the
  // panel sides (width_at_least …) and the panel fields (cover_at_most …); BOUNDS picks the sides.
  const key = suggestion?.outer_mm ? "outer_mm" : suggestion?.inner_mm ? "inner_mm" : suggestion?.artwork ? "artwork" : null;
  if (!key) return [];
  const label = BASIS[{ outer_mm: "outer", inner_mm: "inner", artwork: "artwork" }[key]];
  return BOUNDS.filter(([bound]) => suggestion[key][bound] != null)
    .map(([bound, side, verb]) => `${label} ${side}를 ${fmt(suggestion[key][bound])} mm ${verb}`);
}

function artworkAdvice(suggestion) {
  const art = suggestion?.artwork ?? {};
  return [["cover_at_least", "덮는 폭을", "이상으로 늘리"], ["cover_at_most", "덮는 폭을", "이하로 줄이"],
          ["fit_at_most", "끼움 여유를", "이하로 줄이"], ["thickness_at_most", "화판 두께를", "이하로 줄이"],
          ["spacer_at_most", "스페이서를", "이하로 줄이"]]
    .filter(([bound]) => art[bound] != null)
    .map(([bound, what, verb]) => `${what} ${fmt(art[bound])} mm ${verb}`);
}

function pictureAdvice(suggestion) {
  const picture = suggestion?.picture ?? {};
  return [["width_at_most", "그림 가로를"], ["height_at_most", "그림 세로를"], ["margin_at_most", "그림 여유를"]]
    .filter(([bound]) => picture[bound] != null)
    .map(([bound, what]) => `${what} ${fmt(picture[bound])} mm 이하로 줄이`);
}

function stockAdvice(suggestion) {
  const stock = suggestion?.stock_mm ?? {};
  return [["length_at_least", "원판 길이를"], ["width_at_least", "원판 폭을"], ["thickness_at_least", "원판 두께를"]]
    .filter(([bound]) => stock[bound] != null)
    .map(([bound, what]) => `${what} ${fmt(stock[bound])} mm 이상으로 늘리`);
}

// ["가로를 473 mm 이하로 줄이", "세로를 751 mm 이상으로 늘리"] -> "…줄이거나 …늘리세요."
function advise(options, fallback) {
  return options.length ? `${options.join("거나 ")}세요.` : fallback;
}

export function describeError(body, ctx = {}) {
  const rule = body?.rule_id ?? "unknown";
  const details = body?.details && typeof body.details === "object" ? body.details : {};
  const make = RULES[rule];
  const out = make
    ? make(details, { ...ctx, request: body?.request ?? ctx.request, suggestion: body?.suggestion })
    : { text: body?.message || "알 수 없는 오류입니다." };
  const inputs = [...(FIELD_INPUTS[details.field] ?? []), ...(out.inputs ?? [])].filter(Boolean);
  return { text: out.text, rule, where: body?.where ?? "request", inputs };
}

export function brief(value) {
  const text = typeof value === "number" ? fmt(value, 4) : JSON.stringify(value);
  return text && text.length > 80 ? `${text.slice(0, 77)}…` : text;
}

export function describeFailedCheck(check, ctx = {}) {
  const near = check.measured?.closest_pair;
  if (check.rule_id === "distinct_machining_regions_separated" && near?.features?.length === 2) {
    const part = near.part_id;
    const family = part.split("-")[0];
    const [a, b] = near.features.map((f) => (f.startsWith(`${part}-`) ? f.slice(part.length + 1) : f));
    // Pockets along a vertical member seat horizontal bars, so their spacing is the vertical cell.
    const vertical = ["F01", "S01", "L01"].includes(family);
    let text = `${KIND[family] ?? "부품"} ${part}의 홈 ${josa(a, "과", "와")} ${josa(b, "이", "가")} 붙습니다`;
    text += near.overlap_area_mm2 ? `(겹침 ${fmt(near.overlap_area_mm2)} mm²).` : ".";
    const gap = ctx.cell ? ctx.cell[vertical ? 1 : 0] : null;
    if (gap != null && ctx.relief) {
      text += ` 창살 사이 빈칸이 ${fmt(gap)} mm인데, 이웃한 두 홈의 도그본 반지름 ${fmt(ctx.relief)} mm를 더하면 ${fmt(2 * ctx.relief)} mm라서 모자랍니다.`;
    }
    text += vertical ? " 가로 창살 수를 줄이세요." : " 세로 창살 수를 줄이세요.";
    return { text, rule: check.rule_id };
  }
  const targets = check.targets?.length ? ` · 대상 ${check.targets.join(", ")}` : "";
  return { text: `${check.message || check.rule_id}: 기대 ${brief(check.expected)}, 실측 ${brief(check.actual)}${targets}`, rule: check.rule_id };
}

const STOPPED = {
  "job.timeout": "작업이 제한 시간 120초 안에 끝나지 않았습니다.",
  "worker.stopped": "작업 프로세스가 결과를 남기지 못하고 멈췄습니다.",
  "job.failed": "생성 중 오류가 났습니다.",
  "build.failed": "생성 중 오류가 났습니다.",
};

export function describeBuildFailure(error, ctx = {}) {
  const validation = error?.validation;
  if (error?.rule_id === "geometry.validation" && validation) {
    return {
      title: `도면 검사 ${validation.total}개 중 ${validation.failed.length}개 실패`,
      items: validation.failed.map((check) => describeFailedCheck(check, ctx)),
    };
  }
  if (STOPPED[error?.rule_id]) return { title: STOPPED[error.rule_id], items: [{ text: error.message, rule: error.rule_id }] };
  const e = describeError(error, ctx);
  return { title: "생성하지 못했습니다", items: [{ text: e.text, rule: e.rule }] };
}

// validation_report.json `pending`: what nominal CAD checks do not cover.
export const PENDING_KO = {
  "Actual hinges, screws, load capacity and swing interference": "실제 경첩·나사·하중·개폐 간섭",
  "Rear backing, mounting, picture protection and fastener clearance": "뒤판·설치·그림 보호·체결 여유",
  "Stock species, grain integrity, thickness, moisture and movement": "목재 수종·결·두께·함수율·변형",
  "Fit coupons and nominal zero-clearance joint tolerances": "끼움 시험편과 무간극 결합 공차",
  "CAM pocket union, open-edge overrun and cutter compensation": "CAM 홈 합치기·열린 가장자리 초과 절삭·공구 보정",
  "Workholding, tabs/onion skin, feeds/speeds and final manufacturing approval": "고정·탭·이송과 회전 속도·최종 제작 승인",
};
export const TARGETS = {
  saved_dxf: "저장 DXF 재측정", lattice_per_leaf: "창살 배치", stock_mm: "원판", picture: "그림",
  outer_mm: "입력 크기(외경)", inner_mm: "입력 크기(내경)", artwork: "화판",
};
export const DRAWINGS = [
  ["01_one_board_nesting.png", "01 원판 배치"], ["02_joinery_details.png", "02 결합 상세"],
  ["03_assembly_reference.png", "03 조립 기준"], ["04_opening_reference.png", "04 열림 기준"],
  ["05_all_pockets_closeup.png", "05 전체 홈 확대"],
];

export function bytes(n) {
  if (n < 1024) return `${n} B`;
  return n < 1e6 ? `${fmt(n / 1024, 1)} KB` : `${fmt(n / 1e6, 2)} MB`;
}

export function when(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { short: "", long: "" };
  const two = (n) => String(n).padStart(2, "0");
  const day = `${two(d.getMonth() + 1)}-${two(d.getDate())}`;
  const time = `${two(d.getHours())}:${two(d.getMinutes())}`;
  return { short: `${day} ${time}`, long: `${d.getFullYear()}-${day} ${time}` };
}

export function packageTitle(s, sizes = {}) {
  const kind = s.type === "single" ? `단문 · ${SIDE[s.hinge_side] ?? ""} 경첩` : "양문";
  let picture = "그림 없음";
  if (s.artwork) picture = `액자형 · 화판 ${pair(s.artwork.size_mm)}`;
  else if (s.picture) {
    const named = Object.entries(sizes).find(([, v]) => v[0] === s.picture.size_mm[0] && v[1] === s.picture.size_mm[1]);
    picture = `${named ? named[0] : pair(s.picture.size_mm)} 그림`;
  }
  return [kind, `${BASIS[s.size.basis]} ${pair(s.size.requested_mm)}`, `창살 ${s.lattice_per_leaf.join("+")}`, picture].join(" · ");
}

// The rules each preset follows; a preset not named here follows the shared standard rules.
const PRESET_RULES = { hanok_A3_portrait_R3: "A3 세로형 R3 규칙", standard_4x8_v1: "4×8 원판 기본 규칙" };

export function presetText(info) {
  if (!info) return "";
  const parts = [PRESET_RULES[info.id] ?? "단문·양문 공용 기본 규칙"];
  parts.push(info.types.length === 1 ? `${TYPE[info.types[0]]} 전용` : "단문·양문 모두");
  if (info.min_leaf_ratio > 0) parts.push(`창짝 높이/폭 ${fmt(info.min_leaf_ratio)} 이상`);
  parts.push(info.picture ? `그림 ${pair(info.picture.size_mm)} 기본` : "그림 없음이 기본");
  if (info.id !== "hanok_A3_portrait_R3") parts.push("액자형 가능");
  if (info.stock_mm) parts.push(`원판 ${pair(info.stock_mm)} · 여유 ${fmt(info.edge_margin_mm)} · 간격 ${fmt(info.part_gap_mm)} mm`);
  return parts.join(" · ");
}
