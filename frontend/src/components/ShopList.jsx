export default function ShopList({ pois, midpoint }) {
  if (!pois?.length) {
    return null;
  }

  return (
    <section className="panel">
      <h2>候选店铺</h2>
      {midpoint ? (
        <p className="note">
          中点约 {midpoint.longitude.toFixed(6)}, {midpoint.latitude.toFixed(6)}
          。中点只表示地理位置大致居中，不代表两人出行时间相同。
        </p>
      ) : null}
      <ol className="shop-list">
        {pois.map((poi, index) => (
          <li key={`${poi.name}-${index}`}>
            <strong>{poi.name}</strong>
            <p>{poi.address}</p>
            <p className="shop-distance">距离中点 {poi.distance_to_midpoint_m} 米</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
