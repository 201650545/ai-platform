/**
 * ⚠️ 已部分失效（2026-09-19 标注）—— 请勿直接照抄本脚本的判定逻辑
 *
 * 镜像站于 2026-09-15 改版：思考菜单「Thinking• Extended」已下线，现为「Thinking• Standard」/「GPT-5.6 Luna」等；
 * 成功切档后 pill 文案为 "Thinking" 而非 "Extended"。本脚本最后修改于 2026-09-06，早于改版 9 天。
 *
 * 三处断裂（逐行证据见 D:\Work\自适应工作流引擎\docs\02-镜像站试点盘点.md §四）：
 *   行 14    hydration 闸门 /^(Auto|Extended)$/ → 实际 pill 为 Model/Thinking，poll 超时返回 err:'pill-not-ready'
 *   行 21-22 菜单项匹配 /Thinking.*Extended/i   → 现无该项，菜单空转
 *   行 24-25 判定 t === 'Extended' 才算 ok      → 切档成功后实为 'Thinking'，恒返回 ok:false（假阴性）
 *
 * 风险性质：本脚本会给出**假信号**（假阴性 ok:false / 误以为已在深度档），比直接报错更危险 ——
 *           而本手册纪律是「B 返回 ok:true 才可发问」，照抄将导致送审链路被卡死，或在错误档位发问。
 *
 * 替代方案：契约化自适应版 runner
 *   D:\Work\自适应工作流引擎\runners\evalB_ext_adaptive.js
 *   （域名 / 选择器 / 菜单文案全部改为从契约 contracts\gpt-mirror-extended-review.yaml 的 candidates
 *     候选集读取；pill 就绪判定放宽为集合；校验读探针回填的 resolved_label，不再字面量比对）
 *   该 runner 在 A2 阶段落地。落地前请勿在未核对 pill 与菜单实际文案的情况下依赖本脚本的返回值。
 *
 * 保留原因：本文件是 2026-09-06 实测「零→Extended 74s→9.6s」提速结论的原始载体，兼作回归基线与
 *           「硬编码断言如何静默过期」的失效样本，故只加标注、不改逻辑。
 *           （决策 D4，记录于 D:\Work\自适应工作流引擎\docs\01-任务看板.md §六）
 */
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