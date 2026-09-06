# 语音约碰面地点

同一座城市内，用语音描述两人所在地点，推荐中间附近的碰面店铺。

中点只表示地理位置大致居中，不能代表两人出行时间相同。店铺距离只表示距离中点。

当前状态：功能已按第一条提示词和已确认方案实现并接入前端，**不能据此宣称项目验收完成**。下列清单由你逐项勾选。Mock 或后端单接口通过，不能替代真实上游联调。

## 对照第一条提示词

### 已实现（代码层面，不等于已验收）

- 按住录音 → 上传 → 识别 → 提取 → 地理中点搜店 → 展示最多 3 家 → 推荐语与语音播报。
- 第一版只支持同一座城市内的两个人；人数不符、跨城、地点含糊/缺失、定位不明确、无候选时停止后续搜店或后续链路，并返回中文错误。
- 前端 React + Vite + JavaScript，端口 5175；Axios 统一封装；按真实阶段展示状态，不用 SSE、轮询或虚构百分比。
- 后端 FastAPI，端口 8003；成功体 `{ request_id, data }`；失败体 `{ request_id, error: { code, message, stage } }`；音频下载按文件返回。
- 上传字段名 `file`，浏览器生成 multipart 边界；不转 Base64 上传。
- 录音限制：WebM/Opus、1–60 秒、最大 5MB；麦克风拒绝或录制失败不发业务请求。
- 失败时保留本轮已完成信息；新一轮成功提交会清空上一轮编号、文字、店铺和播报，取消或忽略旧请求。
- `audio_id` / `search_id` / TTS 编号带 `created_at`，读取时超过 24 小时视为无效。
- TTS 或音频下载失败时保留 `reply_text`，`audio_url` 为 `null` 并带 `warning`。
- `.env`、虚拟环境、`node_modules`、运行时 `backend/storage/**` 已写入 `.gitignore`；httpx 访问日志级别为 WARNING，避免把带密钥的完整 URL 打到 INFO。

### 尚未实现或与原文有偏差

- **过期文件不会从磁盘删除**：过期后读取会 404，但没有定时清理任务，`backend/storage/` 下的过期 `rec_` / `sch_` / `tts_` 文件会留在本地。失败上传的 `.part` 会删除。
- 仓库中没有 `backend/storage/.gitkeep`（`.gitignore` 里预留了例外）；进程运行时会自动创建目录。
- 第一条写的后端基址是 `http://localhost:8003`。为避免 Windows 上 `localhost` 走 IPv6 超时，前端 Axios 现使用 `http://127.0.0.1:8003`；CORS 仍允许 `localhost:5175` 与 `127.0.0.1:5175`。finalize 返回的 `audio_url` 仍可能带 `localhost`，前端取音频时会改写到 `127.0.0.1`。
- `frontend/package.json` 的 `engines` 仍写 Node `>=22.12.0 <23`，与本机已用的 Node 24 / README 说明不完全一致。
- 没有前端自动化测试；没有把过期存储做成后台清扫。

### 尚未验证（不能标为通过）

- 本轮对照检查**没有**重新执行 pytest、没有启动服务、没有代做浏览器验收。
- 真实百炼 ASR / TTS、DeepSeek 提取与推荐、高德搜店、前端从录音到播放的整链，是否全部按本清单通过，以你的勾选为准。
- 自动播放被浏览器拦截后的手动播放、断网/超时提示、新旧响应不混用，需在页面上实测。
- Mock 通过不能替代真实接口联调。

## 环境依赖

| 依赖 | 说明 |
| --- | --- |
| Python 3.14 | 本机已确认使用 3.14；后端虚拟环境用同一解释器。 |
| Node.js | 建议 22.x；本机若为 24，以实际能跑 `npm run dev` 为准。 |
| FFmpeg / `ffprobe` | `/upload` 只探测、不转码。未安装时上传返回 `AUDIO_PROBE_UNAVAILABLE`（502），健康检查仍可用。 |
| 浏览器 | Chrome / Edge / Firefox（需支持 WebM/Opus 与麦克风）。 |
| 端口 | 后端 `127.0.0.1:8003`，前端 `127.0.0.1:5175`，不要改。 |

