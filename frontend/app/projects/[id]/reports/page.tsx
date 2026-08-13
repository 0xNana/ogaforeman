'use client';

import { Download, Share2 } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';

import { useProject } from '@/components/project-context';

export default function ReportsPage() {
  const { project, report } = useProject().snapshot;
  if (report.date === 'No report yet') {
    return <div><div className="page-heading"><div><span className="eyebrow">Reports</span><h1>Daily report</h1><p>Ready to review, share or send to a client.</p></div></div><div className="empty-state"><span className="empty-state-icon">OG</span><h2>Nothing from site yet.</h2><p>Send OG an update when work starts moving.</p><Link className="btn btn-primary btn-small" href={`/projects/${project.id}/site-update`}>Talk to OG</Link></div></div>;
  }
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Reports</span><h1>Daily report</h1><p>Ready to review, share or send to a client.</p></div><div className="page-heading-actions"><button className="btn btn-quiet btn-small" type="button"><Share2 size={15} /> Share</button><button className="btn btn-primary btn-small" type="button"><Download size={15} /> Export</button></div></div>
      <article className="report-paper"><div className="report-top"><div><span className="report-mark">OG Foreman · {project.name}</span><h2>Daily Report</h2><p>{report.date}</p></div><span className="status-pill completed">Prepared</span></div><div className="report-section-grid"><ReportSection title="Completed" items={report.completed} /><ReportSection title="In progress" items={report.inProgress} /><ReportSection title="Blocked" items={report.blocked} /><ReportSection title="Materials" items={report.materials} /><ReportSection title="Tomorrow" items={report.tomorrow} /><ReportSection title="Risks" items={report.risks} /></div>{report.photos.length > 0 && <div className="report-gallery">{report.photos.map((photo, index) => <Image src={photo} alt={`${project.name} site update ${index + 1}`} width={900} height={600} key={photo} />)}</div>}<div className="report-footer"><span>Prepared by OG</span><span>Based on today&apos;s site updates</span></div></article>
    </div>
  );
}

function ReportSection({ title, items }: Readonly<{ title: string; items: string[] }>) {
  return <section className="report-section"><h3>{title}</h3>{items.length > 0 ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="faint" style={{ marginTop: '14px', fontSize: '0.84rem' }}>Nothing to report.</p>}</section>;
}
