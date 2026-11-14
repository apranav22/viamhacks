// Start a capture run or live anomaly detection from the Live view (dashboard/runner.py does the checks + logging).
(()=>{
const $=id=>document.getElementById(id);
const form=$('run-form');
if(!form)return;
let status={running:false},busy=false;
const kind=()=>form.querySelector('input[name=kind]:checked').value;
const names={button_ss_long:'Button screw',hex_nut:'Hex nut',socket_thin_long:'Thin long socket screw',socket_thin_short:'Thin short socket screw',socket_m16:'Large socket screw',hex_bolt_partial:'Long hex bolt',hex_bolt_short:'Short hex bolt'};
function fill(select,values,label=v=>v){for(const v of values){const o=document.createElement('option');o.value=v;o.textContent=label(v);select.append(o);}}
function spec(){
  const s={kind:kind(),target:$('run-target').value,background:$('run-background').value,views:$('run-views').value,
    watch_timeout:Number($('run-timeout').value),refs:$('run-refs').checked,estop_confirmed:$('run-estop').checked};
  if(s.kind==='capture'){
    const label=$('run-label').value;
    Object.assign(s,{type:$('run-type').value,label:label==='other'?'other:'+$('run-other').value.trim().toLowerCase():label,
      reps:Number($('run-reps').value),assume_lying:$('run-lying').checked});
  }else Object.assign(s,{items:Number($('run-items').value),bundle:$('run-bundle').value,decide:$('run-decide').value,device:$('run-device').value});
  return s;
}
function summary(s){
  const where=s.target==='station'?'on the station':'from this computer';
  return s.kind==='capture'?`Capture ${s.reps} picks of ${names[s.type]||s.type} (${s.label}) ${where}, ${s.views} views?`
    :`Sort ${s.items} items with ${s.bundle} ${where}, ${s.views} views?`;
}
function render(){
  const k=kind();
  for(const el of form.querySelectorAll('[data-kind]'))el.hidden=el.dataset.kind!==k;
  $('run-other-wrap').hidden=k!=='capture'||$('run-label').value!=='other';
  $('run-start').textContent=k==='capture'?'Start capture run':'Start live detection';
  $('run-start').disabled=busy||status.running||status.telemetry_active||!$('run-estop').checked;
  $('run-stop').disabled=busy||!status.running;
  const r=status.run;
  let text='';
  if(status.running)text=`${r.kind==='capture'?'Capture':'Detection'} running on ${r.target==='station'?'the station':'this computer'} since ${new Date(r.started*1000).toLocaleTimeString()}`;
  else if(r&&r.ended)text=`Last run ended: ${r.why||'done'}`;
  else if(status.telemetry_active)text='Another run is active';
  if(r&&r.warning)text+=` — ${r.warning}`;
  $('run-state').textContent=text;
  $('run-badge').textContent=status.running?'● running':'';
  const out=status.output||[];
  $('run-output').hidden=!out.length;
  const pre=$('run-output'),atEnd=pre.scrollTop+pre.clientHeight>=pre.scrollHeight-4;
  pre.textContent=out.join('\n');
  if(atEnd)pre.scrollTop=pre.scrollHeight;
}
async function call(path,body){
  const r=await fetch(path,{method:body?'POST':'GET',cache:'no-store',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  const data=await r.json();
  if(!r.ok)throw new Error(data.error||'request failed');
  return data;
}
async function poll(){
  try{status=await call('/api/run/status');}catch(e){/* keep the last status */}
  render();
}
form.addEventListener('change',render);
$('run-estop').addEventListener('input',render);
form.addEventListener('submit',async e=>{
  e.preventDefault();
  const s=spec();
  if(!s.estop_confirmed||!confirm(summary(s)+'\n\nThe arm will move. A person must be at the E-stop.'))return;
  busy=true;render();
  let failure=null;
  try{status=await call('/api/run/start',s);$('run-estop').checked=false;}   // re-confirm for every run
  catch(err){failure=err.message;}
  busy=false;render();
  if(failure)$('run-state').textContent='Not started: '+failure;
});
$('run-stop').addEventListener('click',async()=>{
  busy=true;render();
  try{status=await call('/api/run/stop',{});}catch(err){$('run-state').textContent='Stop failed: '+err.message;}
  busy=false;render();
});
(async()=>{
  let opts;
  try{opts=await call('/api/run/options');}catch(e){return;}
  if(!opts.enabled)return;
  fill($('run-type'),opts.types,v=>names[v]||v);
  fill($('run-bundle'),opts.bundles,v=>v==='active'?'Active model':v.replace(/^models\//,''));
  if(opts.bundles.includes(opts.default_bundle))$('run-bundle').value=opts.default_bundle;
  $('run-control').hidden=false;
  render();poll();setInterval(poll,2000);
})();
})();
