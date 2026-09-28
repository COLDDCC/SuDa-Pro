const { call } = require('../../utils/request.js');
const { orderStatus } = require('../../utils/format.js');

const TABS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '未发货' },
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
    // 切 tab 时上一个 tab 的请求可能还没回来，它晚到的结果不能拼进/覆盖新 tab 的列表
    const seq = (this.loadSeq = (this.loadSeq || 0) + 1);
    this.setData({ loadingMore: true });
    const params = { page, page_size: PAGE_SIZE };
    if (this.data.activeTab) params.status = this.data.activeTab;

    call('System.Order.order', params)
      .then((res) => {
        if (seq !== this.loadSeq) return;
        const newRows = res.list.map((o) => ({ ...o, statusInfo: orderStatus(o.display_status) }));
        const list = reset ? newRows : this.data.list.concat(newRows);
        this.setData({
          list,
          page: page + 1,
          hasMore: list.length < res.total,
        });
      })
      .finally(() => {
        if (seq === this.loadSeq) this.setData({ loadingMore: false });
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
