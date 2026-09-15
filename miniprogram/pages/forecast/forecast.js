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
  },

  onFieldInput(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({ [`form.${field}`]: e.detail.value });
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
