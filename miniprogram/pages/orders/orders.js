const { call } = require('../../utils/request.js');
const { orderStatus } = require('../../utils/format.js');

// 和后端的订单状态一一对应。运费线下收，下单后第一站是「待付款」——
// 之前这里把 pending 标成「待发货」，用户点进去看到的其实是等他付钱的单，
// 而「已付款待打包」压根没有入口。
const TABS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待付款' },
  { key: 'paid', label: '待打包' },
  { key: 'shipped', label: '运输中' },
  { key: 'signed', label: '已签收' },
  { key: 'closed', label: '已关闭' },
];

const PAGE_SIZE = 10;

Page({
  data: {
    tabs: TABS,
    activeTab: '',
    list: [],
    page: 1,
    hasMore: true,
    loadingMore: false,
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadList({ reset: true });
  },

  onPullDownRefresh() {
    this.loadList({ reset: true, done: () => wx.stopPullDownRefresh() });
  },

  // 订单可能不止一页，上拉到底自动翻页加载，不然超过第一页的订单永远看不到
  onReachBottom() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    this.loadList({ reset: false });
  },

  loadList({ reset, done } = {}) {
    const page = reset ? 1 : this.data.page;
    this.setData({ loadingMore: true });
    const params = { page, page_size: PAGE_SIZE };
    if (this.data.activeTab) params.status = this.data.activeTab;

    call('System.Order.order', params)
      .then((res) => {
        const newRows = res.list.map((o) => ({ ...o, statusInfo: orderStatus(o.status) }));
        const list = reset ? newRows : this.data.list.concat(newRows);
        this.setData({
          list,
          page: page + 1,
          hasMore: list.length < res.total,
        });
      })
      .finally(() => {
        this.setData({ loadingMore: false });
        done && done();
      });
  },

  onTabTap(e) {
    this.setData({ activeTab: e.currentTarget.dataset.key }, () => this.loadList({ reset: true }));
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/order-detail/order-detail?id=${id}` });
  },
});
