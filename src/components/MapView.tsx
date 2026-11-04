import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type Ref } from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { C, R } from '@/lib/theme';
import { T } from './ui';

/* A real street map: MapLibre GL drawing OpenStreetMap vector tiles (OpenFreeMap, no key needed).
   It runs inside a web view, so it looks the same on iOS and Android and works in Expo Go.
   Swap for @maplibre/maplibre-react-native in a development build if we need native gestures. */
export type LatLng = { lat: number; lng: number };
export type MapPin = LatLng & { id: string; label: string; color: string };
type Props = {
  height?: number;
  pins?: MapPin[];
  center?: LatLng & { label?: string };
  radiusKm?: number;
  zoom?: number;
  /* frame every pin and the centre instead of a fixed zoom */
  fit?: boolean;
  picked?: LatLng | null;
  onPick?: (ll: LatLng) => void;
  onPinPress?: (id: string) => void;
};

/* react-native-webview 14's prop types collapse to `never` under React Native 0.88's types, so we type the props we use. */
type WebViewHandle = { injectJavaScript: (js: string) => void };
type WebViewProps = {
  ref?: Ref<WebViewHandle>; source: { html: string; baseUrl?: string }; originWhitelist?: string[]; onMessage?: (e: WebViewMessageEvent) => void;
  javaScriptEnabled?: boolean; domStorageEnabled?: boolean; scrollEnabled?: boolean; bounces?: boolean; overScrollMode?: 'never'; nestedScrollEnabled?: boolean;
  setSupportMultipleWindows?: boolean; showsHorizontalScrollIndicator?: boolean; showsVerticalScrollIndicator?: boolean;
  onError?: () => void; onHttpError?: () => void; style?: StyleProp<ViewStyle>; containerStyle?: StyleProp<ViewStyle>; accessibilityLabel?: string;
};
const Web = WebView as unknown as ComponentType<WebViewProps>;

const HTML = `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/5.6.0/maplibre-gl.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@700&display=swap">
<script src="https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/5.6.0/maplibre-gl.js"></script>
<style>
html,body,#m{margin:0;padding:0;height:100%;width:100%;background:${C.map};overflow:hidden;-webkit-tap-highlight-color:transparent}
.pin{display:flex;align-items:center;gap:5px;background:#fff;border:1px solid ${C.line};border-radius:999px;padding:4px 9px;font:700 12px Manrope,sans-serif;color:${C.ink};white-space:nowrap;box-shadow:0 1px 2px rgba(17,23,20,.12);cursor:pointer}
.pin i{width:7px;height:7px;border-radius:50%;display:block}
.here{width:12px;height:12px;border-radius:50%;background:${C.ink};border:2px solid #fff;box-shadow:0 0 0 1px rgba(17,23,20,.2)}
.pick{display:flex;flex-direction:column;align-items:center}
.pick b{width:30px;height:30px;border-radius:50%;background:${C.accent};border:3px solid #fff;display:grid;place-items:center;box-shadow:0 1px 3px rgba(17,23,20,.3)}
.pick s{width:3px;height:9px;background:${C.accent};display:block}
.maplibregl-ctrl-attrib{font:500 9px Manrope,sans-serif}
</style></head><body><div id="m"></div><script>
var post=function(o){window.ReactNativeWebView&&window.ReactNativeWebView.postMessage(JSON.stringify(o))};
var lastCam='',map,ready=false,pending=null,markers=[],here=null,pickMk=null,pickOn=false,first=true;
function circle(c,km){var pts=[],n=64,dLat=km/110.574,dLng=km/(111.32*Math.cos(c.lat*Math.PI/180));for(var i=0;i<=n;i++){var a=i/n*2*Math.PI;pts.push([c.lng+dLng*Math.cos(a),c.lat+dLat*Math.sin(a)])}return{type:'Feature',geometry:{type:'Polygon',coordinates:[pts]}}}
function apply(s){
  if(!ready){pending=s;return}
  pickOn=!!s.pick;
  markers.forEach(function(m){m.remove()});markers=[];
  (s.pins||[]).forEach(function(p){var el=document.createElement('div');el.className='pin';el.innerHTML='<i style="background:'+p.color+'"></i>'+p.label;
    el.addEventListener('click',function(e){e.stopPropagation();post({type:'pin',id:p.id})});
    markers.push(new maplibregl.Marker({element:el,anchor:'bottom'}).setLngLat([p.lng,p.lat]).addTo(map))});
  if(here){here.remove();here=null}
  if(s.center&&(s.radiusKm||s.center.label)){var el=document.createElement('div');el.className='here';here=new maplibregl.Marker({element:el}).setLngLat([s.center.lng,s.center.lat]).addTo(map)}
  map.getSource('ring').setData(s.center&&s.radiusKm?circle(s.center,s.radiusKm):{type:'FeatureCollection',features:[]});
  if(s.picked){if(!pickMk){var el=document.createElement('div');el.className='pick';el.innerHTML='<b><svg width="14" height="14" viewBox="0 0 24 24"><path d="M4 11.2 12 5l8 6.2V20h-5.5v-5.2h-5V20H4z" fill="#fff"/></svg></b><s></s>';pickMk=new maplibregl.Marker({element:el,anchor:'bottom'}).setLngLat([s.picked.lng,s.picked.lat]).addTo(map)}else pickMk.setLngLat([s.picked.lng,s.picked.lat])}
  else if(pickMk){pickMk.remove();pickMk=null}
  var pts=(s.pins||[]).map(function(p){return[p.lng,p.lat]});if(s.center)pts.push([s.center.lng,s.center.lat]);
  /* move the camera only when what it frames changes, so a new pick never undoes the owner's panning */
  var cam=JSON.stringify([pts,s.zoom,!!s.fit]);if(cam===lastCam)return;lastCam=cam;
  if(s.fit&&pts.length>1){var b=new maplibregl.LngLatBounds(pts[0],pts[0]);pts.forEach(function(q){b.extend(q)});
    map.fitBounds(b,{padding:{top:44,bottom:30,left:44,right:44},maxZoom:s.zoom||15.5,duration:first?0:450});first=false}
  else if(s.center){var o={center:[s.center.lng,s.center.lat],zoom:s.zoom||14};if(first){map.jumpTo(o);first=false}else map.easeTo(Object.assign(o,{duration:450}))}
}
window.setMapState=function(s){apply(s)};
map=new maplibregl.Map({container:'m',style:'https://tiles.openfreemap.org/styles/positron',center:[76.772,30.755],zoom:13.5,attributionControl:{compact:true},dragRotate:false,pitchWithRotate:false,touchPitch:false,fadeDuration:0});
map.touchZoomRotate.disableRotation();
function init(){
  if(ready||!map.isStyleLoaded())return;
  map.addSource('ring',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
  map.addLayer({id:'ring-fill',type:'fill',source:'ring',paint:{'fill-color':'${C.accent}','fill-opacity':0.07}});
  map.addLayer({id:'ring-line',type:'line',source:'ring',paint:{'line-color':'${C.accent}','line-width':1.4,'line-dasharray':[2,2]}});
  ready=true;post({type:'ready'});if(pending){var p=pending;pending=null;apply(p)}
  var a=document.querySelector('.maplibregl-ctrl-attrib');if(a)a.classList.remove('maplibregl-compact-show');
}
map.on('styledata',init);map.on('load',init);
map.on('click',function(e){if(pickOn)post({type:'pick',lat:e.lngLat.lat,lng:e.lngLat.lng})});
map.on('error',function(e){post({type:'error',msg:String(e&&e.error&&e.error.message||e)})});
</script></body></html>`;

