const { call } = require('../../utils/request.js');
const { orderStatus } = require('../../utils/format.js');

const TABS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待发货' },
  { key: 'shipped', label: '运输中' },
  { key: 'signed', label: '已签收' },
  { key: 'closed', label: '已关闭' },
];

Page({
  data: {
    tabs: TABS,
    activeTab: '',
    list: [],
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadList();
  },

  onPullDownRefresh() {
    this.loadList(() => wx.stopPullDownRefresh());
  },

  loadList(done) {
    call('System.Order.order', this.data.activeTab ? { status: this.data.activeTab } : {})
      .then((res) => {
        this.setData({
          list: res.list.map((o) => ({ ...o, statusInfo: orderStatus(o.status) })),
        });
      })
      .finally(() => done && done());
  },

  onTabTap(e) {
    this.setData({ activeTab: e.currentTarget.dataset.key }, () => this.loadList());
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/order-detail/order-detail?id=${id}` });
  },
});
