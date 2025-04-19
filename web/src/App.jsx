import React, { useState, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import {
  LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer
} from 'recharts';

export default function App() {
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [analyticsError, setAnalyticsError] = useState(null);

  // Load history & analytics on mount
  useEffect(() => {
    // Fetch history
    fetch('/history')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setHistory)
      .catch(() => setHistory([]));

    // Fetch analytics
    fetch('/analytics')
      .then(async (r) => {
        if (!r.ok) {
          const txt = await r.text();
          console.error('Analytics error:', txt);
          throw new Error('Failed to load analytics');
        }
        return r.json();
      })
      .then(setAnalytics)
      .catch((e) => {
        setAnalytics(null);
        setAnalyticsError(e.message);
      });
  }, []);

  const onDrop = useCallback(async (files) => {
    setError(null);
    setAnalyticsError(null);
    setLoading(true);

    const form = new FormData();
    form.append('file', files[0]);

    let text;
    try {
      const res = await fetch('/digest', { method: 'POST', body: form });
      text = await res.text();
      if (!res.ok) throw new Error(text);
    } catch (e) {
      setError(`Upload error: ${e.message}`);
      setLoading(false);
      return;
    }

    let json;
    try {
      json = JSON.parse(text);
    } catch {
      setError(`Invalid JSON returned:\n${text}`);
      setLoading(false);
      return;
    }

    setResult(json);

    // Refresh history
    try {
      const hRes = await fetch('/history');
      if (hRes.ok) setHistory(await hRes.json());
    } catch {}

    // Refresh analytics
    try {
      const aRes = await fetch('/analytics');
      if (!aRes.ok) throw new Error(await aRes.text());
      setAnalytics(await aRes.json());
      setAnalyticsError(null);
    } catch (e) {
      console.error('Analytics fetch after drop failed:', e);
      setAnalytics(null);
      setAnalyticsError('Unable to load analytics');
    }

    setLoading(false);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  return (
    <div className="min-h-screen p-6 bg-gray-100 font-sans">
      <h1 className="text-3xl font-bold text-center mb-6">Paycheck Digest</h1>

      <div {...getRootProps()} className="mx-auto max-w-md p-6 border-2 border-dashed rounded bg-white cursor-pointer">
        <input {...getInputProps()} />
        <p className="text-center text-gray-600">
          {isDragActive
            ? 'Drop your PDF/ZIP here…'
            : 'Drag & drop a pay‑stub PDF/ZIP here, or click to select'}
        </p>
      </div>

      {loading && (
        <div className="text-center mt-4 text-blue-600">Processing…</div>
      )}

      {error && (
        <div className="mt-4 max-w-md mx-auto p-4 bg-red-100 text-red-700 rounded">
          <strong>Error:</strong>
          <pre className="whitespace-pre-wrap">{error}</pre>
        </div>
      )}

      {analyticsError && (
        <div className="mt-4 max-w-md mx-auto p-4 bg-yellow-100 text-yellow-800 rounded">
          <strong>Analytics Error:</strong> {analyticsError}
        </div>
      )}

      {analytics && typeof analytics.total_gross === 'number' && (
        <div className="grid grid-cols-2 gap-4 mt-8 max-w-xl mx-auto">
          <div className="p-4 bg-white rounded shadow">
            <h2 className="font-semibold">Total Gross</h2>
            <p>${analytics.total_gross.toFixed(2)}</p>
          </div>
          <div className="p-4 bg-white rounded shadow">
            <h2 className="font-semibold">Total Net</h2>
            <p>${analytics.total_net.toFixed(2)}</p>
          </div>
          <div className="p-4 bg-white rounded shadow">
            <h2 className="font-semibold">Avg Net</h2>
            <p>${analytics.avg_net.toFixed(2)}</p>
          </div>
          <div className="p-4 bg-white rounded shadow">
            <h2 className="font-semibold">Net Trend</h2>
            <p>{analytics.net_trend_slope.toFixed(2)} per period</p>
          </div>
        </div>
      )}

      {history.length > 1 && (
        <div className="mt-8 max-w-xl mx-auto">
          <h2 className="text-2xl font-semibold mb-2">Net Pay Trend</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={history}>
              <CartesianGrid stroke="#ccc" />
              <XAxis dataKey="period_start" />
              <YAxis dataKey="net_pay" />
              <Tooltip />
              <Line type="monotone" dataKey="net_pay" stroke="#2563EB" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {result && !loading && (
        <div className="mt-8 p-6 bg-white rounded shadow max-w-xl mx-auto">
          <h2 className="text-xl font-semibold mb-2">Latest Result</h2>
          <div className="summary-container" dangerouslySetInnerHTML={{ __html: result.html_summary }} />
        </div>
      )}
    </div>
  );
}
