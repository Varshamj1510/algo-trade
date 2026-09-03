function StockChart() {
  const points = [42, 52, 48, 66, 69, 78, 74, 86, 94, 89, 110, 120];

  return (
    <div className="chart-wrap">
      <svg viewBox="0 0 540 220" className="chart-svg" role="img" aria-label="stock chart">
        <defs>
          <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#7c3aed" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path
          d="M 0 180 C 40 150, 60 120, 100 130 S 180 90, 220 100 S 300 50, 340 64 S 420 26, 460 70 S 500 110, 540 40 L 540 220 L 0 220 Z"
          fill="url(#chartFill)"
        />
        <path
          d="M 0 180 C 40 150, 60 120, 100 130 S 180 90, 220 100 S 300 50, 340 64 S 420 26, 460 70 S 500 110, 540 40"
          fill="none"
          stroke="#8b5cf6"
          strokeWidth="4"
          strokeLinecap="round"
        />
      </svg>
      <div className="chart-legend">
        <span>High momentum</span>
        <span className="trend-up">+12.4%</span>
      </div>
    </div>
  );
}

export default StockChart;
