const { call } = require('../../utils/request.js');

Page({
  data: {
    warehouse: null,
    notices: [],
    lines: [],
    feeNotes: [],
    serviceWechat: '',
    weightInput: '',
    valueInput: '',
    feeResult: [],
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadWarehouse();
    this.loadNotices();
    this.loadFeeInfo();
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

  // 「国际物流费用说明」：线路价格 + 囤货/航班等规则
  loadFeeInfo() {
    call('System.Address.lineList', {}).then((lines) => this.setData({ lines })).catch(() => {});
    call('System.Config.feeNotes', {})
      .then((res) => this.setData({ feeNotes: res.notes, serviceWechat: res.service_wechat }))
      .catch(() => {});
  },

  onCopyAddress() {
    if (!this.data.warehouse) return;
    const w = this.data.warehouse;
    wx.setClipboardData({
      data: `${w.address}\n【务必备注会员代码：${w.member_code}】`,
    });
  },

  onCopyWechat() {
    if (this.data.serviceWechat) wx.setClipboardData({ data: this.data.serviceWechat });
  },

  onWeightInput(e) {
    this.setData({ weightInput: e.detail.value });
  },

  onValueInput(e) {
    this.setData({ valueInput: e.detail.value });
  },

  onEstimateFee() {
    const weight = parseFloat(this.data.weightInput);
    if (!weight || weight <= 0) {
      wx.showToast({ title: '请输入有效重量(kg)', icon: 'none' });
      return;
    }
    const params = { weight };
    const value = parseFloat(this.data.valueInput);
    if (value > 0) params.value = value;
    call('System.Address.estimateFee', params)
      .then((result) => this.setData({ feeResult: result }))
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
