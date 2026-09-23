const { call } = require('../../utils/request.js');
const { orderStatus, packageStatus } = require('../../utils/format.js');
const { BASE_URL: baseUrl } = require('../../utils/config.js');

Page({
  data: {
    order: null,
    service: {},
  },

  onLoad(query) {
    this.orderId = query.id;
    // 费用线下收，订单详情这一页最需要让用户能直接找到客服。
    call('System.Config.customerService')
      .then((service) => this.setData({ service }))
      .catch(() => {});
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadDetail();
  },

  loadDetail() {
    call('System.Order.orderDetail', { order_id: this.orderId }).then((order) => {
      order.statusInfo = orderStatus(order.status);
      order.packages = order.packages.map((p) => {
        const urls = (p.photos || []).map((ph) => baseUrl + ph.url);
        return { ...p, statusInfo: packageStatus(p.status), photoUrls: urls, hasPhotos: urls.length > 0 };
      });
      this.setData({ order });
    });
  },

  onCopyWechat() {
    wx.setClipboardData({
      data: this.data.service.wechat,
      success: () => wx.showToast({ title: '微信号已复制', icon: 'none' }),
    });
  },

  onCopyOrderNo() {
    wx.setClipboardData({
      data: this.data.order.order_no,
      success: () => wx.showToast({ title: '订单号已复制，发给客服即可', icon: 'none' }),
    });
  },

  onConfirmReceived() {
    wx.showModal({
      title: '确认已收到包裹？',
      content: '确认后订单完结，如果包裹有问题请先联系客服',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Order.confirmReceived', { order_id: this.orderId })
          .then(() => {
            wx.showToast({ title: '已确认签收' });
            this.loadDetail();
          })
          .catch(() => {});
      },
    });
  },

  onPreviewPhoto(e) {
    const { urls, current } = e.currentTarget.dataset;
    wx.previewImage({ urls, current });
  },

  onCloseOrder() {
    wx.showModal({
      title: '确认关闭订单',
      content: '关闭后包裹会回到"已入库"状态，可以重新下单',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Order.orderClose', { order_id: this.orderId }).then(() => this.loadDetail());
      },
    });
  },
});
