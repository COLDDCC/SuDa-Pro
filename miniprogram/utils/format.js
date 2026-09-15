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

module.exports = { packageStatus, orderStatus };
