import * as THREE from 'three';
import { OrbitControls } from './vendor/controls/OrbitControls.js';
import {
  loadTerrainData,
  buildTerrainGeometry,
  applyExaggeration,
  loadCdlTexture,
  loadFieldData,
  buildFieldOutlines,
  updateFieldOutlineHeights,
  loadCropCodes,
  buildHighlightTexture,
  buildFieldFills,
  updateFieldFillHeights,
} from './terrain.js';
import { initScenarioPanel, renderResults } from './panel.js';
import { initChat } from './chat.js';

const DEFAULT_EXAGGERATION = 4;
const ZOOM_FACTOR = 0.8;

// Land-cover categories that aren't actually a farmed crop -- shown in their own
// group/section instead of mixed in with real crops.
const NON_CROP_NAMES = new Set([
  'Bare Ground', 'City / Dense Buildings', 'Houses (scattered)', 'Houses / Buildings',
  'Lawn Sod / Grass Seed', 'No Data', 'Pasture / Grazing Land', 'Roads / Yards',
  'Shrubs / Brush', 'Water', 'Wetland (marsh)', 'Wetland (trees)',
]);
const isCrop = (name) => !NON_CROP_NAMES.has(name);

const canvas = document.getElementById('scene');
const yearSlider = document.getElementById('year-slider');
const yearLabel = document.getElementById('year-label');
const exagSlider = document.getElementById('exag-slider');
const exagLabel = document.getElementById('exag-label');
const legendEl = document.getElementById('legend');
const areaSizeEl = document.getElementById('area-size');
const cropFilterEl = document.getElementById('crop-filter');
const tooltipEl = document.getElementById('field-tooltip');
const compassArrow = document.getElementById('compass-arrow');
const zoomInBtn = document.getElementById('zoom-in');
const zoomOutBtn = document.getElementById('zoom-out');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xffffff);

// Size against the canvas's own CSS-determined box, not the window -- on narrow
// screens the canvas is a fixed-height strip above the stacked panels, not the
// full viewport, so window.innerWidth/innerHeight would be wrong here.
function canvasSize() {
  return { width: canvas.clientWidth, height: canvas.clientHeight };
}

const camera = new THREE.PerspectiveCamera(50, canvasSize().width / canvasSize().height, 1, 20000);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setSize(canvasSize().width, canvasSize().height, false);
renderer.setPixelRatio(window.devicePixelRatio);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.0);
sun.position.set(1, 1.5, 1);
scene.add(sun);

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

let mesh = null;
let currentMeta = null;
let currentHeights = null;
let fieldData = null; // { outlines, zone, crops }
let outlineLines = null; // [{ fieldId, acres, line }]
let cropNameToCode = new Map();
let cropNameToColor = new Map();
let fillsByFieldId = null;
let currentPlan = null;
let codeCache = null; // { year, codes: Uint8Array }

async function init() {
  const [{ meta, heights }, fields] = await Promise.all([loadTerrainData(), loadFieldData()]);
  currentMeta = meta;
  currentHeights = heights;
  fieldData = fields;

  const geometry = buildTerrainGeometry(meta, heights, DEFAULT_EXAGGERATION);
  const year = yearSlider.value;
  const texture = loadCdlTexture(year);
  const material = new THREE.MeshStandardMaterial({ map: texture });
  mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  const { group, lines } = buildFieldOutlines(fields.outlines, meta, heights, DEFAULT_EXAGGERATION);
  scene.add(group);
  outlineLines = lines;

  const fills = buildFieldFills(fields.outlines, meta, heights, DEFAULT_EXAGGERATION);
  scene.add(fills.group);
  fillsByFieldId = fills.fillsByFieldId;

  const span = Math.max(meta.width, meta.height) * meta.meters_per_pixel;
  camera.position.set(0, span * 1.0, span * 1.0);
  controls.target.set(0, 0, 0);
  controls.update();

  const widthMi = Math.round(meta.width * meta.meters_per_pixel / 1609.34);
  const heightMi = Math.round(meta.height * meta.meters_per_pixel / 1609.34);
  areaSizeEl.textContent = `~${widthMi} x ${heightMi} mi`;

  const legend = await buildLegend();
  buildCropFilter(legend);
  updateLabels();
  wireInteraction();
  initScenarioPanel(showPlanOnMap);
  initChat(showPlanOnMap);
  animate();
}

