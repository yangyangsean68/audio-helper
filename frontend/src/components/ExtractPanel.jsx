export default function ExtractPanel({ extract }) {
  if (!extract) {
    return null;
  }

  return (
    <section className="panel">
      <h2>提取信息</h2>
      <dl className="extract-list">
        <div>
          <dt>地点 A</dt>
          <dd>
            {extract.city_a} {extract.address_a}
          </dd>
        </div>
        <div>
          <dt>地点 B</dt>
          <dd>
            {extract.city_b} {extract.address_b}
          </dd>
        </div>
        <div>
          <dt>类别</dt>
          <dd>{extract.category}</dd>
        </div>
      </dl>
    </section>
  );
}
