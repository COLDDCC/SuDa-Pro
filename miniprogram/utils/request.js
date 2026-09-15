const { BASE_URL } = require('./config.js');

/**
 * 调用后端方法路由接口: POST /api {method, params, token}
 * 统一处理 401 (登录过期) -> 跳转登录页; 其余错误交给调用方 catch。
 */
function call(method, params = {}) {
  const token = wx.getStorageSync('token') || '';
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/api`,
      method: 'POST',
      data: { method, params, token },
      header: { 'content-type': 'application/json' },
      success(res) {
        const body = res.data || {};
        if (body.code === 0) {
          resolve(body.data);
        } else if (body.code === 401) {
          wx.removeStorageSync('token');
          wx.reLaunch({ url: '/pages/login/login' });
          reject(new Error(body.msg || '登录已过期'));
        } else {
          wx.showToast({ title: body.msg || '请求失败', icon: 'none' });
          reject(new Error(body.msg || '请求失败'));
        }
      },
      fail(err) {
        wx.showToast({ title: '网络异常，请检查后端是否已启动', icon: 'none' });
        reject(err);
      },
    });
  });
}

module.exports = { call };
