const PACKAGE_STATUS = {
  pending: { text: '待入库', cls: 'tag-pending' },
  inbound: { text: '已入库', cls: 'tag-inbound' },
  // 订单可能还在待付款，从包裹角度说「已下单」才准确
  ordered: { text: '已下单', cls: 'tag-ordered' },
  shipped: { text: '已发货', cls: 'tag-shipped' },
  cancelled: { text: '已取消', cls: 'tag-cancelled' },
};

const ORDER_STATUS = {
  // 运费线下收，所以下单后第一站是「待付款」——客户得先联系客服转账，
  // 客服确认收款后仓库才会打包。
  pending: { text: '待付款', cls: 'tag-pending' },
  paid: { text: '已付款·待打包', cls: 'tag-ordered' },
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
