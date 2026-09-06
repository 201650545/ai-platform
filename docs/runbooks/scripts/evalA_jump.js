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