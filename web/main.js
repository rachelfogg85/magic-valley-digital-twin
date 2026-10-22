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
  buildFieldFills,
  updateFieldFillHeights,
} from './terrain.js';

const DEFAULT_EXAGGERATION = 4;
const HIGHLIGHT_COLOR = 0xc0392b;
const NORMAL_COLOR = 0x333333;
const DIM_COLOR = 0xdddddd;
const DIMMED_TERRAIN_TINT = 0x999999;

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

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xffffff);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 1, 20000);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setSize(window.innerWidth, window.innerHeight);
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
let fillsByFieldId = null; // Map(fieldId -> Mesh)

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
  camera.position.set(0, span * 0.6, span * 0.6);
  controls.target.set(0, 0, 0);
  controls.update();

  const widthMi = (meta.width * meta.meters_per_pixel / 1609.34).toFixed(1);
  const heightMi = (meta.height * meta.meters_per_pixel / 1609.34).toFixed(1);
  areaSizeEl.textContent = `~${widthMi} x ${heightMi} mi`;

  const legend = await buildLegend();
  buildCropFilter(legend);
  updateLabels();
  wireInteraction();
  animate();
}

async function buildLegend() {
  const legend = await fetch('/data/cdl_legend.json').then((r) => r.json());
  const entries = Object.entries(legend).sort((a, b) => a[1].name.localeCompare(b[1].name));
  legendEl.innerHTML = '<h3>What\'s growing here</h3>' + entries
    .map(([code, info]) => {
      const [r, g, b] = info.color;
      return `<div class="legend-row" title="USDA category: ${info.official_name}"><span class="swatch" style="background: rgb(${r},${g},${b})"></span>${info.name}</div>`;
    })
    .join('');
  return legend;
}

function buildCropFilter(legend) {
  const entries = Object.values(legend).sort((a, b) => a.name.localeCompare(b.name));
  for (const info of entries) {
    const opt = document.createElement('option');
    opt.value = info.name;
    opt.textContent = info.name;
    cropFilterEl.appendChild(opt);
  }
  cropFilterEl.addEventListener('change', applyCropFilter);
}

function applyCropFilter() {
  const target = cropFilterEl.value;
  const year = yearSlider.value;

  // Dim the base crop texture so highlighted fields actually stand out against it,
  // rather than relying on a thin outline color change that's easy to miss.
  if (mesh) mesh.material.color.setHex(target ? DIMMED_TERRAIN_TINT : 0xffffff);

  for (const { fieldId, line } of outlineLines) {
    const crop = fieldData.crops[fieldId]?.[year];
    const matches = Boolean(target) && crop && crop.crop_name === target;
    line.material.color.setHex(!target ? NORMAL_COLOR : matches ? HIGHLIGHT_COLOR : DIM_COLOR);
    const fill = fillsByFieldId.get(fieldId);
    if (fill) fill.visible = matches;
  }
}

function updateLabels() {
  yearLabel.textContent = yearSlider.value;
  exagLabel.textContent = `${exagSlider.value}x`;
}

function wireInteraction() {
  canvas.addEventListener('pointermove', (event) => {
    pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
    pointer.y = -(event.clientY / window.innerHeight) * 2 + 1;
    const field = pickField();
    if (field) {
      tooltipEl.style.display = 'block';
      tooltipEl.style.left = `${event.clientX + 14}px`;
      tooltipEl.style.top = `${event.clientY + 14}px`;
      const crop = fieldData.crops[field.fieldId]?.[yearSlider.value];
      tooltipEl.innerHTML = `<b>Field ${field.fieldId}</b>${field.acres} acres<br>${yearSlider.value}: ${crop ? crop.crop_name : 'no data'}`;
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
  mesh.material.map = loadCdlTexture(yearSlider.value);
  mesh.material.needsUpdate = true;
  if (cropFilterEl.value) applyCropFilter();
});

exagSlider.addEventListener('input', () => {
  updateLabels();
  if (!mesh || !currentMeta) return;
  const exaggeration = Number(exagSlider.value);
  applyExaggeration(mesh.geometry, currentMeta, currentHeights, exaggeration);
  if (outlineLines) updateFieldOutlineHeights(outlineLines, currentMeta, currentHeights, exaggeration);
  if (fillsByFieldId) updateFieldFillHeights(fillsByFieldId, currentMeta, currentHeights, exaggeration);
});

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
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
