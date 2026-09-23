const { call } = require('../../utils/request.js');

Page({
  data: {
    warehouse: null,
    notices: [],
    weightInput: '',
    feeResult: [],
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadWarehouse();
    this.loadNotices();
  },

  loadWarehouse() {
    call('System.Member.getWarehouseList', {})
      .then((list) => {
        if (list && list.length) this.setData({ warehouse: list[0] });
      })
      .catch(() => {});
  },

  loadNotices() {
    call('System.Address.noticeList', {})
      .then((notices) => this.setData({ notices }))
      .catch(() => {});
  },

  goMineForService() {
    wx.switchTab({ url: '/pages/mine/mine' });
  },

  onCopyAddress() {
    if (!this.data.warehouse) return;
    const w = this.data.warehouse;
    wx.setClipboardData({
      data: `${w.address}\n【务必备注会员代码：${w.member_code}】`,
    });
  },

  onWeightInput(e) {
    this.setData({ weightInput: e.detail.value });
  },

  onEstimateFee() {
    const weight = parseFloat(this.data.weightInput);
    if (!weight || weight <= 0) {
      wx.showToast({ title: '请输入有效重量(kg)', icon: 'none' });
      return;
    }
    call('System.Address.estimateFee', { weight })
      .then((result) => // 后端已按价格升序返回。两条线各有便宜的区间（精致小每 0.5kg 跳 ¥35 跳得粗，
        // 无忧草每 0.1kg 跳 ¥8 跳得细，刚跳完档那一段无忧草反而赢），所以哪条更划算
        // 得看具体重量，直接把最便宜的标出来，省得用户自己比。
        this.setData({
          feeResult: result.map((r, i) => ({ ...r, cheapest: i === 0 && result.length > 1 })),
        }))
      .catch(() => {});
  },

  goForecast() {
    wx.navigateTo({ url: '/pages/forecast/forecast' });
  },

  goPackages() {
    wx.switchTab({ url: '/pages/packages/packages' });
  },

  goOrders() {
    wx.switchTab({ url: '/pages/orders/orders' });
  },
});
