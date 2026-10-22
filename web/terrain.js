import * as THREE from 'three';

export async function loadTerrainData() {
  const [meta, heightBuffer] = await Promise.all([
    fetch('/data/terrain_meta.json').then((r) => r.json()),
    fetch('/data/heightmap.bin').then((r) => r.arrayBuffer()),
  ]);
  const heights = new Float32Array(heightBuffer);
  return { meta, heights };
}

// PlaneGeometry builds its vertex buffer row by row in the same order our heightmap
// array was written (row 0 = north edge, row-major), so heights[i] lines up directly
// with the geometry's i-th vertex -- no extra row/col bookkeeping needed.
export function buildTerrainGeometry(meta, heights, exaggeration) {
  const { width, height, meters_per_pixel: mpp } = meta;
  const geometry = new THREE.PlaneGeometry(width * mpp, height * mpp, width - 1, height - 1);
  geometry.rotateX(-Math.PI / 2);
  applyExaggeration(geometry, meta, heights, exaggeration);
  return geometry;
}

export function applyExaggeration(geometry, meta, heights, exaggeration) {
  const position = geometry.attributes.position;
  const base = meta.min_elevation_m;
  for (let i = 0; i < heights.length; i++) {
    position.setY(i, (heights[i] - base) * exaggeration);
  }
  position.needsUpdate = true;
  geometry.computeVertexNormals();
}

export function loadCdlTexture(year) {
  const loader = new THREE.TextureLoader();
  const texture = loader.load(`/data/cdl_${year}.png`);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  return texture;
}
