import { useState } from 'react';
import { Download, ScanSearch, Sparkles, Info, LoaderCircle } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid
} from 'recharts';
import UploadBox from '../components/UploadBox';
import { readImage, screenImage } from '../utils';
import { categories } from '../data';

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export default function SingleAnalysis() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState('');
  const [error, setError] = useState('');

  const choose = (nextFile) => {
    setFile(nextFile);
    setResult(null);
    setError('');
    setStage('');
    setPreview(nextFile ? URL.createObjectURL(nextFile) : '');
  };

  const run = async () => {
    if (!file || busy) return;
    setBusy(true);
    setResult(null);
    setError('');

    try {
      setStage('Loading the selected image…');
      const image = await readImage(file);
      await pause(250);

      setStage('Preparing image tiles…');
      await pause(250);

      setStage('Running RGB-based vegetation and surface screening…');
      const screening = screenImage(image);

      setStage('Building the colour-coded map and summary charts…');
      await pause(250);
      setResult(screening);
    } catch (err) {
      setError(err?.message || 'Image screening failed. Please try another image.');
    } finally {
      setBusy(false);
      setStage('');
    }
  };

  const chartData = result
    ? categories.map((category) => ({
        ...category,
        tiles: result.counts?.[category.name] ?? 0
      }))
    : [];

  const exportCsv = () => {
    if (!result) return;
    const rows = [
      'Tile ID,Category,X,Y',
      ...result.tiles.map((tile) =>
        `${tile.id},"${tile.category}",${tile.x},${tile.y}`
      )
    ];
    const blobUrl = URL.createObjectURL(
      new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8;' })
    );
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = 'ecovission_tile_screening.csv';
    anchor.click();
    URL.revokeObjectURL(blobUrl);
  };

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">IMAGE SCREENING · MODULE 01</div>
          <h1>Single image analysis</h1>
          <p>Upload satellite or aerial imagery to screen forest, water and other visible surface patterns.</p>
        </div>
        <div className="module-tag"><ScanSearch size={16} /> IMAGE SCREENING</div>
      </div>

      <div style={{ maxWidth: 900 }}>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h3>Input image</h3>
              <p>Select an RGB image to begin.</p>
            </div>
          </div>

          <UploadBox
            label="Satellite or aerial image"
            file={file}
            onFile={choose}
          />

          {preview && (
            <div className="preview-box">
              <img src={preview} alt="Selected satellite image preview" />
              <div>
                <b>{file?.name}</b>
                <small>Image selected · Ready for screening</small>
              </div>
            </div>
          )}

          <button
            className="primary-btn full"
            disabled={!file || busy}
            onClick={run}
          >
            {busy ? <LoaderCircle className="ecovission-spin" size={17} /> : <Sparkles size={17} />}
            {busy ? 'Processing image…' : 'Run image screening'}
          </button>

          {busy && (
            <div className="ecovission-progress" role="status" aria-live="polite">
              <div className="ecovission-progress-title">
                <LoaderCircle className="ecovission-spin" size={17} />
                ECOVISSION image screening
              </div>
              <p>{stage}</p>
              <div className="ecovission-progress-track">
                <div className="ecovission-progress-bar" />
              </div>
            </div>
          )}

          {error && <div className="error-note">{error}</div>}

          <div className="small-note">
            <Info size={16} />
            Minimum image size: 160 × 160 pixels. Current browser screening uses RGB-based heuristics; categories are indicative, not validated land-cover predictions.
          </div>
        </section>
      </div>

      {result && (
        <div className="results-section ecovission-results">
          <div className="results-title">
            <div>
              <div className="eyebrow">SCREENING OUTPUT</div>
              <h2>Analysis results</h2>
              <p>{result.width} × {result.height} px · {result.total} complete tiles</p>
            </div>
            <button className="secondary-btn" onClick={exportCsv}>
              <Download size={16} /> Export CSV
            </button>
          </div>

          <div className="stat-grid result-stats">
            {categories.map((category) => (
              <div className="stat-card compact" key={category.name}>
                <span>
                  <i className="inline-dot" style={{ background: category.color }} />
                  {category.name}
                </span>
                <strong>{result.counts?.[category.name] ?? 0}</strong>
                <small>Tiles screened</small>
              </div>
            ))}
          </div>

          <section className="panel image-output-panel">
            <h3>Colour-coded screening regions</h3>
            <p>Each 160 × 160 pixel tile is tinted and outlined according to its screening category.</p>
            <div className="ecovission-overlay-wrap">
              <img
                src={result.overlay}
                alt="Colour-coded satellite image screening output"
              />
            </div>
            <div className="class-legend output-legend">
              {categories.map((category) => (
                <div key={category.name}>
                  <i style={{ background: category.color }} />
                  {category.name}
                </div>
              ))}
            </div>
          </section>

          <div className="ecovission-chart-grid">
            <section className="panel chart-panel">
              <h3>Tile distribution</h3>
              <p>Share of screened tiles by category.</p>
              <div className="ecovission-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={chartData.filter((item) => item.tiles > 0)}
                      dataKey="tiles"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={66}
                      outerRadius={105}
                      paddingAngle={2}
                      label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                    >
                      {chartData.filter((item) => item.tiles > 0).map((item) => (
                        <Cell key={item.name} fill={item.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value, name) => [`${value} tiles`, name]} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="panel chart-panel">
              <h3>Tiles by category</h3>
              <p>Number of tiles assigned to each screening class.</p>
              <div className="ecovission-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData}
                    layout="vertical"
                    margin={{ top: 8, right: 22, bottom: 8, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={155}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip formatter={(value) => [`${value} tiles`, 'Count']} />
                    <Bar dataKey="tiles" radius={[0, 7, 7, 0]} barSize={22}>
                      {chartData.map((item) => (
                        <Cell key={item.name} fill={item.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>

          <section className="panel tile-table">
            <h3>Tile-level screening report</h3>
            <p>First 100 tile records shown.</p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tile ID</th>
                    <th>Pixel position</th>
                    <th>Screening category</th>
                  </tr>
                </thead>
                <tbody>
                  {result.tiles.slice(0, 100).map((tile) => (
                    <tr key={tile.id}>
                      <td>#{String(tile.id).padStart(3, '0')}</td>
                      <td>{tile.x}, {tile.y}</td>
                      <td>{tile.category}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="notice">
            <Info size={18} />
            <p>
              <b>Model status:</b> This React page currently runs RGB-based heuristic screening in the browser. It does not load or call a trained ML model. The original Python pipeline may extract ResNet50V2 features, but the forest-category labels are assigned using RGB heuristics rather than a trained land-cover classifier.
            </p>
          </div>
        </div>
      )}

      <style>{`
        .ecovission-results {
          display: flex;
          flex-direction: column;
          gap: 22px;
          margin-top: 28px;
          min-width: 0;
        }
        .ecovission-overlay-wrap {
          width: 100%;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 10px 0 4px;
          min-width: 0;
        }
        .ecovission-overlay-wrap img {
          display: block;
          width: 100%;
          max-height: 620px;
          object-fit: contain;
          border-radius: 12px;
          background: #eef2ed;
        }
        .ecovission-chart-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 22px;
          align-items: stretch;
          min-width: 0;
        }
        .ecovission-chart-grid > .panel { min-width: 0; }
        .ecovission-chart {
          height: 320px;
          width: 100%;
          min-width: 0;
        }
        .ecovission-progress {
          margin-top: 16px;
          padding: 16px;
          border: 1px solid #d8e8dc;
          border-radius: 12px;
          background: #f0f7f1;
        }
        .ecovission-progress-title {
          display: flex;
          align-items: center;
          gap: 9px;
          color: #245b3c;
          font-weight: 700;
        }
        .ecovission-progress p {
          margin: 9px 0 12px;
          color: #668073;
          font-size: 13px;
        }
        .ecovission-progress-track {
          height: 6px;
          overflow: hidden;
          border-radius: 10px;
          background: #dce9df;
        }
        .ecovission-progress-bar {
          height: 100%;
          width: 35%;
          border-radius: 10px;
          background: #2f8050;
          animation: ecovission-progress-motion 1.4s ease-in-out infinite alternate;
        }
        .ecovission-spin { animation: ecovission-spin 1s linear infinite; }
        @keyframes ecovission-spin { to { transform: rotate(360deg); } }
        @keyframes ecovission-progress-motion {
          from { width: 25%; }
          to { width: 92%; }
        }
        @media (max-width: 900px) {
          .ecovission-chart-grid { grid-template-columns: minmax(0, 1fr); }
          .ecovission-chart { height: 290px; }
        }
      `}</style>
    </div>
  );
}
