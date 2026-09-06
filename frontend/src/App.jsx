import { useCallback, useState } from "react";
import CityField from "./components/CityField.jsx";
import ExtractPanel from "./components/ExtractPanel.jsx";
import PlayerBar from "./components/PlayerBar.jsx";
import RecordButton from "./components/RecordButton.jsx";
import RecordingPreview from "./components/RecordingPreview.jsx";
import ShopList from "./components/ShopList.jsx";
import StatusBar from "./components/StatusBar.jsx";
import TranscriptPanel from "./components/TranscriptPanel.jsx";
import { useHoldRecorder } from "./useHoldRecorder.js";
import { useMeetingPipeline } from "./useMeetingPipeline.js";

export default function App() {
  const [city, setCity] = useState("杭州");
  const {
    healthStatus,
    stage,
    inFlight,
    errorText,
    round,
    needsManualPlay,
    audioLoadError,
    runPipeline,
    playManually,
  } = useMeetingPipeline();

  const onRecordingComplete = useCallback(
    (recording) => {
      runPipeline(recording, city);
    },
    [city, runPipeline],
  );

  const recorder = useHoldRecorder({ onRecordingComplete });

  return (
    <main className="page">
      <h1>语音约碰面地点</h1>
      <p className="lead">
        说出两人所在地点，系统会在同一座城市内推荐中间附近的碰面店铺。
      </p>
      <p className="note">
        中点只表示地理位置大致居中，不代表两人出行时间相同。店铺距离只表示距离中点。
      </p>

      <CityField value={city} onChange={setCity} disabled={inFlight} />

      <StatusBar
        recorderPhase={recorder.phase}
        elapsedSec={recorder.elapsedSec}
        pipelineStage={stage}
        inFlight={inFlight}
        healthStatus={healthStatus}
      />
      {recorder.mimeType ? (
        <p className="note">将使用格式：{recorder.mimeType}</p>
      ) : null}

      <RecordButton
        phase={recorder.phase}
        elapsedSec={recorder.elapsedSec}
        busy={inFlight}
        buttonProps={{
          ...recorder.buttonProps,
          disabled: recorder.buttonProps.disabled || inFlight,
        }}
      />

      {recorder.error ? <p className="error">{recorder.error}</p> : null}
      {errorText ? <p className="error error-multiline">{errorText}</p> : null}

      <RecordingPreview result={recorder.result} />
      <TranscriptPanel text={round.transcript} />
      <ExtractPanel extract={round.extract} />
      <ShopList pois={round.pois} midpoint={round.midpoint} />
      <PlayerBar
        replyText={round.replyText}
        warning={round.warning}
        audioUrl={round.audioUrl}
        needsManualPlay={needsManualPlay}
        audioLoadError={audioLoadError}
        onPlay={playManually}
      />
    </main>
  );
}
