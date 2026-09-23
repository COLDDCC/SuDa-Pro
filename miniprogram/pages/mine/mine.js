const { call } = require('../../utils/request.js');

Page({
  data: {
    member: null,
    service: {},
    hasService: false,
  },

  onLoad() {
    // 不做在线支付，钱线下收，用户必须能找到客服。内容在后端 business.py 里配。
    call('System.Config.customerService')
      .then((service) => this.setData({ service, hasService: Object.keys(service).length > 0 }))
      .catch(() => {});
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    call('System.Member.memberInfo', {}).then((member) => this.setData({ member }));
  },

  onCopyWechat() {
    wx.setClipboardData({
      data: this.data.service.wechat,
      success: () => wx.showToast({ title: '微信号已复制', icon: 'none' }),
    });
  },

  onPreviewQrcode() {
    wx.previewImage({ urls: [this.data.service.qrcode] });
  },

  onCallService() {
    wx.makePhoneCall({ phoneNumber: this.data.service.phone });
  },

  goClaim() {
    wx.navigateTo({ url: '/pages/claim/claim' });
  },

  goAddressList() {
    wx.navigateTo({ url: '/pages/address-list/address-list' });
  },

  onLogout() {
    wx.showModal({
      title: '确认退出登录？',
      success: (res) => {
        if (!res.confirm) return;
        wx.removeStorageSync('token');
        wx.reLaunch({ url: '/pages/login/login' });
      },
    });
  },
});
