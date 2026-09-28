const { call } = require('./request.js');

// 订阅消息（入库/发货/签收通知）。
// 微信要求 wx.requestSubscribeMessage 必须在用户点击的回调里"同步"调用——先 await 一个网络请求
// 再调会报 "can only be invoked by user TAP gesture"。所以模板 ID 在页面加载时先取好（prefetch），
// 点击时直接用缓存的 ID 弹窗。后端没配置模板时 ID 为空，什么都不弹。
let cached = null;

function prefetch() {
  if (cached) return Promise.resolve(cached);
  return call('System.Config.subscribeTemplates', {})
    .then((ids) => { cached = ids || {}; return cached; })
    .catch(() => ({}));
}

// events: ['inbound'] / ['shipped', 'signed']。用户拒绝或出错都当作正常情况，永远 resolve。
function request(events) {
  const tmplIds = events.map((e) => cached && cached[e]).filter(Boolean);
  if (!tmplIds.length || !wx.requestSubscribeMessage) return Promise.resolve();
  return new Promise((resolve) => {
    wx.requestSubscribeMessage({ tmplIds, complete: () => resolve() });
  });
}

module.exports = { prefetch, request };
