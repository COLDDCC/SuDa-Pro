const { call } = require('../../utils/request.js');
const { packageStatus } = require('../../utils/format.js');

const TABS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待入库' },
  { key: 'inbound', label: '已入库' },
  { key: 'ordered', label: '待发货' },
  { key: 'shipped', label: '已发货' },
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
    call('System.Order.goodsList', this.data.activeTab ? { status: this.data.activeTab } : {})
      .then((list) => {
        this.setData({
          list: list.map((p) => ({ ...p, statusInfo: packageStatus(p.status) })),
        });
      })
      .finally(() => done && done());
  },

  onTabTap(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ activeTab: key }, () => this.loadList());
  },

  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认删除',
      content: '删除后不可恢复',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Order.delectGood', { id }).then(() => this.loadList());
      },
    });
  },

  goForecast() {
    wx.navigateTo({ url: '/pages/forecast/forecast' });
  },

  goCreateOrder() {
    wx.navigateTo({ url: '/pages/order-create/order-create' });
  },
});
