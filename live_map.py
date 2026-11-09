"""AMap display and tightly scoped local security-code proxy."""
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def proxy_response(request_path, config):
    parsed = urlsplit(request_path)
    routes = {
        '/_AMapService/v3/log/init': 'https://restapi.amap.com/v3/log/init',
        '/_AMapService/v4/map/styles': 'https://webapi.amap.com/v4/map/styles',
        '/_AMapService/v3/assistant/coordinate/convert': 'https://restapi.amap.com/v3/assistant/coordinate/convert',
    }
    if parsed.path not in routes or len(parsed.query) > 12000:
        raise ValueError('Unsupported map request')
    params = [(k, v) for k, v in parse_qsl(parsed.query, max_num_fields=40)
              if k.lower() not in ('key', 'jscode')]
    callback = dict(params).get('callback')
    if callback and not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$.]*', callback):
        raise ValueError('Invalid callback')
    params.extend([('key', config['js_key']), ('jscode', config['security_code'])])
    url = routes[parsed.path] + '?' + urlencode(params)
    with build_opener(NoRedirect()).open(Request(url), timeout=10) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError('Map response too large')
        # Never return a provider response that echoes the server-side secret.
        if config['security_code'].encode('ascii') in body:
            raise ValueError('Unexpected map response')
        content_type = 'application/javascript; charset=utf-8' if callback else response.headers.get('Content-Type', 'application/json')
        return body, content_type


def map_widget(community, rows, radius, config, fallback):
    if not config:
        return '<p class="map-status">未配置在线地图，当前显示位置示意图。</p>' + fallback
    points = [dict(id=community['id'], name=community['name'], kind='community',
                   position=[community['longitude'], community['latitude']])]
    points += [dict(id=row['id'], name=row['name'], kind=row['kind'],
                    position=[row['longitude'], row['latitude']]) for row in rows]
    data = json.dumps(dict(key=config['js_key'], points=points, radius=radius), ensure_ascii=True).replace('<', '\\u003c')
    return '''<div id="live-map" aria-label="周边高德地图" style="height:360px;width:100%"></div>
<p id="map-status" class="map-status" role="status">正在加载高德地图…</p>
<button type="button" id="map-reset" hidden>查看全部地点</button>
<details id="map-fallback"><summary>查看离线位置示意图</summary>''' + fallback + '''</details>
<script id="map-data" type="application/json">''' + data + '''</script>
<script>
(() => {
  const data = JSON.parse(document.getElementById('map-data').textContent);
  const status = document.getElementById('map-status');
  const fallback = document.getElementById('map-fallback');
  let finished = false, map;
  function fail(message) {
    if (finished) return;
    finished = true;
    status.textContent = message + '，仍可使用下方示意图和地点列表。';
    document.getElementById('live-map').hidden = true;
    fallback.open = true;
    if (map) map.destroy();
  }
  const timer = setTimeout(() => fail('地图加载超时，请检查网络或地图配置'), 45000);
  window._AMapSecurityConfig = {serviceHost: location.origin + '/_AMapService'};
  const sdk = document.createElement('script');
  sdk.src = 'https://webapi.amap.com/maps?v=2.0&key=' + encodeURIComponent(data.key);
  sdk.onerror = () => fail('地图脚本加载失败');
  sdk.onload = async () => {
    if (finished) return;
    try {
      if (!window.AMap) throw new Error();
      const positions = [];
      // Convert each reference point explicitly; keep results in memory only.
      for (const point of data.points) {
        if (finished) return;
        const converted = await new Promise((resolve, reject) => {
          AMap.convertFrom(point.position, 'gps', (state, result) => {
            if (state === 'complete' && result.locations && result.locations.length === 1)
              resolve(result.locations[0]);
            else reject(new Error('conversion'));
          });
        });
        positions.push(converted);
      }
      if (finished) return;
      map = new AMap.Map('live-map', {center: positions[0], zoom: 14, viewMode: '2D'});
      const circle = new AMap.Circle({center:positions[0], radius:data.radius,
        strokeColor:'#8871cd', strokeWeight:1, fillColor:'#8871cd', fillOpacity:0.08});
      map.add(circle);
      const markers = [];
      data.points.forEach((point, i) => {
        const content = document.createElement('button');
        content.type = 'button';
        content.className = 'live-pin ' + point.kind;
        content.textContent = i === 0 ? '家' : String(i);
        content.setAttribute('aria-label', '查看 ' + point.name);
        const marker = new AMap.Marker({position:positions[i], content:content, anchor:'center', title:point.name});
        marker.on('click', () => {
          const card = document.getElementById('place-' + point.id);
          if (card) { location.hash = card.id; card.focus({preventScroll:true}); }
          status.textContent = point.name + ' · 区域参考点，具体入口待核实';
        });
        map.add(marker); markers.push(marker);
        const card = document.getElementById('place-' + point.id);
        if (card) {
          const locate = document.createElement('button');
          locate.type = 'button'; locate.className = 'locate-place'; locate.textContent = '在地图中查看';
          locate.onclick = () => {
            map.setZoomAndCenter(16, positions[i]);
            document.getElementById('live-map').scrollIntoView({block:'center'});
            status.textContent = point.name + ' · 区域参考点，具体入口待核实';
          };
          card.appendChild(locate);
        }
      });
      const reset = document.getElementById('map-reset');
      reset.onclick = () => map.setFitView([circle, ...markers], false, [35,35,35,35]);
      map.on('complete', () => {
        if (finished) return;
        finished = true; clearTimeout(timer);
        status.textContent = '地图已加载 · 可拖动、滚轮缩放；点编号查看详情。位置为区域参考点。';
        reset.hidden = false;
      });
      reset.onclick();
    } catch (error) { fail('地图或坐标转换失败' + (error.message.startsWith('conversion:') ? '（' + error.message.slice(11) + '）' : '') + '，请检查配置与服务权限'); }
  };
  document.head.appendChild(sdk);
})();
</script>'''
