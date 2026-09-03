function Navbar() {
  return (
    <nav className="navbar">
      <div className="brand">AI TRADING</div>
      <div className="nav-links">
        <a href="#">Dashboard</a>
        <a href="#">Analysis</a>
        <a href="#">Backtest</a>
      </div>
      <button className="nav-button">Live Market</button>
    </nav>
  );
}

export default Navbar;
