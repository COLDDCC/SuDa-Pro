// Minimal WeChat mini-program runtime mock: Page(), setData, wx.* — wx.request hits the real backend.
const path = require('path');
const MP = path.resolve(__dirname, '../../../miniprogram');
const storage = {};
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
  navigateTo: (o) => log.push(['navigateTo', o.url, o]),
  navigateBack: () => log.push(['navigateBack']),
  redirectTo: (o) => log.push(['redirectTo', o.url]),
  switchTab: (o) => log.push(['switchTab', o.url]),
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
