# GPT 镜像站一键脚本交接文档（给执行 Agent：照此可与调度大脑同速）

> 目标：从零（新标签捏 wendabao 账号池）到「**新对话 + 模型 pill = Extended 可发问**」，一键双脚本，实测 9.6s；慢于 25s 即算没吃透本文。
> 全文自包含：脚本源码内嵌在 §5/§6，可直接照抄落盘；已存档副本在 `D:\Work\AI平台\docs\运行手册\scripts\`（evalA_jump.js / evalB_ext.js）。
> 父级规范：`GPT镜像站送审流程.md` §三·五。只读不破坏共享标签（`tab new` 自开，绝不碰别人 tab）。

## 0. 你要交付什么
对本任务：跑通「新对话切 Extended」+「旧对话切 Extended」两条，各自用系统时钟计时，按 §7 汇报表返回。**别改任何仓库、别回历练、别在页面里发真实问题**（本测试只验证通道 + 闸门，不消费 GPT 轮次）。

## 1. 前置（30 秒）
- opencli 连的是**日常 Chrome**（profile `n8hh7hyn`，daemon 19825）。先 `opencli doctor` 确认 Extension connected。
- 不进新实例、不新登录。所有浏览器动作走 `opencli browser n8hh7hyn <cmd>`。

## 2. 完整命令（3 步 = 新对话 Extended）
```bash
# 第一步：新标签进账号池（不覆盖/不取消任何已开标签）
opencli browser n8hh7hyn tab new "https://ai.wendabao-f.net/?utm_source=hidden-ncn"
sleep 2
# 第二步：跳镜像（劫持 window.open → location.href）
opencli browser n8hh7hyn eval "$(cat evalA_jump.js)"
# 第三步：全自动切 Extended + 验证。返回 {ok:true} 才算通
opencli browser n8hh7hyn eval "$(cat evalB_ext.js)"
```
- 新对话 composer = textarea；**旧对话** composer = contenteditable，进 `/c/<id>` 后照跑第二步的 `evalB_ext.js` 即可（同一个 `button.__composer-pill`）。
- 怎么进旧对话：第二步跳进镜像后，`eval` 点侧栏第一个 `/c/` 链接，再跑 evalB。

## 3. opencli eval 的硬知识（决定你能不能快起来）
- **脚本形态统一为 IIFE 自执行 `(() => {...})()`**：传一个"立即可求值的表达式"，返回一个值或 Promise。**别传裸箭头函数字面量 `() => {...}` 去让 opencli"帮你调"**——不同 opencli 版本（v1.8.0 等）对"是否自动调用返回的函数"契约不一，裸 thunk 会报 `Unexpected token ')'`。IIFE 在任何版本都是安全的。本交接内嵌的 evalA/evalB 已是 IIFE 形态，直接照抄。
- **别传 `--tab <id>` 给 eval**：要定向到某标签，先用 `tab select <id>` 钉为会话默认目标，再直接 `eval`。`--tab` 在部分版本未被 eval 注册，会打乱实参解析（也可能正是 SyntaxError 的来源）。
- **`opencli browser n8hh7hyn eval "<js>"` 会等待 JS 里 `returned Promise` resolve 后才返回**。所以能在**一次 eval 内**写 `async` 函数 + `await new Promise(r=>setTimeout(r,ms))` 做自旋轮询，把「等人/等导航/等 React 更新」变成 JS 内部 await，而不是外面 sleep+多次往返。**这是最大提速杠杆**。
- **eval 契约两行自检**（别的 harness 翻车先跑这个，一次定位自己版本的最小可用形态）：
  ```bash
  opencli browser n8hh7hyn eval "1+1"      # 应为 2
  opencli browser n8hh7hyn eval "(()=>1)()" # 应为 1（IIFE 值形态）
  ```
  若两行都不返回数字= 该环境 eval 产出是字符串/需换输出解析；若第一行行而第二行报错= 它不接受 IIFE，把全文 `opencli browser eval --help` 和 `opencli --version` 抄回给调度大脑。
- 每次 eval 到本地 daemon 有 ~1–3s 往返。**往返越少越快**。靶子是 3 次 opencli 调用跑完全流程。
- 任何 `location.href=...` 跳转会**销毁当前 eval 的执行上下文**，所以「跳转」和「跳转后切 Extended」必须分成两次 eval（evalA 跳、evalB 落地等+切）。

## 4. 三大坑（跨实例 / Radix 菜单，必读）
1. **hydration 坑（最容易扑空）**：不同 vip 实例改版不同，部分实例 composer pill 首载文本是**占位 `Model`**（模型列表没加载完），这时点它菜单永远开不出、选不到 Extended。**必须先等 pill 文本变成可操作 `Auto`/`Extended` 再动手**。evalB 已内建此闸门，别删。
2. **Radix 菜单必须完整指针序列 + 原生 click**：只 `el.click()` 或合成单个 click **打不开**模型选择菜单。需要合成 `pointerover→pointermove→pointerenter→pointerdown→pointerup→mousedown→mouseup`（带 `pointerId:1,pointerType:'mouse',button:0,detail:1`，坐标取 `getBoundingClientRect()` 中心）+ 最后**再调 `el.click()`**。evalB 已封装成 `clickEl()`。
3. **别用固定 sleep**：页面到位用 await 轮询（轮询 fn 返回 truthy 才继续），比 `sleep 5` 稳而且快——等到了就走、等不到超时抛。evalB 已封装 `poll(fn,timeout)`。

## 5. evalA_jump.js（跳镜像 · 全文）
```javascript
(() => {
  window.__openUrl = null;
  window.open = function(u){ window.__openUrl = u; return null; };
  const card = document.querySelectorAll('.n-card')[0];
  const span = card ? [...card.querySelectorAll('span')].find(s => /^GPT-5/.test((s.innerText||'').trim())) : null;
  if (!span) return JSON.stringify({err:'no-gpt5-span'});
  const r = span.getBoundingClientRect(), cx = r.left+r.width/2, cy = r.top+r.height/2;
  const fire = t => span.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,pointerId:1,pointerType:'mouse',button:0,detail:1,clientX:cx,clientY:cy}));
  ['pointerover','pointermove','pointerdown','mousedown','pointerup','mouseup'].forEach(fire);
  span.click();
  const u = window.__openUrl;
  if (!u) return JSON.stringify({err:'no-openurl'});
  location.href = u;
  return JSON.stringify({jumped: u.slice(0,55)});
})()
```
说明：账号池当前全卡活跃，取 `.n-card[0]` 第一个 GPT-5 span。点它 → 触发被 Chrome 拦截的 `window.open` → 已被劫持存进 `__openUrl` → `location.href=__openUrl` 秒跳 vip-XX。若将来受限卡变多，先扫「绿色活跃」卡再点，勿点受限。

## 6. evalB_ext.js（落地等待 + 切 Extended + 验证 · 全文）
```javascript
(() => {
  const poll = (fn, timeout, interval=200) => (async()=>{
    const t0=Date.now();
    while(Date.now()-t0<timeout){ const v=fn(); if(v) return v; await new Promise(r=>setTimeout(r,interval)); }
    return null;
  })();
  const clickEl = el => {
    const r=el.getBoundingClientRect(), cx=r.left+r.width/2, cy=r.top+r.height/2;
    const fire=t=>el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,pointerId:1,pointerType:'mouse',button:0,detail:1,clientX:cx,clientY:cy}));
    fire('pointerover'); fire('pointermove'); fire('pointerenter'); fire('pointerdown'); fire('pointerup'); fire('mousedown'); fire('mouseup'); el.click();
  };
  return (async()=>{
    if(!await poll(()=>location.host.includes('67673.live')?true:null, 15000)) return JSON.stringify({err:'nav-timeout',host:location.host});
    const pill = await poll(()=>{ const p=document.querySelector('button.__composer-pill'); if(!p) return null; const t=(p.textContent||'').trim(); return /^(Auto|Extended)$/.test(t)?p:null; }, 10000);
    if(!pill) return JSON.stringify({err:'pill-not-ready', txt:(document.querySelector('button.__composer-pill')||{}).textContent});
    const before=(pill.textContent||'').trim();
    if(before==='Extended') return JSON.stringify({already:'Extended', ok:true});
    for(let i=0;i<3;i++){
      clickEl(pill);
      await new Promise(r=>setTimeout(r,300));
      const found=await poll(()=>[...document.querySelectorAll('[role=menuitemradio]')].find(b=>/Thinking.*Extended/i.test((b.textContent||'').trim().replace(/\s+/g,' ')))?1:null, 2500);
      if(found){ const it=[...document.querySelectorAll('[role=menuitemradio]')].find(b=>/Thinking.*Extended/i.test((b.textContent||'').trim())); clickEl(it); break; }
    }
    const ok=await poll(()=>{const p=document.querySelector('button.__composer-pill');const t=(p&&p.textContent||'').trim();return t==='Extended'?t:null;},5000);
    return JSON.stringify({before, after:ok||(document.querySelector('button.__composer-pill')||{}).textContent, ok:ok==='Extended'});
  })();
})()
```

## 7. 汇报格式（务必照填，调度大脑要统计时长）
```
【镜像通道测试简报】
- 通道：新对话 Extended → <ok:true / 报错键>
  耗时 = <s> 秒（自 t1 起跑 tab new 前 `date +%s.%N`，到 evalB 返回 `date +%s.%N` 之差）
- 通道：旧对话 Extended → <ok:true / 报错键>
  耗时 = <s> 秒
- 卡点/踩坑：<一句话>（若无写"无"）
- 是否发了真实问题：<否>（本测试不该发）
```
- 判定：总耗时 ≤25s 且两路 `ok:true` = 通过。>25s 就把它复现给调度大脑（大概率 hydration 坑或往返过多）。

## 红线
- 别回历练 / 别改代码 / 别写仓库 / 别发真实问题消费轮次 / secret 不回显。
- 共享标签纪律：只用 `tab new` 自开，绝不动别人 tab。