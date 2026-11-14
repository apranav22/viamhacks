/* [claude-code/claude-opus-5-5 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/model-compare · 2026-11-14]
 * Models tab: every evaluated step against the morning baseline, then failures side by side.
 * Reads only frozen benchmark replays (/api/models/compare). No inference, no robot access. */
'use strict';
window.ModelReview=(()=>{
  const state={data:null,before:null,after:null,filter:'fixed',images:new Map()};
  const el=id=>document.getElementById(id),txt=(id,v)=>{el(id).textContent=v??'';};
  const ready=()=>(state.data?.versions||[]).filter(v=>v.ready);
  const byId=id=>(state.data?.versions||[]).find(v=>v.id===id);
  const wrong=v=>v.counts.missed+v.counts.false_rejects+v.counts.unknown;
  const sign=n=>n>0?`+${n}`:n<0?`−${-n}`:'±0';
  const pretty=s=>String(s||'').replace(/_/g,' ').replace(/^./,c=>c.toUpperCase());
  const short=v=>v.baseline?'Morning baseline':v.label.replace(/\s*\((trained|Fri)[^)]*\)\s*$/,'');

  function outcome(row){
    // Correct = the verdict the recorded label asks for. Uncertain is never counted as correct.
    const defect=row.label!=='good';
    if(row.category==='unknown')return {ok:false,word:'Uncertain',hint:'no usable verdict'};
    if(defect)return row.category==='detected'?{ok:true,word:'Caught'}:{ok:false,word:'Missed'};
    return row.category==='good_passed'?{ok:true,word:'Passed'}:{ok:false,word:'Wrongly rejected'};
  }
  function ratio(score){
    if(score?.status!=='ok'||!(score.threshold>0))return null;
    return score.score/score.threshold;
  }

  function steps(){
    const list=el('mc-steps'),versions=ready(),base=versions.find(v=>v.baseline)||versions[0];list.replaceChildren();
    if(!base){txt('mc-sub','No version has verified results on every benchmark item yet.');return;}
    const best=[...versions].sort((a,b)=>wrong(a)-wrong(b)||b.completed-a.completed)[0];
    txt('mc-sub',best===base?'No step has beaten the morning baseline yet.':
      `Best now: ${short(best)}. ${best.counts.detected}/${best.defective} defects caught (${sign(best.counts.detected-base.counts.detected)} vs morning), `+
      `${best.counts.false_rejects}/${best.good} good parts rejected (${sign(best.counts.false_rejects-base.counts.false_rejects)}).`);
    versions.forEach((v,i)=>{
      const li=node('li',null,'mc-step'+(v===base?' base':'')+(v.id===state.after?' active':'')+(v===best&&v!==base?' best':''));
      const head=node('div',null,'mc-step-head');
      head.append(node('span',v===base?'Start':`Step ${i}`,'mc-step-n'));
      if(v===best&&v!==base)head.append(node('span','Best','mc-tag'));
      li.append(head,node('strong',short(v),'mc-step-title'));
      const bits=[v.family==='efficientad-s'?'EfficientAD-S':'PatchCore',v.type_clf?'type classifier':'size routing'];
      if(v.train_picks)bits.push(`${v.train_picks} training picks`);
      li.append(node('p',bits.join(' · '),'subtle mc-step-sub'));
      li.append(metric('Defects caught',v.counts.detected,v.defective,v.counts.detected-base.counts.detected,true,v===base));
      li.append(metric('Good parts rejected',v.counts.false_rejects,v.good,v.counts.false_rejects-base.counts.false_rejects,false,v===base));
      if(v.counts.unknown)li.append(node('p',`${v.counts.unknown} uncertain (rejected by live policy)`,'subtle mc-unknown'));
      if(v!==base){li.tabIndex=0;li.setAttribute('role','button');li.title='Compare this step with the morning baseline';
        const pick=()=>{state.before=base.id;state.after=v.id;sync();};li.onclick=pick;li.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick();}};}
      list.append(li);
    });
  }
  function metric(name,value,total,delta,higherBetter,isBase){
    const wrap=node('div',null,'mc-metric'),line=node('div',null,'mc-metric-line');
    line.append(node('span',name,'subtle'),node('b',`${value}/${total}`));
    const good=higherBetter?delta>0:delta<0,bad=higherBetter?delta<0:delta>0;
    if(!isBase)line.append(node('span',sign(delta),'mc-delta'+(good?' up':bad?' down':'')));
    const bar=node('div',null,'mc-bar'+(higherBetter?'':' inverse')),fill=node('i');fill.style.width=`${total?100*value/total:0}%`;bar.append(fill);
    wrap.append(line,bar);return wrap;
  }

  function pairs(){
    const a=byId(state.before),b=byId(state.after);if(!a?.ready||!b?.ready)return [];
    const left=new Map(a.rows.map(r=>[r.pick+'/'+r.file,r]));
    return b.rows.map(r=>{const l=left.get(r.pick+'/'+r.file);if(!l)return null;const x=outcome(l),y=outcome(r);
      return {before:l,after:r,ob:x,oa:y,group:!x.ok&&y.ok?'fixed':x.ok&&!y.ok?'broken':!x.ok&&!y.ok?'still':'both'};}).filter(Boolean);
  }
  function compare(){
    const all=pairs(),count=g=>all.filter(p=>p.group===g).length,a=byId(state.before),b=byId(state.after);
    const n={fixed:count('fixed'),broken:count('broken'),still:count('still')};
    const filters=el('mc-filters'),grid=el('mc-grid');filters.replaceChildren();grid.replaceChildren();
    if(!all.length){txt('mc-verdict','Choose two versions with verified results.');return;}
    el('mc-verdict').replaceChildren(
      node('span',`${short(b)} vs ${short(a)}: `),node('b',`fixes ${n.fixed}`,'up'),node('span',' · '),
      node('b',`breaks ${n.broken}`,n.broken?'down':''),node('span',' · '),node('b',`${n.still} still wrong in both`));
    for(const [key,label] of [['fixed','Fixed'],['broken','Newly wrong'],['still','Still wrong'],['failures','All failures']]){
      const total=key==='failures'?all.filter(p=>p.group!=='both').length:n[key];
      const btn=node('button',`${label} ${total}`,'mc-filter '+key);btn.setAttribute('aria-pressed',String(state.filter===key));
      btn.onclick=()=>{state.filter=key;compare();};filters.append(btn);
    }
    const shown=all.filter(p=>state.filter==='failures'?p.group!=='both':p.group===state.filter);
    txt('model-empty',shown.length?'':({fixed:'Nothing fixed between these two versions.',broken:'No new failures: everything the earlier version got right is still right.',still:'No item is wrong in both versions.',failures:'Both versions agree with every recorded label.'})[state.filter]);
    el('model-empty').hidden=!!shown.length;
    for(const p of shown)grid.append(card(p,a,b));
  }
  function side(label,o,row,v){
    const s=node('div',null,'mc-side '+(o.ok?'ok':'bad'));
    s.append(node('span',label,'mc-side-label'),node('b',(o.ok?'✓ ':'✗ ')+o.word));
    const r=ratio(row.score);
    const detail=r==null?(o.hint||'no routed score'):`${r.toFixed(2)}× threshold`+(row.selected_type&&row.selected_type!==row.type?` · routed as ${pretty(row.selected_type)}`:'');
    s.append(node('small',detail));
    return s;
  }
  function card(p,a,b){
    const row=p.after,art=node('article',null,'mc-card '+p.group),thumb=node('div',null,'mc-thumb');
    const canvas=document.createElement('canvas');canvas.width=360;canvas.height=240;canvas.setAttribute('aria-label',`Camera image of ${pretty(row.type)}, cropped to the part`);thumb.append(canvas);draw(canvas,row);
    const defect=row.label!=='good';
    const meta=node('div',null,'mc-meta');
    meta.append(node('strong',`${pretty(row.type)} · ${defect?'defect: '+row.label:'good part'}`),node('span',row.pick.replace('_collect',''),'subtle'));
    const pair=node('div',null,'mc-pair');pair.append(side('Before',p.ob,p.before,a),side('After',p.oa,row,b));
    art.append(thumb,meta,pair);art.tabIndex=0;art.title='Open this capture in History';
    const open=()=>openHistory(row);art.onclick=open;art.onkeydown=e=>{if(e.key==='Enter')open();};
    return art;
  }
  async function draw(canvas,row){
    // Display crop of the saved camera image around the recorded bbox (not the model's own preprocessed input).
    if(!row.bbox){try{const [run,item]=row.pick.split('/'),d=await get('/api/history/item',{run,item});row.bbox=d.captures.find(c=>c.filename===row.file)?.bbox||null;}catch{}}
    let img=state.images.get(row.image);
    if(!img){img=new Image();img.decoding='async';img.src=row.image;state.images.set(row.image,img);}
    const paint=()=>{const ctx=canvas.getContext('2d'),[x0,y0,x1,y1]=row.bbox||[0,0,img.naturalWidth,img.naturalHeight];
      const cx=(x0+x1)/2,cy=(y0+y1)/2,ar=canvas.width/canvas.height;let w=(x1-x0)*1.5,h=(y1-y0)*1.5;
      if(w/h<ar)w=h*ar;else h=w/ar;
      ctx.drawImage(img,cx-w/2,cy-h/2,w,h,0,0,canvas.width,canvas.height);};
    if(img.complete&&img.naturalWidth)paint();else img.addEventListener('load',paint,{once:true});
    img.addEventListener('error',()=>canvas.replaceWith(node('p','Image unavailable','subtle')),{once:true});
  }
  async function openHistory(row){
    const [run,item]=row.pick.split('/');ui.evaluationChoice=state.after;mode('history');await loadRun(run,item);
    if(ui.mode==='history'&&ui.run===run&&ui.item===item){const c=ui.detail?.captures?.find(c=>c.filename===row.file);if(c){ui.selected.set(captureKey(ui.detail),c.id);render();}}
  }

  function sync(){
    const entries=ready().map(v=>[v.id,short(v)]);
    options(el('mc-before'),entries,state.before);options(el('mc-after'),entries,state.after);
    steps();compare();details();
  }
  function details(){
    const body=el('model-versions');body.replaceChildren();
    for(const v of state.data?.versions||[]){const tr=node('tr');
      tr.append(node('td',short(v)),node('td',v.ready?`${v.counts.detected}/${v.defective} caught · ${v.counts.false_rejects}/${v.good} good rejected · ${v.counts.unknown} uncertain`:'Not comparable: '+(v.issues||[]).join('; ')),
        node('td',[v.bundle,v.device,v.agent].filter(Boolean).join(' · ')));body.append(tr);}
    txt('model-note',state.data?.benchmark?.limitations||'');
  }
  async function load(id){
    try{
      state.data=await get('/api/models/compare',{benchmark:id});
      // Tolerate an older server that lacks these fields: derive them from the bundle path / report label.
      for(const v of state.data.versions){
        v.baseline??=/codex_curated_/.test(v.bundle||'');v.family??=(/effad/i.test(v.bundle||'')?'efficientad-s':'patchcore');
        v.type_clf??=/type classifier/i.test(v.source_label||'');
        for(const r of v.rows||[])r.image??='/api/history/image?path='+encodeURIComponent(r.pick+'/'+r.file);
      }
      state.data.versions.sort((a,b)=>(b.baseline-a.baseline)||(a.completed-b.completed));
      const versions=ready(),base=versions.find(v=>v.baseline)||versions[0];
      const best=[...versions].sort((a,b)=>wrong(a)-wrong(b)||b.completed-a.completed)[0];
      if(!byId(state.before)?.ready)state.before=base?.id;
      if(!byId(state.after)?.ready)state.after=(best!==base?best:versions[versions.length-1])?.id;
      const m=state.data.benchmark.members,good=m.filter(x=>x.label==='good').length;
      txt('model-benchmark-count',`${m.length} held-out top-camera picks: ${good} good, ${m.length-good} defective`);
      state.filter=pairs().some(p=>p.group==='fixed')?'fixed':'failures';
      sync();
    }catch(e){txt('model-empty',e.message);el('model-empty').hidden=false;}
  }
  async function init(){
    try{const data=await get('/api/models/benchmarks');options(el('model-benchmark'),data.benchmarks.map(b=>[b.id,b.name]),data.benchmarks[0]?.id);
      if(data.benchmarks.length)await load(data.benchmarks[0].id);else txt('model-empty','No benchmark definitions available.');}
    catch(e){txt('model-empty',e.message);}
  }
  el('model-benchmark').onchange=e=>load(e.target.value);
  el('mc-before').onchange=e=>{state.before=e.target.value;sync();};
  el('mc-after').onchange=e=>{state.after=e.target.value;sync();};
  el('mc-swap').onclick=()=>{[state.before,state.after]=[state.after,state.before];sync();};
  el('model-details-open').onclick=()=>el('model-dialog').showModal();
  el('model-details-close').onclick=()=>el('model-dialog').close();
  return {init,outcome};
})();
ModelReview.init();
