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

  // 从地址选择页返回时 onShow 也会触发：这里刷新数据但保留用户已经做的选择，
  // 不然刚选好的地址会被默认地址覆盖、选好的线路会被重置成第一条。
  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadPackages();
    this.loadLines();
    if (!this.data.address) this.loadDefaultAddress();
  },

  loadPackages() {
    call('System.Order.goodsList', {}).then((list) => {
      const eligible = list.filter((p) => p.status === 'pending' || p.status === 'inbound');
      const eligibleIds = eligible.map((p) => p.id);
      const selectedIds = this.data.selectedIds.filter((id) => eligibleIds.includes(id));
      this.setData({ packages: eligible, selectedIds }, () => this.recalc());
    });
  },

  loadLines() {
    call('System.Order.getLine', {}).then((lines) => {
      const current = lines.find((l) => l.id === this.data.lineId) || lines[0];
      this.setData({
        lines,
        lineId: current ? current.id : null,
        selectedLineName: current ? current.name : '',
      }, () => this.recalc());
    });
  },

  loadDefaultAddress() {
    call('System.Member.getMemberAddress', {}).then((addr) => {
      if (!this.data.address) this.setData({ address: addr });
    });
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
  // 选中包裹净重都是 0 时照样问后端：下单会按线路最低计费重量收费，不能显示 ¥0。
  recalc() {
    const selectedPkgs = this.data.packages.filter((p) => this.data.selectedIds.includes(p.id));
    const weight = selectedPkgs.reduce((sum, p) => sum + Number(p.netwt), 0);
    this.setData({ totalWeight: weight.toFixed(2) });

    // 连续勾选/切线路会并发多个请求，只认最后一次的结果，避免旧响应后到把金额盖掉
    const seq = (this.recalcSeq = (this.recalcSeq || 0) + 1);
    if (!this.data.lineId || !selectedPkgs.length) {
      this.setData({ totalFee: '0' });
      return;
    }
    const lineId = this.data.lineId;
    call('System.Address.estimateFee', { weight: weight.toFixed(3) })
      .then((result) => {
        if (seq !== this.recalcSeq) return;
        const matched = result.find((r) => r.line_id === lineId);
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
