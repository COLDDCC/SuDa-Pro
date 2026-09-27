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
    // 用户点"确定"后选中的省市区（id + name）。提交只认它，不认 multiIndex：
    // multiIndex 在滚动过程中就会变，用户滚了一下又点取消，它已经不是用户选的值了；
    // 而且没打开过选择器时 multiIndex 是 [0,0,0]，直接用会悄悄存成北京市东城区。
    region: null,
  },

  // 数据只在 onLoad 加载一次。放在 onShow 里的话，用户切出去复制身份证号再切回来
  // 也会触发 onShow，已经填了一半的表单会被服务器上的旧数据整个覆盖掉。
  onLoad(query) {
    if (!getApp().ensureLogin()) return;
    this.setData({ id: query.id ? Number(query.id) : null });
    call('System.Address.province', {}).then((provinces) => {
      this.setData({ provinces });
      if (this.data.id) {
        this.loadDetail();
      } else if (provinces.length) {
        this.loadCitiesFor(provinces[0].id, () => this.loadDistrictsFor(this.data.cities[0].id));
      }
    });
  },

  // 滚动很快时会同时发出好几个请求，只采用最后一次的结果，避免城市列表和省份对不上
  loadCitiesFor(provinceId, cb) {
    const seq = (this.citySeq = (this.citySeq || 0) + 1);
    call('System.Address.city', { province_id: provinceId }).then((cities) => {
      if (seq !== this.citySeq) return;
      this.setData({ cities }, () => cb && cb());
    });
  },

  loadDistrictsFor(cityId, cb) {
    const seq = (this.districtSeq = (this.districtSeq || 0) + 1);
    call('System.Address.district', { city_id: cityId }).then((districts) => {
      if (seq !== this.districtSeq) return;
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
      if (a.province_id && a.city_id && a.district_id) {
        this.setData({
          region: {
            province: { id: a.province_id, name: a.province },
            city: { id: a.city_id, name: a.city },
            district: { id: a.district_id, name: a.district },
          },
          regionText: `${a.province}${a.city}${a.district}`,
        });
      }
      this.loadCitiesFor(a.province_id, () => {
        this.loadDistrictsFor(a.city_id, () => {
          const pIdx = this.data.provinces.findIndex((p) => p.id === a.province_id);
          const cIdx = this.data.cities.findIndex((c) => c.id === a.city_id);
          const dIdx = this.data.districts.findIndex((d) => d.id === a.district_id);
          this.setData({
            multiIndex: [Math.max(pIdx, 0), Math.max(cIdx, 0), Math.max(dIdx, 0)],
          });
        });
      });
    });
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
          this.setData({ multiIndex: idx });
        });
      });
    } else if (column === 1) {
      const city = this.data.cities[value];
      this.loadDistrictsFor(city.id, () => {
        idx[2] = 0;
        this.setData({ multiIndex: idx });
      });
    } else {
      this.setData({ multiIndex: idx });
    }
  },

  onPickerChange(e) {
    const [pi, ci, di] = e.detail.value;
    const p = this.data.provinces[pi];
    const c = this.data.cities[ci];
    const d = this.data.districts[di];
    this.setData({ multiIndex: e.detail.value });
    // 列表还在加载（滚动后立刻点确定）时可能对不上，这次选择就不算数
    if (!p || !c || !d || c.province_id !== p.id || d.city_id !== c.id) {
      wx.showToast({ title: '地区还在加载，请重新选择', icon: 'none' });
      return;
    }
    this.setData({
      region: { province: p, city: c, district: d },
      regionText: `${p.name}${c.name}${d.name}`,
    });
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
    if (!this.data.region) return wx.showToast({ title: '请选择省/市/区', icon: 'none' });
    if (!this.data.address) return wx.showToast({ title: '请填写详细地址', icon: 'none' });
    if (!/^\d{15}(\d{2}[0-9Xx])?$/.test(this.data.idnumber)) {
      return wx.showToast({ title: '身份证号格式不正确（报关需要实名）', icon: 'none' });
    }

    const { province, city, district } = this.data.region;
    const payload = {
      consigner: this.data.consigner,
      mobile: this.data.mobile,
      address: this.data.address,
      idnumber: this.data.idnumber,
      is_default: this.data.is_default,
      province_id: province.id,
      city_id: city.id,
      district_id: district.id,
    };

    const method = this.data.id ? 'System.Member.updateAddress' : 'System.Member.addAddress';
    if (this.data.id) payload.id = this.data.id;

    // mask 挡住重复点击，不然连点两下会存出两条一样的地址
    wx.showLoading({ title: '保存中...', mask: true });
    call(method, payload)
      .then(() => {
        wx.hideLoading();
        wx.showToast({ title: '已保存' });
        setTimeout(() => wx.navigateBack(), 600);
      })
      .catch(() => wx.hideLoading());
  },
});
