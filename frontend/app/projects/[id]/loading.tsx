export default function ProjectLoading() {
  return (
    <div aria-busy="true" aria-label="Loading project" className="loading-stack">
      <p className="loading-label">Loading project…</p>
      <div className="loading-block loading-heading" />
      <div className="loading-block loading-card" />
      <div className="loading-grid"><div className="loading-block" /><div className="loading-block" /><div className="loading-block" /></div>
    </div>
  );
}
