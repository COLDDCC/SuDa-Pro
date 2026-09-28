const { call } = require('../../utils/request.js');
const { orderStatus, packageStatus, formatTime } = require('../../utils/format.js');

Page({
  data: {
    order: null,
  },

  onLoad(query) {
    this.orderId = query.id;
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadDetail();
  },

  onPullDownRefresh() {
    this.loadDetail(() => wx.stopPullDownRefresh());
  },

  loadDetail(done) {
    call('System.Order.orderDetail', { order_id: this.orderId })
      .then((order) => {
        order.statusInfo = orderStatus(order.display_status);
        order.hasStorageFee = Number(order.storage_fee) > 0;
        order.packages = order.packages.map((p) => ({ ...p, statusInfo: packageStatus(p.status) }));
        // 最新的轨迹放最上面
        order.tracks = order.tracks.map((t) => ({ ...t, time: formatTime(t.time) })).reverse();
        this.setData({ order });
      })
      .finally(() => done && done());
  },

  onCopyWechat() {
    wx.setClipboardData({ data: this.data.order.service_wechat });
  },

  onCopyInter() {
    wx.setClipboardData({ data: this.data.order.inter_order });
  },

  onConfirmReceipt() {
    wx.showModal({
      title: '确认收货',
      content: '确认已经收到这个订单的全部包裹了吗？',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Order.confirmReceipt', { order_id: this.orderId }).then(() => {
          wx.showToast({ title: '已确认收货' });
          this.loadDetail();
        });
      },
    });
  },

  onCloseOrder() {
    wx.showModal({
      title: '确认关闭订单',
      content: '关闭后包裹会回到下单前的状态，可以重新下单',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Order.orderClose', { order_id: this.orderId }).then(() => this.loadDetail());
      },
    });
  },
});
