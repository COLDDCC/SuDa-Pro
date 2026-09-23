const { call } = require('../../utils/request.js');
const { packageStatus } = require('../../utils/format.js');
const { BASE_URL: baseUrl } = require('../../utils/config.js');

const TABS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待入库' },
  { key: 'inbound', label: '已入库' },
  { key: 'ordered', label: '已下单' },
  { key: 'shipped', label: '已发货' },
];

Page({
  data: {
    tabs: TABS,
    activeTab: '',
    list: [],
    photoFee: '',
  },

  onLoad() {
    call('System.Order.photoServiceInfo')
      .then((info) => this.setData({ photoFee: info.fee }))
      .catch(() => {});
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    this.loadList();
  },

  onPullDownRefresh() {
    this.loadList(() => wx.stopPullDownRefresh());
  },

  loadList(done) {
    call('System.Order.goodsList', this.data.activeTab ? { status: this.data.activeTab } : {})
      .then((list) => {
        this.setData({
          list: list.map((p) => ({
            ...p,
            statusInfo: packageStatus(p.status),
            // 仓库拍的照片分两种：入库拍照是用户付费申请的，打包留底是发货前的存档。
            // 用户看的时候不用区分，都摊平成一条图片带。
            photoUrls: (p.photos || []).map((ph) => baseUrl + ph.url),
            hasPhotos: (p.photos || []).length > 0,
            // 已经拍了就不能取消了（服务已经发生），按钮得跟着变。
            photoDone: (p.photos || []).some((ph) => ph.kind === 'inbound'),
            canAskPhoto: p.status === 'pending' || p.status === 'inbound',
          })),
        });
      })
      .finally(() => done && done());
  },

  onTabTap(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ activeTab: key }, () => this.loadList());
  },

  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认删除',
      content: '删除后不可恢复',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Order.delectGood', { id }).then(() => this.loadList());
      },
    });
  },

  // 预报时没勾拍照的，到仓后还能补申请；没拍之前也能反悔取消。
  onTogglePhoto(e) {
    const { id, requested, done } = e.currentTarget.dataset;
    if (requested && done) {
      return wx.showToast({ title: '仓库已经拍好了，取消不了啦', icon: 'none' });
    }
    if (requested) {
      call('System.Order.cancelPhotoRequest', { goods_id: id })
        .then(() => {
          wx.showToast({ title: '已取消', icon: 'none' });
          this.loadList();
        })
        .catch(() => {});
      return;
    }
    wx.showModal({
      title: '申请入库拍照',
      content: this.data.photoFee
        ? `仓库拆箱验货时帮你拍照，¥${this.data.photoFee}/个包裹，下单时一并结算`
        : '仓库拆箱验货时帮你拍照，费用下单时一并结算',
      success: (res) => {
        if (!res.confirm) return;
        call('System.Order.requestPhoto', { goods_id: id })
          .then(() => {
            wx.showToast({ title: '已申请', icon: 'none' });
            this.loadList();
          })
          .catch(() => {});
      },
    });
  },

  onPreviewPhoto(e) {
    const { urls, current } = e.currentTarget.dataset;
    wx.previewImage({ urls, current });
  },

  goForecast() {
    wx.navigateTo({ url: '/pages/forecast/forecast' });
  },

  goCreateOrder() {
    wx.navigateTo({ url: '/pages/order-create/order-create' });
  },
});
