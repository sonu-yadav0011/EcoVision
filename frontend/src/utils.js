export const readImage=file=>new Promise((resolve,reject)=>{const img=new Image(),url=URL.createObjectURL(file);img.onload=()=>{URL.revokeObjectURL(url);resolve(img)};img.onerror=()=>{URL.revokeObjectURL(url);reject(Error('Could not read this image.'))};img.src=url});export function screenImage(img){
  const c=document.createElement('canvas'),ctx=c.getContext('2d',{willReadFrequently:true});
  c.width=img.naturalWidth;c.height=img.naturalHeight;ctx.drawImage(img,0,0);
  const d=ctx.getImageData(0,0,c.width,c.height).data;
  const names=['Intact Forest','Degraded / Jhum Scrub','Deforested / Cleared Land','Water Body','Other / Unclassified','No Data'];
  const counts=Object.fromEntries(names.map(name=>[name,0])),tiles=[];let id=0;
  for(let y=0;y+160<=c.height;y+=160)for(let x=0;x+160<=c.width;x+=160){
    let green=0,blue=0,black=0,bright=0,samples=0;
    for(let py=y;py<y+160;py+=2)for(let px=x;px<x+160;px+=2){
      const i=(py*c.width+px)*4,r=d[i],g=d[i+1],b=d[i+2];samples++;
      if(g>r*1.05&&g>b*1.05&&(r+g+b)/3>31)green++;
      if(b>r*1.12&&b>g*1.04&&b>45)blue++;
      if(r<=12&&g<=12&&b<=12)black++;
      if(r>210&&g>210&&b>210)bright++;
    }
    const greenRatio=green/samples,blueRatio=blue/samples,blackRatio=black/samples,brightRatio=bright/samples;
    let category;
    if(blackRatio>=.6)category='No Data';
    else if(blueRatio>=.42&&blueRatio>greenRatio*.8)category='Water Body';
    else if(greenRatio>=.6)category='Intact Forest';
    else if(greenRatio>=.35)category='Degraded / Jhum Scrub';
    else if(brightRatio>=.55||blueRatio>=.2)category='Other / Unclassified';
    else category='Deforested / Cleared Land';
    counts[category]++;tiles.push({id:++id,x,y,category});
  }
  if(!tiles.length)throw Error('Image must be at least 160 × 160 pixels.');
  const overlay=document.createElement('canvas');overlay.width=c.width;overlay.height=c.height;
  const ox=overlay.getContext('2d');ox.drawImage(img,0,0);
  const palette={'Intact Forest':'#22c55e','Degraded / Jhum Scrub':'#facc15','Deforested / Cleared Land':'#ef4444','Water Body':'#38a5e8','Other / Unclassified':'#a78bfa','No Data':'#94a3b8'};
  for(const t of tiles){ox.fillStyle=palette[t.category]+'55';ox.fillRect(t.x,t.y,160,160);ox.strokeStyle=palette[t.category];ox.lineWidth=Math.max(2,Math.round(Math.min(c.width,c.height)/500));ox.strokeRect(t.x+1,t.y+1,158,158)}
  return{counts,tiles,total:tiles.length,width:c.width,height:c.height,overlay:overlay.toDataURL('image/png')};
}
export function compareImages(a,b,threshold){const w=a.naturalWidth,h=a.naturalHeight,ca=document.createElement('canvas'),cb=document.createElement('canvas');ca.width=cb.width=w;ca.height=cb.height=h;const xa=ca.getContext('2d'),xb=cb.getContext('2d');xa.drawImage(a,0,0,w,h);xb.drawImage(b,0,0,w,h);const da=xa.getImageData(0,0,w,h).data,db=xb.getImageData(0,0,w,h).data,out=xb.createImageData(w,h);let flagged=0;const grid=Array.from({length:16},(_,i)=>({cell:`R${Math.floor(i/4)+1}-C${i%4+1}`,total:0,changed:0}));for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=(y*w+x)*4,diff=(Math.abs(da[i]-db[i])+Math.abs(da[i+1]-db[i+1])+Math.abs(da[i+2]-db[i+2]))/3,yes=diff>=threshold;if(yes)flagged++;const cell=Math.floor(y/h*4)*4+Math.floor(x/w*4);grid[cell].total++;if(yes)grid[cell].changed++;out.data[i]=yes?db[i]*.35+255*.65:db[i];out.data[i+1]=yes?db[i+1]*.35:db[i+1];out.data[i+2]=yes?db[i+2]*.35:db[i+2];out.data[i+3]=255}xb.putImageData(out,0,0);return{percent:flagged/(w*h)*100,flagged,total:w*h,overlay:cb.toDataURL('image/png'),grid:grid.map(g=>({...g,percent:g.total?g.changed/g.total*100:0}))}}