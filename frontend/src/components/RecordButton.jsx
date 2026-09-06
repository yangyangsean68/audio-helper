export default function RecordButton({ phase, elapsedSec, buttonProps }) {
  const recording = phase === "recording";
  const requesting = phase === "requesting";
  const label = recording
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
