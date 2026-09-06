export default function TranscriptPanel({ text }) {
  if (!text) {
    return null;
  }

  return (
    <section className="panel">
      <h2>识别文字</h2>
      <p className="panel-body">{text}</p>
    </section>
  );
}
