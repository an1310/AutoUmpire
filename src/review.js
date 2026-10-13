import { projectTrackedZone, validTrackingRecord } from './replayProjection.js';
const video=document.querySelector('#video');
const canvas=document.querySelector('#overlay');
const ctx=canvas.getContext('2d');
const status=document.querySelector('#status');
let data=null,poses=new Map(),videoUrl=null,stopped=false;
function validateTracking(data) {
 if(data?.schema!=='autoumpire-tracking-v1' || !(data.fps>0) ||
    !data.camera || !Array.isArray(data.poses) ||
    !(data.camera.width>0&&data.camera.height>0) || !Array.isArray(data.camera.matrix))
   throw new TypeError('Unsupported tracking JSON schema');
}
document.querySelector('#videoFile').addEventListener('change',e=>{
  if(videoUrl)URL.revokeObjectURL(videoUrl);
  const file=e.target.files?.[0];if(!file)return;
  videoUrl=URL.createObjectURL(file);video.src=videoUrl;
});
document.querySelector('#trackFile').addEventListener('change',async e=>{
  const file=e.target.files?.[0];if(!file)return;
  try{
    const value=JSON.parse(await file.text());validateTracking(value);
    data=value;poses=new Map(data.poses.map(r=>[r.frame,r]));
    status.textContent=`Loaded ${data.poses.length} accepted poses; ${data.frames_processed} total frames.`;
  }catch(err){data=null;poses=new Map();status.textContent='Cannot load tracking JSON: '+err.message;}
});
function draw(_,meta){
  const W=video.videoWidth,H=video.videoHeight;
  if(W&&H&&(canvas.width!==W||canvas.height!==H)){canvas.width=W;canvas.height=H;}
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if(data && W && H && data.camera.width===W && data.camera.height===H){
    const time=meta?.mediaTime??video.currentTime;
    const frame=Math.round(time*data.fps);
    const record=poses.get(frame);
    if(validTrackingRecord(record)){
      const segments=projectTrackedZone(record,data.camera);
      ctx.beginPath();ctx.strokeStyle='#ffd154';ctx.lineWidth=Math.max(2,W/960);
      ctx.shadowColor='#000';ctx.shadowBlur=3;
      for(const [a,b] of segments){ctx.moveTo(...a);ctx.lineTo(...b);}
      ctx.stroke();ctx.shadowBlur=0;
      status.textContent=`Frame ${frame} · ${record.source} · marker-fit ${record.reprojection_px.toFixed(2)}px RMS (NOT absolute accuracy)`;
    }else status.textContent=`Frame ${frame} · tracking unavailable / rejected · overlay hidden`;
  } else if(data && W && H){status.textContent='Video resolution differs from calibration. Overlay disabled.';}
  if(!stopped&&typeof video.requestVideoFrameCallback==='function'&&!video.paused)
    video.requestVideoFrameCallback(draw);
}
video.addEventListener('play',()=>{
  stopped=false;
  if(typeof video.requestVideoFrameCallback==='function')video.requestVideoFrameCallback(draw);
  else (function loop(){if(video.paused)return;draw();requestAnimationFrame(loop);})();
});
for(const event of ['seeked','loadedmetadata','pause','ended']) video.addEventListener(event,()=>draw());
window.addEventListener('pagehide',()=>{stopped=true;if(videoUrl)URL.revokeObjectURL(videoUrl);});
