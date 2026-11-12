import { useCallback, useEffect, useRef, type ComponentType, type Ref } from 'react';
import { type StyleProp, type ViewStyle } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { C } from '@/design';
import { API_BASE } from '@/core/api';
import { MAP_THEME, MapFrame, handleMapEvent, mapState, useMapStatus } from './MapFrame';
import type { MapCoreEvent } from './mapCore';
import type { MapViewProps } from './mapTypes';
import { MAPCORE_SCRIPT, MAPLIBRE_JS } from './mapEngine.generated';
import { MAPLIBRE_CSS } from './mapCss.generated';

export type { Bounds, LatLng, MapPin, MapRegion } from './mapTypes';
export { kmBetween } from './geo';

/* A real street map: MapLibre GL drawing OpenStreetMap vector tiles (OpenFreeMap, no key needed).
   It runs inside a web view, so it looks the same on iOS and Android and works in Expo Go. The MapLibre library and
   the map's behaviour (a generated copy of mapCore.js) are bundled into the app (mapEngine.generated.ts); only the
   tiles, style and label fonts come over the network.
   Swap for @maplibre/maplibre-react-native in a development build if we need native gestures. */

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
<style>${MAPLIBRE_CSS}</style>
<script>${MAPLIBRE_JS}</script>
<style>
html,body,#m{margin:0;padding:0;height:100%;width:100%;background:${C.map};overflow:hidden;-webkit-tap-highlight-color:transparent}
.maplibregl-ctrl-attrib{font:500 9px -apple-system,Roboto,sans-serif}
</style></head><body><div id="m"></div><script>${MAPCORE_SCRIPT}</script><script>
/* a thin shell: the behaviour is mapCore.js (createMapCore), shared with the website */
var ready=false;
function post(o){if(o.type==='ready')ready=true;window.ReactNativeWebView&&window.ReactNativeWebView.postMessage(JSON.stringify(o))}
window.onerror=function(m){post({type:'error',fatal:!ready,msg:String(m)})};
var core=null;
if(!window.maplibregl||!window.createMapCore)post({type:'error',fatal:true,msg:'The map could not start.'});
else try{core=createMapCore(window.maplibregl,document.getElementById('m'),post,${JSON.stringify(MAP_THEME)})}catch(e){post({type:'error',fatal:true,msg:String(e&&e.message||e)})}
window.setMapState=function(s){if(core)core.setState(s)};
</script></body></html>`;

export function MapView(props: MapViewProps) {
  const { height, fill, bare, onPick } = props;
  const ref = useRef<WebViewHandle>(null);
  const status = useMapStatus();
  const { loads, attempt } = status;
  const json = JSON.stringify(mapState(props));
  useEffect(() => {
    if (loads) ref.current?.injectJavaScript(`window.setMapState&&window.setMapState(${json});true;`);
  }, [loads, json]);
  const handlers = useRef(props);
  useEffect(() => { handlers.current = props; });
  const onMessage = useCallback((e: WebViewMessageEvent) => {
    let m: MapCoreEvent;
    try { m = JSON.parse(e.nativeEvent.data); } catch { return; }
    handleMapEvent(m, status, handlers.current);
  }, [status]);
  return (
    <MapFrame height={height} fill={fill} bare={bare} picking={!!onPick} status={status}>
      <Web key={attempt} ref={ref} source={{ html: HTML, baseUrl: `${API_BASE}/` }} originWhitelist={['*']} onMessage={onMessage}
        javaScriptEnabled domStorageEnabled scrollEnabled={false} bounces={false} overScrollMode="never" nestedScrollEnabled
        setSupportMultipleWindows={false} showsHorizontalScrollIndicator={false} showsVerticalScrollIndicator={false}
        onError={() => status.onFatal()}
        style={{ flex: 1, backgroundColor: C.map }} containerStyle={{ backgroundColor: C.map }}
        accessibilityLabel={onPick ? 'Map. Tap your building to place the pin.' : 'Map of PGs'} />
    </MapFrame>
  );
}
