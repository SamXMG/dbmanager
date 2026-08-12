// dbmanager 前端 - 轻量集中状态管理(发布订阅)
// 对应商业数据库工具"状态驱动界面"的核心: 状态变化 -> 相关 UI 自动刷新, 不再散落手动调用
// 用法:
//   store.set('curDb', 'client')      // 改状态(自动通知所有订阅者)
//   store.get('curDb')                // 读状态
//   store.watch('curDb', v => ...)    // 订阅(返回取消订阅函数)
const store = (function () {
  const state = {};
  const subs = {};
  return {
    set(key, val) {
      const prev = state[key];
      if (Object.is(prev, val)) return;
      state[key] = val;
      (subs[key] || []).forEach(fn => {
        try { fn(val, prev); } catch (e) { console.error('[store]', key, e); }
      });
    },
    get(key) { return state[key]; },
    watch(key, fn) {
      (subs[key] = subs[key] || []).push(fn);
      return () => { subs[key] = (subs[key] || []).filter(f => f !== fn); };
    }
  };
})();
