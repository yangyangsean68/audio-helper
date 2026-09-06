import { useState } from "react";
import CityField from "./components/CityField.jsx";
import RecordButton from "./components/RecordButton.jsx";
import RecordingPreview from "./components/RecordingPreview.jsx";
import { useHoldRecorder } from "./useHoldRecorder.js";

export default function App() {
  const [city, setCity] = useState("杭州");
  const recorder = useHoldRecorder();

  const statusText = recorder.phase === "recording"
    ? "录音中"
    : recorder.phase === "requesting"
      ? "正在申请麦克风"
      : recorder.phase === "stopping"
        ? "正在结束录音"
        : recorder.result
          ? "录音完成，可试听或下载"
          : "准备录音";

  return (
    <main className="page">
      <h1>语音约碰面地点</h1>
      <p className="lead">
        说出两人所在地点，系统会在同一座城市内推荐中间附近的碰面店铺。
      </p>
      <p className="note">
        中点只表示地理位置大致居中，不代表两人出行时间相同。本轮只做本地录音，不会上传或搜店。
      </p>

      <CityField value={city} onChange={setCity} />

      <p className="status">状态：{statusText}</p>
      {recorder.mimeType ? (
        <p className="note">将使用格式：{recorder.mimeType}</p>
      ) : null}

      <RecordButton
        phase={recorder.phase}
        elapsedSec={recorder.elapsedSec}
        buttonProps={recorder.buttonProps}
      />

      {recorder.error ? <p className="error">{recorder.error}</p> : null}

      <RecordingPreview result={recorder.result} />
    </main>
  );
}
