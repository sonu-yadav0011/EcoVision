import {useState,useEffect} from 'react';
import {MapContainer,TileLayer,CircleMarker,Popup,useMap,GeoJSON} from 'react-leaflet';
import {MapPin,Trees,Layers,ScanSearch,ArrowUpRight,LocateFixed} from 'lucide-react';
import {locations} from '../data';
import L from 'leaflet';

// Forest Survey of India, ISFR 2023, Volume II, Table 10.19.3 (11 districts).
const forestStats={
Dimapur:{area:927,vdf:24.70,mdf:116.04,open:323.13,total:463.87,cover:50.04,change:-3.48,scrub:7.49},
Kiphire:{area:1130,vdf:139.29,mdf:268.29,open:404.31,total:811.89,cover:71.85,change:-0.54,scrub:65.20},
Kohima:{area:1463,vdf:119.25,mdf:345.10,open:625.54,total:1089.89,cover:74.50,change:-4.15,scrub:42.47},
Longleng:{area:562,vdf:15.73,mdf:125.76,open:243.93,total:385.42,cover:68.58,change:5.26,scrub:22.76},
Mokokchung:{area:1615,vdf:2.32,mdf:546.66,open:791.87,total:1340.85,cover:83.02,change:14.88,scrub:36.72},
Mon:{area:1786,vdf:96.35,mdf:523.69,open:735.76,total:1355.80,cover:75.91,change:-18.30,scrub:99.90},
Peren:{area:1651,vdf:148.40,mdf:649.11,open:702.29,total:1499.80,cover:90.84,change:-8.48,scrub:74.95},
Phek:{area:2026,vdf:265.57,mdf:549.16,open:677.58,total:1492.31,cover:73.66,change:0.88,scrub:62.08},
Tuensang:{area:2536,vdf:356.80,mdf:433.80,open:568.81,total:1359.41,cover:53.60,change:-14.28,scrub:108.56},
Wokha:{area:1628,vdf:0.93,mdf:461.60,open:831.04,total:1293.57,cover:79.46,change:-7.99,scrub:59.00},
Zunheboto:{area:1255,vdf:87.04,mdf:442.60,open:600.02,total:1129.66,cover:90.01,change:-15.69,scrub:88.14}
};
const forestSource='Forest Survey of India, India State of Forest Report 2023, Volume II, Chapter 10.19, Table 10.19.3.';

function Focus({selected,geojson}) {
 const map=useMap();
 useEffect(()=>{
  if(selected==='All locations'){map.flyTo([26.1,94.5],7,{duration:.8});return;}
  const f=geojson?.features?.find(x=>(x.properties?.districtname||'').toLowerCase()===selected.toLowerCase());
  if(f){const bounds=L.geoJSON(f).getBounds();if(bounds.isValid())map.flyToBounds(bounds,{padding:[24,24],duration:.8});}
  else {const p=locations.find(x=>x.name===selected);if(p)map.flyTo([p.lat,p.lng],9,{duration:.8});}
 },[selected,geojson,map]);
 return null;
}

