const PACKAGE_STATUS = {
  pending: { text: '待入库', cls: 'tag-pending' },
  inbound: { text: '已入库', cls: 'tag-inbound' },
  ordered: { text: '待发货', cls: 'tag-ordered' },
  shipped: { text: '已发货', cls: 'tag-shipped' },
  cancelled: { text: '已取消', cls: 'tag-cancelled' },
};

const ORDER_STATUS = {
  pending: { text: '待发货', cls: 'tag-pending' },
  shipped: { text: '运输中', cls: 'tag-shipped' },
  signed: { text: '已签收', cls: 'tag-inbound' },
  closed: { text: '已关闭', cls: 'tag-closed' },
};

function packageStatus(status) {
  return PACKAGE_STATUS[status] || { text: status, cls: '' };
}

function orderStatus(status) {
  return ORDER_STATUS[status] || { text: status, cls: '' };
}

// 后端返回的时间是不带时区的 UTC（Python datetime.utcnow().isoformat()，
// 形如 2026-09-27T04:02:26.935417），直接显示既难看又比北京时间慢 8 小时。
// 手动解析而不是 new Date(str)：iOS 上 6 位小数秒的字符串解析会得到 Invalid Date。
function formatTime(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(iso || '');
  if (!m) return iso || '';
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

module.exports = { packageStatus, orderStatus, formatTime };
