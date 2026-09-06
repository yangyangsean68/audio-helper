import { useEffect, useState } from "react";
import { getHealth } from "./api.js";

export default function App() {
  const [health, setHealth] = useState("检查中…");

  useEffect(() => {
    let cancelled = false;

    getHealth()
      .then((response) => {
        if (cancelled) {
          return;
        }
        const status = response.data?.data?.status;
        setHealth(status === "ok" ? "后端健康检查通过" : "后端响应异常");
      })
      .catch(() => {
        if (!cancelled) {
          setHealth("无法连接后端（请确认已在 8003 端口启动）");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page">
      <h1>语音约碰面地点</h1>
      <p className="lead">
        说出两人所在地点，系统会在同一座城市内推荐中间附近的碰面店铺。
      </p>
      <p className="note">
        当前为项目骨架：录音与找店功能尚未接入。中点只表示地理位置大致居中，不代表两人出行时间相同。
      </p>
      <p className="status">后端状态：{health}</p>
    </main>
  );
}
