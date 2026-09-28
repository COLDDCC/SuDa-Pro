const { call } = require('../../utils/request.js');

Page({
  data: {
    member: null,
    serviceWechat: '',
    editing: false,
    nickname: '',
    mobile: '',
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    call('System.Member.memberInfo', {}).then((member) => this.setData({ member }));
    call('System.Config.webSite', {}).then((site) => this.setData({ serviceWechat: site.service_wechat })).catch(() => {});
  },

  onCopyCode() {
    wx.setClipboardData({ data: this.data.member.cn_code });
  },

  onCopyWechat() {
    wx.setClipboardData({ data: this.data.serviceWechat });
  },

  onEdit() {
    this.setData({ editing: true, nickname: this.data.member.nickname, mobile: this.data.member.mobile });
  },

  onCancelEdit() {
    this.setData({ editing: false });
  },

  onFieldInput(e) {
    this.setData({ [e.currentTarget.dataset.field]: e.detail.value });
  },

  // 昵称和手机号是仓库在后台认出"这是谁的包裹"的依据，微信登录拿不到，需要用户自己填
  onSaveProfile() {
    const nickname = this.data.nickname.trim();
    const mobile = this.data.mobile.trim();
    if (!nickname) return wx.showToast({ title: '请填写昵称', icon: 'none' });
    if (mobile && !/^1\d{10}$/.test(mobile)) return wx.showToast({ title: '手机号格式不正确', icon: 'none' });
    wx.showLoading({ title: '保存中...', mask: true });
    call('System.Member.saveProfile', { nickname, mobile })
      .then((member) => {
        wx.hideLoading();
        this.setData({ member, editing: false });
        wx.showToast({ title: '已保存' });
      })
      .catch(() => wx.hideLoading());
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
