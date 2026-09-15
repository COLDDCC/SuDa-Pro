const { call } = require('../../utils/request.js');

Page({
  data: {
    packages: [],
    selectedIds: [],
    lines: [],
    lineId: null,
    selectedLineName: '',
    address: null,
    remark: '',
    totalWeight: '0',
    totalFee: '0',
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadPackages();
    this.loadLines();
    this.loadDefaultAddress();
  },

  loadPackages() {
    call('System.Order.goodsList', {}).then((list) => {
      const eligible = list.filter((p) => p.status === 'pending' || p.status === 'inbound');
      this.setData({ packages: eligible });
    });
  },

  loadLines() {
    call('System.Order.getLine', {}).then((lines) => {
      this.setData({ lines });
      if (lines.length) {
        this.setData({ lineId: lines[0].id, selectedLineName: lines[0].name }, () => this.recalc());
      }
    });
  },

  loadDefaultAddress() {
    call('System.Member.getMemberAddress', {}).then((addr) => this.setData({ address: addr }));
  },

  onTogglePackage(e) {
    const id = e.currentTarget.dataset.id;
    let selected = this.data.selectedIds.slice();
    if (selected.includes(id)) {
      selected = selected.filter((x) => x !== id);
    } else {
      selected.push(id);
    }
    this.setData({ selectedIds: selected }, () => this.recalc());
  },

  onLineChange(e) {
    const line = this.data.lines[e.detail.value];
    this.setData({ lineId: line.id, selectedLineName: line.name }, () => this.recalc());
  },

  // 重量只是本地求和，展示用的运费一律问后端要（System.Address.estimateFee），
  // 不在前端重新实现一遍四舍五入逻辑，避免和后端算出来的最终金额不一致。
  recalc() {
    const selectedPkgs = this.data.packages.filter((p) => this.data.selectedIds.includes(p.id));
    const weight = selectedPkgs.reduce((sum, p) => sum + Number(p.netwt), 0);
    this.setData({ totalWeight: weight.toFixed(2) });

    if (!this.data.lineId || weight <= 0) {
      this.setData({ totalFee: '0' });
      return;
    }
    call('System.Address.estimateFee', { weight })
      .then((result) => {
        const matched = result.find((r) => r.line_id === this.data.lineId);
        this.setData({ totalFee: matched ? matched.fee : '0' });
      })
      .catch(() => {});
  },

  onRemarkInput(e) {
    this.setData({ remark: e.detail.value });
  },

  goChooseAddress() {
    wx.navigateTo({
      url: '/pages/address-list/address-list?select=1',
      events: {
        selectAddress: (addr) => this.setData({ address: addr }),
      },
    });
  },

  onSubmit() {
    if (!this.data.address) return wx.showToast({ title: '请选择收件地址', icon: 'none' });
    if (!this.data.selectedIds.length) return wx.showToast({ title: '请选择包裹', icon: 'none' });
    if (!this.data.lineId) return wx.showToast({ title: '请选择物流线路', icon: 'none' });

    wx.showLoading({ title: '提交中...' });
    call('System.Order.savePage', {
      address_id: this.data.address.id,
      line_id: this.data.lineId,
      package_ids: this.data.selectedIds,
      remark: this.data.remark,
    })
      .then(() => {
        wx.hideLoading();
        wx.showToast({ title: '下单成功' });
        setTimeout(() => wx.redirectTo({ url: '/pages/orders/orders' }), 800);
      })
      .catch(() => wx.hideLoading());
  },
});
