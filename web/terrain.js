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

export async function loadFieldData() {
  const [outlines, zoneBuffer, crops] = await Promise.all([
    fetch('/data/field_outlines.json').then((r) => r.json()),
    fetch('/data/field_zone.bin').then((r) => r.arrayBuffer()),
    fetch('/data/field_crops.json').then((r) => r.json()),
  ]);
  return { outlines, zone: new Int16Array(zoneBuffer), crops };
}

function sampleHeight(meta, heights, localX, localZ, exaggeration) {
  const totalWidth = meta.width * meta.meters_per_pixel;
  const totalHeight = meta.height * meta.meters_per_pixel;
  const col = Math.round((localX + totalWidth / 2) / meta.meters_per_pixel);
  const row = Math.round((localZ + totalHeight / 2) / meta.meters_per_pixel);
  const c = Math.min(Math.max(col, 0), meta.width - 1);
  const r = Math.min(Math.max(row, 0), meta.height - 1);
  return (heights[r * meta.width + c] - meta.min_elevation_m) * exaggeration;
}

// Field outlines are drawn as thin loops lifted slightly above the terrain surface
// (sampled per-vertex so they hug the hills) so they stay visible without z-fighting.
export function buildFieldOutlines(outlines, meta, heights, exaggeration) {
  const group = new THREE.Group();
  const lines = [];
  for (const field of outlines) {
    const points = field.ring.map(([x, z]) => {
      const y = sampleHeight(meta, heights, x, z, exaggeration) + 1.5;
      return new THREE.Vector3(x, y, z);
    });
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color: 0x333333 });
    const line = new THREE.LineLoop(geometry, material);
    line.userData.fieldId = field.field_id;
    group.add(line);
    lines.push({ fieldId: field.field_id, acres: field.acres, line });
  }
  return { group, lines };
}

export function updateFieldOutlineHeights(lines, meta, heights, exaggeration) {
  for (const { line } of lines) {
    const pos = line.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      pos.setY(i, sampleHeight(meta, heights, x, z, exaggeration) + 1.5);
    }
    pos.needsUpdate = true;
  }
}

// One solid-colored overlay mesh per field, hidden until a plan is run -- used to
// show the optimizer's recommended crop per field (field-level is the right
// granularity here, since the LP itself decides one crop per whole field).
export function buildFieldFills(outlines, meta, heights, exaggeration) {
  const group = new THREE.Group();
  const fillsByFieldId = new Map();
  for (const field of outlines) {
    const shapePoints = field.ring.map(([x, z]) => new THREE.Vector2(x, z));
    const shape = new THREE.Shape(shapePoints);
    const geometry = new THREE.ShapeGeometry(shape);
    const position = geometry.attributes.position;
    for (let i = 0; i < position.count; i++) {
      const worldX = position.getX(i);
      const worldZ = position.getY(i);
      const y = sampleHeight(meta, heights, worldX, worldZ, exaggeration) + 2.0;
      position.setXYZ(i, worldX, y, worldZ);
    }
    position.needsUpdate = true;
    geometry.computeVertexNormals();
    const material = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.88,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.visible = false;
    group.add(mesh);
    fillsByFieldId.set(field.field_id, mesh);
  }
  return { group, fillsByFieldId };
}

export function updateFieldFillHeights(fillsByFieldId, meta, heights, exaggeration) {
  for (const mesh of fillsByFieldId.values()) {
    const position = mesh.geometry.attributes.position;
    for (let i = 0; i < position.count; i++) {
      const x = position.getX(i);
      const z = position.getZ(i);
      position.setY(i, sampleHeight(meta, heights, x, z, exaggeration) + 2.0);
    }
    position.needsUpdate = true;
  }
}

// Real per-pixel crop codes (same grid as the heightmap, before the display PNG's
// cosmetic upscale/blur) -- used to highlight a chosen crop exactly where it grows,
// rather than approximating by field polygon (which can span several real crops; see
// design.md's note on merged fields).
export async function loadCropCodes(year) {
  const buf = await fetch(`/data/cdl_codes_${year}.bin`).then((r) => r.arrayBuffer());
  return new Uint8Array(buf);
}

export function buildHighlightTexture(codes, width, height, targetCode, highlightColor) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  const imageData = ctx.createImageData(width, height);
  const data = imageData.data;
  const [hr, hg, hb] = highlightColor;
  for (let i = 0; i < codes.length; i++) {
    const o = i * 4;
    if (codes[i] === targetCode) {
      data[o] = hr;
      data[o + 1] = hg;
      data[o + 2] = hb;
    } else {
      data[o] = 225;
      data[o + 1] = 225;
      data[o + 2] = 225;
    }
    data[o + 3] = 255;
  }
  ctx.putImageData(imageData, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  return texture;
}

export function loadCdlTexture(year) {
  const loader = new THREE.TextureLoader();
  const texture = loader.load(`/data/cdl_${year}.png`);
  texture.colorSpace = THREE.SRGBColorSpace;
  // Linear filtering (vs. nearest) softens the raw 10 m pixel grid so field edges
  // don't look like hard blocks up close, and mipmaps keep distant fields from
  // shimmering/aliasing when zoomed out.
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.anisotropy = 8;
  return texture;
}