检查探测工具：

```powershell
ffprobe -version
```

未安装时（新开终端后再查 PATH）：

```powershell
winget install Gyan.FFmpeg
```

## 配置

```powershell
cd backend
copy .env.example .env
```

在 `backend/.env` 填写，**不要提交该文件**：

| 变量 | 用途 |
| --- | --- |
| `BAILIAN_API_KEY` | 百炼 ASR 与 TTS（北京地域） |
| `DEEPSEEK_API_KEY` | 提取与推荐语 |
| `AMAP_API_KEY` | 高德 Web 服务 Key（地理编码与周边搜店） |

密钥留空时：`GET /health` 仍应成功；调用对应上游的接口应失败且**不发付费请求**（搜店/识别/提取/推荐缺密钥返回 `UPSTREAM_ERROR`；TTS 缺密钥则文字降级，不把整次 finalize 打成失败）。

改 `.env` 后必须**重启 uvicorn**。`--reload` 会加载代码，但环境变量以进程启动时为准。

## 启动

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8003 --reload
```

- 服务：http://127.0.0.1:8003
- 健康检查：http://127.0.0.1:8003/health
- 接口文档：http://127.0.0.1:8003/docs

前端（另开终端）：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5175

## 密钥保护与 Git 忽略

应被忽略、不要提交：

- `backend/.env` 及任何真实密钥
- `.venv/`、`node_modules/`、`frontend/dist/`
- `backend/storage/` 下的录音、搜店 json、TTS 音频（运行时数据）

可提交：`backend/.env.example`（仅空值或公开 URL 模板）。

自查：

```powershell
git check-ignore -v backend/.env backend/storage
git status --short
```

`.env` 与 `storage` 下文件不应出现在待提交列表。日志里不应出现完整的 `key=` 查询串。

## 模拟测试（不替代真实联调）

在后端虚拟环境中：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest tests/test_health.py tests/test_upload.py tests/test_asr.py tests/test_extract.py tests/test_search.py tests/test_finalize.py
```

这些用例用 Mock 覆盖正常分支和部分异常，**避免反复打付费接口**。通过只能说明本地分支逻辑，不能证明百炼 / DeepSeek / 高德已跑通。

## 验收清单（按实际操作顺序）

请逐项做、逐项记录。标了「真实」的必须打到真实上游或真实浏览器行为；标了「Mock」的可用 pytest 或故意制造故障。同一项若两种都做，分别记结果。

### 0. 准备

1. `ffprobe -version` 有输出。
2. 后端启动后访问 `/health`，`data.status` 为 `ok`（不需要密钥）。
3. 前端打开后页面显示服务状态「正常」；Network 中有 `GET /health`。
4. 城市默认「杭州」，可修改。

### 1. 正常录音到推荐结果和语音播放（真实）

口示例句：「我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。」

1. 按住录音超过 1 秒、不超过 60 秒后松开。处理中按钮应为「处理中，请稍候」，不可再按住提交。
2. 状态顺序：检查服务中 → 上传中 → 识别中 → 提取中 → 找店中 → 生成推荐中（取音频时可短暂为播报中）。
3. Network 顺序与要点：

| 顺序 | 方法 | 路径 | 核对 |
| --- | --- | --- | --- |
| 1 | GET | `/health` | 200，`data.status=ok` |
| 2 | POST | `/upload` | 字段 `file`；`Content-Type` 带 `boundary`；只上传一次；`data.audio_id` 为 `rec_` |
| 3 | POST | `/asr` | JSON `audio_id`；`data.text` |
| 4 | POST | `/extract` | JSON `text` + `city`；五个字段 |
| 5 | POST | `/search` | 五个提取字段；`search_id`、`midpoint`、最多 3 条 `pois` |
| 6 | POST | `/finalize` | 只传 `search_id`，不要再传店铺列表 |
| 7 | GET | `/audio/tts_...` | 地址来自 finalize 的 `audio_url`，不要用 `rec_` 拼接；响应是音频字节 |

