// 小程序页面逻辑测试：不需要微信开发者工具，用 node 模拟 Page/wx，请求打到本地后端。
// 用法：先按 README 启动后端（端口 8811），然后 STAFF_KEY=你的值 node backend/scripts/page_test/test_pages.js
const { loadPage, idle, storage, log, call, staff } = require('./harness.js');
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
  const pkg0 = await call('System.Order.addforecast', { express_num: 'EE1-' + Date.now(), good_name: '未称重包裹' });
  pg = loadPage('order-create'); pg.onLoad(); pg.onShow(); await idle();
  ok(pg.data.address.id === addrA.id, 'defaults to the default address');
  ok(pg.data.lines.map((l) => l.name).join() === '精致小,无忧草', 'line picker offers 精致小 / 无忧草');
  pg.onLineChange({ detail: { value: 1 } });
  pg.onTogglePackage({ currentTarget: { dataset: { id: pkg0.id } } }); await idle();
  const lines = await call('System.Address.estimateFee', { weight: 0 });
  const line3 = lines.find((l) => l.line_id === pg.data.lineId);
  ok(pg.data.totalFee === '80.00' && pg.data.totalFee === line3.fee, `unweighed package shows 无忧草 first-weight fee ¥${pg.data.totalFee} (not ¥0)`);
  ok(pg.data.feeEstimated === true, 'fee flagged as estimate until the warehouse weighs it');
  log.length = 0; pg.goChooseAddress();
  log.find((l) => l[0] === 'navigateTo')[2].events.selectAddress(addrB);
  pg.onShow(); await idle();
  ok(pg.data.address.id === addrB.id, 'picked address kept after onShow (used to revert to default)');
  ok(pg.data.lineId === line3.line_id, 'picked line kept after onShow (used to reset to first)');
  ok(pg.data.selectedIds.includes(pkg0.id), 'package selection kept');
  log.length = 0; pg.onSubmit(); await idle();
  ok(log.some((l) => l[0] === 'loading' && l[1] === true), 'submit loading masks double taps');
  await new Promise((r) => setTimeout(r, 900));
  ok(log.some((l) => l[0] === 'switchTab' && l[1] === '/pages/orders/orders'), 'after ordering, lands on the orders tab (redirectTo to a tabBar page silently failed)');
  const orders = await call('System.Order.order', {});
  const detail = await call('System.Order.orderDetail', { id: orders.list[0].id });
  ok(detail.address.id === addrB.id && detail.total_fee === line3.fee, 'order was placed to the picked address and line at the displayed fee');

  console.log('order-detail: weigh -> pay -> ship -> confirm receipt');
  pg = loadPage('order-detail'); pg.onLoad({ id: detail.id }); pg.onShow(); await idle();
  ok(pg.data.order.statusInfo.text === '待入库称重', 'unweighed order shows 待入库称重');
  await staff('System.Order.markInbound', { id: pkg0.id, actual_weight: '1.23' });
  pg.onShow(); await idle();
  // 无忧草 1.23kg: 80 + ceil(0.23/0.1)=3 * 8 = 104
  ok(pg.data.order.statusInfo.text === '待付款' && pg.data.order.total_fee === '104.00', `after weighing: 待付款 ¥${pg.data.order.total_fee}`);
  ok('service_wechat' in pg.data.order, 'payment card has the service WeChat to transfer to');
  await staff('System.Order.markPaid', { id: detail.id });
  pg.onShow(); await idle();
  ok(pg.data.order.statusInfo.text === '待发货' && pg.data.order.paid, 'after staff confirms payment: 待发货');
  await staff('System.Order.markShipped', { id: detail.id, inter_order: 'EE9' + Date.now() });
  pg.onShow(); await idle();
  ok(pg.data.order.statusInfo.text === '运输中' && /航班/.test(pg.data.order.tracks[0].status_text), 'shipped, newest track (with flight) on top');
  pg.onConfirmReceipt(); await idle();
  ok(pg.data.order.statusInfo.text === '已签收', 'user confirms receipt from the order page');

  console.log('order-detail: times');
  pg = loadPage('order-detail'); pg.onLoad({ id: detail.id }); pg.onShow(); await idle();
  ok(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(pg.data.order.tracks[0].time), 'track time formatted: ' + pg.data.order.tracks[0].time);

  console.log('orders: tab switch with slow response');
  const pkgC = await call('System.Order.addforecast', { express_num: 'C-' + Date.now() });
  const closeMe = await call('System.Order.savePage', { address_id: addrA.id, line_id: lines[0].line_id, package_ids: [pkgC.id] });
  await call('System.Order.orderClose', { id: closeMe.order_id });
  await call('System.Order.savePage', { address_id: addrA.id, line_id: lines[0].line_id, package_ids: [pkgC.id] });
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

  console.log('forecast: tracking number only + status');
  pg = loadPage('forecast'); pg.onLoad(); await idle();
  log.length = 0; pg.onSubmit(); await idle();
  ok(toasts().includes('请填写快递单号'), 'tracking number is the only required field');
  const num = 'F-' + Date.now();
  pg.onFieldInput({ currentTarget: { dataset: { field: 'express_num' } }, detail: { value: num } });
  pg.onLogisticsChange({ detail: { value: '0' } });
  pg.onSubmit(); await idle();
  let mine = (await call('System.Order.goodsList', {})).find((p) => p.express_num === num);
  ok(mine && mine.logistics_status === 'not_shipped', 'forecast saved with chosen status 卖家未发货');

  console.log('packages: change status of a package not yet arrived');
  pg = loadPage('packages'); pg.onShow(); await idle();
  pg.onLogisticsChange({ currentTarget: { dataset: { id: mine.id } }, detail: { value: '1' } }); await idle();
  mine = (await call('System.Order.goodsList', {})).find((p) => p.express_num === num);
  ok(mine.logistics_status === 'in_transit', 'status updated to 已发货，在路上');
  ok(pg.data.list.find((p) => p.id === mine.id).logistics_text === '已发货，在路上', 'list refreshed with new status');

  console.log('mine: nickname + phone');
  pg = loadPage('mine'); pg.onShow(); await idle();
  ok(/^[0-9A-F]{8}$/.test(pg.data.member.cn_code), 'member code shown: ' + pg.data.member.cn_code);
  pg.onEdit(); pg.setData({ nickname: '测试昵称', mobile: '123' });
  log.length = 0; pg.onSaveProfile(); await idle();
  ok(toasts().includes('手机号格式不正确'), 'bad phone rejected in the page');
  pg.setData({ mobile: '13912345678' }); pg.onSaveProfile(); await idle();
  ok(pg.data.member.nickname === '测试昵称' && pg.data.member.mobile === '13912345678' && !pg.data.editing, 'profile saved');

  console.log('index: fee notes + calculator');
  pg = loadPage('index'); pg.onShow(); await idle();
  ok(pg.data.lines.length === 2 && pg.data.feeNotes.some((n) => n.includes('大连港')), 'fee explanation shows both lines and the rules');
  pg.onWeightInput({ detail: { value: '0.5' } }); pg.onValueInput({ detail: { value: '600' } }); pg.onEstimateFee(); await idle();
  ok(!pg.data.feeResult[0].available && pg.data.feeResult[1].available, '600元 package: 精致小 marked 不适用, 无忧草 available');

  console.log(`\n${passed} checks passed`);
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
