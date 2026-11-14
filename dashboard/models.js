/* [claude-code/claude-opus-5-5 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/model-compare · 2026-11-14]
 * Models tab: leaderboard of every model variant on a chosen evaluation set, head to head A vs B, and the pictures
 * behind every number. Reads /api/models/matrix (saved offline scores). No inference, no robot access. */
'use strict';
window.ModelReview=(()=>{
  const SETS=[
    ['bench','Benchmark','The same 62 frozen pictures for every model. Pictures a model trained or calibrated on are left out of its count.'],
    ['test','Held-out','Pictures from the model\'s own collection runs that it never trained or calibrated on.'],
    ['unseen','Unseen runs','Pictures from runs collected after the model was built: the closest thing to new data.'],
    ['heldall','All held-out','Held-out plus unseen runs: everything the model never learned from.'],
    ['calibration','Calibration','Good pictures used to set the model\'s threshold. Sanity check, not generalisation.'],
    ['train','Training','Good pictures the model learned from. Sanity check: failures here mean the model cannot fit its own data.']];
  const ROLE={t:'Training',c:'Calibration',h:'Held-out',u:'Unseen run',x:'Not used'};
  const OUT={caught:'Caught',missed:'Missed',passed:'Passed',false_reject:'Wrongly rejected',uncertain:'Uncertain'};
  const state={data:null,set:'bench',a:null,b:null,view:null,list:[],lb:0,images:new Map()};
  const el=id=>document.getElementById(id),txt=(id,v)=>{el(id).textContent=v??'';};
  const pretty=s=>String(s||'').replace(/_/g,' ').replace(/^./,c=>c.toUpperCase());
  const model=id=>state.data?.models.find(m=>m.id===id);
  const title=m=>m?`${m.name}${m.pooled?'':m.routing==='type classifier'?' · classifier':' · size'}`:'';

  function inSet(cell,pick,set){
    if(!cell)return false;const r=cell[0];
    return set==='bench'?pick.bench&&(r==='h'||r==='u'):set==='test'?r==='h':set==='unseen'?r==='u':set==='heldall'?r==='h'||r==='u':set==='calibration'?r==='c':r==='t';
  }
  function outcome(cell,pick){
    const v=cell[1];if(v==='?')return 'uncertain';
    return pick.label!=='good'?(v==='r'?'caught':'missed'):(v==='a'?'passed':'false_reject');
  }
  const ok=o=>o==='caught'||o==='passed';
  function stats(m,set){
    const s={n:0,def:0,good:0,caught:0,missed:0,passed:0,false_reject:0,uncertain:0,items:{}};
    state.data.picks.forEach((p,i)=>{const c=m.cells[i];if(!inSet(c,p,set))return;s.n++;p.label==='good'?s.good++:s.def++;const o=outcome(c,p);s[o]++;(s.items[o]??=[]).push(i);});
    s.errors=s.missed+s.false_reject+s.uncertain;s.acc=s.n?(s.caught+s.passed)/s.n:null;return s;
  }
  function roles(m){const r={t:0,c:0,h:0,u:0};for(const c of m.cells)if(c&&r[c[0]]!=null)r[c[0]]++;return r;}

  function sets(){
    const box=el('mb-sets');box.replaceChildren();
    for(const [id,label] of SETS){const b=node('button',label,'mb-set');b.setAttribute('aria-pressed',String(state.set===id));b.onclick=()=>{state.set=id;state.view=null;render();};box.append(b);}
    txt('mb-set-note',SETS.find(s=>s[0]===state.set)[2]);
  }
  function link(text,view,cls){
    if(!text||text==='0')return node('span',text,'mb-zero');
    const b=node('button',text,'mb-num '+(cls||''));b.onclick=()=>{state.view=view;gallery();el('mb-gallery-title').scrollIntoView({behavior:'smooth',block:'start'});};return b;
  }
  function board(){
    const body=el('mb-board');body.replaceChildren();
    const rows=state.data.models.map(m=>({m,s:stats(m,state.set)}));
    rows.sort((x,y)=>(!!y.s.n-!!x.s.n)||(x.s.errors/(x.s.n||1))-(y.s.errors/(y.s.n||1)));
    const best=rows.find(r=>r.s.n);
    for(const {m,s} of rows){
      const tr=node('tr',null,(m.id===state.a?'is-a ':'')+(m.id===state.b?'is-b':''));
      for(const side of ['a','b']){const td=node('td');const r=document.createElement('input');r.type='radio';r.name='mb-'+side;r.checked=state[side]===m.id;r.setAttribute('aria-label',`Use ${title(m)} as model ${side.toUpperCase()}`);r.onchange=()=>{state[side]=m.id;state.view=null;render();};td.append(r);tr.append(td);}
      const name=node('td',null,'mb-name');name.append(node('strong',m.name));
      const tags=node('div',null,'mb-tags');tags.append(node('span',m.family,'mb-tag '+(m.family==='EfficientAD-S'?'ead':'pc')));
      if(!m.pooled)tags.append(node('span',m.routing,'mb-tag'));
      if(m.baseline)tags.append(node('span','morning baseline','mb-tag base'));
      if(m.scope==='benchmark')tags.append(node('span','benchmark only','mb-tag warn'));
      if(best&&m===best.m&&s.n)tags.append(node('span','best on this set','mb-tag win'));
      name.append(tags);tr.append(name);
      tr.append(splitBar(m));
      if(!s.n){const td=node('td',m.scope==='benchmark'?'Only benchmark results available':'No pictures in this set','subtle');td.colSpan=5;tr.append(td);body.append(tr);continue;}
      const caught=node('td',null,'num');caught.append(link(`${s.caught}/${s.def}`,{kind:'model',id:m.id,outs:['caught']}),bar(s.def?s.caught/s.def:0,'good'));
      const fr=node('td',null,'num');fr.append(link(`${s.false_reject}/${s.good}`,{kind:'model',id:m.id,outs:['false_reject']},'bad'),bar(s.good?s.false_reject/s.good:0,'bad'));
      const missed=node('td',null,'num');missed.append(link(String(s.missed),{kind:'model',id:m.id,outs:['missed']},'bad'));
      const unc=node('td',null,'num');unc.append(link(String(s.uncertain),{kind:'model',id:m.id,outs:['uncertain']},'warn'));
      tr.append(caught,missed,fr,unc,node('td',`${(100*s.acc).toFixed(1)}%`,'num mb-acc'));
      body.append(tr);
    }
  }
  function bar(f,kind){const b=node('div',null,'mb-bar '+kind),i=node('i');i.style.width=`${Math.round(100*f)}%`;b.append(i);return b;}
  function splitBar(m){
    const td=node('td',null,'mb-split'),r=roles(m),total=r.t+r.c+r.h+r.u,b=node('div',null,'mb-stack');
    for(const k of ['t','c','h','u']){if(!r[k])continue;const i=node('i',null,'r'+k);i.style.flex=String(r[k]);i.title=`${ROLE[k]}: ${r[k]}`;b.append(i);}
    td.append(b,node('small',m.scope==='benchmark'?`${r.h} benchmark pictures`:`${r.t} train · ${r.c} cal · ${r.h} held-out · ${r.u} unseen`,'subtle'));
    td.title=`${total} pictures scored`;return td;
  }

  function h2h(){
    const A=model(state.a),B=model(state.b),entries=state.data.models.map(m=>[m.id,title(m)]);
    options(el('mb-a'),entries,state.a);options(el('mb-b'),entries,state.b);
    const quad=el('mb-quad');quad.replaceChildren();el('mb-better').replaceChildren();el('mb-worse').replaceChildren();
    if(!A||!B||A===B){txt('mb-h2h-note','Pick two different models (A and B columns in the table).');return;}
    const g={both_right:[],b_better:[],a_better:[],both_wrong:[]};
    state.data.picks.forEach((p,i)=>{const ca=A.cells[i],cb=B.cells[i];if(!inSet(ca,p,state.set)||!inSet(cb,p,state.set))return;
      const x=ok(outcome(ca,p)),y=ok(outcome(cb,p));g[x&&y?'both_right':!x&&y?'b_better':x&&!y?'a_better':'both_wrong'].push(i);});
    const n=Object.values(g).reduce((s,l)=>s+l.length,0);
    txt('mb-h2h-note',n?`${n} pictures in "${SETS.find(s=>s[0]===state.set)[1]}" for both models. B: ${title(B)}. A: ${title(A)}.`:'These two models share no pictures in this set. Try "All held-out" or "Benchmark".');
    if(!n)return;
    for(const [key,label,cls] of [['b_better','B right, A wrong','good'],['a_better','A right, B wrong','bad'],['both_wrong','Both wrong','warn'],['both_right','Both right','']]){
      const c=node('button',null,'mb-q '+cls);c.append(node('b',String(g[key].length)),node('span',label));c.setAttribute('aria-pressed',String(state.view?.kind==='h2h'&&state.view.cell===key&&!state.view.group));
      c.onclick=()=>{state.view={kind:'h2h',cell:key,items:g[key]};gallery();};quad.append(c);
    }
    chips('mb-better',g.b_better,'b_better');chips('mb-worse',g.a_better,'a_better');
    if(!state.view)state.view={kind:'h2h',cell:g.b_better.length?'b_better':'a_better',items:g.b_better.length?g.b_better:g.a_better};
  }
  function chips(id,items,cell){
    const box=el(id),groups=new Map();
    for(const i of items){const p=state.data.picks[i],k=`${pretty(p.type)} · ${p.label==='good'?'good part':'defect: '+p.label}`;(groups.get(k)??groups.set(k,[]).get(k)).push(i);}
    if(!groups.size){box.append(node('p','None','subtle'));return;}
    for(const [k,list] of [...groups].sort((a,b)=>b[1].length-a[1].length)){const c=node('button',null,'mb-chip');c.append(node('span',k),node('b',String(list.length)));
      c.onclick=()=>{state.view={kind:'h2h',cell,group:k,items:list};gallery();el('mb-gallery-title').scrollIntoView({behavior:'smooth',block:'start'});};box.append(c);}
  }

  function gallery(){
    const v=state.view,grid=el('mb-gallery');grid.replaceChildren();
    for(const b of el('mb-quad').querySelectorAll('.mb-q'))b.setAttribute('aria-pressed','false');
    if(!v){txt('mb-gallery-title','Pictures');txt('mb-gallery-count','');return;}
    let list,heading;
    if(v.kind==='model'){const m=model(v.id),s=stats(m,state.set);list=v.outs.flatMap(o=>s.items[o]||[]);heading=`${title(m)}: ${v.outs.map(o=>OUT[o].toLowerCase()).join(', ')}`;}
    else{list=v.items;heading={b_better:'B right, A wrong',a_better:'A right, B wrong',both_wrong:'Both wrong',both_right:'Both right'}[v.cell]+(v.group?` · ${v.group}`:'');}
    state.list=list;txt('mb-gallery-title',heading);txt('mb-gallery-count',`${list.length} picture${list.length===1?'':'s'} · ${SETS.find(s=>s[0]===state.set)[1]}`);
    el('model-empty').hidden=!!list.length;txt('model-empty','No pictures here.');
    const A=model(state.a),B=model(state.b),pair=v.kind==='h2h'?[['A',A],['B',B]]:[['',model(v.id)]];
    list.forEach((i,pos)=>{
      const p=state.data.picks[i],card=node('article',null,'mb-card'),thumb=node('div',null,'mb-thumb'),c=document.createElement('canvas');c.width=320;c.height=213;thumb.append(c);draw(c,p,1.5);
      const meta=node('div',null,'mb-meta');meta.append(node('strong',pretty(p.type)),node('span',p.label==='good'?'good part':'defect: '+p.label,'mb-label '+(p.label==='good'?'g':'d')));
      const verdicts=node('div',null,'mb-verdicts');
      for(const [k,m] of pair){const cell=m.cells[i],o=outcome(cell,p),d=node('div',null,'mb-v '+(ok(o)?'ok':'bad'));
        d.append(node('span',k||'Verdict','mb-v-k'),node('b',(ok(o)?'✓ ':'✗ ')+OUT[o]),node('small',cell[2]!=null?`${cell[2].toFixed(2)}× thr`+(cell[3]&&cell[3]!==p.type?` · as ${pretty(cell[3])}`:''):'no score'));verdicts.append(d);}
      card.append(thumb,meta,verdicts);card.tabIndex=0;card.onclick=()=>open(pos);card.onkeydown=e=>{if(e.key==='Enter')open(pos);};grid.append(card);
    });
    if(v.kind==='h2h')for(const b of el('mb-quad').querySelectorAll('.mb-q'))if(b.querySelector('span').textContent===({b_better:'B right, A wrong',a_better:'A right, B wrong',both_wrong:'Both wrong',both_right:'Both right'})[v.cell])b.setAttribute('aria-pressed','true');
  }
  function image(p){let img=state.images.get(p.image);if(!img){img=new Image();img.decoding='async';img.src=p.image;state.images.set(p.image,img);}return img;}
  function draw(canvas,p,pad,box=false){
    const img=image(p),paint=()=>{const ctx=canvas.getContext('2d'),W=canvas.width,H=canvas.height;
      if(!pad){ctx.drawImage(img,0,0,W,H);if(box&&p.bbox){const sx=W/img.naturalWidth,sy=H/img.naturalHeight,[x0,y0,x1,y1]=p.bbox;ctx.lineWidth=3;ctx.strokeStyle='#ffcc00';ctx.strokeRect(x0*sx,y0*sy,(x1-x0)*sx,(y1-y0)*sy);}return;}
      const [x0,y0,x1,y1]=p.bbox||[0,0,img.naturalWidth,img.naturalHeight],cx=(x0+x1)/2,cy=(y0+y1)/2,ar=W/H;let w=(x1-x0)*pad,h=(y1-y0)*pad;if(w/h<ar)w=h*ar;else h=w/ar;
      ctx.fillStyle='#000';ctx.fillRect(0,0,W,H);ctx.drawImage(img,cx-w/2,cy-h/2,w,h,0,0,W,H);};
    if(img.complete&&img.naturalWidth)paint();else img.addEventListener('load',paint,{once:true});
  }
  function open(pos){state.lb=pos;lightbox();const d=el('mb-lightbox');if(!d.open)d.showModal();}
  function lightbox(){
    const i=state.list[state.lb],p=state.data.picks[i];
    txt('mb-lb-title',`${pretty(p.type)} · ${p.label==='good'?'good part':'defect: '+p.label}`);txt('mb-lb-pos',`${state.lb+1} / ${state.list.length}`);
    el('mb-lb-prev').disabled=state.lb===0;el('mb-lb-next').disabled=state.lb>=state.list.length-1;
    draw(el('mb-lb-full'),p,0,true);draw(el('mb-lb-crop'),p,1.3);
    txt('mb-lb-meta',`${p.pick} · ${p.file}${p.bench?' · in benchmark':''} · recorded label: ${p.label}`);
    const body=el('mb-lb-rows');body.replaceChildren();
    for(const m of state.data.models){const c=m.cells[i],tr=node('tr',null,(m.id===state.a?'is-a ':'')+(m.id===state.b?'is-b':''));
      tr.append(node('td',title(m)));
      if(!c){tr.append(node('td','Not scored','subtle'),node('td','—'),node('td','—','num'));body.append(tr);continue;}
      const o=outcome(c,p);tr.append(node('td',ROLE[c[0]],c[0]==='t'||c[0]==='c'?'subtle':''),node('td',(ok(o)?'✓ ':'✗ ')+OUT[o],ok(o)?'clear':'flagged'),
        node('td',c[2]!=null?`${c[2].toFixed(2)}×`+(c[3]&&c[3]!==p.type?` (as ${pretty(c[3])})`:''):'—','num'));body.append(tr);}
  }

  function render(){
    if(!state.data)return;sets();board();h2h();gallery();
    const d=state.data,good=d.picks.filter(p=>p.label==='good').length;
    txt('mb-sub',`${d.models.length} model variants · ${d.picks.length} saved top-camera pictures (${good} good, ${d.picks.length-good} defective) from ${d.runs} runs`+(d.mismatched.length?` · ${d.mismatched.length} pictures changed since scoring, left out`:''));
  }
  async function init(){
    try{
      state.data=await get('/api/models/matrix');const ms=state.data.models;
      const benchErr=m=>{const s=stats(m,'bench');return s.n?s.errors/s.n:9;};
      state.a=(ms.find(m=>m.baseline)||ms[0])?.id;state.b=[...ms].filter(m=>m.id!==state.a).sort((x,y)=>benchErr(x)-benchErr(y))[0]?.id;
      render();
    }catch(e){txt('mb-sub',e.message);}
  }
  el('mb-a').onchange=e=>{state.a=e.target.value;state.view=null;render();};
  el('mb-b').onchange=e=>{state.b=e.target.value;state.view=null;render();};
  el('mb-swap').onclick=()=>{[state.a,state.b]=[state.b,state.a];state.view=null;render();};
  el('mb-lb-prev').onclick=()=>{state.lb--;lightbox();};el('mb-lb-next').onclick=()=>{state.lb++;lightbox();};
  el('mb-lb-close').onclick=()=>el('mb-lightbox').close();
  el('mb-lightbox').addEventListener('keydown',e=>{if(e.key==='ArrowLeft'&&state.lb>0){state.lb--;lightbox();}if(e.key==='ArrowRight'&&state.lb<state.list.length-1){state.lb++;lightbox();}});
  el('mb-lb-history').onclick=async()=>{const p=state.data.picks[state.list[state.lb]],[run,item]=p.pick.split('/');el('mb-lightbox').close();mode('history');await loadRun(run,item);
    if(ui.mode==='history'&&ui.run===run&&ui.item===item){const c=ui.detail?.captures?.find(c=>c.filename===p.file);if(c){ui.selected.set(captureKey(ui.detail),c.id);render_history();}}};
  el('model-details-open').onclick=()=>el('model-dialog').showModal();
  el('model-details-close').onclick=()=>el('model-dialog').close();
  return {init,outcome,inSet};
})();
const render_history=()=>render();
ModelReview.init();
