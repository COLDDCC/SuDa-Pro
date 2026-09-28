// Minimal WeChat mini-program runtime mock: Page(), setData, wx.* — wx.request hits the real backend.
const path = require('path');
const MP = path.resolve(__dirname, '../../../miniprogram');
const storage = {};
const TABBAR = JSON.parse(require('fs').readFileSync(path.join(MP, 'app.json'))).tabBar.list.map((t) => '/' + t.pagePath);
const isTab = (url) => TABBAR.includes(url.split('?')[0]);
// 跟真机一样：navigateTo/redirectTo 不能去 tabBar 页，switchTab 只能去 tabBar 页，违反时抛错让测试失败
function nav(kind, o, tabOnly) {
  if (isTab(o.url) !== tabOnly) throw new Error(`wx.${kind} cannot open ${o.url}`);
  log.push([kind, o.url, o]);
}
const log = [];
let pending = 0;
global.wx = {
  getStorageSync: (k) => storage[k] || '',
  setStorageSync: (k, v) => { storage[k] = v; },
  removeStorageSync: (k) => { delete storage[k]; },
  showToast: (o) => log.push(['toast', o.title]),
  showLoading: (o) => log.push(['loading', o.mask]),
  hideLoading: () => {},
  showModal: (o) => o.success({ confirm: true }),
  reLaunch: (o) => log.push(['reLaunch', o.url]),
  navigateTo: (o) => nav('navigateTo', o, false),
  navigateBack: () => log.push(['navigateBack']),
  redirectTo: (o) => nav('redirectTo', o, false),
  switchTab: (o) => nav('switchTab', o, true),
  stopPullDownRefresh: () => {},
  request(o) {
    pending++;
    const delay = global.__delay ? global.__delay(o.data) : 0;
    setTimeout(() => fetch(o.url, { method: 'POST', headers: o.header, body: JSON.stringify(o.data) })
      .then((r) => r.json()).then((data) => o.success({ data }), (e) => o.fail(e))
      .finally(() => pending--), delay);
  },
};
global.getApp = () => ({ ensureLogin: () => !!storage.token });
let captured;
global.Page = (def) => { captured = def; };
function loadPage(name) {
  const file = path.join(MP, 'pages', name, name + '.js');
  delete require.cache[file];
  require(file);
  const page = Object.assign({}, captured);
  page.data = JSON.parse(JSON.stringify(captured.data));
  page.setData = function (patch, cb) {
    for (const [k, v] of Object.entries(patch)) {
      const parts = k.split('.');
      let o = this.data;
      while (parts.length > 1) o = o[parts.shift()];
      o[parts[0]] = v;
    }
    cb && cb.call(this);
  };
  page.getOpenerEventChannel = () => page.__channel;
  return page;
}
const idle = async () => { await new Promise((r) => setTimeout(r, 20)); while (pending) await new Promise((r) => setTimeout(r, 10)); await new Promise((r) => setTimeout(r, 20)); };
const { call } = require(path.join(MP, 'utils/request.js'));
module.exports = { loadPage, idle, storage, log, call };
