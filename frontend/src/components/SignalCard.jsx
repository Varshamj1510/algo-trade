function SignalCard({ signal }) {
  return (
    <article className="signal-card">
      <div className="card-header">
        <span className="symbol">{signal.symbol}</span>
        <span className={`signal-pill ${signal.signal.toLowerCase()}`}>{signal.signal}</span>
      </div>
      <div className="price-row">
        <strong>${signal.price}</strong>
        <span>{signal.confidence}% confidence</span>
      </div>
    </article>
  );
}

export default SignalCard;
