import { extensionForMime, formatDuration, formatFileSize } from "../recording.js";

export default function RecordingPreview({ result }) {
  if (!result) {
    return null;
  }

  const filename = `recording.${extensionForMime(result.mimeType)}`;

  return (
    <section className="preview">
      <h2>本次录音</h2>
      <p className="preview-meta">
        格式 {result.mimeType || "未知"} · 大小 {formatFileSize(result.sizeBytes)} · 时长{" "}
        {formatDuration(result.durationSec)}
      </p>
      <audio className="preview-player" controls src={result.url} />
      <a className="download-link" href={result.url} download={filename}>
        下载本次录音
      </a>
    </section>
  );
}
