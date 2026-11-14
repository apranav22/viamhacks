/* [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14] */
'use strict';
const {RunState,frameUrl,anomalyStatus,captureVerdict,finite}=DashboardState;
const $=id=>document.getElementById(id);
const names={button_ss_long:'Button screw',hex_nut:'Hex nut',socket_thin_long:'Thin long socket screw',socket_thin_short:'Thin short socket screw',socket_m16:'Large socket screw',hex_bolt_partial:'Long hex bolt',hex_bolt_short:'Short hex bolt'};
const human=value=>names[value] || value || 'Unknown part';
const text=(id,value)=>{$(id).textContent=value ?? '';};
const show=(id,visible)=>{const element=$(id);element.hidden=!visible;element.toggleAttribute('hidden',!visible);};
const format=(v,d=2)=>finite(v)?v.toFixed(d):'—';
const outcome=value=>({good:'Accept decision',reject:'Reject decision',collect:'Collected',dropped:'Part dropped',none:'No decision'})[value] || 'Inspecting / no decision';
const live=new RunState();
const ui={mode:['#live','#models'].includes(location.hash)?location.hash.slice(1):'history',runs:[],run:null,runData:null,item:null,detail:null,liveItem:null,evaluation:'recorded',evaluationChoice:null,selected:new Map(),camera:'cam',connected:false};
let request=0,indexRequest=0,renderPending=false,stripKey='',currentCapture=null;
function error(message){text('error',message);show('error',!!message);}
function node(tag,content,className){const e=document.createElement(tag);if(content!=null)e.textContent=content;if(className)e.className=className;return e;}
function options(element,entries,value){const signature=JSON.stringify(entries);if(element.dataset.options!==signature){element.replaceChildren(...entries.map(([v,label])=>{const o=node('option',label);o.value=v;return o;}));element.dataset.options=signature;}element.value=value;}
async function get(path,params={}){const response=await fetch(path+'?'+new URLSearchParams(params),{cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error || 'Could not load saved data');return data;}
function schedule(){if(renderPending)return;renderPending=true;requestAnimationFrame(()=>{renderPending=false;render();});}
function mode(value){ui.mode=value;$('details-dialog').close();$('model-dialog').close();location.hash=value;render();}
function activeItem(){return ui.mode==='live'?live.items.get(String(ui.liveItem)):ui.detail;}
function captureKey(item){return [ui.mode,ui.mode==='live'?live.run:ui.run,item.id].join(':');}
function evaluation(item){return ui.mode==='history'?(item.evaluations || []).find(e=>e.id===ui.evaluation):null;}
function scoreFor(c,e){return e?(e.scores[c.id] || {status:'not_replayed',detail:'This capture was not included in this replay'}):(c.score || {});}
function tapeFor(c){
  const value=c.tape ?? c.score?.tape, threshold=c.tape_threshold ?? c.score?.tape_threshold;
  let flagged=c.score?.tape_flagged;
  if(c.trigger_detector==='tape')flagged=true;
  else if(finite(value)&&finite(threshold))flagged=value>threshold;
  return {status:flagged===true?'Flagged':flagged===false?'No flag':finite(value)?'Measured':'Not evaluated',flagged,value,threshold};
}
function setImage(id,url,empty){const image=$(id);if(image.dataset.source===String(url)&&(!url||image.getAttribute('src')===String(url)))return;image.dataset.source=String(url);show(id,false);if(empty)show(empty,!url);image.onload=()=>{show(id,true);if(empty)show(empty,false);if(id==='original')renderImageGeometry();};image.onerror=()=>{show(id,false);if(empty)show(empty,true);if(id==='original'){show('detection-overlay',false);show('region-crop',false);}};if(url)image.src=url;else image.removeAttribute('src');}
function renderImageGeometry(){
  const c=currentCapture,img=$('original'),b=c?.bbox;
  const valid=!img.hidden&&img.complete&&img.naturalWidth>0&&Array.isArray(b)&&b.length===4&&b.every(finite)&&b[0]>=0&&b[1]>=0&&b[2]>b[0]&&b[3]>b[1]&&b[2]<=img.naturalWidth&&b[3]<=img.naturalHeight;
  show('detection-overlay',valid);show('region-crop',false);
  if(!valid)return;
  const [x,y,x2,y2]=b;
  $('detection-overlay').setAttribute('viewBox',`0 0 ${img.naturalWidth} ${img.naturalHeight}`);
  $('detection-overlay').setAttribute('aria-label',c.view==='top'?'Saved blob detection box':'Saved inspection region');
  for(const [key,value] of Object.entries({x,y,width:x2-x,height:y2-y}))$('detection-box').setAttribute(key,value);
  $('detection-box').classList.toggle('region',c.view!=='top');
  if($('crop').dataset.source==='undefined'||$('crop').dataset.source==='null'){
    for(const [key,value] of Object.entries({x,y,width:x2-x,height:y2-y}))$('region-bound').setAttribute(key,value);
    $('region-crop').setAttribute('viewBox',`${x} ${y} ${x2-x} ${y2-y}`);
    $('region-image').setAttribute('href',c.url);$('region-image').setAttribute('width',img.naturalWidth);$('region-image').setAttribute('height',img.naturalHeight);
    show('region-crop',true);show('crop-error',false);
  }
}
function runLabel(run){
  const match=run.id.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  const date=run.started?new Date(run.started):match?new Date(+match[1],+match[2]-1,+match[3],+match[4],+match[5],+match[6]):null;
  return date&&!Number.isNaN(date.getTime())?date.toLocaleDateString(undefined,{month:'short',day:'numeric'})+' · '+date.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit',second:'2-digit'}):run.id.replaceAll('_',' ');
}
function itemList(){return ui.mode==='live'?Array.from(live.items.values()):ui.runData?.items || [];}
function selectItem(id){if(ui.mode==='live'){ui.liveItem=id;$('follow').checked=false;render();}else loadItem(id);}
function renderItemNavigation(){
  const items=itemList(),id=ui.mode==='live'?ui.liveItem:ui.item,index=items.findIndex(i=>i.id===id);
  const entries=items.map((i,n)=>[i.id,i.number!=null?`Item ${n+1} of ${items.length}`:i.id==='_telemetry'?'Recorded captures':'Run images']);
  options($('item-picker'),entries,id);$('previous-item').disabled=index<=0;$('next-item').disabled=index<0||index>=items.length-1;
}

async function loadRuns(refresh=false){
  const token=++indexRequest;$('refresh').disabled=true;error('');
  try{const data=await get('/api/history/runs',refresh?{refresh:'1'}:{});if(token!==indexRequest)return;ui.runs=data.runs;
    text('history-count',`${data.totals.runs} runs · ${data.totals.items} items / groups · ${data.totals.captures.toLocaleString()} saved captures, plus telemetry recordings`);
    if(data.warnings?.length)error(data.warnings.join(' · '));
    const desired=ui.run || new URLSearchParams(location.search).get('run');
    renderRunOptions();
    const first=ui.runs.find(r=>r.id===desired) || ui.runs.find(r=>r.capture_count>0) || ui.runs[0];
    if(first)await loadRun(first.id,refresh?ui.item:new URLSearchParams(location.search).get('item'));
    else{ui.detail=null;ui.runData=null;render();}
  }catch(e){if(token===indexRequest)error(e.message);}finally{if(token===indexRequest)$('refresh').disabled=false;}
}
function renderRunOptions(){
  const search=$('run-search').value.toLowerCase(),kind=$('run-kind').value;
  const rows=ui.runs.filter(r=>(!kind || r.kind===kind)&&(!search || [r.id,...r.parts].join(' ').toLowerCase().includes(search)));
  const entries=rows.map(r=>[r.id,runLabel(r)]);
  if(!entries.length)entries.push(['','No matching runs']);
  else if(ui.run && !rows.some(r=>r.id===ui.run))entries.unshift(['','Choose a matching run']);
  options($('history-run'),entries,rows.some(r=>r.id===ui.run)?ui.run:entries[0][0]);
}
async function loadRun(id,wantedItem){
  if(!id)return;const token=++request;ui.run=id;ui.runData=null;ui.detail=null;ui.item=null;error('');render();
  try{const data=await get('/api/history/run',{run:id});if(token!==request)return;ui.runData=data;renderRunOptions();
    const note=data.note || {};text('run-note',[note.what,note.note].filter(Boolean).join(' · '));show('run-notes',!!(note.what || note.note));
    const first=data.items.find(i=>i.id===wantedItem) || data.items.find(i=>i.capture_count>0) || data.items[0];
    if(first)await loadItem(first.id);else render();
  }catch(e){if(token===request)error(e.message);}
}
async function loadItem(id){
  const token=++request,run=ui.run;ui.item=id;ui.detail=null;ui.evaluation='recorded';error('');render();
  try{const data=await get('/api/history/item',{run,item:id});if(token!==request)return;
    if(data.events){const recorded=new RunState();for(const event of data.events)recorded.ingest(event);
      const captures=Array.from(recorded.items.values()).flatMap(i=>i.captures.map(c=>({...c,label:`Item ${i.number} · ${c.label || c.view}`})));
      ui.detail={...data,captures,record:{decision:null,reason:'Recorded telemetry; capture-level evidence shown below'},unassigned:[],evaluations:[]};
    }else ui.detail=data;
    const evals=ui.detail.evaluations || [];
    ui.evaluation=ui.evaluationChoice==='recorded'?'recorded':evals.find(e=>e.id===ui.evaluationChoice)?.id || [...evals].sort((a,b)=>(b.completed || 0)-(a.completed || 0))[0]?.id || 'recorded';
    if(ui.mode==='history')history.replaceState(null,'','?'+new URLSearchParams({run,item:id})+'#history');
    render();
  }catch(e){if(token===request)error(e.message);}
}
function renderLive(){
  text('live-title',live.run || 'Waiting for a run');
  text('live-subtitle',live.replay?'Recorded telemetry replay · no live robot run':live.run?'State: '+live.stage:'No run telemetry has arrived.');
  const age=live.lastReceived?(Date.now()-live.lastReceived)/1000:Infinity;
  text('live-status',!ui.connected?'Disconnected':live.replay?'Replay':!live.run?'Idle':live.stage==='IDLE'?'Run ended':age>5?'Telemetry stale':'Receiving telemetry');
  if($('follow').checked && live.current!=null)ui.liveItem=String(live.current);
  if(!live.items.has(String(ui.liveItem)))ui.liveItem=Array.from(live.items.keys()).at(-1) || null;
  const frame=live.feeds[ui.camera],url=frame&&frameUrl(frame);setImage('feed-image',url,'feed-empty');
  if(frame){const seconds=finite(frame.t)?Math.max(0,Date.now()/1000-frame.t):null;const continuous=['watch','preview'].includes(frame.k);
    text('feed-age',(live.replay?'Replay snapshot':continuous?(seconds!=null&&seconds<3?'Live preview':'Stale preview'):'Snapshot')+(seconds!=null?' · '+seconds.toFixed(1)+' s old':''));
  }else text('feed-age','No frame');
  text('feed-age-visible',$('feed-age').textContent);
}
function renderCaptures(item,e){
  const captures=item.captures || [],selectionKey=captureKey(item);
  let chosen=captures.find(c=>c.id===ui.selected.get(selectionKey));
  if(!chosen)chosen=(e?captures.find(c=>e.scores[c.id]?.status==='ok'):captures.find(c=>c.trigger)) || captures.filter(c=>c.view==='top').at(-1) || captures[0];
  const signature=JSON.stringify([selectionKey,ui.evaluation,item.label,captures.map(c=>[c.id,c.url,anomalyStatus(scoreFor(c,e)),tapeFor(c).status,c.trigger])]);
  if(stripKey!==signature){stripKey=signature;const focus=document.activeElement?.dataset.capture;$('captures').replaceChildren();
    for(const [index,c] of captures.entries()){const verdict=captureVerdict(scoreFor(c,e),tapeFor(c).flagged,item.label,!!e);
      const button=node('button',String(index+1),'capture-button '+verdict.tone);if(verdict.short)button.append(node('span',' · '+verdict.short,'capture-result'));button.type='button';button.dataset.capture=c.id;
      button.setAttribute('aria-label',`Capture ${index+1}: ${c.label || c.filename} · ${verdict.text}`);button.title=`${c.label || c.filename} · ${verdict.text}`;
      button.addEventListener('click',()=>{ui.selected.set(selectionKey,c.id);render();});$('captures').append(button);
      if(focus===c.id)button.focus();
    }
  }
  const selectedIndex=captures.findIndex(c=>c.id===chosen?.id),page=Math.floor(Math.max(0,selectedIndex)/6);
  for(const [i,b] of Array.from($('captures').children).entries()){b.setAttribute('aria-pressed',String(b.dataset.capture===chosen?.id));b.hidden=Math.floor(i/6)!==page;}
  show('capture-page-prev',captures.length>6);show('capture-page-next',captures.length>6);
  $('capture-page-prev').disabled=page===0;$('capture-page-next').disabled=(page+1)*6>=captures.length;

  text('capture-count',`${captures.length} ${ui.mode==='history'?'saved captures':'captures received'}`);show('no-captures',!captures.length);show('capture-content',!!chosen);
  show('capture-details',!!chosen);
  if(chosen)renderCapture(item,chosen,e);else{text('verdict','No captures saved');text('verdict-source','');}
}
function renderCapture(item,c,e){
  const score=scoreFor(c,e),tape=tapeFor(c);
  const verdict=captureVerdict(score,tape.flagged,item.label,!!e);text('verdict',verdict.text);$('verdict').className=verdict.tone;
  text('verdict-source',e?(score.status==='not_replayed'?'Not included in recheck':'Rechecked image'):'');
  text('capture-title',c.label || c.filename);text('capture-time',finite(c.timestamp)?new Date(c.timestamp*1000).toLocaleString():'Capture time not recorded');
  currentCapture=c;show('detection-overlay',false);show('region-crop',false);setImage('original',c.url,'image-error');text('image-caption','Camera image');
  let crop=c.crop_url,cropLabel=c.crop_label || 'Saved crop';
  if(e && score.input_verified && e.crop_policy==='part-top-v2' && c.view==='top' && c.bbox){crop='/api/history/crop?'+new URLSearchParams({run:ui.run,item:item.id,capture:c.id,evaluation:e.id});cropLabel='Model crop reconstructed with verified replay preprocessing';}
  setImage('crop',crop,'crop-error');text('crop-error',crop?'Crop unavailable':'No crop saved');text('crop-caption',crop?'Inspected crop':c.bbox?'Detection crop':'Crop');renderImageGeometry();
  text('evidence-source',e?e.label:'Recorded evidence');text('anomaly-status',anomalyStatus(score));$('anomaly-status').className=score.anomalous===true?'flagged':score.anomalous===false?'clear':'';
  text('anomaly-value',score.status==='ok'?`${format(score.score)} / ${format(score.threshold)} threshold${finite(score.ratio)?' · '+format(score.ratio,3)+'×':''}${finite(score.infer_ms)?' · '+format(score.infer_ms,1)+' ms':''}`:score.detail || 'No model result for this capture');
  text('tape-status',tape.status);$('tape-status').className=tape.flagged===true?'flagged':'';
  text('tape-value',finite(tape.value)?`${format(tape.value*100)}%${finite(tape.threshold)?' / '+format(tape.threshold*100)+'% threshold':' · threshold not recorded'}${e?' · original run measurement':''}`:'No measurement recorded');
  const type=score.selected_type || score.detail?.match(/(?:best type|type)\s+([a-zA-Z0-9_]+)/)?.[1];
  text('selected-model',type?human(type):'Not recorded');
  text('trigger',c.trigger?(c.trigger_detector==='tape'?'Blue-tape rule':c.trigger_detector==='anomalib'?'Anomalib':'Decision at this view; detector not identified'):'No decision attributed to this capture');
  show('known-type',!!score.known_type_score);text('known-type',score.known_type_score?`Diagnostic with known type ${human(score.known_type)}: ${format(score.known_type_score.ratio,3)}× threshold. This did not change the recorded decision.`:'');
  text('source-note',[e?'Model results were rechecked later; the original decision above is unchanged.':null,c.source_note,crop?cropLabel:c.bbox?'Crop from the saved bounding box; model input was not recorded.':'Model input image was not recorded.',c.bbox?(c.view==='top'?'Solid box: recorded blob detection.':'Dashed box: recorded inspection region, not a blob detection.'):null,verdict.tone==='missed'?'Defect missed is based on the saved item label; individual surfaces were not separately labeled.':null].filter(Boolean).join(' '));
}
function render(){
  const isLive=ui.mode==='live',isModels=ui.mode==='models';show('models',isModels);$('nav-models').setAttribute('aria-pressed',String(isModels));document.body.classList.toggle('models-mode',isModels);document.body.classList.toggle('live-camera',isLive&&$('live-view').value==='camera');document.body.classList.toggle('live-inspection',isLive&&$('live-view').value==='inspection');show('live',isLive);show('history',!isLive&&!isModels);document.body.classList.toggle('live-mode',isLive);
  $('nav-live').setAttribute('aria-pressed',String(isLive));$('nav-history').setAttribute('aria-pressed',String(!isLive&&!isModels));
  text('connection',ui.connected?'':'Disconnected');
  if(isModels)return;
  if(isLive)renderLive();renderItemNavigation();
  const item=activeItem();show('empty',!item);show('item-content',!!item);show('inspection-details',!!item);if(!item)return;
  const r=item.record || {},e=evaluation(item);
  text('item-title',(item.number!=null?'Item '+item.number:item.id==='_run'?'Run images':'Recorded captures')+(item.part&&item.part!=='auto'?' · '+human(item.part):''));
  text('item-subtitle',isLive?live.run:ui.run);
  const evals=item.evaluations || [];show('evaluation-wrap',!isLive&&!!evals.length);
  options($('evaluation'),[['recorded','Recorded run'],...evals.map(v=>[v.id,v.label])],e?.id || 'recorded');
  text('decision',outcome(r.decision));$('decision').className=r.decision==='reject'?'flagged':r.decision==='good'?'clear':'';text('reason',r.reason || 'No decision recorded');
  text('latency',finite(r.latency_ms)?format(r.latency_ms,0)+' ms':'—');text('cycle',finite(r.cycle_s)?format(r.cycle_s,2)+' s':'—');
  text('delivery',item.delivery || (r.t_released?'Release recorded; physical placement unconfirmed':r.picked===false?'Not picked':'Delivery not confirmed'));
  const notice=[item.excluded?'Excluded: '+(typeof item.excluded==='string'?item.excluded:JSON.stringify(item.excluded)):null,item.notice,...(item.unassigned || [])].filter(Boolean).join(' · ');text('item-notice',notice);show('item-notice',!!notice);
  renderCaptures(item,e);
  const fields=[['Recorded label',item.label || 'Unverified / not recorded'],['Background',item.metadata?.background || 'Not recorded'],['Pose',r.pose || item.metadata?.pose || 'Not recorded'],['Result source',e?e.label:'Original run'],['Model bundle',e?.bundle || 'Not recorded'],['Execution device',e?.device || 'Not recorded']];
  $('record-fields').replaceChildren(...fields.flatMap(([k,v])=>[node('dt',k),node('dd',v)]));
  text('raw-record',JSON.stringify({record:r,metadata:item.metadata || {},evaluation:e?{...e,scores:undefined}:undefined},null,2));
}
$('nav-live').addEventListener('click',()=>mode('live'));$('nav-history').addEventListener('click',()=>mode('history'));
window.addEventListener('hashchange',()=>{ui.mode=['#live','#models'].includes(location.hash)?location.hash.slice(1):'history';render();});
$('refresh').addEventListener('click',()=>loadRuns(true));
for(const id of ['run-search','run-kind'])$(id).addEventListener(id==='run-search'?'input':'change',renderRunOptions);
$('history-run').addEventListener('change',event=>loadRun(event.target.value));
$('evaluation').addEventListener('change',event=>{ui.evaluationChoice=ui.evaluation=event.target.value;render();});
$('item-picker').addEventListener('change',event=>selectItem(event.target.value));
for(const [id,step] of [['previous-item',-1],['next-item',1]])$(id).addEventListener('click',()=>{const items=itemList(),current=ui.mode==='live'?ui.liveItem:ui.item,index=items.findIndex(i=>i.id===current);if(items[index+step])selectItem(items[index+step].id);});
$('follow').addEventListener('change',render);$('camera').addEventListener('change',event=>{ui.camera=event.target.value;renderLive();});
const stream=new EventSource('/events');
stream.onopen=()=>{ui.connected=true;schedule();};stream.onerror=()=>{ui.connected=false;schedule();};
stream.onmessage=event=>{try{const ev=JSON.parse(event.data);live.ingest(ev);if(ui.mode==='live')schedule();}catch(e){console.error('Invalid dashboard event',e);}};
setInterval(()=>{if(ui.mode==='live')renderLive();},1000);

$('nav-models').addEventListener('click',()=>mode('models'));
$('live-view').addEventListener('change',render);
for(const [id,step] of [['capture-page-prev',-6],['capture-page-next',6]])$(id).addEventListener('click',()=>{const item=activeItem();if(!item)return;const captures=item.captures||[],selected=Array.from($('captures').children).findIndex(b=>b.getAttribute('aria-pressed')==='true'),index=Math.max(0,Math.min(captures.length-1,selected+step));if(captures[index]){ui.selected.set(captureKey(item),captures[index].id);render();}});
$('open-details').addEventListener('click',()=>$('details-dialog').showModal());
$('close-details').addEventListener('click',()=>$('details-dialog').close());
for(const button of document.querySelectorAll('[data-detail-page]'))button.addEventListener('click',()=>{for(const b of document.querySelectorAll('[data-detail-page]')){const selected=b===button;b.setAttribute('aria-pressed',String(selected));show('detail-'+b.dataset.detailPage,selected);}});
$('download-record').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([$('raw-record').textContent],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='capture-record.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});

render();loadRuns();
