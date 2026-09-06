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