const { call } = require('../../utils/request.js');
const { BASE_URL: baseUrl } = require('../../utils/config.js');

Page({
  data: {
    list: [],
    expressNum: '',
    loading: true,
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadList();
  },

  onPullDownRefresh() {
    this.loadList(() => wx.stopPullDownRefresh());
  },

  loadList(done) {
    // 列表只给单号后四位——完整单号摆出来，任何人都能照着认领别人的包裹。
    call('System.Order.unclaimedList', {})
      .then((list) => this.setData({
        list: list.map((u) => ({ ...u, photoFull: u.photo_url ? baseUrl + u.photo_url : '' })),
      }))
      .finally(() => {
        this.setData({ loading: false });
        done && done();
      });
  },

  onExpressInput(e) {
    this.setData({ expressNum: e.detail.value });
  },

  // 点列表里某一条只是把后四位填进输入框提示一下，完整单号还得用户自己填，
  // 这是这个功能唯一的门槛，不能省。
  onPickHint(e) {
    wx.showToast({
      title: `请填写以 ${e.currentTarget.dataset.tail} 结尾的完整单号`,
      icon: 'none',
      duration: 2500,
    });
  },

  onPreviewPhoto(e) {
    wx.previewImage({ urls: [e.currentTarget.dataset.url] });
  },

  onClaim() {
    const num = this.data.expressNum.trim();
    if (!num) return wx.showToast({ title: '请填写完整的快递单号', icon: 'none' });

    wx.showLoading({ title: '认领中...' });
    call('System.Order.claimPackage', { express_num: num })
      .then((pkg) => {
        wx.hideLoading();
        wx.showModal({
          title: '认领成功',
          content: `「${pkg.good_name}」已经进了你的包裹列表，可以直接去下单发货了`,
          showCancel: false,
          success: () => wx.switchTab({ url: '/pages/packages/packages' }),
        });
      })
      .catch(() => wx.hideLoading());
  },
});
