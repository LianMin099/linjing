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
        '/_AMapService/v3/place/around': 'https://restapi.amap.com/v3/place/around',
    }
    if parsed.path not in routes or len(parsed.query) > 12000:
        raise ValueError('Unsupported map request')
    params = [(k, v) for k, v in parse_qsl(parsed.query, max_num_fields=40)
              if k.lower() not in ('key', 'jscode')]
    callback = dict(params).get('callback')
    if callback and not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$.]*', callback):
        raise ValueError('Invalid callback')
    web_request = parsed.path in ('/_AMapService/v3/log/init',
                                  '/_AMapService/v3/assistant/coordinate/convert',
                                  '/_AMapService/v3/place/around')
    if web_request and not config.get('web_key'):
        raise ValueError('Web service key is not configured')
    params.append(('key', config['web_key'] if web_request else config['js_key']))
    if not web_request:
        params.append(('jscode', config['security_code']))
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


def map_widget(community, rows, radius, config, fallback, school=None):
    if not config:
        return '<p class="map-status">未配置在线地图，当前显示位置示意图。</p>' + fallback
    if not config.get('web_key'):
        return '<p class="map-status">在线地图还缺少高德 Web 服务 Key。请运行「配置地图.cmd」补填后重新启动。</p>' + fallback
    points = [dict(id=community['id'], name=community['name'], kind='community',
                   position=[community['longitude'], community['latitude']])]
    points += [dict(id=row['id'], name=row['name'], kind=row['kind'],
                    position=[row['longitude'], row['latitude']]) for row in rows]
    data = json.dumps(dict(key=config['js_key'], points=points, radius=radius, school=school), ensure_ascii=True).replace('<', '\\u003c')
    return '''<div id="live-map" aria-label="周边高德地图" style="height:360px;width:100%"></div>
<p id="map-status" class="map-status" role="status">正在加载高德地图…</p>
<button type="button" id="map-reset" hidden>查看全部地点</button>
<div id="amap-live-search" hidden>
<h4>高德实时查找</h4>
<p>按学校周边 3 公里临时查看高德地点。结果由高德直接显示，不计入邻境已入库数量。</p>
<button type="button" data-amap-search="银行">查银行</button>
<button type="button" data-amap-search="住宅小区">查小区</button>
<button type="button" id="amap-search-clear">清除实时结果</button>
<p id="amap-search-status" role="status">点击按钮后开始搜索。</p>
<div id="amap-search-results"></div>
</div>
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
      async function convertGps(position) {
        const query = new URLSearchParams({locations:position.join(','), coordsys:'gps', output:'json'});
        const response = await fetch('/_AMapService/v3/assistant/coordinate/convert?' + query);
        if (!response.ok) throw new Error('conversion:http');
        const result = await response.json();
        if (result.status !== '1' || typeof result.locations !== 'string')
          throw new Error('conversion:service');
        const converted = result.locations.split(',').map(Number);
        if (converted.length !== 2 || !converted.every(Number.isFinite))
          throw new Error('conversion:coordinates');
        return converted;
      }
      const positions = [];
      // Convert each reference point explicitly; keep results in memory only.
      for (const point of data.points) {
        if (finished) return;
        positions.push(await convertGps(point.position));
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
      if (Array.isArray(data.school) && data.school.length === 2) {
        const livePanel = document.getElementById('amap-live-search');
        const searchStatus = document.getElementById('amap-search-status');
        const resultPanel = document.getElementById('amap-search-results');
        let searchMarkers = [];
        let schoolCenter = null;
        livePanel.hidden = false;
        function clearResults() {
          map.remove(searchMarkers);
          searchMarkers = [];
          resultPanel.replaceChildren();
        }
        document.querySelectorAll('[data-amap-search]').forEach(button => {
          button.addEventListener('click', async () => {
            button.disabled = true;
            searchStatus.textContent = '正在查询学校附近的' + button.dataset.amapSearch + '…';
            try {
              if (!schoolCenter) schoolCenter = await convertGps(data.school);
              const query = new URLSearchParams({location:schoolCenter.join(','), radius:'3000',
                keywords:button.dataset.amapSearch, offset:'20', page:'1', output:'json'});
              const response = await fetch('/_AMapService/v3/place/around?' + query);
              if (!response.ok) throw new Error('http');
              const result = await response.json();
              if (result.status !== '1' || !Array.isArray(result.pois)) throw new Error('service');
              clearResults();
              for (const poi of result.pois) {
                const name = String(poi.name || '未命名地点');
                const address = String(poi.address || '地址未知');
                const point = String(poi.location || '').split(',').map(Number);
                const item = document.createElement('div');
                item.className = 'amap-result';
                const title = document.createElement('strong'); title.textContent = name;
                const detail = document.createElement('span'); detail.textContent = address;
                item.append(title, detail); resultPanel.append(item);
                if (point.length === 2 && point.every(Number.isFinite)) {
                  const marker = new AMap.Marker({position:point, title:name});
                  marker.on('click', () => { searchStatus.textContent = name + ' · 高德实时候选'; });
                  map.add(marker); searchMarkers.push(marker);
                  item.addEventListener('click', () => map.setZoomAndCenter(16, point));
                }
              }
              searchStatus.textContent = '本页显示 ' + result.pois.length + ' 条高德实时候选；未加入邻境数据库。';
            } catch (_) {
              searchStatus.textContent = '学校坐标转换或地点搜索失败，请检查服务权限或稍后再试。';
            }
            button.disabled = false;
          });
        });
        document.getElementById('amap-search-clear').onclick = () => {
          clearResults();
          searchStatus.textContent = '已清除实时结果。';
          reset.onclick();
        };
      }
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
