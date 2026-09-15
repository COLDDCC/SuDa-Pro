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

  recalc() {
    const selectedPkgs = this.data.packages.filter((p) => this.data.selectedIds.includes(p.id));
    const weight = selectedPkgs.reduce((sum, p) => sum + Number(p.netwt), 0);
    const line = this.data.lines.find((l) => l.id === this.data.lineId);
    if (!line || weight <= 0) {
      this.setData({ totalWeight: weight.toFixed(2), totalFee: '0' });
      return;
    }
    const billable = Math.max(weight, Number(line.min_weight));
    const fee = (billable * Number(line.price_per_kg)).toFixed(2);
    this.setData({ totalWeight: weight.toFixed(2), totalFee: fee });
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
