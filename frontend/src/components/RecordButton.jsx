export default function RecordButton({ phase, elapsedSec, busy, buttonProps }) {
  const recording = phase === "recording";
  const requesting = phase === "requesting";
  const label = busy
    ? "处理中，请稍候"
    : recording
      ? `录音中 ${elapsedSec.toFixed(1)} 秒，松开结束`
      : requesting
        ? "正在打开麦克风…"
        : "按住说话";

  return (
    <button
      className={`record-button${recording ? " record-button-active" : ""}`}
      {...buttonProps}
    >
      {label}
    </button>
  );
}