// Paints each field with its optimizer-recommended crop color, dims the base crop
// texture so the recommendation reads clearly, and clears any active crop filter
// (the two highlight mechanisms would otherwise fight over the same fields).
function showPlanOnMap(result) {
  if (cropFilterEl.value) {
    cropFilterEl.value = '';
    applyCropFilter();
  }
  currentPlan = result.plan;
  renderResults(result);
  mesh.material.color.setHex(0xaaaaaa);
  for (const [fieldId, fillMesh] of fillsByFieldId) {
    const crop = result.plan[fieldId];
    if (crop) {
      const [r, g, b] = cropNameToColor.get(crop) || [192, 57, 43];
      fillMesh.material.color.setRGB(r / 255, g / 255, b / 255);
      fillMesh.visible = true;
    } else {
      fillMesh.visible = false;
    }
  }
}

function legendRows(entries) {
  return entries
    .map(([code, info]) => {
      const [r, g, b] = info.color;
      return `<div class="legend-row" title="USDA category: ${info.official_name}"><span class="swatch" style="background: rgb(${r},${g},${b})"></span>${info.name}</div>`;
    })
    .join('');
}

async function buildLegend() {
  const legend = await fetch('/data/cdl_legend.json').then((r) => r.json());
  const entries = Object.entries(legend).sort((a, b) => a[1].name.localeCompare(b[1].name));
  const crops = entries.filter(([, info]) => isCrop(info.name));
  const other = entries.filter(([, info]) => !isCrop(info.name));

  legendEl.innerHTML =
    '<h3>What\'s growing here</h3>' + legendRows(crops) +
    (other.length ? '<h3 class="legend-other">Other land cover</h3>' + legendRows(other) : '');

  for (const [code, info] of entries) {
    cropNameToCode.set(info.name, Number(code));
    cropNameToColor.set(info.name, info.color);
  }
  return legend;
}

function buildCropFilter(legend) {
  const entries = Object.values(legend).sort((a, b) => a.name.localeCompare(b.name));
  const crops = entries.filter((info) => isCrop(info.name));
  const other = entries.filter((info) => !isCrop(info.name));

  function addGroup(label, items) {
    const group = document.createElement('optgroup');
    group.label = label;
    for (const info of items) {
      const opt = document.createElement('option');
      opt.value = info.name;
      opt.textContent = info.name;
      group.appendChild(opt);
    }
    cropFilterEl.appendChild(group);
  }
  addGroup('Crops', crops);
  if (other.length) addGroup('Other land cover', other);
  cropFilterEl.addEventListener('change', applyCropFilter);
}

// Highlights the chosen crop pixel-for-pixel (the real classification grid), not by
// field polygon -- a field can be a merged blob of several real crops (see
// design.md), so field-level highlighting was misleading about exactly where a crop
// grows. Everything that isn't the chosen crop fades to light gray.
function clearPlanOverlay() {
  currentPlan = null;
  if (!fillsByFieldId) return;
  for (const fillMesh of fillsByFieldId.values()) fillMesh.visible = false;
}

async function applyCropFilter() {
  const target = cropFilterEl.value;
  const year = yearSlider.value;

  if (!mesh) return;
  clearPlanOverlay();
  mesh.material.color.setHex(0xffffff);
  if (!target) {
    mesh.material.map = loadCdlTexture(year);
    mesh.material.needsUpdate = true;
    return;
  }

  if (!codeCache || codeCache.year !== year) {
    codeCache = { year, codes: await loadCropCodes(year) };
  }
  const targetCode = cropNameToCode.get(target);
  const highlightColor = cropNameToColor.get(target) || [192, 57, 43];
  mesh.material.map = buildHighlightTexture(
    codeCache.codes,
    currentMeta.width,
    currentMeta.height,
    targetCode,
    highlightColor,
  );
  mesh.material.needsUpdate = true;
}

