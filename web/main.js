import * as THREE from 'three';
import { OrbitControls } from './vendor/controls/OrbitControls.js';
import { loadTerrainData, buildTerrainGeometry, applyExaggeration, loadCdlTexture } from './terrain.js';

const DEFAULT_EXAGGERATION = 4;

const canvas = document.getElementById('scene');
const yearSlider = document.getElementById('year-slider');
const yearLabel = document.getElementById('year-label');
const exagSlider = document.getElementById('exag-slider');
const exagLabel = document.getElementById('exag-label');
const legendEl = document.getElementById('legend');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xcfd8dc);

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

let mesh = null;
let currentMeta = null;
let currentHeights = null;

async function init() {
  const { meta, heights } = await loadTerrainData();
  currentMeta = meta;
  currentHeights = heights;

  const geometry = buildTerrainGeometry(meta, heights, DEFAULT_EXAGGERATION);
  const year = yearSlider.value;
  const texture = loadCdlTexture(year);
  const material = new THREE.MeshStandardMaterial({ map: texture });
  mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  const span = Math.max(meta.width, meta.height) * meta.meters_per_pixel;
  camera.position.set(0, span * 0.6, span * 0.6);
  controls.target.set(0, 0, 0);
  controls.update();

  await buildLegend();
  updateLabels();
  animate();
}

async function buildLegend() {
  const legend = await fetch('/data/cdl_legend.json').then((r) => r.json());
  const entries = Object.entries(legend).sort((a, b) => a[1].name.localeCompare(b[1].name));
  legendEl.innerHTML = '<h3>Crops in this area</h3>' + entries
    .map(([code, info]) => {
      const [r, g, b] = info.color;
      return `<div class="legend-row"><span class="swatch" style="background: rgb(${r},${g},${b})"></span>${info.name}</div>`;
    })
    .join('');
}

function updateLabels() {
  yearLabel.textContent = yearSlider.value;
  exagLabel.textContent = `${exagSlider.value}x`;
}

yearSlider.addEventListener('input', () => {
  updateLabels();
  if (!mesh) return;
  mesh.material.map = loadCdlTexture(yearSlider.value);
  mesh.material.needsUpdate = true;
});

exagSlider.addEventListener('input', () => {
  updateLabels();
  if (!mesh || !currentMeta) return;
  applyExaggeration(mesh.geometry, currentMeta, currentHeights, Number(exagSlider.value));
});

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

init();
