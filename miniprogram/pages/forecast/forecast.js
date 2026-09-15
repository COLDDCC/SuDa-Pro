const { call } = require('../../utils/request.js');

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
    pasteText: '',
  },

  onFieldInput(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({ [`form.${field}`]: e.detail.value });
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
    if (!f.express_num) return wx.showToast({ title: '请填写快递单号', icon: 'none' });
    if (!f.good_name) return wx.showToast({ title: '请填写品名', icon: 'none' });

    wx.showLoading({ title: '提交中...' });
    call('System.Order.addforecast', {
      express_num: f.express_num,
      good_name: f.good_name,
      count: Number(f.count) || 1,
      netwt: Number(f.netwt) || 0,
      price: Number(f.price) || 0,
      cc_registered_price: Number(f.cc_registered_price) || Number(f.price) || 0,
    })
      .then(() => {
        wx.hideLoading();
        wx.showToast({ title: '预报成功' });
        setTimeout(() => wx.switchTab({ url: '/pages/packages/packages' }), 800);
      })
      .catch(() => wx.hideLoading());
  },
});
