# 测试任务：镜像站「零→Extended」通道计时（交给你自测）

> 转发对象：任意执行 Agent。你要做的：**照下面的命令跑一遍，用系统时钟计时，按最后格式回一份简报。** 只测通道 + 闸门，**不要发任何真实问题**（不消费 GPT 轮次），不改代码、不写仓库。
> 规范真源（选项）：`D:\Work\AI平台\docs\运行手册\GPT镜像站一键交接文档（给执行Agent）.md` —— 卡住了先读它 §3/§4。

## 你要跑的命令（新对话路）
```bash
T1=$(date +%s.%N)
opencli browser n8hh7hyn tab new "https://ai.wendabao-f.net/?utm_source=hidden-ncn"
sleep 2
opencli browser n8hh7hyn eval "$(cat /tmp/evalA_jump.js)"   # 见下「脚本A」
R=$(opencli browser n8hh7hyn eval "$(cat /tmp/evalB_ext.js)")  # 见下「脚本B」
T2=$(date +%s.%N)
echo "$R"
echo "新对话耗时 = $(echo "$T2 $T1" | awk '{print ($1-$2)}') 秒"
```

## 脚本A：先落盘到 /tmp/evalA_jump.js
```bash
cat > /tmp/evalA_jump.js <<'JSEOF'
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
JSEOF
```

## 脚本B：再落盘到 /tmp/evalB_ext.js
```bash
cat > /tmp/evalB_ext.js <<'JSEOF'
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
JSEOF
```

## 旧对话路（合并计时可选）
跳进镜像后，先 eval 点侧栏第一个 `/c/` 链接（或直接 `tab new <该 vip 的 /c/>`），再对当前页跑一遍 `evalB_ext.js`，同样前后 `date +%s.%N` 计时。旧对话 composer 是 contenteditable，但同一个 `button.__composer-pill`，evalB 直接吃。

## 内存里先过一遍三大坑（免得白跑）
1. **hydration**：部分实例 pill 首载是占位 `Model`，必须等它变 `Auto`/`Extended` 才点——evalB 已内建，别删那步。
2. **Radix 菜单**：只 `.click()` 打不开，必须完整指针序列+原生 click——evalB 的 `clickEl()` 已封装。
3. **别用固定 sleep**：靠 await 轮询，等等到、等不到超时。
4. **脚本传 IIFE 自执行 `(()=>{...})()`，别加 `--tab`**：裸箭头字面量 `() => {...}` 在部分 opencli 版本（v1.8.0 等）会报 `Unexpected token ')'`；要定向别的标签先用 `tab select <id>` 钉死。若仍翻车，先跑契约自检：`opencli browser n8hh7hyn eval "1+1"` 应回 `2`，`eval "(()=>1)()"` 应回 `1`，把结果与 `opencli --version` 一起抄回。

## 汇报格式（照填）
```
【镜像通道测试简报】
- 新对话 Extended → <ok:true / err键>　耗时 <s> 秒
- 旧对话 Extended → <ok:true / err键>　耗时 <s> 秒
- 卡点：<一句话，无则"无">
- 是否发了真实问题：否
```
提示：≤25s 且两路 ok:true = 通过；>25s 把复现卡点抄给调度大脑。