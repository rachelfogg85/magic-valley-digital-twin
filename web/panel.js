const waterSlider = document.getElementById('water-slider');
const waterLabel = document.getElementById('water-label');
const priceCaseSelect = document.getElementById('price-case');
const runBtn = document.getElementById('run-plan-btn');
const resultsEl = document.getElementById('scenario-results');
const yearSlider = document.getElementById('year-slider');

const fmtMoney = (n) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

waterSlider.addEventListener('input', () => {
  waterLabel.textContent = `${waterSlider.value}%`;
});

function acresTable(acresByCrop) {
  const rows = Object.entries(acresByCrop).sort((a, b) => b[1] - a[1]);
  if (rows.length === 0) return '<div class="sub">(all fields fallow)</div>';
  return (
    '<table>' +
    rows.map(([crop, acres]) => `<tr><td>${crop}</td><td>${acres.toLocaleString()} ac</td></tr>`).join('') +
    '</table>'
  );
}

export function renderResults(result) {
  const waterTag = result.binding_constraints.includes('water')
    ? '<span class="binding-tag">limit reached</span>'
    : '';
  const capTags = result.binding_constraints
    .filter((c) => c.endsWith('_contract_cap'))
    .map((c) => `<span class="binding-tag">${c.replace('_contract_cap', '').replace('_', ' ')} capped</span>`)
    .join('');

  const actualBlock = result.actual_profit_mid != null
    ? `<div class="result-block">
        <b>What was actually planted this year</b>
        ${acresTable(result.actual_acres_by_crop)}
        <div class="sub">Actual estimated profit (typical prices): ${fmtMoney(result.actual_profit_mid)}</div>
      </div>`
    : '';

  resultsEl.innerHTML = `
    <div class="result-block">
      <b>Estimated profit</b>
      <div class="profit-range">${fmtMoney(result.profit_low)} &ndash; ${fmtMoney(result.profit_high)}</div>
      <div class="sub">Typical-price estimate: ${fmtMoney(result.profit_mid)}</div>
    </div>
    <div class="result-block">
      <b>Water used</b>
      ${result.total_water_af.toLocaleString()} of ${result.water_limit_af.toLocaleString()} acre-feet ${waterTag}
    </div>
    <div class="result-block">
      <b>Recommended plan</b>
      ${acresTable(result.acres_by_crop)}
      ${capTags}
    </div>
    ${actualBlock}
  `;
}

export function initScenarioPanel(onPlanReady) {
  runBtn.addEventListener('click', async () => {
    runBtn.disabled = true;
    runBtn.textContent = 'Running...';
    try {
      const resp = await fetch('/api/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          water_pct: Number(waterSlider.value),
          year: Number(yearSlider.value),
          price_case: priceCaseSelect.value,
          use_rotation: true,
        }),
      });
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
      const result = await resp.json();
      onPlanReady(result); // calls renderResults() and recolors the map
    } catch (err) {
      resultsEl.innerHTML = `<div class="result-block sub">Couldn't run the plan: ${err.message}</div>`;
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = 'Run plan';
    }
  });
}
