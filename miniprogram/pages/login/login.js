const { call } = require('../../utils/request.js');

Page({
  data: {
    devIdentifier: '',
    // 配齐微信凭证后 devLogin 会被后端禁用，留着按钮用户点了只会看到一条
    // 看不懂的报错，所以先问后端能不能用微信登录，再决定显示哪个。
    wechatLogin: true,
    ready: false,
    siteName: '',
    siteSlogan: '',
  },

  onLoad() {
    // 品牌名也从后端取：改名字只要改 business.py，不用重发小程序。
    call('System.Config.webSite')
      .then((site) => this.setData({
        wechatLogin: !!site.wechat_login,
        siteName: site.name,
        siteSlogan: site.slogan,
        ready: true,
      }))
      .catch(() => this.setData({ ready: true }));
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
