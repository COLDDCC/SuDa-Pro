const { call } = require('../../utils/request.js');
const { LOGISTICS_OPTIONS } = require('../../utils/format.js');
const subscribe = require('../../utils/subscribe.js');

Page({
  data: {
    form: {
      express_num: '',
      good_name: '',
      count: '1',
      netwt: '',
      price: '',
      cc_registered_price: '',
    },
    logisticsOptions: LOGISTICS_OPTIONS,
    logisticsIndex: 1, // 默认"已发货，在路上"
    showMore: false,
    pasteText: '',
  },

  onLoad() {
    subscribe.prefetch();
  },

  onFieldInput(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({ [`form.${field}`]: e.detail.value });
  },

  onLogisticsChange(e) {
    this.setData({ logisticsIndex: Number(e.detail.value) });
  },

  onToggleMore() {
    this.setData({ showMore: !this.data.showMore });
  },

  onPasteTextInput(e) {
    this.setData({ pasteText: e.detail.value });
  },

  // 差异化功能：把快递单上的文字拍照后用手机自带的"提取文字"功能复制粘贴过来，
  // 自动识别单号，省得整串手打。识别不到就提示手动填，不影响正常流程。
  onRecognize() {
    const text = this.data.pasteText.trim();
    if (!text) return wx.showToast({ title: '先粘贴快递单上的文字', icon: 'none' });

    call('System.Order.parseTrackingText', { text })
      .then((result) => {
        if (!result.best_guess) {
          wx.showToast({ title: '没识别到单号，请手动填写', icon: 'none' });
          return;
        }
        this.setData({ 'form.express_num': result.best_guess });
        wx.showToast({ title: '已自动填入，请核对', icon: 'none' });
      })
      .catch(() => {});
  },

  onSubmit() {
    const f = this.data.form;
    const expressNum = f.express_num.trim();
    if (!expressNum) return wx.showToast({ title: '请填写快递单号', icon: 'none' });

    const params = {
      express_num: expressNum,
      logistics_status: LOGISTICS_OPTIONS[this.data.logisticsIndex].value,
    };
    // 选填项：填了才传，没填由后端用默认值（重量以入库称重为准）
    if (f.good_name.trim()) params.good_name = f.good_name.trim();
    if (Number(f.count) > 0) params.count = Number(f.count);
    if (Number(f.netwt) > 0) params.netwt = Number(f.netwt);
    if (Number(f.price) > 0) params.price = Number(f.price);
    const declared = Number(f.cc_registered_price) || Number(f.price);
    if (declared > 0) params.cc_registered_price = declared;

    // 订阅弹窗和请求之间有空档，loading 的 mask 挡不住这段时间的连点，用标记位兜住
    if (this.submitting) return;
    this.submitting = true;
    // 先弹"包裹入库时通知我"的订阅授权（必须在点击回调里同步调用），再提交
    subscribe.request(['inbound']).then(() => {
      wx.showLoading({ title: '提交中...', mask: true });
      call('System.Order.addforecast', params)
        .then(() => {
          wx.hideLoading();
          wx.showToast({ title: '预报成功' });
          setTimeout(() => wx.switchTab({ url: '/pages/packages/packages' }), 800);
        })
        .catch(() => { wx.hideLoading(); this.submitting = false; });
    });
  },
});
