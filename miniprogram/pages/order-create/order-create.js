const { call } = require('../../utils/request.js');
const subscribe = require('../../utils/subscribe.js');

Page({
  data: {
    packages: [],
    selectedIds: [],
    lines: [],
    lineId: null,
    selectedLineName: '',
    selectedLineDesc: '',
    address: null,
    remark: '',
    totalWeight: '0',
    totalFee: '0',
    feeEstimated: false, // 有包裹还没称重：金额是按预报重量估的
    lineUnavailable: '', // 选中的线路不适用的原因（比如价值超限）
  },

  onLoad() {
    subscribe.prefetch();
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
        selectedLineDesc: current ? current.description : '',
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
    this.setData({ lineId: line.id, selectedLineName: line.name, selectedLineDesc: line.description }, () => this.recalc());
  },

  // 重量只是本地求和，展示用的运费一律问后端要（System.Address.estimateFee），
  // 不在前端重新实现一遍四舍五入逻辑，避免和后端算出来的最终金额不一致。
  // 重量：已入库的用仓库实际称重，没入库的用预报时填的重量（预估）。
  // 重量是 0 时照样问后端：按首重收费，不能显示 ¥0。
  recalc() {
    const selectedPkgs = this.data.packages.filter((p) => this.data.selectedIds.includes(p.id));
    const weight = selectedPkgs.reduce((sum, p) => sum + Number(p.actual_weight !== null ? p.actual_weight : p.netwt), 0);
    const value = selectedPkgs.reduce((sum, p) => sum + Number(p.price), 0);
    this.setData({
      totalWeight: weight.toFixed(2),
      feeEstimated: selectedPkgs.some((p) => p.actual_weight === null),
    });

    // 连续勾选/切线路会并发多个请求，只认最后一次的结果，避免旧响应后到把金额盖掉
    const seq = (this.recalcSeq = (this.recalcSeq || 0) + 1);
    if (!this.data.lineId || !selectedPkgs.length) {
      this.setData({ totalFee: '0' });
      return;
    }
    const lineId = this.data.lineId;
    const params = { weight: weight.toFixed(3) };
    if (value > 0) params.value = value.toFixed(2);
    call('System.Address.estimateFee', params)
      .then((result) => {
        if (seq !== this.recalcSeq) return;
        const matched = result.find((r) => r.line_id === lineId);
        this.setData({
          totalFee: matched ? matched.fee : '0',
          lineUnavailable: matched && !matched.available ? matched.unavailable_reason : '',
        });
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
    if (this.data.lineUnavailable) return wx.showToast({ title: this.data.lineUnavailable, icon: 'none' });

    const payload = {
      address_id: this.data.address.id,
      line_id: this.data.lineId,
      package_ids: this.data.selectedIds,
      remark: this.data.remark,
    };
    // 先弹"发货/签收时通知我"的订阅授权（必须在点击回调里同步调用），再提交
    subscribe.request(['shipped', 'signed']).then(() => {
      wx.showLoading({ title: '提交中...', mask: true });
      call('System.Order.savePage', payload)
        .then(() => {
          wx.hideLoading();
          wx.showToast({ title: '下单成功' });
          // orders 是 tabBar 页，redirectTo/navigateTo 跳 tabBar 页会直接失败，必须用 switchTab
          setTimeout(() => wx.switchTab({ url: '/pages/orders/orders' }), 800);
        })
        .catch(() => wx.hideLoading());
    });
  },
});
