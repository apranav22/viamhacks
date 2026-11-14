// [pi/gpt-6-astra · op Ali · Alis-MacBook-Air.local · ali/pipeline]
// Offline contract tests. No sockets, SDK, browser or robot connection.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function ui(){
  const elements=new Map();
  const element=id=>{if(!elements.has(id)) elements.set(id,{id,style:{},dataset:{},children:[],classList:{toggle(){}},removeAttribute(k){delete this[k]},setAttribute(){},prepend(){},getContext(){return {fillRect(){}}}});return elements.get(id)};
  const context=vm.createContext({document:{getElementById:element,querySelectorAll:()=>[],createElement:()=>({})},Date,console,setInterval(){},Image:function(){}});
  let script=fs.readFileSync('dashboard/index.html','utf8').split('<script>')[1].split('</script>')[0];
  script=script.replace('renderAll(); connect();','');
  vm.runInContext(script+'\nrenderAll=()=>{}; backlog=true;',context);
  return {run:code=>vm.runInContext(code,context),elements,element};
}
test('camera selection survives look, watch state and run reset',()=>{
  const u=ui();
  u.run('S.tab="ref"; onEvent({k:"look",t:1,n:1,item:null}); onEvent({k:"state",state:"WATCH",item:1,t:2}); onEvent({k:"run",t:3,cmd:"test",run:"offline"})');
  assert.equal(u.run('S.tab'),'ref');
});
test('newest frame wins across watch, snapshot and active-run preview',()=>{
  const u=ui();
  u.run('S.watch={k:"watch",t:1,frame:{id:"old"}}; S.snap.cam={k:"snap",t:2,frame:{id:"snapshot"}}; S.state="PICK"; render()');
  assert.equal(u.element('cam').src,'/frame/snapshot');
  u.run('$("cam").onload(); onEvent({k:"preview",cam:"cam",t:3,frame:{id:"preview"}}); render()');
  assert.equal(u.element('cam').src,'/frame/preview');
  u.run('onEvent({k:"preview",cam:"cam",t:2,frame:{id:"late"}})');
  assert.equal(u.run('PV.cams.cam.frame.id'),'preview');
  assert.match(u.run('frameLabel(S.snap.cam)'),/SNAPSHOT.*s old/);
  assert.match(u.run('frameLabel(S.watch)'),/STALE PREVIEW/);
  assert.match(u.run('frameLabel({k:"preview",t:Date.now()/1000})'),/LIVE PREVIEW/);
});
test('item progress persists and distinguishes decision, release and missing evidence',()=>{
  const u=ui();
  u.run('S.item=1; S.live=true; recordProgress({k:"look",n:1,item:{},frame:{id:"a"}}); recordProgress({k:"grasp_result",n:1,ok:false,attempt:1}); recordProgress({k:"decision",n:1,decision:"reject",reason:"tape"})');
  assert.equal(u.run('S.progress[1].Placement'),'not confirmed');
  assert.match(u.run('S.progress[1]["Grip verification"]'),/MISSED/);
  u.run('recordProgress({k:"span",item:1,name:"release (reject)",phase:"drop",error:"jam"})');
  assert.match(u.run('S.progress[1].Placement'),/failed/);
  u.run('recordProgress({k:"span",item:1,name:"release (reject)",phase:"drop",error:null}); S.item=2; recordProgress({k:"state",item:2,state:"PICK"}); renderProgress()');
  assert.match(u.run('S.progress[1].Placement'),/release sequence completed.*physical placement not confirmed/);
  assert.match(u.element('progress').innerHTML,/Item 1/);
  assert.match(u.element('progress').innerHTML,/not reported/);
});
test('dry run release never confirms physical placement',()=>{
  const u=ui();
  u.run('S.item=1; recordProgress({k:"span",name:"release (set)",phase:"place"})');
  assert.match(u.run('S.progress[1].Placement'),/physical placement not confirmed/);
});
