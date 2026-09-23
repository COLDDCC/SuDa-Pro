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
    fees: [],
    selectedLine: null,
    declaredValue: '0',
  },

  onLoad(query) {
    // 从首页计算器跳过来时会带上用户刚选中的线路，这里记下来，
    // loadLines 拿到数据后用它做默认选中。
    this.presetLineId = query.line_id ? Number(query.line_id) : null;
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadPackages();
    this.loadLines();
    this.loadDefaultAddress();
  },

  loadPackages() {
    // 只有已入库的包裹能下单：还没到仓的东西既没称重也没法合箱打包，
    // 放进来只会让用户选了半天再被后端打回来。
    call('System.Order.goodsList', { status: 'inbound' }).then((list) => {
      this.setData({
        packages: list.map((p) => ({
          ...p,
          photoCharged: (p.photos || []).some((ph) => ph.kind === 'inbound'),
        })),
      });
    });
  },

  loadLines() {
    call('System.Order.getLine', {}).then((lines) => {
      this.setData({ lines });
      if (lines.length) {
        const preset = lines.find((l) => l.id === this.presetLineId) || lines[0];
        this.setData({
          lineId: preset.id, selectedLineName: preset.name, selectedLine: preset,
        }, () => this.recalc());
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
    this.setData({ selectedIds: selected }, () => {
      this.refreshDeclaredValue();
      this.recalc();
    });
  },

  onLineChange(e) {
    const line = this.data.lines[e.detail.value];
    this.setData({
      lineId: line.id, selectedLineName: line.name, selectedLine: line,
    }, () => this.recalc());
  },

  // 申报价值决定能走哪条线，选包裹时就把这个数亮出来，省得提交后才被打回。
  // 后端有权威校验，这里只是提前提示。
  refreshDeclaredValue() {
    const total = this.data.packages
      .filter((p) => this.data.selectedIds.includes(p.id))
      .reduce((sum, p) => sum + (Number(p.cc_registered_price) || Number(p.price) || 0), 0);
    this.setData({ declaredValue: total.toFixed(2) });
  },

  // 费用一律问后端要（System.Order.previewFee），前端一个数都不自己算。
  // 这个接口和真正下单时用的是同一个函数，所以这里显示多少，提交后就扣多少。
  recalc() {
    if (!this.data.lineId || !this.data.selectedIds.length) {
      this.setData({ totalWeight: '0', totalFee: '0', fees: [] });
      return;
    }
    call('System.Order.previewFee', {
      line_id: this.data.lineId,
      package_ids: this.data.selectedIds,
    })
      .then((preview) => this.setData({
        totalWeight: preview.total_weight,
        totalFee: preview.total_fee,
        fees: preview.fees,
      }))
      .catch(() => this.setData({ totalFee: '0', fees: [] }));
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
