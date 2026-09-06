export default function CityField({ value, onChange, disabled }) {
  return (
    <label className="city-field">
      <span>当前城市</span>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="off"
        disabled={disabled}
      />
    </label>
  );
}
