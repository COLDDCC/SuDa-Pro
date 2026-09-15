const { call } = require('../../utils/request.js');

Page({
  data: {
    devIdentifier: '',
  },

  onWechatLogin() {
    wx.login({
      success: (loginRes) => {
        if (!loginRes.code) {
          wx.showToast({ title: '获取微信登录凭证失败', icon: 'none' });
          return;
        }
        this.finishLogin('System.Login.wechatLogin', { code: loginRes.code });
      },
      fail: () => wx.showToast({ title: '微信登录失败', icon: 'none' }),
    });
  },

  onDevIdentifierInput(e) {
    this.setData({ devIdentifier: e.detail.value });
  },

  onDevLogin() {
    const identifier = this.data.devIdentifier.trim() || 'dev-user';
    this.finishLogin('System.Login.devLogin', { identifier, nickname: identifier });
  },

  finishLogin(method, params) {
    wx.showLoading({ title: '登录中...' });
    call(method, params)
      .then((data) => {
        wx.setStorageSync('token', data.token);
        wx.hideLoading();
        wx.reLaunch({ url: '/pages/index/index' });
      })
      .catch(() => wx.hideLoading());
  },
});
