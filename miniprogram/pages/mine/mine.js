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
    this.loadMember();
  },

  loadMember() {
    call('System.Member.memberInfo', {}).then((member) => this.setData({ member }));
  },

  // 微信登录拿不到昵称和手机号（个人主体小程序没有一键获取手机号的权限），
  // 所以给用户一个手填的入口。没有这个的话，后台看到的全是"未设昵称"，
  // 客户没下单前你根本联系不上他。
  onEditProfile() {
    const m = this.data.member || {};
    wx.showModal({
      title: '设置昵称',
      editable: true,
      placeholderText: '方便客服认出你',
      content: m.nickname || '',
      success: (res) => {
        if (!res.confirm) return;
        const nickName = (res.content || '').trim();
        if (!nickName) return;
        call('System.Member.saveNickName', { nickName })
          .then(() => {
            wx.showToast({ title: '已保存', icon: 'none' });
            this.loadMember();
          })
          .catch(() => {});
      },
    });
  },

  onEditMobile() {
    wx.showModal({
      title: '绑定手机号',
      editable: true,
      placeholderText: '11 位手机号',
      content: (this.data.member || {}).mobile || '',
      success: (res) => {
        if (!res.confirm) return;
        const mobile = (res.content || '').trim();
        if (!/^1\d{10}$/.test(mobile)) {
          return wx.showToast({ title: '手机号格式不正确', icon: 'none' });
        }
        call('System.Login.checkMobile', { mobile })
          .then(() => {
            wx.showToast({ title: '已绑定', icon: 'none' });
            this.loadMember();
          })
          .catch(() => {});
      },
    });
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
