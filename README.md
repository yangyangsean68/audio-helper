# 语音约碰面地点

同一座城市内，用语音描述两人所在地点，推荐中间附近的碰面店铺。

当前进度：项目骨架。已提供后端 `GET /health` 和可打开的前端基础页。录音、识别、找店等业务接口尚未实现。

中点只表示地理位置大致居中，不能代表两人出行时间相同。店铺距离只表示距离中点。

## 环境

- Python 3.14（本机已确认使用 3.14，不再要求 3.11）
- Node.js 22.12 及以上的 22.x

## 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --host 127.0.0.1 --port 8003 --reload
```

密钥可先留空。未填写外部服务密钥时，健康检查仍应返回成功。

- 服务：http://127.0.0.1:8003
- 健康检查：http://127.0.0.1:8003/health
- 接口文档：http://127.0.0.1:8003/docs

可选（本轮未在本机执行）：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest tests/test_health.py
```

## 前端

另开一个终端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5175

## 模拟测试与真实接口验收

- 模拟测试：后续业务接口将用 Mock 覆盖正常和异常分支，避免反复调用付费服务。Mock 通过不能证明真实上游已跑通。
- 真实接口验收：配置 `.env` 中的 `BAILIAN_API_KEY`、`DEEPSEEK_API_KEY`、`AMAP_API_KEY` 后，需人工验证 ASR、DeepSeek、高德、TTS，并做一次前端全链路验收。真实调用须确认后再执行。