function updateLabels() {
  yearLabel.textContent = yearSlider.value;
  exagLabel.textContent = `${exagSlider.value}x`;
}

function wireInteraction() {
  canvas.addEventListener('pointermove', (event) => {
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    const field = pickField();
    if (field) {
      tooltipEl.style.display = 'block';
      tooltipEl.style.left = `${event.clientX + 14}px`;
      tooltipEl.style.top = `${event.clientY + 14}px`;
      const crop = fieldData.crops[field.fieldId]?.[yearSlider.value];
      const actualLine = `${yearSlider.value} actual: ${crop ? crop.crop_name : 'no data'}`;
      const recommended = currentPlan?.[field.fieldId];
      const planLine = recommended ? `<br>Recommended: ${recommended}` : '';
      tooltipEl.innerHTML = `<b>Field ${field.fieldId}</b>${field.acres} acres<br>${actualLine}${planLine}`;
    } else {
      tooltipEl.style.display = 'none';
    }
  });
  canvas.addEventListener('pointerleave', () => {
    tooltipEl.style.display = 'none';
  });
}

function pickField() {
  if (!mesh || !currentMeta) return null;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObject(mesh);
  if (hits.length === 0) return null;
  const p = hits[0].point;
  const meta = currentMeta;
  const totalWidth = meta.width * meta.meters_per_pixel;
  const totalHeight = meta.height * meta.meters_per_pixel;
  const col = Math.floor((p.x + totalWidth / 2) / meta.meters_per_pixel);
  const row = Math.floor((p.z + totalHeight / 2) / meta.meters_per_pixel);
  if (col < 0 || col >= meta.width || row < 0 || row >= meta.height) return null;
  const zoneIdx = fieldData.zone[row * meta.width + col];
  if (zoneIdx < 0) return null;
  return outlineLines[zoneIdx] ? { fieldId: outlineLines[zoneIdx].fieldId, acres: outlineLines[zoneIdx].acres } : null;
}

yearSlider.addEventListener('input', () => {
  updateLabels();
  if (!mesh) return;
  clearPlanOverlay();
  mesh.material.color.setHex(0xffffff);
  if (cropFilterEl.value) {
    applyCropFilter();
  } else {
    mesh.material.map = loadCdlTexture(yearSlider.value);
    mesh.material.needsUpdate = true;
  }
});

exagSlider.addEventListener('input', () => {
  updateLabels();
  if (!mesh || !currentMeta) return;
  const exaggeration = Number(exagSlider.value);
  applyExaggeration(mesh.geometry, currentMeta, currentHeights, exaggeration);
  if (outlineLines) updateFieldOutlineHeights(outlineLines, currentMeta, currentHeights, exaggeration);
  if (fillsByFieldId) updateFieldFillHeights(fillsByFieldId, currentMeta, currentHeights, exaggeration);
});

function zoom(factor) {
  const offset = new THREE.Vector3().subVectors(camera.position, controls.target);
  offset.multiplyScalar(factor);
  camera.position.copy(controls.target).add(offset);
  controls.update();
}

zoomInBtn.addEventListener('click', () => zoom(ZOOM_FACTOR));
zoomOutBtn.addEventListener('click', () => zoom(1 / ZOOM_FACTOR));

window.addEventListener('resize', () => {
  const { width, height } = canvasSize();
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
});

function updateCompass() {
  // Angle of the camera around the target, in the ground (x,z) plane. The SVG arrow
  // already points toward -z (north in our local mesh space), so rotate it by the
  // same angle the camera has swung, in the opposite direction, to keep it pointing
  // at true north on screen as the user orbits.
  const offset = new THREE.Vector3().subVectors(camera.position, controls.target);
  const angle = Math.atan2(offset.x, offset.z);
  compassArrow.style.transform = `rotate(${angle}rad)`;
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  updateCompass();
  renderer.render(scene, camera);
}

init();
