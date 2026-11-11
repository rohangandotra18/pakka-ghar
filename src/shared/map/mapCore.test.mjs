/* Run with `npm run test:map` (plain node, no framework). Checks mapCore.js against a fake MapLibre and a fake DOM:
   the camera rule, selection, label escaping, clustering, the ready/region events, and that the classic-script copy the
   build script makes for the phone's web view evaluates to a working factory. */
import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));
const source = fs.readFileSync(here + 'mapCore.js', 'utf8');
const { toClassicScript } = createRequire(import.meta.url)('../../../scripts/build-map-engine.js');
/* the real file, as an ES module (a data: URL, because the repo has no "type": "module") */
const { createMapCore } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

/* ---- fakes ---- */
function makeEl(doc, tag) {
  const listeners = {};
  const el = {
    tag, style: { cssText: '' }, attrs: {}, children: [], className: '', textContent: '',
    get firstChild() { return this.children[0] || null; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, removeAttribute(k) { delete this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
    dispatch(t, ev = {}) { (listeners[t] || []).forEach(f => f({ stopPropagation() {}, preventDefault() {}, ...ev })); },
  };
  doc.created.push(el);
  return el;
}
function makeEnv() {
  const doc = { created: [], createElement(tag) { return makeEl(doc, tag); } };
  const container = { ownerDocument: doc };
  const markers = [];
  class Marker {
    constructor(opts) { this.el = opts.element; this.anchor = opts.anchor; this.removed = false; markers.push(this); }
    setLngLat(ll) { this.lngLat = ll; return this; }
    addTo() { return this; }
    remove() { this.removed = true; return this; }
  }
  const maps = [];
  class FakeMap {
    constructor(opts) {
      this.opts = opts; this.handlers = {}; this.sources = {}; this.layers = []; this.camera = [];
      this.styleJson = false; this.rendered = [];
      this.touchZoomRotate = { disableRotation() {} }; this.keyboard = { disableRotation() {} };
      this.canvas = { style: {} }; this.removed = false; this.sourceFeatures = []; this.expansion = [];
      this.view = { w: 76, s: 30, e: 77, n: 31, c: { lng: 76.5, lat: 30.5 }, z: 13.5 };
      maps.push(this);
    }
    on(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
    fire(t, e = {}) { (this.handlers[t] || []).slice().forEach(f => f(e)); }
    addSource(id, spec) {
      if (!this.styleJson) throw new Error('Style is not done loading');
      const src = { spec, data: spec.data, setData: d => { src.data = d; }, getClusterExpansionZoom: id2 => { this.expansion.push(id2); return Promise.resolve(17); } };
      this.sources[id] = src;
    }
    getSource(id) { return this.sources[id]; }
    removeSource(id) { delete this.sources[id]; }
    addLayer(l) { this.layers.push(l); }
    isSourceLoaded() { return true; }
    querySourceFeatures() { return this.sourceFeatures; }
    getCanvas() { return this.canvas; }
    getBounds() { const v = this.view; return { getWest: () => v.w, getSouth: () => v.s, getEast: () => v.e, getNorth: () => v.n }; }
    getCenter() { return this.view.c; }
    getZoom() { return this.view.z; }
    fitBounds(b, o) { this.camera.push(['fitBounds', b, o]); this.fire('moveend', {}); }
    jumpTo(o) { this.camera.push(['jumpTo', o]); this.fire('moveend', {}); }
    easeTo(o) { this.camera.push(['easeTo', o]); this.fire('moveend', {}); }
    remove() { this.removed = true; }
  }
  const maplibregl = { Map: FakeMap, Marker };
  return { doc, container, markers, maps, maplibregl };
}
function boot(createFn = createMapCore) {
  const env = makeEnv();
  const events = [];
  const core = createFn(env.maplibregl, env.container, e => events.push(e), { accent: '#0E6B50', ink: '#111714', line: '#E2E7E3' });
  const map = env.maps[0];
  return { ...env, core, map, events };
}
function makeReady(t) {
  t.map.styleJson = true; t.map.fire('styledata'); t.map.fire('render');
}
const A = { id: 'a', lat: 30.75, lng: 76.77, label: '₹8k', color: '#f00' };
const B = { id: 'b', lat: 30.76, lng: 76.78, label: '₹9k', color: '#00f', title: 'Sunrise PG' };
const C0 = { lat: 30.755, lng: 76.772 };
const base = { pins: [A, B], center: C0, zoom: 15, fit: false, picked: null, pick: false, selectedId: null, cluster: false };
const live = markers => markers.filter(m => !m.removed);
const moves = map => map.camera.length;

let passed = 0;
function test(name, fn) {
  return Promise.resolve().then(fn).then(() => { passed++; console.log('ok  ' + name); }, err => { console.error('FAIL ' + name); throw err; });
}

await test('ready waits for the style and the first drawn frame, not `load`', () => {
  const t = boot();
  t.map.fire('render');
  assert.equal(t.events.length, 0, 'a frame before the style is usable is not ready');
  t.map.fire('styledata'); // addSource throws until the style JSON is loaded
  assert.equal(t.events.length, 0);
  t.map.styleJson = true; t.map.fire('styledata');
  assert.equal(t.events.length, 0, 'style alone is not enough');
  t.map.fire('render');
  assert.deepEqual(t.events.map(e => e.type), ['ready']);
  assert.ok(t.map.sources.ring && t.map.sources.pins);
  t.map.fire('render');
  assert.equal(t.events.filter(e => e.type === 'ready').length, 1);
});

await test('state sent before ready is applied once ready; first region is not by the user', () => {
  const t = boot();
  t.core.setState(base);
  assert.equal(live(t.markers).length, 0);
  makeReady(t);
  assert.equal(live(t.markers).filter(m => m.el.attrs['aria-label']).length, 2 + 0);
  assert.equal(t.map.camera[0][0], 'jumpTo');
  const regions = t.events.filter(e => e.type === 'region');
  assert.equal(regions.length, 1);
  assert.equal(regions[0].byUser, false);
  assert.deepEqual(Object.keys(regions[0].bounds).sort(), ['east', 'north', 'south', 'west']);
});

await test('fit false: pins changing never move the camera; center or zoom does', () => {
  const t = boot(); makeReady(t); t.core.setState(base);
  const n = moves(t.map);
  t.core.setState({ ...base, pins: [A] });
  t.core.setState({ ...base, pins: [A, B, { ...A, id: 'c', lat: 31, lng: 77 }] });
  t.core.setState({ ...base, pins: [] });
  assert.equal(moves(t.map), n, 'pins must not move the camera');
  t.core.setState({ ...base, pins: [], center: { lat: 30.8, lng: 76.9 } });
  assert.equal(moves(t.map), n + 1);
  assert.equal(t.map.camera.at(-1)[0], 'easeTo');
  t.core.setState({ ...base, pins: [], center: { lat: 30.8, lng: 76.9 }, zoom: 16 });
  assert.equal(moves(t.map), n + 2);
  t.core.setState({ ...base, pins: [A], center: { lat: 30.8, lng: 76.9 }, zoom: 16 });
  assert.equal(moves(t.map), n + 2);
});

await test('fit true: the camera follows the set of points', () => {
  const t = boot(); makeReady(t); t.core.setState({ ...base, fit: true });
  assert.equal(t.map.camera.at(-1)[0], 'fitBounds');
  const n = moves(t.map);
  t.core.setState({ ...base, fit: true });
  assert.equal(moves(t.map), n, 'same points: no move');
  t.core.setState({ ...base, fit: true, pins: [A, B, { ...A, id: 'c', lat: 31.2, lng: 77.1 }] });
  assert.equal(moves(t.map), n + 1);
  const [name, b, o] = t.map.camera.at(-1);
  assert.equal(name, 'fitBounds');
  assert.deepEqual(b, [[76.77, 30.75], [77.1, 31.2]]);
  assert.equal(o.maxZoom, 15);
  t.core.setState({ ...base, fit: true, pins: [A, B, { ...A, id: 'c', lat: 31.2, lng: 77.1 }], picked: { lat: 30.9, lng: 76.9 } });
  assert.equal(moves(t.map), n + 1, 'a pick is not a camera change');
  /* turning fit off with the same center and zoom does not move */
  t.core.setState({ ...base, fit: false });
  assert.equal(moves(t.map), n + 1);
});

await test('a new picked point never moves the camera and shows one marker', () => {
  const t = boot(); makeReady(t); t.core.setState({ ...base, pins: [], pick: true });
  const n = moves(t.map), before = t.markers.length;
  t.core.setState({ ...base, pins: [], pick: true, picked: { lat: 30.7, lng: 76.7 } });
  t.core.setState({ ...base, pins: [], pick: true, picked: { lat: 30.71, lng: 76.71 } });
  assert.equal(moves(t.map), n);
  assert.equal(t.markers.length - before, 1, 'the pick marker is created once and then moved');
  assert.deepEqual(t.markers.at(-1).lngLat, [76.71, 30.71]);
  assert.equal(t.map.canvas.style.cursor, 'crosshair');
  t.core.setState({ ...base, pins: [], pick: true, picked: null });
  assert.equal(t.markers.at(-1).removed, true);
  t.map.fire('click', { lngLat: { lat: 1, lng: 2 } });
  assert.deepEqual(t.events.at(-1), { type: 'pick', lat: 1, lng: 2 });
  t.core.setState({ ...base, pins: [], pick: false });
  t.map.fire('click', { lngLat: { lat: 3, lng: 4 } });
  assert.notEqual(t.events.at(-1).lat, 3, 'no pick event when picking is off');
});

await test('byUser is true only for moves MapLibre attributes to input', () => {
  const t = boot(); makeReady(t); t.core.setState(base);
  const n = t.events.filter(e => e.type === 'region').length;
  t.core.setState({ ...base, zoom: 16 }); // easeTo from code
  t.map.fire('moveend', { originalEvent: { type: 'mouseup' } });
  t.map.fire('moveend', { originalEvent: undefined });
  const r = t.events.filter(e => e.type === 'region').slice(n);
  assert.deepEqual(r.map(x => x.byUser), [false, true, false]);
});

await test('selectedId restyles one pin without rebuilding markers or moving the camera', () => {
  const t = boot(); makeReady(t); t.core.setState(base);
  const made = t.markers.length, n = moves(t.map), regions = t.events.length;
  t.core.setState({ ...base, selectedId: 'b' });
  assert.equal(t.markers.length, made);
  assert.equal(moves(t.map), n);
  assert.equal(t.events.length, regions);
  const el = id => t.markers.find(m => m.el.attrs['aria-label'] === (id === 'a' ? '₹8k' : 'Sunrise PG')).el;
  assert.equal(el('b').style.background, '#0E6B50');
  assert.equal(el('b').style.color, '#fff');
  assert.equal(el('b').style.zIndex, '10');
  assert.equal(el('b').attrs['aria-current'], 'true');
  assert.equal(el('a').style.background, '#fff');
  t.core.setState({ ...base, selectedId: 'a' });
  assert.equal(t.markers.length, made);
  assert.equal(el('b').style.background, '#fff');
  assert.equal(el('a').style.zIndex, '10');
  /* an equal but new pins array does not rebuild either */
  t.core.setState({ ...base, selectedId: 'a', pins: [{ ...A }, { ...B }] });
  assert.equal(t.markers.length, made);
});

await test('pins are accessible, press by click or key, and labels are text, never markup', () => {
  const evil = '<img src=x onerror=alert(1)>';
  const t = boot(); makeReady(t);
  t.core.setState({ ...base, pins: [{ ...A, label: evil }, B] });
  const evilMarker = t.markers.find(m => m.el.children[1] && m.el.children[1].textContent === evil);
  assert.ok(evilMarker, 'label is the textContent of a span');
  assert.equal(evilMarker.el.attrs['aria-label'], evil, 'falls back to the label (as an attribute value, not markup)');
  assert.equal(evilMarker.el.attrs.role, 'button');
  assert.equal(evilMarker.el.attrs.tabindex, '0');
  assert.ok(!t.doc.created.some(e => e.tag === 'img'), 'no <img> element was ever created');
  assert.ok(!t.doc.created.some(e => 'innerHTML' in e), 'innerHTML is never touched');
  const b = t.markers.find(m => m.el.attrs.title === 'Sunrise PG');
  assert.ok(b, 'title is used for aria-label and tooltip');
  b.el.dispatch('click');
  b.el.dispatch('keydown', { key: 'Enter' });
  b.el.dispatch('keydown', { key: 'a' });
  assert.deepEqual(t.events.filter(e => e.type === 'pin'), [{ type: 'pin', id: 'b' }, { type: 'pin', id: 'b' }]);
});

await test('cluster: groups come from the clustering source, press zooms in, close pins show singly', async () => {
  const t = boot(); makeReady(t);
  t.core.setState({ ...base, cluster: true });
  assert.equal(live(t.markers).length, 0, 'nothing drawn until the source reports');
  assert.equal(t.map.sources.pins.data.features.length, 2);
  assert.equal(t.map.sources.pins.spec.cluster, true);
  t.map.sourceFeatures = [
    { properties: { cluster: true, cluster_id: 7, point_count: 6 }, geometry: { coordinates: [76.9, 30.9] } },
    { properties: { cluster: true, cluster_id: 7, point_count: 6 }, geometry: { coordinates: [76.9, 30.9] } }, // same cluster seen in two tiles
    { properties: { id: 'a' }, geometry: { coordinates: [76.77, 30.75] } },
  ];
  t.map.fire('sourcedata', { sourceId: 'pins' });
  const cl = live(t.markers).find(m => m.el.attrs['aria-label'] === '6 PGs, zoom in');
  assert.ok(cl, 'cluster marker with an accessible label');
  assert.equal(cl.el.textContent, '6');
  assert.equal(live(t.markers).length, 2, 'one cluster and one single pin');
  const n = moves(t.map);
  cl.el.dispatch('click');
  await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(t.map.expansion, [7]);
  assert.deepEqual(t.map.camera.at(-1), ['easeTo', { center: [76.9, 30.9], zoom: 17, duration: 450 }]);
  assert.equal(moves(t.map), n + 1);
  const region = t.events.filter(e => e.type === 'region').at(-1);
  assert.equal(region.byUser, false, 'a cluster zoom started by the code is not the person moving the map');
  /* zoomed in: every pin individually, and the cluster marker goes away */
  t.map.sourceFeatures = [
    { properties: { id: 'a' }, geometry: { coordinates: [76.77, 30.75] } },
    { properties: { id: 'b' }, geometry: { coordinates: [76.78, 30.76] } },
  ];
  t.map.fire('moveend', {});
  assert.deepEqual(live(t.markers).map(m => m.el.attrs['aria-label']).sort(), ['Sunrise PG', '₹8k'].sort());
  /* turning clustering off goes back to plain pins and empties the source */
  t.core.setState({ ...base, cluster: false });
  assert.equal(t.map.sources.pins.data.features.length, 0);
  assert.equal(live(t.markers).length, 2);
});

await test('errors: fatal before ready, not after; a failed Map constructor is reported', () => {
  const t = boot();
  t.map.fire('error', { error: { message: 'boom' } });
  assert.deepEqual(t.events.at(-1), { type: 'error', fatal: true, msg: 'boom' });
  makeReady(t);
  t.map.fire('error', { error: { message: 'tile 404' } });
  assert.equal(t.events.at(-1).fatal, false);
  const env = makeEnv();
  env.maplibregl.Map = class { constructor() { throw new Error('Failed to initialize WebGL'); } };
  const events = [];
  const core = createMapCore(env.maplibregl, env.container, e => events.push(e), null);
  assert.deepEqual(events, [{ type: 'error', fatal: true, msg: 'Failed to initialize WebGL' }]);
  core.setState(base); core.destroy();
});

await test('destroy removes markers and the map', () => {
  const t = boot(); makeReady(t); t.core.setState({ ...base, picked: { lat: 30.7, lng: 76.7 }, selectedId: 'a' });
  t.core.destroy();
  assert.equal(live(t.markers).length, 0);
  assert.equal(t.map.removed, true);
  t.core.setState(base);
  assert.equal(live(t.markers).length, 0);
});

await test('the build script\'s web view copy evaluates to a working factory', () => {
  const script = toClassicScript(source);
  assert.ok(!/^export /m.test(script));
  const ctx = vm.createContext({});
  vm.runInContext(script, ctx);
  assert.equal(typeof ctx.createMapCore, 'function');
  assert.equal(Object.keys(ctx).join(), 'createMapCore', 'nothing else leaks into the global scope');
  const t = boot(ctx.createMapCore);
  makeReady(t);
  t.core.setState({ ...base, selectedId: 'a' });
  assert.deepEqual(t.events.map(e => e.type), ['ready', 'region']);
  assert.equal(live(t.markers).length, 2);
  assert.equal(t.map.camera[0][0], 'jumpTo');
  /* the generated file, when present, holds exactly this text */
  const gen = here + 'mapEngine.generated.ts';
  if (fs.existsSync(gen)) {
    const m = fs.readFileSync(gen, 'utf8').match(/^export const MAPCORE_SCRIPT = (.*);$/m);
    assert.ok(m, 'MAPCORE_SCRIPT is exported');
    assert.equal(JSON.parse(m[1]), script, 'run `npm run map:engine` after editing mapCore.js');
  }
});

await test('the build script refuses a mapCore.js whose shape it cannot convert', () => {
  const bad = [
    ['no factory', 'const x = 1;\n'],
    ['two factories', source + '\nexport function createMapCore() {}\n'],
    ['another export', source + '\nexport const other = 1;\n'],
    ['an import', 'import x from "y";\n' + source],
    ['does not parse', source + '\n}}}\n'],
  ];
  for (const [why, text] of bad) assert.throws(() => toClassicScript(text), /mapCore\.js/, why);
});

console.log(`\n${passed} tests passed`);
