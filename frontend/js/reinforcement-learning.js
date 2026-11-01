const form = document.getElementById('rl-form');
const symbolSelect = document.getElementById('rl-symbol');
const statusMessage = document.getElementById('rl-status');
const runButton = document.getElementById('rl-run');
const resultsSection = document.getElementById('rl-results');
const currency = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

const user = parseUser();
if (!requireAuth()) {
  showStatus('Sign in to use the research lab.', true);
} else {
  if (user) {
    const displayName = user.full_name || user.username || 'Investor';
    document.getElementById('top-user-name').textContent = displayName;
    document.getElementById('user-avatar').textContent = displayName.charAt(0).toUpperCase();
  }
  document.getElementById('logout-btn').addEventListener('click', logoutUser);
  document.getElementById('menu-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });
  bindSidebarNavigation();
}

function showStatus(message, isError = false) {
  statusMessage.textContent = message;
  statusMessage.classList.toggle('is-error', isError);
}

function renderChart(points) {
  const values = points.map((point) => point.equity);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const chartWidth = 756;
  const chartHeight = 170;
  const top = 15;
  const left = 2;
  const line = points.map((point, index) => {
    const x = left + index / Math.max(points.length - 1, 1) * chartWidth;
    const y = top + (maximum - point.equity) / range * chartHeight;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  document.getElementById('rl-chart-line').setAttribute('points', line.join(' '));
  document.getElementById('rl-chart-start').textContent = points[0]?.date || '';
  document.getElementById('rl-chart-end').textContent = points.at(-1)?.date || '';
}

function renderActions(actions) {
  const body = document.getElementById('rl-actions');
  body.replaceChildren();
  document.getElementById('rl-empty-actions').hidden = actions.length > 0;
  for (const action of [...actions].reverse()) {
    const row = document.createElement('tr');
    const date = document.createElement('td');
    const name = document.createElement('td');
    const price = document.createElement('td');
    date.textContent = action.date;
    name.textContent = action.action;
    name.className = `rl-action-${action.action}`;
    price.textContent = currency.format(action.price);
    row.append(date, name, price);
    body.append(row);
  }
}

function renderResults(result) {
  resultsSection.hidden = false;
  document.getElementById('rl-result-title').textContent = `${result.symbol} · Q-learning`;
  document.getElementById('rl-result-period').textContent =
    `${result.test_period.start_date} to ${result.test_period.end_date} · unseen evaluation data`;

  const returnValue = document.getElementById('rl-return');
  returnValue.textContent = `${result.return_pct > 0 ? '+' : ''}${result.return_pct}%`;
  returnValue.classList.toggle('is-positive', result.return_pct > 0);
  returnValue.classList.toggle('is-negative', result.return_pct < 0);
  document.getElementById('rl-final-value').textContent = currency.format(result.final_value);
  document.getElementById('rl-capital-label').textContent =
    `from ${currency.format(result.initial_capital)} starting capital`;
  document.getElementById('rl-benchmark').textContent =
    `${result.buy_and_hold_return_pct > 0 ? '+' : ''}${result.buy_and_hold_return_pct}%`;
  document.getElementById('rl-drawdown').textContent = `${result.max_drawdown_pct}%`;
  document.getElementById('rl-trades').textContent = result.total_trades;
  document.getElementById('rl-training-range').textContent =
    `${result.training_period.start_date} — ${result.training_period.end_date}`;
  document.getElementById('rl-training-observations').textContent =
    result.training_period.observations;
  document.getElementById('rl-episodes').textContent = result.episodes;
  document.getElementById('rl-test-range').textContent =
    `${result.test_period.start_date} — ${result.test_period.end_date}`;
  document.getElementById('rl-test-observations').textContent =
    result.test_period.observations;
  renderChart(result.equity_curve);
  renderActions(result.actions);
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadInstruments() {
  if (!localStorage.getItem('algotrade_token')) {
    return;
  }
  try {
    const response = await apiRequest('/api/reinforcement-learning/instruments');
    symbolSelect.replaceChildren(new Option('Choose an instrument', ''));
    for (const instrument of response.data) {
      symbolSelect.add(new Option(
        `${instrument.symbol} · ${instrument.observations.toLocaleString()} candles`,
        instrument.symbol,
      ));
    }
    if (!response.data.length) {
      showStatus('No instruments have enough bundled history for a separate test window.', true);
      return;
    }
    showStatus('Historical CSV data is ready. This experiment runs offline.');
  } catch (error) {
    showStatus(error.message, true);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const symbol = symbolSelect.value;
  if (!symbol) {
    showStatus('Choose an instrument before running the experiment.', true);
    return;
  }

  runButton.disabled = true;
  runButton.querySelector('span').textContent = 'Training agent…';
  resultsSection.hidden = true;
  showStatus('Training on the earlier period, then evaluating on held-out historical data.');
  try {
    const response = await apiRequest('/api/reinforcement-learning/backtest', {
      method: 'POST',
      body: JSON.stringify({
        symbol,
        initial_capital: Number(document.getElementById('rl-capital').value),
      }),
    });
    renderResults(response.data);
    showStatus('Experiment complete. The test period was not used for training.');
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    runButton.disabled = false;
    runButton.querySelector('span').textContent = 'Train & evaluate';
  }
});

loadInstruments();
