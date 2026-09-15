App({
  globalData: {
    memberInfo: null,
  },

  onLaunch() {
    // no-op: 各页面 onShow 时自行检查登录态并按需跳转登录页
  },

  ensureLogin() {
    const token = wx.getStorageSync('token');
    if (!token) {
      wx.reLaunch({ url: '/pages/login/login' });
      return false;
    }
    return true;
  },
});
