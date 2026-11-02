/* Public page, direct loopback recording. No operating-system sniffing. */
(() => {
'use strict';
const nativeFetch=window.fetch.bind(window);
let connection=null, renewed=0, pending=null, activeFrame=null;
const panel=document.createElement('section');panel.id='recording-panel';
const style=document.createElement('style');
style.textContent=`html.recording-screen,html.recording-screen body{height:100%;overflow:hidden}
.recording-screen body> :not(#recording-panel){display:none!important}
.recording-screen #recording-panel{position:fixed;inset:0;display:flex;flex-direction:column;background:var(--bg);overflow:hidden}
.recording-screen #recording-panel>h2{display:none}
.recording-screen #room-toolbar{display:flex;align-items:center;gap:12px;padding:8px 16px;flex-shrink:0;border-bottom:1px solid var(--line)}
.recording-screen #local-note{flex:1;margin:0;font-size:14px}
.recording-screen #room-screen{flex:1;min-height:0;overflow:hidden}
#room-screen iframe{display:block;width:100%;height:100%;border:0}
@media(max-width:600px){.recording-screen #room-toolbar{gap:6px;padding:6px}.recording-screen #local-note{font-size:12px}}`;
document.head.append(style);
panel.innerHTML='<h2>Recording</h2><div id="room-toolbar"><p id="local-note" role="status">Checking for Studio on this computer…</p><button id="local-retry">Connect to recording Mac</button> <button id="room-return" hidden>Return to room</button> <button id="room-close" hidden>Close room</button><button id="room-viewer" hidden>Back to productions</button></div><div id="room-screen"></div>';
document.querySelector('#content').before(panel);
const slot=document.createComment('recording panel');panel.before(slot);
let viewerScroll=0;
const exit=panel.querySelector('#room-viewer');
function enterRoom(){
 if(!document.documentElement.classList.contains('recording-screen'))viewerScroll=window.scrollY;
 document.body.append(panel);document.documentElement.classList.add('recording-screen');exit.hidden=false;back.hidden=true;
}
function leaveRoom(){
 document.documentElement.classList.remove('recording-screen');slot.after(panel);exit.hidden=true;
 screen.replaceChildren();activeFrame=null;back.hidden=!kind;window.scrollTo(0,viewerScroll);
}
const note=panel.querySelector('#local-note'), retry=panel.querySelector('#local-retry');
const back=panel.querySelector('#room-return'), close=panel.querySelector('#room-close');
const screen=panel.querySelector('#room-screen');
let kind=null;
const message=s=>{note.textContent=s;};
async function json(response){const value=await response.json();if(!response.ok)throw Error(value.error||'Studio connection failed');return value;}
async function credentials(){
 if(connection&&Date.now()-renewed<120000)return connection;
 if(!pending)pending=(async()=>{
  const value=await json(await nativeFetch('/api/local-connection',{cache:'no-store'}));
  if(!value.local){
   const url=new URL(value.base);
   if(url.protocol!=='http:'||url.hostname!=='localhost'||url.pathname!=='/'||url.username||url.password)throw Error('Invalid local Studio address');
   const answer=await json(await nativeFetch(value.base+'/bridge/probe',{headers:{'X-Studio-Local':value.token},credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(5000),targetAddressSpace:'loopback'}));
   if(answer.instance!==value.instance)throw Error('This computer is running a different Studio');
  }
  connection=value;renewed=Date.now();return value;
 })().finally(()=>{pending=null;});
 return pending;
}
window.studioFetch=async (path,options={})=>{
 if(typeof path!=='string'||!(/^\/room\//.test(path)||path==='/api/status'))throw Error('Unsupported recording route');
 const c=await credentials();
 const headers=new Headers(options.headers||{});
 if(!c.local)headers.set('X-Studio-Local',c.token);
 // Never retry a command: a lost response may still have recorded the action.
 return nativeFetch((c.local?'':c.base)+path,{...options,headers,credentials:'omit',cache:'no-store',targetAddressSpace:'loopback'});
};
async function status(){
 const s=await json(await window.studioFetch('/api/status'));
 kind=s.room;back.hidden=!kind||!!activeFrame;close.hidden=!kind;close.disabled=s.busy;exit.disabled=s.busy;
 if(!kind&&activeFrame)leaveRoom();
 const oldStatus=document.getElementById('room');if(oldStatus)oldStatus.closest('section').hidden=true;
 document.querySelectorAll('[data-open-room]').forEach(b=>{b.disabled=!!kind;});
 if(!activeFrame)message(kind?'A '+kind+' room is open · '+s.stage:'Connected to this recording Mac. Choose a production to open its room.');
 return s;
}
async function showRoom(){
 if(!kind)return;
 const res=await window.studioFetch('/room/'+kind+'/');
 if(!res.ok)throw Error((await res.json()).error||'Room unavailable');
 let html=await res.text();
 // The trusted room page runs under this page's origin; its requests use the
 // parent's verified direct transport. No credential is placed in a URL.
 const bootstrap='<script>window.fetch=(...a)=>parent.studioFetch(...a);window.studioRefreshRoom=()=>parent.studioRefreshRoom(window);<\/script>';
 html=html.replace('<head>','<head>'+bootstrap);
 screen.replaceChildren();activeFrame=document.createElement('iframe');
 activeFrame.title=kind==='sing'?'Singing room':'Talking room';
 enterRoom();
 activeFrame.srcdoc=html;screen.append(activeFrame);
 message('Connected to this recording Mac · '+(kind==='sing'?'Singing':'Talking')+' room');
 activeFrame.focus();
}
window.studioRefreshRoom=source=>{if(source===activeFrame?.contentWindow)return showRoom();};
async function connect(){
 retry.disabled=true;message('Checking for Studio on this computer…');connection=null;
 try{await credentials();await status();retry.hidden=true;document.querySelector('footer').textContent='Recording connected directly to this Mac · Viewer available on other devices.';}
 catch(e){retry.hidden=false;document.querySelectorAll('[data-open-room]').forEach(b=>{b.disabled=true;});message('Viewing only: could not connect to the recording Mac. If you are on that Mac, allow this site to connect to localhost in your browser, then retry. '+e.message);document.querySelector('footer').textContent='Viewer · Recording requires a connection to the Studio server on this computer.';}
 finally{retry.disabled=false;}
}
exit.onclick=async()=>{try{const s=await status();if(s.busy){message('Finish or abort the current activity before returning to productions.');return;}leaveRoom();await status();}catch(e){message(e.message);}};
retry.onclick=connect;
back.onclick=()=>showRoom().catch(e=>message(e.message));
close.onclick=async()=>{try{await json(await window.studioFetch('/room/close',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}));leaveRoom();await status();}catch(e){message(e.message);}};
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-open-room]');if(!button)return;
 button.disabled=true;
 try{await json(await window.studioFetch('/room/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:button.dataset.openRoom,production:button.dataset.production})}));await status();await showRoom();}
 catch(error){message(error.message);button.disabled=false;}
});
// Viewer refreshes replace production cards; keep their controls in sync.
new MutationObserver(()=>document.querySelectorAll('[data-open-room]').forEach(b=>{b.disabled=!connection||!!kind;})).observe(document.querySelector('#content'),{childList:true,subtree:true});
setInterval(()=>{if(connection&&!document.hidden)status().catch(e=>{retry.hidden=false;message('Recording connection interrupted: '+e.message);});},2000);
connect();
})();
