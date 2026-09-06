import axios from "axios";

export const API_BASE = "http://127.0.0.1:8003";

/** 略长于各后端接口的完整调用预算，且不对付费接口做自动重试。 */
export const TIMEOUTS = {
  health: 8000,
  upload: 25000,
  asr: 30000,
  extract: 22000,
  search: 55000,
  finalize: 36000,
  audio: 8000,
};

export const STAGE_LABELS = {
  health: "检查服务中",
  upload: "上传中",
  asr: "识别中",
  extract: "提取中",
  search: "找店中",
  finalize: "生成推荐中",
  audio: "播报中",
};

export const api = axios.create({
  baseURL: API_BASE,
  timeout: TIMEOUTS.upload,
});

function unwrap(response) {
  const body = response.data;
  return {
    request_id: body.request_id,
    data: body.data,
  };
}

async function readErrorBody(error) {
  const payload = error.response?.data;
  if (payload instanceof Blob) {
    try {
      return JSON.parse(await payload.text());
    } catch {
      return null;
    }
  }
  if (payload && typeof payload === "object") {
    return payload;
  }
  return null;
}

export async function normalizeRequestError(error, stage) {
  if (error?.code === "ERR_CANCELED" || error?.name === "CanceledError") {
    return { canceled: true };
  }

  const body = await readErrorBody(error);
  if (body?.error) {
    return {
      canceled: false,
      kind: "business",
      code: body.error.code,
      message: body.error.message,
      stage: body.error.stage || stage,
      request_id: body.request_id,
    };
  }

  if (error?.code === "ECONNABORTED" || /timeout/i.test(error?.message || "")) {
    return {
      canceled: false,
      kind: "timeout",
      code: "CLIENT_TIMEOUT",
      message: "请求超时，请稍后重试。",
      stage,
    };
  }

  if (!error?.response) {
    return {
      canceled: false,
      kind: "network",
      code: "NETWORK_ERROR",
      message: "网络连接失败，请确认后端已启动。",
      stage,
    };
  }

  return {
    canceled: false,
    kind: "unknown",
    code: "REQUEST_FAILED",
    message: "请求失败，请稍后重试。",
    stage,
  };
}

export function formatErrorText(error) {
  const stageLabel = STAGE_LABELS[error.stage] || error.stage;
  const parts = [error.message];
  if (error.code || stageLabel) {
    parts.push([stageLabel, error.code].filter(Boolean).join(" · "));
  }
  return parts.filter(Boolean).join("\n");
}

export function getHealth(config) {
  return api
    .get("/health", { timeout: TIMEOUTS.health, ...config })
    .then(unwrap);
}

export function uploadRecording(blob, mimeType, config = {}) {
  const form = new FormData();
  const file = new File([blob], "recording.webm", {
    type: blob.type || mimeType || "audio/webm",
  });
  form.append("file", file);
  // 不设置 Content-Type，由浏览器生成 multipart 边界。
  return api
    .post("/upload", form, {
      timeout: TIMEOUTS.upload,
      signal: config.signal,
    })
    .then(unwrap);
}

export function recognizeAudio(audioId, config) {
  return api
    .post("/asr", { audio_id: audioId }, { timeout: TIMEOUTS.asr, ...config })
    .then(unwrap);
}

export function extractMeeting(text, city, config) {
  return api
    .post(
      "/extract",
      { text, city },
      { timeout: TIMEOUTS.extract, ...config },
    )
    .then(unwrap);
}

export function searchPlaces(fields, config) {
  return api
    .post(
      "/search",
      {
        city_a: fields.city_a,
        address_a: fields.address_a,
        city_b: fields.city_b,
        address_b: fields.address_b,
        category: fields.category,
      },
      { timeout: TIMEOUTS.search, ...config },
    )
    .then(unwrap);
}

export function finalizeSearch(searchId, config) {
  return api
    .post(
      "/finalize",
      { search_id: searchId },
      { timeout: TIMEOUTS.finalize, ...config },
    )
    .then(unwrap);
}

export function resolveAudioUrl(audioUrl) {
  if (!audioUrl) {
    return null;
  }
  try {
    const resolved = new URL(audioUrl, API_BASE);
    const backendHosts = new Set(["localhost:8003", "127.0.0.1:8003"]);
    if (backendHosts.has(resolved.host)) {
      return `${API_BASE}${resolved.pathname}${resolved.search}`;
    }
    return resolved.href;
  } catch {
    const path = audioUrl.startsWith("/") ? audioUrl : `/${audioUrl}`;
    return `${API_BASE}${path}`;
  }
}

export async function fetchAudioFile(audioUrl, config) {
  const url = resolveAudioUrl(audioUrl);
  const response = await api.get(url, {
    responseType: "blob",
    timeout: TIMEOUTS.audio,
    ...config,
  });
  const contentType = response.headers["content-type"] || "";
  if (contentType.includes("application/json")) {
    const body = JSON.parse(await response.data.text());
    const error = new Error(body.error?.message || "音频加载失败");
    error.response = { data: body, status: response.status };
    throw error;
  }
  return response.data;
}
