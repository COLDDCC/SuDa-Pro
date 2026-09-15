const { call } = require('../../utils/request.js');

Page({
  data: {
    id: null,
    consigner: '',
    mobile: '',
    address: '',
    idnumber: '',
    is_default: false,

    provinces: [],
    cities: [],
    districts: [],
    multiIndex: [0, 0, 0],
    regionText: '请选择省/市/区',
  },

  onLoad(query) {
    this.setData({ id: query.id ? Number(query.id) : null });
  },

  onShow() {
    if (!getApp().ensureLogin()) return;
    call('System.Address.province', {}).then((provinces) => {
      this.setData({ provinces });
      if (this.data.id) {
        this.loadDetail();
      } else if (provinces.length) {
        this.loadCitiesFor(provinces[0].id, () => this.loadDistrictsFor(this.data.cities[0].id));
      }
    });
  },

  loadCitiesFor(provinceId, cb) {
    call('System.Address.city', { province_id: provinceId }).then((cities) => {
      this.setData({ cities }, () => cb && cb());
    });
  },

  loadDistrictsFor(cityId, cb) {
    call('System.Address.district', { city_id: cityId }).then((districts) => {
      this.setData({ districts }, () => cb && cb());
    });
  },

  loadDetail() {
    call('System.Member.addressDetail', { id: this.data.id }).then((a) => {
      this.setData({
        consigner: a.consigner,
        mobile: a.mobile,
        address: a.address,
        idnumber: a.idnumber,
        is_default: a.is_default,
      });
      this.loadCitiesFor(a.province_id, () => {
        this.loadDistrictsFor(a.city_id, () => {
          const pIdx = this.data.provinces.findIndex((p) => p.id === a.province_id);
          const cIdx = this.data.cities.findIndex((c) => c.id === a.city_id);
          const dIdx = this.data.districts.findIndex((d) => d.id === a.district_id);
          this.setData({
            multiIndex: [Math.max(pIdx, 0), Math.max(cIdx, 0), Math.max(dIdx, 0)],
          });
          this.updateRegionText();
        });
      });
    });
  },

  updateRegionText() {
    const [pi, ci, di] = this.data.multiIndex;
    const p = this.data.provinces[pi];
    const c = this.data.cities[ci];
    const d = this.data.districts[di];
    if (p && c && d) {
      this.setData({ regionText: `${p.name}${c.name}${d.name}` });
    }
  },

  onColumnChange(e) {
    const { column, value } = e.detail;
    const idx = this.data.multiIndex.slice();
    idx[column] = value;

    if (column === 0) {
      const province = this.data.provinces[value];
      this.loadCitiesFor(province.id, () => {
        idx[1] = 0;
        this.loadDistrictsFor(this.data.cities[0].id, () => {
          idx[2] = 0;
          this.setData({ multiIndex: idx }, () => this.updateRegionText());
        });
      });
    } else if (column === 1) {
      const city = this.data.cities[value];
      this.loadDistrictsFor(city.id, () => {
        idx[2] = 0;
        this.setData({ multiIndex: idx }, () => this.updateRegionText());
      });
    } else {
      this.setData({ multiIndex: idx }, () => this.updateRegionText());
    }
  },

  onPickerChange(e) {
    this.setData({ multiIndex: e.detail.value }, () => this.updateRegionText());
  },

  onFieldInput(e) {
    this.setData({ [e.currentTarget.dataset.field]: e.detail.value });
  },

  onDefaultChange(e) {
    this.setData({ is_default: e.detail.value.length > 0 });
  },

  onSubmit() {
    if (!this.data.consigner) return wx.showToast({ title: '请填写收件人', icon: 'none' });
    if (!/^1\d{10}$/.test(this.data.mobile)) return wx.showToast({ title: '手机号格式不正确', icon: 'none' });
    if (!this.data.address) return wx.showToast({ title: '请填写详细地址', icon: 'none' });
    if (!/^\d{15}(\d{2}[0-9Xx])?$/.test(this.data.idnumber)) {
      return wx.showToast({ title: '身份证号格式不正确（报关需要实名）', icon: 'none' });
    }

    const [pi, ci, di] = this.data.multiIndex;
    const province = this.data.provinces[pi];
    const city = this.data.cities[ci];
    const district = this.data.districts[di];

    const payload = {
      consigner: this.data.consigner,
      mobile: this.data.mobile,
      address: this.data.address,
      idnumber: this.data.idnumber,
      is_default: this.data.is_default,
      province_id: province && province.id,
      city_id: city && city.id,
      district_id: district && district.id,
    };

    const method = this.data.id ? 'System.Member.updateAddress' : 'System.Member.addAddress';
    if (this.data.id) payload.id = this.data.id;

    wx.showLoading({ title: '保存中...' });
    call(method, payload)
      .then(() => {
        wx.hideLoading();
        wx.showToast({ title: '已保存' });
        setTimeout(() => wx.navigateBack(), 600);
      })
      .catch(() => wx.hideLoading());
  },
});
