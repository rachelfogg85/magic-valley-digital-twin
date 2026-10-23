const waterSlider = document.getElementById('water-slider');
const waterLabel = document.getElementById('water-label');
const priceCaseSelect = document.getElementById('price-case');
const runBtn = document.getElementById('run-plan-btn');
const resultsEl = document.getElementById('scenario-results');
const yearSlider = document.getElementById('year-slider');

const fmtMoney = (n) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const fmtNum = (n) => Math.round(n).toLocaleString('en-US');

// Minimal CSV parser that respects quoted fields (crop_params.csv's source column
// contains commas inside quotes).
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [header, ...body] = rows.filter((r) => r.length > 1 || r[0]);
  return body.map((r) => Object.fromEntries(header.map((h, i) => [h, r[i]])));
}

let cropParamsByName = null;
async function loadCropParams() {
  if (cropParamsByName) return cropParamsByName;
  const text = await fetch('/data/crop_params.csv').then((r) => r.text());
  cropParamsByName = Object.fromEntries(parseCsv(text).map((row) => [row.crop, row]));
  return cropParamsByName;
}

function assumptionsTable(params, crops) {
  const rows = crops
    .filter((c) => c !== 'Fallow' && params[c])
    .map((c) => {
      const p = params[c];
      return `<tr><td>${c}</td><td>$${fmtNum(Number(p.price_mid))}/${p.unit}</td>` +
        `<td>${fmtNum(Number(p.yield_mid))} ${p.unit}/ac</td>` +
        `<td>$${fmtNum(Number(p.cost_per_acre))}/ac</td></tr>`;
    });
  if (rows.length === 0) return '';
  return `
    <details class="result-block">
      <summary style="cursor:pointer; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted);">How profit is calculated</summary>
      <table style="margin-top:6px;">
        <tr><th>Crop</th><th>Price (typical)</th><th>Yield (typical)</th><th>Cost</th></tr>
        ${rows.join('')}
      </table>
      <div class="sub">Profit per acre = price &times; yield &minus; cost, then &times; acres. Low/high use the same formula with low/high price and yield instead.
      Units: bu = bushel, cwt = hundredweight (100 lb), ton = 2,000 lb, ac = acre, AF = acre-foot (water to cover 1 acre, 1 foot deep).</div>
      <div class="sub"><a href="https://github.com/rachelfogg85/magic-valley-digital-twin/blob/main/data/processed/crop_params.csv" target="_blank" rel="noopener">View crop_params.csv on GitHub</a> for every number's exact source, or
      <a href="https://github.com/rachelfogg85/magic-valley-digital-twin/tree/main/data/processed" target="_blank" rel="noopener">browse all the data</a> this app uses.</div>
    </details>`;
}

waterSlider.addEventListener('input', () => {
  waterLabel.textContent = `${waterSlider.value}%`;
});

function acresTable(acresByCrop) {
  const rows = Object.entries(acresByCrop).sort((a, b) => b[1] - a[1]);
  if (rows.length === 0) return '<div class="sub">(all fields fallow)</div>';
  return (
    '<table>' +
    rows.map(([crop, acres]) => `<tr><td>${crop}</td><td>${fmtNum(acres)} ac</td></tr>`).join('') +
    '</table>'
  );
}

export async function renderResults(result) {
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
        <div class="sub">Actual estimated profit: ${fmtMoney(result.actual_profit_low)} &ndash; ${fmtMoney(result.actual_profit_high)} (typical ${fmtMoney(result.actual_profit_mid)})</div>
      </div>`
    : '';

  const params = await loadCropParams();
  const allCrops = [...new Set([...Object.keys(result.acres_by_crop), ...Object.keys(result.actual_acres_by_crop || {})])];
  const totalAcres = Object.values(result.acres_by_crop).reduce((a, b) => a + b, 0);
  const cropCount = Object.keys(result.acres_by_crop).length;

  resultsEl.innerHTML = `
    <div class="result-block">
      <b>Estimated profit</b>
      <div class="profit-range">${fmtMoney(result.profit_low)} &ndash; ${fmtMoney(result.profit_high)}</div>
      <div class="sub">Typical estimate: ${fmtMoney(result.profit_mid)}</div>
      <div class="sub">For all ${fmtNum(totalAcres)} acres, ${cropCount} crop${cropCount === 1 ? '' : 's'}, one ${yearSlider.value} growing season.</div>
    </div>
    <div class="result-block">
      <b>Water used</b>
      ${fmtNum(result.total_water_af)} of ${fmtNum(result.water_limit_af)} acre-feet ${waterTag}
    </div>
    <div class="result-block">
      <b>Recommended plan</b>
      ${acresTable(result.acres_by_crop)}
      ${capTags}
    </div>
    ${actualBlock}
    ${assumptionsTable(params, allCrops)}
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