export function MapView({ height = 220, pins = [], center, radiusKm, zoom, fit, picked, onPick, onPinPress }: Props) {
  const ref = useRef<WebViewHandle>(null);
  /* counts 'ready' messages, so the pins are re-sent whenever the web view (re)loads */
  const [loads, setLoads] = useState(0);
  const [failed, setFailed] = useState(false);
  const state = useMemo(() => ({ pins, center, radiusKm, zoom, fit, picked: picked ?? null, pick: !!onPick }), [pins, center, radiusKm, zoom, fit, picked, onPick]);
  const json = JSON.stringify(state);
  useEffect(() => {
    if (loads) ref.current?.injectJavaScript(`window.setMapState&&window.setMapState(${json});true;`);
  }, [loads, json]);
  const onMessage = useCallback((e: WebViewMessageEvent) => {
    let m: { type: string; id?: string; lat?: number; lng?: number };
    try { m = JSON.parse(e.nativeEvent.data); } catch { return; }
    if (m.type === 'ready') setLoads(n => n + 1);
    else if (m.type === 'pin' && m.id) onPinPress?.(m.id);
    else if (m.type === 'pick' && m.lat != null && m.lng != null) onPick?.({ lat: m.lat, lng: m.lng });
  }, [onPick, onPinPress]);
  return (
    <View style={{ height, borderRadius: R.lg, overflow: 'hidden', borderWidth: 1, borderColor: onPick ? C.accent : C.line, backgroundColor: C.map }}>
      <Web ref={ref} source={{ html: HTML, baseUrl: 'https://pakkaghar.app/' }} originWhitelist={['*']} onMessage={onMessage}
        javaScriptEnabled domStorageEnabled scrollEnabled={false} bounces={false} overScrollMode="never" nestedScrollEnabled
        setSupportMultipleWindows={false} showsHorizontalScrollIndicator={false} showsVerticalScrollIndicator={false}
        onError={() => setFailed(true)} onHttpError={() => setFailed(true)}
        style={{ flex: 1, backgroundColor: C.map }} containerStyle={{ backgroundColor: C.map }}
        accessibilityLabel={onPick ? 'Map. Tap your building to place the pin.' : 'Map of PGs'} />
      {!loads && (
        <View pointerEvents="none" style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: C.map }}>
          <T v="sm">{failed ? 'Map needs an internet connection.' : 'Loading map…'}</T>
        </View>
      )}
    </View>
  );
}

/* straight-line distance in km */
export function kmBetween(a: LatLng, b: LatLng) {
  const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}