export default function Dashboard(){
  const [selected,setSelected]=useState('All locations');
  const [districtGeo,setDistrictGeo]=useState(null);
  const [geoError,setGeoError]=useState('');
  useEffect(()=>{const url='https://livingatlas.esri.in/server1/rest/services/ForestSurvey/District_Wise_Forest_Cover_2023/MapServer/0/query?where=statename%3D%27Nagaland%27&outFields=districtname,calarea,vdf2023,mdf2023,of2023,total,percalarea,change2021rasbased,scrub&returnGeometry=true&outSR=4326&f=geojson';fetch(url).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(j=>{if(j.type==='FeatureCollection'&&j.features?.length)setDistrictGeo(j);else throw new Error()}).catch(()=>setGeoError('District boundaries could not be loaded. Check your internet connection.'));},[]);
  const [base,setBase]=useState('satellite');
  const active=locations.find(x=>x.name===selected);
  const districtCount=Object.keys(forestStats).length;
  const cards=[
    [MapPin,'District locations',String(districtCount),'Nagaland focus','green'],
    [Trees,'Forest screening classes','04','Forest · scrub · cleared · no data','gold'],
    [ScanSearch,'Analysis workflows','02','Single image and date comparison','blue'],
    [Layers,'Map viewing layers','02','Satellite imagery and street map','coral']
  ];
  return <div className="page">
    <div className="page-heading">
      <div><div className="eyebrow">NORTHEAST FOREST WATCH · NAGALAND</div><h1>Forest monitoring workspace</h1><p>Explore district locations and inspect the surrounding landscape using the interactive map.</p></div>
    </div>

    <div className="hero-banner">
      <div><div className="hero-kicker">ECOVISSION · REGIONAL FOREST VIEW</div><h2>Explore the forest.<br/><em>Understand change.</em></h2><p>Navigate Nagaland, view satellite basemaps and screen uploaded imagery for possible vegetation patterns.</p></div>
      <div className="hero-art"><div className="sun"/><div className="mountain m1"/><div className="mountain m2"/><div className="tree-line">♠　♠　♠　♠</div></div>
    </div>

    <div className="stat-grid">{cards.map(([Icon,label,value,sub,color])=><div className="stat-card" key={label}><div className={'stat-icon '+color}><Icon size={18}/></div><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>)}</div>

    <section className="panel">
      <div className="panel-heading">
        <div><div className="eyebrow">INTERACTIVE GEOGRAPHIC WORKSPACE</div><h3>Nagaland forest landscape explorer</h3><p>Select a district location and switch between satellite imagery and the street map.</p></div>
        <div style={{display:'flex',gap:8,flexWrap:'wrap',alignItems:'center'}}>
          <select aria-label="Select district location" value={selected} onChange={e=>setSelected(e.target.value)}><option value="All locations">All locations</option>{locations.map(l=><option key={l.name} value={l.name}>{l.district}</option>)}</select>
          <div className="map-layer-toggle"><button type="button" className={base==='satellite'?'active':''} onClick={()=>setBase('satellite')}>Satellite</button><button type="button" className={base==='street'?'active':''} onClick={()=>setBase('street')}>Street</button></div>
        </div>
      </div>

      <div className="map-frame">
        <MapContainer center={[26.1,94.5]} zoom={7} scrollWheelZoom style={{height:'100%',width:'100%'}}>
          {base==='satellite'
            ? <TileLayer attribution='Imagery © Esri' url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"/>
            : <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>}
          <Focus selected={selected} geojson={districtGeo}/>
          {districtGeo&&<GeoJSON key={selected} data={districtGeo} style={f=>{const active=(f.properties?.districtname||'').toLowerCase()===selected.toLowerCase();return{color:active?'#f6c85f':'#e7f4e7',weight:active?4:1.5,fillColor:active?'#e6b94d':'#3c9b68',fillOpacity:active ? 0.28 : 0.07}}} onEachFeature={(f,layer)=>{const n=f.properties?.districtname;layer.on({click:()=>setSelected(n)});layer.bindTooltip(n,{sticky:true});}}/>}
          {!districtGeo&&locations.map(p=><CircleMarker key={p.name} center={[p.lat,p.lng]} radius={5} pathOptions={{color:'#fff',fillColor:'#398b5b',fillOpacity:.8}} eventHandlers={{click:()=>setSelected(p.name)}}><Popup>{p.district}</Popup></CircleMarker>)}
        </MapContainer>
      </div>
      <div className="map-legend"><span><i className="legend-dot"/> District location</span><span className="map-note">{base==='satellite'?'Satellite imagery basemap · Esri':'Street basemap · OpenStreetMap'}</span></div>{geoError&&<p className="small-note">{geoError}</p>}
    </section>

    <section className="panel district-detail">
      <div className="district-detail-head"><div><div className="eyebrow">SELECTED DISTRICT</div><h3>{active?`${active.district} district`:'Nagaland overview'}</h3><p>{active?'Location profile and suggested image-review focus.':'Select a district marker or use the dropdown to view its district profile.'}</p></div><span className="district-chip"><LocateFixed size={14}/>{active?'Focused location':'Regional view'}</span></div>
      {active&&forestStats[active.name]?<><div className="forest-stat-strip"><div><small>Forest cover (2023)</small><strong>{forestStats[active.name].cover.toFixed(2)}%</strong></div><div><small>Total forest area</small><strong>{forestStats[active.name].total.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})} km²</strong></div><div><small>Change vs 2021 raster</small><strong className={forestStats[active.name].change<0?'negative':'positive'}>{forestStats[active.name].change>0?'+':''}{forestStats[active.name].change.toFixed(2)} km²</strong></div></div><div className="forest-class-grid">{[['Very dense forest','vdf'],['Moderately dense forest','mdf'],['Open forest','open'],['Scrub','scrub']].map(([label,key])=><div className="forest-class" key={key}><small>{label}</small><strong>{forestStats[active.name][key].toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})} km²</strong></div>)}</div><p className="forest-method-note">Source: {forestSource} The change value is relative to the 2021 raster-based assessment.</p></>:active?<div className="district-overview"><Trees size={20}/><p>ISFR 2023 does not provide a separate figure for {active.name} in its 11-district table. No value is estimated here.</p></div>:<div className="district-overview"><Trees size={20}/><p>Select a district boundary to view its official forest-cover area, percentage, density classes, scrub area and reported change since the 2021 raster assessment.</p></div>}

    </section>

    <div className="notice"><Layers size={18}/><p><b>Data interpretation note</b> District statistics are from FSI ISFR 2023. The satellite layer is only a basemap, not a live forest-cover classification or hotspot detector. Use the Single Image Analysis and Two Image Comparison pages to screen imagery you provide.</p></div>
    <style>{`
      .map-layer-toggle{display:flex;border:1px solid #dfe7df;border-radius:9px;padding:3px;background:#f7faf7}
      .map-layer-toggle button{border:0;background:transparent;color:#617267;padding:7px 10px;border-radius:6px;font-size:10px;font-weight:700;cursor:pointer}
      .map-layer-toggle button.active{background:#285b40;color:#fff}
      .district-detail{margin-top:2px}
      .district-detail-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:16px}
      .district-detail-head h3{font:750 17px var(--font-family, 'Gabriel Sans', sans-serif);margin:5px 0;color:#23382b}
      .district-detail-head p{font-size:11px;color:#77867b;margin:0}
      .district-chip{display:inline-flex;align-items:center;gap:6px;padding:7px 10px;background:#edf5ed;color:#47714f;border-radius:20px;font-size:10px;font-weight:700;white-space:nowrap}
      .forest-stat-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0}.forest-stat-strip>div{background:#eff6ef;border:1px solid #e1ece0;border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:5px}.forest-stat-strip small,.forest-class small{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#728176;font-weight:700}.forest-stat-strip strong{font-size:20px;color:#285b40}.forest-stat-strip .negative{color:#b65a4e}.forest-stat-strip .positive{color:#397b52}.forest-class-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.forest-class{padding:12px;border:1px solid #e8eee6;border-radius:9px;display:flex;flex-direction:column;gap:7px}.forest-class strong{font-size:13px;color:#314d39}.forest-method-note{font-size:10px;color:#7b887e;line-height:1.5;margin-top:12px}.district-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
      .district-detail-item{background:#f8faf7;border:1px solid #e8eee6;border-radius:10px;padding:13px;display:flex;flex-direction:column;gap:6px}
      .district-detail-item small{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:#849287;font-weight:700}
      .district-detail-item strong{font-size:12px;color:#2c4935}
      .district-detail-item span{font-size:10px;line-height:1.55;color:#718076}
      .district-overview{display:flex;align-items:center;gap:12px;padding:14px;background:#f6faf5;border-radius:10px;color:#55745d}
      .district-overview p{font-size:11px;line-height:1.6;margin:0}
      @media(max-width:700px){.forest-stat-strip{grid-template-columns:1fr}.forest-class-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.district-detail-grid{grid-template-columns:1fr}.district-detail-head{flex-direction:column}.panel-heading{flex-direction:column}.panel-heading select{width:100%}}
    `}</style>
  </div>;
}
