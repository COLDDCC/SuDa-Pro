// 小程序页面逻辑测试：不需要微信开发者工具，用 node 模拟 Page/wx，请求打到本地后端。
// 用法：先按 README 启动后端（端口 8811），然后 node backend/scripts/page_test/test_pages.js
const { loadPage, idle, storage, log, call } = require('./harness.js');
const assert = require('assert');
let passed = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); passed++; console.log('  ✔', msg); };
const toasts = () => log.filter((l) => l[0] === 'toast').map((l) => l[1]);

(async () => {
  storage.token = (await call('System.Login.devLogin', { identifier: 'mp-' + Date.now() })).token;
  const base = { consigner: '李四', mobile: '13900000000', address: '人民路1号', idnumber: '110101199001011234' };

  console.log('address-edit: new address');
  let pg = loadPage('address-edit');
  pg.onLoad({}); await idle();
  Object.assign(pg.data, base);
  log.length = 0; pg.onSubmit(); await idle();
  ok(toasts().includes('请选择省/市/区') && !log.some((l) => l[0] === 'navigateBack'), 'never opening the picker blocks submit (used to save 北京市东城区)');
  pg.onColumnChange({ detail: { column: 0, value: 1 } }); await idle();
  pg.onPickerChange({ detail: { value: pg.data.multiIndex } });
  ok(pg.data.regionText.startsWith('天津市'), 'confirming picks 天津市: ' + pg.data.regionText);
  pg.onColumnChange({ detail: { column: 0, value: 2 } }); await idle(); // scroll to 河北, then cancel
  pg.onSubmit(); await idle();
  let list = await call('System.Member.memberAddressList', {});
  ok(list[0].province === '天津市', 'scrolled-then-cancelled picker still saves the confirmed region: ' + list[0].province);

  console.log('address-edit: fast scrolling');
  pg = loadPage('address-edit'); pg.onLoad({}); await idle();
  global.__delay = (d) => (d.method === 'System.Address.city' && d.params.province_id === 4 ? 300 : 0);
  pg.onColumnChange({ detail: { column: 0, value: 3 } });
  pg.onColumnChange({ detail: { column: 0, value: 4 } });
  await new Promise((r) => setTimeout(r, 500)); await idle(); global.__delay = null;
  ok(pg.data.cities.every((c) => c.province_id === 5), 'slow earlier city response does not overwrite the latest province');

  console.log('address-edit: edit keeps region');
  const addrB = list[0];
  pg = loadPage('address-edit'); pg.onLoad({ id: String(addrB.id) }); await idle();
  ok(pg.data.region && pg.data.region.province.id === addrB.province_id, 'edit mode pre-fills the saved region');
  ok(typeof pg.onShow !== 'function', 'no onShow reload to wipe in-progress edits');

  console.log('order-create: selection survives returning from address picker');
  const addrA = await call('System.Member.addAddress', { ...base, consigner: '默认王', province_id: 1, city_id: 1, district_id: 1, is_default: true });
  const pkg0 = await call('System.Order.addforecast', { express_num: 'EE1', good_name: '零重包裹', netwt: 0 });
  pg = loadPage('order-create'); pg.onShow(); await idle();
  ok(pg.data.address.id === addrA.id, 'defaults to the default address');
  pg.onLineChange({ detail: { value: 2 } });
  pg.onTogglePackage({ currentTarget: { dataset: { id: pkg0.id } } }); await idle();
  const lines = await call('System.Address.estimateFee', { weight: 0 });
  const line3 = lines.find((l) => l.line_id === pg.data.lineId);
  ok(pg.data.totalFee === line3.fee && pg.data.totalFee !== '0', `zero-weight package shows min-weight fee ¥${pg.data.totalFee} (was ¥0)`);
  log.length = 0; pg.goChooseAddress();
  log.find((l) => l[0] === 'navigateTo')[2].events.selectAddress(addrB);
  pg.onShow(); await idle();
  ok(pg.data.address.id === addrB.id, 'picked address kept after onShow (used to revert to default)');
  ok(pg.data.lineId === line3.line_id, 'picked line kept after onShow (used to reset to first)');
  ok(pg.data.selectedIds.includes(pkg0.id), 'package selection kept');
  log.length = 0; pg.onSubmit(); await idle();
  ok(log.some((l) => l[0] === 'loading' && l[1] === true), 'submit loading masks double taps');
  const orders = await call('System.Order.order', {});
  const detail = await call('System.Order.orderDetail', { id: orders.list[0].id });
  ok(detail.address.id === addrB.id && detail.total_fee === line3.fee, 'order was placed to the picked address and line at the displayed fee');

  console.log('order-detail: times');
  pg = loadPage('order-detail'); pg.onLoad({ id: detail.id }); pg.onShow(); await idle();
  ok(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(pg.data.order.tracks[0].time), 'track time formatted: ' + pg.data.order.tracks[0].time);

  console.log('orders: tab switch with slow response');
  await call('System.Order.orderClose', { id: detail.id });
  await call('System.Order.savePage', { address_id: addrA.id, line_id: 1, package_ids: [pkg0.id] });
  pg = loadPage('orders');
  global.__delay = (d) => (d.method === 'System.Order.order' && !d.params.status ? 300 : 0);
  pg.onShow();
  pg.onTabTap({ currentTarget: { dataset: { key: 'closed' } } });
  await new Promise((r) => setTimeout(r, 500)); await idle(); global.__delay = null;
  ok(pg.data.list.length > 0 && pg.data.list.every((o) => o.status === 'closed'), 'closed tab only shows closed orders');

  console.log('packages: tab switch with slow response');
  pg = loadPage('packages');
  global.__delay = (d) => (d.method === 'System.Order.goodsList' && !d.params.status ? 300 : 0);
  pg.onShow();
  pg.onTabTap({ currentTarget: { dataset: { key: 'ordered' } } });
  await new Promise((r) => setTimeout(r, 500)); await idle(); global.__delay = null;
  ok(pg.data.list.length > 0 && pg.data.list.every((p) => p.status === 'ordered'), 'ordered tab only shows ordered packages');

  console.log(`\n${passed} checks passed`);
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
