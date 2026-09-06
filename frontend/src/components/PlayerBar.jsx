export default function PlayerBar({
  replyText,
  warning,
  audioUrl,
  needsManualPlay,
  audioLoadError,
  onPlay,
}) {
  if (!replyText && !warning) {
    return null;
  }

  return (
    <section className="panel">
      <h2>推荐语</h2>
      {replyText ? <p className="panel-body">{replyText}</p> : null}
      {warning ? <p className="warning">{warning}</p> : null}
      {audioLoadError ? <p className="warning">{audioLoadError}</p> : null}
      {audioUrl && needsManualPlay ? (
        <button type="button" className="play-button" onClick={onPlay}>
          播放推荐语音
        </button>
      ) : null}
    </section>
  );
}
