const { call } = require('../../utils/request.js');
const { orderStatus, packageStatus } = require('../../utils/format.js');
const { BASE_URL: baseUrl } = require('../../utils/config.js');

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
