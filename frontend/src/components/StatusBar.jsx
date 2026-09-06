import { STAGE_LABELS } from "../api.js";

export default function StatusBar({
  recorderPhase,
  elapsedSec,
  pipelineStage,
  inFlight,
  healthStatus,
}) {
  let status = "准备录音";
  if (recorderPhase === "requesting") {
    status = "正在申请麦克风";
  } else if (recorderPhase === "recording") {
    status = `录音中 ${elapsedSec.toFixed(1)} 秒`;
  } else if (recorderPhase === "stopping") {
    status = "正在结束录音";
  } else if (pipelineStage === "done") {
    status = "完成";
  } else if (pipelineStage === "error") {
    status = "已停止后续请求";
  } else if (inFlight || STAGE_LABELS[pipelineStage]) {
    status = STAGE_LABELS[pipelineStage] || "处理中";
  }

  const healthLabel =
    healthStatus === "ok"
      ? "正常"
      : healthStatus === "offline"
        ? "未连接"
        : healthStatus
          ? healthStatus
          : "检查中";

  return (
    <div className="status-block">
      <p className="status">状态：{status}</p>
      <p className="note">服务状态：{healthLabel}</p>
    </div>
  );
}