4. 页面展示：识别文字、地点 A/B 与类别、最多 3 家店（店名、地址、「距离中点 N 米」，顺序与 `/search` 一致）、推荐语。不是写死的示例店。
5. 中点文案不声称等时。`midpoint` 经度在前、纬度在后。
6. 能听到推荐语音；若被浏览器拦截自动播放，应出现「播放推荐语音」，点按后能播。

### 2. 麦克风拒绝、非法文件和重复点击

| 项 | 操作 | 期望 | 方式 |
| --- | --- | --- | --- |
| 麦克风拒绝 | 浏览器拒绝麦克风后按住录音 | 中文提示，Network 中无 `/upload` 及后续业务请求 | **真实（浏览器）** |
| 录音过短 | 松开早于 1 秒 | 提示时长限制，不上传 | **真实（浏览器）** |
| 重复提交 | 一轮处理中再次按住或连点 | 按钮禁用，不能并行第二轮付费请求 | **真实（页面）** |
| 文件过大 | `/docs` 或 curl 上传超过 5MB | 413 `AUDIO_TOO_LARGE` | **Mock / 手工上传**（不必用真实 ASR） |
| 非法格式 | `/docs` 上传 mp3、txt 等 | 415 `AUDIO_UNSUPPORTED_TYPE`（依赖 ffprobe） | **Mock / 手工上传** |
| 时长非法 | 探测时长不在 1–60 秒 | 422 `AUDIO_DURATION_INVALID` | **Mock（pytest `test_upload.py`）** |

### 3. 地址缺失、人数不符、跨城、定位不明确和无候选

提取类可走页面录音（**真实 ASR + DeepSeek**），或在 `/docs` 直接 `POST /extract`（**真实 DeepSeek，跳过录音**）。搜店类可走页面（**真实高德**）或 `/docs` 的 `POST /search`；对应 pytest 为 **Mock**。

| 项 | 建议输入 | 期望 | 方式 |
| --- | --- | --- | --- |
| 地址缺失 | 「我在杭州东站，帮我找个咖啡店。」 | 422 `EXTRACT_INCOMPLETE`，不调用 `/search` | 真实提取 或 Mock `test_extract.py` |
| 人数不符 | 明确三个人、三个地点 | 422 `PARTY_COUNT_INVALID`，不搜店 | 真实提取 或 Mock |
| 跨城 | 一人杭州、一人上海 | 422 `CROSS_CITY`（extract 或 search），不搜店 | 真实 或 Mock |
| 含糊地址 | 「我在家，朋友在公司」 | 422 `EXTRACT_INCOMPLETE` | 真实提取 或 Mock |
| 定位不明确 | search 用过粗地址（如只说「东站」且高德多候选无法区分） | 422 `LOCATION_AMBIGUOUS`，无 `search_id` | 真实高德 或 Mock `test_search.py` |
| 无候选 | 类别换成中点附近几乎没有的类型（如「核电站」） | 422 `NO_POI` | 真实高德 或 Mock |

页面上这些失败应显示中文提示和 `error.code` / 阶段，并**保留已经完成的识别文字**（若已识别）。不要出现假店铺。

### 4. 外部服务异常、超时，以及 TTS / 音频下载失败后的文字降级

