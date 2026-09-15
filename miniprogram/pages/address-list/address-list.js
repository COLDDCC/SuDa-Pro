const { call } = require('../../utils/request.js');

Page({
  data: {
    list: [],
    selectMode: false,
  },

  onLoad(query) {
    this.setData({ selectMode: query.select === '1' });
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadList();
  },

  loadList() {
    call('System.Member.memberAddressList', {}).then((list) => this.setData({ list }));
  },

  onSelect(e) {
    if (!this.data.selectMode) return;
    const id = e.currentTarget.dataset.id;
    const addr = this.data.list.find((a) => a.id === id);
    const eventChannel = this.getOpenerEventChannel();
    if (eventChannel && eventChannel.emit) eventChannel.emit('selectAddress', addr);
    wx.navigateBack();
  },

  onEdit(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/address-edit/address-edit?id=${id}` });
  },

  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认删除该地址？',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Member.addressDelete', { id }).then(() => this.loadList());
      },
    });
  },

  onSetDefault(e) {
    const id = e.currentTarget.dataset.id;
    call('System.Member.modifyAddressDefault', { id }).then(() => this.loadList());
  },

  goAdd() {
    wx.navigateTo({ url: '/pages/address-edit/address-edit' });
  },
});
