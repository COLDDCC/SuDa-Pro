const { call } = require('../../utils/request.js');

Page({
  data: {
    member: null,
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    call('System.Member.memberInfo', {}).then((member) => this.setData({ member }));
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