| 项 | 操作 | 期望 | 方式 |
| --- | --- | --- | --- |
| 缺密钥不发网 | 清空对应 key，重启后再调该接口 | `UPSTREAM_ERROR`（TTS 除外见下行），无付费请求 | **Mock（pytest 已覆盖）**；真实可对照 uvicorn 日志 |
| 上游超时 | pytest 模拟 httpx.TimeoutException | 504 `UPSTREAM_TIMEOUT` | **Mock** |
| 上游 5xx/协议错误 | pytest 模拟失败响应 | 502 `UPSTREAM_ERROR` | **Mock** |
| 推荐语失败 | finalize 时 DeepSeek 失败 | 502/504，没有空的成功 `reply_text` | **Mock**；真实需等上游故障，不要为测而反复重试付费接口 |
| TTS 失败文字降级 | 推荐语能成功的前提下，临时清空 `BAILIAN_API_KEY` 后重启，再 `/finalize` | 200，`reply_text` 仍在，`audio_url` 为 `null`，有 `warning` | **真实（关 TTS 密钥）** 或 Mock `test_finalize.py` |
| 音频下载/格式失败 | pytest 模拟 TTS URL 不可用或无法识别的字节 | 同上文字降级 | **Mock** |
| 前端断网 | 处理中关掉后端或断网 | 提示网络连接失败，停止后续请求，保留已完成信息 | **真实（页面）** |
| 前端超时 | 可在 Network 里 throttle，或临时把后端预算拖过 Axios 超时 | 提示超时，不自动重试付费接口 | **真实（页面）** 或观察无重试 |

测完 TTS 降级后把 `BAILIAN_API_KEY` 填回并重启。

### 5. 页面失败后保留信息，重新录音后清除旧结果，新旧响应不混用（真实，页面）

1. 故意在提取或搜店失败（例如跨城口播）：识别文字仍在，后面的店铺/推荐语不应出现。
2. 一次成功出结果后，再录一句并成功提交：上一轮 `audio_id` / `search_id` / 文字 / 店铺 / 推荐语 / 旧音频应被清空；旧音频停止。
3. 处理中按钮不可用，因此不会并行两轮；若用 Network 延迟观察，迟到的旧响应不得写回新一轮结果。
4. 离开页面或刷新后，麦克风指示灯应关掉（卸载释放）。

### 6. 编号有效期、临时数据清理、密钥保护和 Git 忽略

| 项 | 操作 | 期望 | 方式 |
| --- | --- | --- | --- |
| 录音编号过期 | pytest 把 sidecar `created_at` 改为 25 小时前再 `get_audio` | 404 `AUDIO_ID_NOT_FOUND` | **Mock `test_upload.py`** |
| 查询编号过期 | 同样改 `search` json 的 `created_at` 再 `/finalize` | 404 `SEARCH_ID_NOT_FOUND` | **手工改文件** 或对照存储读取逻辑 |
| 音频编号过期 | 过期 `tts_` 再 `GET /audio/{id}` | 404 JSON，不是空文件 | **Mock `test_finalize.py` / 手工** |
| 磁盘清理 | 查看 `backend/storage/` | **当前不会自动删除过期文件**；只在读取时拒绝。此项记为已知缺口，不要当成已实现 | 观察 |
| 失败上传残留 | 上传非法文件后看 `storage/audio` | 不应留下对应 `.part` | **手工上传** |
| Git 忽略 | `git status`、`git check-ignore` | `.env`、storage 音频/json 不进版本库 | 本地检查 |
| 密钥 | 看 uvicorn 日志 | 不要出现完整 `key=` URL | 观察 |

成功搜店后，`backend/storage/search/sch_....json` 应含 `created_at`。TTS 文件扩展名应与文件头一致（wav 为 `RIFF`），不要只看 URL 后缀。

## 接口细节（搜店与中点）

高德 `location` 是经度在前、纬度在后。中点是两侧经度、纬度分别算术平均。`distance_to_midpoint_m` 只表示距离该地理中点。

正常搜店示例（`/docs` 或真实前端提取结果应类似）：

```json
{
  "city_a": "杭州",
  "address_a": "杭州东站",
  "city_b": "杭州",
  "address_b": "西湖龙翔桥地铁站",
  "category": "咖啡店"
}
```

`/search` 单次高德预算约 12 秒，整段约 45 秒，优先 IPv4。前端找店超时为 55 秒，略长于后端。

## 记录方式

请按清单序号记下：通过 / 失败 / 未测，并注明是 **真实服务** 还是 **Mock**。未执行的项保持「未测」，不要标成通过。
