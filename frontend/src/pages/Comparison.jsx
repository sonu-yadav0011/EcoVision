import { useState } from 'react';
import { ArrowLeftRight, Download, Info, SlidersHorizontal, LoaderCircle, Server } from 'lucide-react';
import UploadBox from '../components/UploadBox';
import { analyzeImageComparison } from '../api';

export default function Comparison() {
  const [a, setA] = useState(null);
  const [b, setB] = useState(null);
  const [previewA, setPreviewA] = useState('');
  const [previewB, setPreviewB] = useState('');
  const [sensitivity, setSensitivity] = useState(35);
  const [area, setArea] = useState('Nagaland monitoring area');
  const [labelA, setLabelA] = useState('Earlier');
  const [labelB, setLabelB] = useState('Later');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!a || !b || busy) return;
    setError('');
    setResult(null);
    setBusy(true);
    try {
      const response = await analyzeImageComparison({
        earlierFile: a,
        laterFile: b,
        monitoringArea: area,
        earlierLabel: labelA,
        laterLabel: labelB,
        sensitivity,
      });
      setResult(response);
    } catch (err) {
      setError(err?.message || 'Backend comparison failed.');
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (!result) return;
    const row = [
      'Comparison ID,Monitoring area,Earlier image,Later image,Sensitivity,Flagged pixels (%),Flagged pixels,Total pixels',
      `"${result.id}","${result.monitoring_area}","${a?.name}","${b?.name}",${result.sensitivity},${result.summary.flagged_pixels_pct},${result.summary.flagged_pixels},${result.summary.total_pixels}`,
    ].join('\n');
    const url = URL.createObjectURL(new Blob([row], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `ecovission_comparison_${result.id}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">VISUAL CHANGE SCREENING · MODULE 02</div>
          <h1>Two image comparison</h1>
          <p>Upload two dates and let the Python backend calculate RGB pixel differences.</p>
        </div>
        <div className="module-tag"><ArrowLeftRight size={16} /> IMAGE COMPARISON</div>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div><h3>Comparison inputs</h3><p>Choose images of the same area, framing and spatial alignment.</p></div>
          <span className="step-chip">STEP 01</span>
        </div>

        <div className="content-grid upload-grid">
          <div>
            <UploadBox label="Earlier image" file={a} onFile={(f) => {
              setA(f); setPreviewA(f ? URL.createObjectURL(f) : ''); setResult(null);
            }} />
            <label className="api-field-label">Earlier date / label</label>
            <input className="api-text-input" value={labelA} onChange={(e) => setLabelA(e.target.value)} />
          </div>
          <div>
            <UploadBox label="Later image" file={b} onFile={(f) => {
              setB(f); setPreviewB(f ? URL.createObjectURL(f) : ''); setResult(null);
            }} />
            <label className="api-field-label">Later date / label</label>
            <input className="api-text-input" value={labelB} onChange={(e) => setLabelB(e.target.value)} />
          </div>
        </div>

        {(previewA || previewB) && (
          <div className="comparison-previews">
            {previewA && <div><b>Earlier image · {a?.name}</b><img src={previewA} alt="Earlier image preview" /></div>}
            {previewB && <div><b>Later image · {b?.name}</b><img src={previewB} alt="Later image preview" /></div>}
          </div>
        )}

        <div className="api-field">
          <label className="api-field-label">Monitoring area name</label>
          <input className="api-text-input" value={area} onChange={(e) => setArea(e.target.value)} />
        </div>

        <div className="sensitivity-row">
          <div>
            <div className="slider-label"><SlidersHorizontal size={17} /> Difference sensitivity <b>{sensitivity}</b></div>
            <small>Lower values flag smaller RGB differences.</small>
          </div>
          <input type="range" min="1" max="255" step="1" value={sensitivity}
            onChange={(e) => { setSensitivity(+e.target.value); setResult(null); }} />
        </div>

        <button className="primary-btn" disabled={!a || !b || busy} onClick={run}>
          {busy ? <LoaderCircle className="ecovission-spin" size={17} /> : <Server size={17} />}
          {busy ? 'Comparing on backend…' : 'Compare using backend'}
        </button>
        {error && <div className="error-note">{error}</div>}
        <div className="small-note"><Info size={16} />The backend resizes the later image to the earlier image dimensions when needed. This is not geographic registration or validated forest-change detection.</div>
      </section>

      {result && (
        <div className="results-section">
          <div className="results-title">
            <div><div className="eyebrow">BACKEND COMPARISON OUTPUT</div><h2>Visual difference summary</h2>
              <p>Comparison ID: {result.id}</p></div>
            <button className="secondary-btn" onClick={download}><Download size={16} /> Export CSV</button>
          </div>

          <div className="stat-grid result-stats">
            <div className="stat-card compact"><span>Pixels flagged</span><strong>{Number(result.summary.flagged_pixels_pct).toFixed(1)}%</strong><small>Above selected threshold</small></div>
            <div className="stat-card compact"><span>Flagged pixel count</span><strong>{Number(result.summary.flagged_pixels).toLocaleString()}</strong><small>RGB differences</small></div>
            <div className="stat-card compact"><span>Total pixels compared</span><strong>{Number(result.summary.total_pixels).toLocaleString()}</strong><small>{result.dimensions.width} × {result.dimensions.height}</small></div>
          </div>

          <section className="panel">
            <h3>Backend-generated change overlay</h3>
            <p>Red highlights show pixels above the selected RGB difference threshold.</p>
            <img className="comparison-output" src={result.overlay_data_url} alt="Backend-generated RGB difference overlay" />
          </section>

          <section className="panel">
            <h3>RGB difference image</h3>
            <img className="comparison-output" src={result.difference_data_url} alt="RGB difference magnitude image" />
          </section>

          <div className="notice"><Info size={18} /><p><b>Interpretation:</b> {result.method}. Flagged pixels are not confirmed forest loss. Illumination, season, haze, cloud, camera angle and misalignment can create false differences.</p></div>
        </div>
      )}

      <style>{`
        .api-field{margin-top:14px;max-width:520px}
        .api-field-label{display:block;margin:12px 0 6px;font-size:13px;font-weight:650;color:var(--text,#34483b)}
        .api-text-input{width:100%;min-height:40px;padding:9px 11px;border:1px solid #d7e2d9;border-radius:9px;background:#fff;color:#24372b;font:inherit}
        .api-text-input:focus{outline:2px solid #a8cfb2;outline-offset:1px}
        .comparison-previews{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:18px 0}
        .comparison-previews img{display:block;width:100%;max-height:280px;object-fit:contain;margin-top:8px;border-radius:10px;background:#eef2ed}
        @media(max-width:750px){.comparison-previews{grid-template-columns:1fr}}
      `}</style>
    </div>
  );
}
